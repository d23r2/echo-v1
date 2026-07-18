"""ECHO Layer 2E — Goal Manager (Phases 1-3). Deterministic, DB-backed via
the isolated db_session fixture — progress is always computed from real
Task/PlanStep evidence, never a model estimate, so no fake provider is
needed anywhere in this file."""

from app import schemas
from app.models import Plan, PlanStep, Task
from app.services import goal_engine


def _goal(db_session, **overrides):
    payload = schemas.GoalCreate(title=overrides.pop("title", "Test goal"), **overrides)
    return goal_engine.create_goal(db_session, payload)


# ---- Approval policy ----


def test_explicit_goal_created_as_approved(db_session):
    goal = _goal(db_session, origin="explicit_user")
    assert goal.status == "approved"
    assert goal.approved_at is not None


def test_system_suggested_goal_remains_proposed(db_session):
    goal = _goal(db_session, origin="system_suggestion")
    assert goal.status == "proposed"
    assert goal.approved_at is None


def test_approve_only_valid_from_proposed(db_session):
    goal = _goal(db_session, origin="system_suggestion")
    approved = goal_engine.approve_goal(db_session, goal.id)
    assert approved.status == "approved"
    try:
        goal_engine.approve_goal(db_session, goal.id)
        raise AssertionError("should have raised")
    except ValueError:
        pass


# ---- Hierarchy and project linkage ----


def test_goal_hierarchy_and_project_linkage(db_session):
    parent = _goal(db_session, title="Parent goal")
    child = _goal(db_session, title="Subgoal", parent_goal_id=parent.id, project_id="proj-1")
    assert child.parent_goal_id == parent.id
    assert child.project_id == "proj-1"
    listed = goal_engine.list_goals(db_session, parent_goal_id=parent.id)
    assert [g.id for g in listed] == [child.id]


def test_child_goal_progress_reported_under_parent(db_session):
    parent = _goal(db_session, title="Parent")
    child = _goal(db_session, title="Child")
    child.parent_goal_id = parent.id
    db_session.commit()
    progress = goal_engine.compute_progress(db_session, parent.id)
    assert len(progress.child_goals) == 1
    assert progress.child_goals[0].goal_id == child.id


# ---- Evidence-based progress ----


def test_progress_uses_completed_evidence_only(db_session):
    goal = _goal(db_session)
    db_session.add_all(
        [
            Task(title="Done task", status="done", goal_id=goal.id),
            Task(title="Open task", status="todo", goal_id=goal.id),
        ]
    )
    db_session.commit()
    progress = goal_engine.compute_progress(db_session, goal.id)
    assert progress.evidence_task_total == 2
    assert progress.evidence_task_done == 1
    assert progress.percent_complete == 50.0


def test_progress_never_fabricated_with_zero_evidence(db_session):
    goal = _goal(db_session)
    progress = goal_engine.compute_progress(db_session, goal.id)
    assert progress.percent_complete == 0.0
    assert progress.evidence_task_total == 0


def test_progress_includes_plan_step_evidence_only_for_approved_plans(db_session):
    goal = _goal(db_session)
    proposed_plan = Plan(objective="not yet approved", goal_id=goal.id, status="proposed")
    approved_plan = Plan(objective="approved plan", goal_id=goal.id, status="approved")
    db_session.add_all([proposed_plan, approved_plan])
    db_session.commit()
    db_session.add_all(
        [
            PlanStep(plan_id=proposed_plan.id, title="should not count", status="completed", order_index=0),
            PlanStep(plan_id=approved_plan.id, title="counts", status="completed", order_index=0),
            PlanStep(plan_id=approved_plan.id, title="also counts", status="pending", order_index=1),
        ]
    )
    db_session.commit()
    progress = goal_engine.compute_progress(db_session, goal.id)
    assert progress.evidence_plan_step_total == 2  # only the approved plan's steps
    assert progress.evidence_plan_step_done == 1


def test_evidence_only_auto_achieve(db_session):
    goal = _goal(db_session)
    db_session.add(Task(title="Only task", status="done", goal_id=goal.id))
    db_session.commit()
    updated = goal_engine.maybe_mark_achieved(db_session, goal.id)
    assert updated.status == "achieved"
    assert updated.achieved_at is not None


