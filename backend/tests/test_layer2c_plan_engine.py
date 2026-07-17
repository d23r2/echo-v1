"""ECHO Layer 2C — plan_engine.py: plan generation, dependency/critical-path
validation, parallel-step detection, approval gating, adaptive replanning,
and execution handoff via the existing permission-gated Action System.
Deterministic, DB-backed via the isolated db_session fixture."""

import pytest

from app import schemas
from app.services import decision_engine as de
from app.services import plan_engine as pe


def _plan(db_session, **kw):
    payload = schemas.PlanCreate(objective=kw.pop("objective", "o"), **kw)
    return pe.create_plan(db_session, payload)


# ---- Plan generation ----


def test_mvp_plan_generated_when_no_steps_given(db_session):
    plan = _plan(db_session)
    assert len(plan.steps) == 1
    assert "o" in plan.steps[0].title


def test_plan_generated_from_selected_decision_option(db_session):
    case = de.create_decision_case(
        db_session,
        schemas.DecisionCaseCreate(question="q", objective="pick approach", options=[schemas.DecisionOptionCreate(label="Approach A", description="do the thing")]),
    )
    de.select_option(db_session, case.id, case.options[0].id)
    db_session.refresh(case)
    plan = _plan(db_session, objective="Ship approach A", decision_case_id=case.id)
    assert any("Approach A" in s.title for s in plan.steps)


def test_explicit_steps_used_verbatim(db_session):
    plan = _plan(db_session, steps=[schemas.PlanStepCreate(title="Step one"), schemas.PlanStepCreate(title="Step two")])
    assert [s.title for s in plan.steps] == ["Step one", "Step two"]


# ---- Dependencies and critical path ----


def test_dependencies_and_critical_path_valid(db_session):
    plan = _plan(
        db_session,
        steps=[
            schemas.PlanStepCreate(title="A"),
            schemas.PlanStepCreate(title="B", depends_on_titles=["A"]),
            schemas.PlanStepCreate(title="C", depends_on_titles=["B"]),
        ],
    )
    validation = pe.validate_plan(db_session, plan.id)
    assert validation.valid is True
    assert len(validation.critical_path_step_ids) == 3


def test_circular_dependency_is_invalid(db_session):
    from app.models import PlanDependency

    plan = _plan(db_session, steps=[schemas.PlanStepCreate(title="X"), schemas.PlanStepCreate(title="Y", depends_on_titles=["X"])])
    x = next(s for s in plan.steps if s.title == "X")
    y = next(s for s in plan.steps if s.title == "Y")
    db_session.add(PlanDependency(plan_id=plan.id, from_step_id=y.id, to_step_id=x.id))
    db_session.commit()
    validation = pe.validate_plan(db_session, plan.id)
    assert validation.valid is False
    assert any("Circular dependency" in i.message for i in validation.issues)


def test_plan_with_no_steps_is_invalid(db_session):
    plan = pe.create_plan(db_session, schemas.PlanCreate(objective="o", steps=[schemas.PlanStepCreate(title="placeholder")]))
    # empty a real plan out to exercise the no-steps validation path
    for step in list(plan.steps):
        db_session.delete(step)
    db_session.commit()
    validation = pe.validate_plan(db_session, plan.id)
    assert validation.valid is False
    assert any("no steps" in i.message.lower() for i in validation.issues)


# ---- Parallel step detection ----


def test_parallel_steps_detected(db_session):
    plan = _plan(
        db_session,
        steps=[
            schemas.PlanStepCreate(title="Root"),
            schemas.PlanStepCreate(title="Branch1", depends_on_titles=["Root"]),
            schemas.PlanStepCreate(title="Branch2", depends_on_titles=["Root"]),
        ],
    )
    validation = pe.validate_plan(db_session, plan.id)
    branch1 = next(s for s in plan.steps if s.title == "Branch1")
    branch2 = next(s for s in plan.steps if s.title == "Branch2")
    same_group = [g for g, ids in validation.parallel_groups.items() if branch1.id in ids and branch2.id in ids]
    assert same_group, f"Expected Branch1/Branch2 in the same parallel group; got {validation.parallel_groups}"