def test_incomplete_evidence_never_auto_achieves(db_session):
    goal = _goal(db_session)
    db_session.add(Task(title="Still open", status="todo", goal_id=goal.id))
    db_session.commit()
    updated = goal_engine.maybe_mark_achieved(db_session, goal.id)
    assert updated.status == "approved"


# ---- Blocker detection / next-action engine ----


def test_blocked_goal_reports_blocker_and_next_action(db_session):
    goal = _goal(db_session)
    db_session.add(Task(title="Blocked item", status="blocked", goal_id=goal.id))
    db_session.commit()
    progress = goal_engine.compute_progress(db_session, goal.id)
    assert "Blocked item" in progress.blockers
    assert progress.next_action == "Blocked item"


def test_review_recommends_blocked_goal_when_nothing_else_actionable(db_session):
    goal = _goal(db_session, priority="high")
    db_session.add(Task(title="Fix this blocker", status="blocked", goal_id=goal.id))
    db_session.commit()
    review = goal_engine.generate_review(db_session, schemas.GoalReviewRequest())
    assert review.recommended_next_action == "Fix this blocker"
    assert review.recommended_next_action_goal_id == goal.id


# ---- Abandonment / history preservation ----


def test_abandoned_goal_history_preserved(db_session):
    goal = _goal(db_session)
    abandoned = goal_engine.abandon_goal(db_session, goal.id, "no longer relevant")
    assert abandoned.status == "abandoned"
    assert abandoned.abandoned_reason == "no longer relevant"
    assert abandoned.abandoned_at is not None
    # The row is never deleted — still fully queryable.
    refetched = goal_engine.get_goal(db_session, goal.id)
    assert refetched is not None
    assert refetched.title == goal.title


def test_cannot_abandon_already_terminal_goal(db_session):
    goal = _goal(db_session)
    goal_engine.abandon_goal(db_session, goal.id, "first reason")
    try:
        goal_engine.abandon_goal(db_session, goal.id, "second reason")
        raise AssertionError("should have raised")
    except ValueError:
        pass


def test_pause_only_valid_from_approved_or_active(db_session):
    goal = _goal(db_session)
    paused = goal_engine.pause_goal(db_session, goal.id)
    assert paused.status == "paused"
    try:
        goal_engine.pause_goal(db_session, goal.id)  # already paused
        raise AssertionError("should have raised")
    except ValueError:
        pass


# ---- Low-energy mode ----


def test_low_energy_recommendation_does_not_silently_change_goal(db_session):
    goal = _goal(db_session)
    db_session.add(Task(title="Small task", status="todo", goal_id=goal.id))
    db_session.commit()
    before = goal_engine.get_goal(db_session, goal.id)
    before_status, before_priority = before.status, before.priority

    review = goal_engine.generate_review(db_session, schemas.GoalReviewRequest(), low_energy=True)

    after = goal_engine.get_goal(db_session, goal.id)
    assert after.status == before_status
    assert after.priority == before_priority
    assert review.recommended_next_action == "Small task"


# ---- Cross-goal review / conflicting commitments ----


def test_review_summary_reflects_stalled_and_missing_next_action_counts(db_session):
    stalled_goal = _goal(db_session)  # no evidence at all -> stale
    review = goal_engine.generate_review(db_session, schemas.GoalReviewRequest())
    assert stalled_goal.id in review.stalled_goal_ids_json
    assert stalled_goal.id in review.missing_next_action_goal_ids_json


def test_conflicting_high_priority_goals_flagged(db_session):
    from datetime import UTC, datetime, timedelta

    target = datetime.now(UTC) + timedelta(days=10)
    a = _goal(db_session, title="Launch A", priority="high", target_date=target)
    b = _goal(db_session, title="Launch B", priority="high", target_date=target + timedelta(days=2))
    review = goal_engine.generate_review(db_session, schemas.GoalReviewRequest())
    assert any(a.title in note and b.title in note for note in review.conflicting_commitment_notes_json)