# ---- Blocked step prevents dependent execution ----


def test_blocked_step_flags_dependent(db_session):
    plan = _plan(db_session, steps=[schemas.PlanStepCreate(title="P"), schemas.PlanStepCreate(title="Q", depends_on_titles=["P"])])
    p_step = next(s for s in plan.steps if s.title == "P")
    p_step.status = "blocked"
    db_session.commit()
    validation = pe.validate_plan(db_session, plan.id)
    assert any("depends on blocked step" in i.message for i in validation.issues)


def test_blocked_step_with_blocked_dependent_raises_no_warning(db_session):
    plan = _plan(db_session, steps=[schemas.PlanStepCreate(title="P"), schemas.PlanStepCreate(title="Q", depends_on_titles=["P"])])
    p_step = next(s for s in plan.steps if s.title == "P")
    q_step = next(s for s in plan.steps if s.title == "Q")
    p_step.status = "blocked"
    q_step.status = "blocked"
    db_session.commit()
    validation = pe.validate_plan(db_session, plan.id)
    assert not any("depends on blocked step" in i.message for i in validation.issues)


# ---- Approval gate / no autonomous consequential action ----


def test_plan_does_not_create_tasks_before_approval(db_session):
    plan = _plan(db_session, steps=[schemas.PlanStepCreate(title="Do the thing")])
    assert plan.status == "proposed"
    with pytest.raises(ValueError):
        pe.materialise_plan(db_session, plan.id)
    assert all(s.materialised_task_id is None for s in plan.steps)


def test_approved_plan_creates_correctly_scoped_tasks(db_session):
    plan = _plan(db_session, steps=[schemas.PlanStepCreate(title="Write the doc", description="details")])
    pe.approve_plan(db_session, plan.id)
    result = pe.materialise_plan(db_session, plan.id)
    assert len(result.created_task_ids) == 1
    from app.models import Task

    task = db_session.get(Task, result.created_task_ids[0])
    assert task.title == "Write the doc"
    assert task.source_type == "plan_step"


def test_materialise_is_idempotent_for_already_materialised_steps(db_session):
    plan = _plan(db_session, steps=[schemas.PlanStepCreate(title="Once")])
    pe.approve_plan(db_session, plan.id)
    first = pe.materialise_plan(db_session, plan.id)
    second = pe.materialise_plan(db_session, plan.id)
    assert len(first.created_task_ids) == 1
    assert len(second.created_task_ids) == 0
    assert second.skipped_step_ids  # already-materialised step is skipped, not duplicated


def test_permission_gated_action_proposal_stays_pending(db_session):
    """When create_task is flagged as requiring confirmation, materialising
    a plan must NOT silently create the task — it must leave a pending
    ActionRun instead (an honest proposal, never an autonomous action).
    (For a low-risk action like create_task, action_system.py's own
    _needs_confirmation() rule is driven by ActionDefinition.
    requires_confirmation, not PermissionSetting.level — this test exercises
    that real lever rather than a level this app's own risk-gating logic
    doesn't consult for low-risk actions.)"""
    from app.models import ActionDefinition
    from app.services import action_system

    action_system.ensure_registered(db_session)
    definition = db_session.query(ActionDefinition).filter(ActionDefinition.name == "create_task").first()
    definition.requires_confirmation = True
    db_session.commit()

    plan = _plan(db_session, steps=[schemas.PlanStepCreate(title="Gated step")])
    pe.approve_plan(db_session, plan.id)
    result = pe.materialise_plan(db_session, plan.id)
    assert result.created_task_ids == []
    assert result.skipped_step_ids

    from app.models import ActionRun

    pending = db_session.query(ActionRun).filter(ActionRun.action_name == "create_task", ActionRun.status == "pending").all()
    assert len(pending) == 1


def test_no_autonomous_consequential_action_on_plan_creation(db_session):
    """Creating (or even approving) a plan must never itself create a Task
    — only the explicit materialise call does."""
    plan = _plan(db_session, steps=[schemas.PlanStepCreate(title="Not yet")])
    pe.approve_plan(db_session, plan.id)
    from app.models import Task

    assert db_session.query(Task).count() == 0


# ---- Adaptive replanning ----


def test_replanning_preserves_completed_steps_and_history(db_session):
    plan = _plan(db_session, steps=[schemas.PlanStepCreate(title="Done already"), schemas.PlanStepCreate(title="Not done yet")])
    pe.approve_plan(db_session, plan.id)
    done_step = next(s for s in plan.steps if s.title == "Done already")
    done_step.status = "completed"
    db_session.commit()

    new_plan = pe.replan(db_session, plan.id, schemas.ReplanRequest(reason="scope changed", trigger="user_correction"))
    assert new_plan.status == "proposed"
    assert new_plan.revision_number == plan.revision_number + 1
    new_done = next(s for s in new_plan.steps if s.title == "Done already")
    assert new_done.status == "completed"
    new_not_done = next(s for s in new_plan.steps if s.title == "Not done yet")
    assert new_not_done.status == "pending"

    db_session.refresh(plan)
    assert plan.superseded_by_plan_id == new_plan.id
    # old plan's own step history is untouched
    old_done = next(s for s in plan.steps if s.title == "Done already")
    assert old_done.status == "completed"

    revisions = new_plan.revisions
    assert len(revisions) == 1
    assert revisions[0].reason == "scope changed"
    assert revisions[0].previous_status == "approved"


def test_changed_constraint_updates_only_affected_steps(db_session):
    plan = _plan(db_session, steps=[schemas.PlanStepCreate(title="Kept"), schemas.PlanStepCreate(title="Failed one")])
    pe.approve_plan(db_session, plan.id)
    kept = next(s for s in plan.steps if s.title == "Kept")
    failed = next(s for s in plan.steps if s.title == "Failed one")
    kept.status = "completed"
    failed.status = "failed"
    db_session.commit()

    new_plan = pe.replan(db_session, plan.id, schemas.ReplanRequest(reason="constraint changed", trigger="changed_constraint"))
    new_titles = [s.title for s in new_plan.steps]
    assert "Kept" in new_titles
    assert "Failed one" not in new_titles  # the failed (affected) branch was dropped, not blindly carried forward
    revision = new_plan.revisions[0]
    assert failed.id in revision.changed_step_ids_json
    assert kept.id not in revision.changed_step_ids_json


def test_replan_rejects_unapproved_plan(db_session):
    plan = _plan(db_session, steps=[schemas.PlanStepCreate(title="x")])
    with pytest.raises(ValueError):
        pe.replan(db_session, plan.id, schemas.ReplanRequest(reason="x"))


# ---- Milestones / risks / resources ----


def test_milestone_reached_once_target_steps_completed(db_session):
    plan = _plan(db_session, steps=[schemas.PlanStepCreate(title="Only step")])
    step = plan.steps[0]
    milestone = pe.add_milestone(db_session, plan.id, name="M1", description=None, target_step_ids=[step.id], verification_criteria=[])
    assert milestone.status == "pending"
    step.status = "completed"
    db_session.commit()
    updated = pe.update_milestone_status(db_session, milestone.id)
    assert updated.status == "reached"


def test_milestone_default_verification_criteria(db_session):
    plan = _plan(db_session, steps=[schemas.PlanStepCreate(title="s")])
    milestone = pe.add_milestone(db_session, plan.id, name="M", description=None, target_step_ids=[], verification_criteria=[])
    assert milestone.verification_criteria_json == ["All target steps completed."]
