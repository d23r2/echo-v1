"""ECHO Layer 2E — Goal Manager (Phases 1-3).

Goals belong to the user; ECHO may propose them but never silently commits
to one (the milestone's own non-negotiable rule) — see create_goal()'s
origin-based approval policy. Progress is always computed from linked,
already-real evidence (Task/PlanStep completion) rather than any model
estimate — see compute_progress(). Deliberately does not build a parallel
milestone/task-execution system: "goal -> subgoal -> milestone -> task" is
satisfied by chaining the already-built Layer 2C Plan/PlanStep/Milestone/
materialise_plan() machinery (a Plan declares goal_id to become one of a
goal's concrete plans) plus Task.goal_id for ad hoc tasks, rather than a
second hierarchy.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app import schemas
from app.models import Goal, GoalReview, Plan, PlanStep, Task, _now

_STALENESS_WINDOW_DAYS = 14


def _as_aware(dt: datetime) -> datetime:
    """SQLite doesn't preserve tzinfo on DateTime(timezone=True) columns —
    a value round-tripped through the DB often comes back naive even though
    it was written as UTC-aware (a known class of bug in this codebase, see
    PROGRESS.md's Schedule due_at fix). Every value this app writes is UTC,
    so a naive value is always safe to treat as UTC."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
_TERMINAL_STATUSES = ("achieved", "abandoned", "superseded")
# Plans in these statuses represent real, approved-or-further work — a
# still-`proposed` (unapproved) plan's steps are not yet real evidence.
_EVIDENCE_PLAN_STATUSES = ("approved", "active", "blocked", "completed")


# ============================================================================
# Phase 1 — CRUD and approval policy
# ============================================================================


def create_goal(db: Session, payload: schemas.GoalCreate) -> Goal:
    now = _now()
    # "System-suggested goal remains proposed" / "Explicit goal created as
    # approved" — the one deterministic approval-policy rule this phase
    # requires. A human stating their own goal doesn't need to approve it a
    # second time; a system-proposed one always does.
    status = "proposed" if payload.origin == "system_suggestion" else "approved"
    goal = Goal(
        title=payload.title,
        description=payload.description,
        scope=payload.scope,
        origin=payload.origin,
        status=status,
        priority=payload.priority,
        horizon=payload.horizon,
        target_date=payload.target_date,
        success_criteria_json=payload.success_criteria,
        constraints_json=payload.constraints,
        motivation=payload.motivation,
        project_id=payload.project_id,
        parent_goal_id=payload.parent_goal_id,
        confidence=payload.confidence,
        approved_at=now if status == "approved" else None,
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


def get_goal(db: Session, goal_id: str) -> Goal | None:
    return db.get(Goal, goal_id)


def list_goals(db: Session, *, status: str | None = None, project_id: str | None = None, parent_goal_id: str | None = None) -> list[Goal]:
    q = db.query(Goal)
    if status:
        q = q.filter(Goal.status == status)
    if project_id:
        q = q.filter(Goal.project_id == project_id)
    if parent_goal_id:
        q = q.filter(Goal.parent_goal_id == parent_goal_id)
    return q.order_by(Goal.created_at.desc()).all()


def update_goal(db: Session, goal_id: str, payload: schemas.GoalUpdate) -> Goal | None:
    goal = db.get(Goal, goal_id)
    if goal is None:
        return None
    updates = payload.model_dump(exclude_unset=True)
    new_status = updates.pop("status", None)
    if new_status is not None:
        if goal.status in _TERMINAL_STATUSES:
            raise ValueError(f"Cannot change status of a goal that is already '{goal.status}'.")
        goal.status = new_status
    for field in ("success_criteria", "constraints"):
        if field in updates:
            setattr(goal, f"{field}_json", updates.pop(field))
    for field, value in updates.items():
        setattr(goal, field, value)
    db.commit()
    db.refresh(goal)
    return goal


def approve_goal(db: Session, goal_id: str) -> Goal | None:
    goal = db.get(Goal, goal_id)
    if goal is None:
        return None
    if goal.status != "proposed":
        raise ValueError(f"Only a 'proposed' goal can be approved (this goal is '{goal.status}').")
    goal.status = "approved"
    goal.approved_at = _now()
    db.commit()
    db.refresh(goal)
    return goal


def pause_goal(db: Session, goal_id: str) -> Goal | None:
    goal = db.get(Goal, goal_id)
    if goal is None:
        return None
    if goal.status not in ("approved", "active"):
        raise ValueError(f"Only an 'approved' or 'active' goal can be paused (this goal is '{goal.status}').")
    goal.status = "paused"
    db.commit()
    db.refresh(goal)
    return goal


def abandon_goal(db: Session, goal_id: str, reason: str) -> Goal | None:
    """Never deletes the row — abandoned-goal history stays fully queryable,
    matching the milestone's explicit "history preserved" requirement."""
    goal = db.get(Goal, goal_id)
    if goal is None:
        return None
    if goal.status in _TERMINAL_STATUSES:
        raise ValueError(f"Goal is already '{goal.status}'.")
    goal.status = "abandoned"
    goal.abandoned_at = _now()
    goal.abandoned_reason = reason
    db.commit()
    db.refresh(goal)
    return goal


# ============================================================================
# Phase 2 — evidence-based progress (never a model estimate)
# ============================================================================


def _evidence_tasks(db: Session, goal_id: str) -> list[Task]:
    return db.query(Task).filter(Task.goal_id == goal_id).all()


def _evidence_plan_steps(db: Session, goal_id: str) -> list[PlanStep]:
    plan_ids = [p.id for p in db.query(Plan).filter(Plan.goal_id == goal_id, Plan.status.in_(_EVIDENCE_PLAN_STATUSES)).all()]
    if not plan_ids:
        return []
    return db.query(PlanStep).filter(PlanStep.plan_id.in_(plan_ids)).all()


def compute_progress(db: Session, goal_id: str, *, _visited: set[str] | None = None) -> schemas.GoalProgressOut:
    goal = db.get(Goal, goal_id)
    if goal is None:
        raise ValueError(f"Unknown goal '{goal_id}'.")
    visited = _visited or set()
    visited.add(goal_id)

    tasks = _evidence_tasks(db, goal_id)
    steps = _evidence_plan_steps(db, goal_id)

    task_done = sum(1 for t in tasks if t.status == "done")
    step_done = sum(1 for s in steps if s.status == "completed")
    total = len(tasks) + len(steps)
    done = task_done + step_done
    percent = round((done / total) * 100, 1) if total > 0 else 0.0

    blockers = [t.title for t in tasks if t.status == "blocked"] + [s.title for s in steps if s.status == "blocked"]

    child_goals_rows = db.query(Goal).filter(Goal.parent_goal_id == goal_id).all()
    child_goals: list[schemas.ChildGoalProgress] = []
    for child in child_goals_rows:
        if child.id in visited:
            continue  # cycle guard — malformed data must never hang this call
        child_progress = compute_progress(db, child.id, _visited=visited)
        child_goals.append(schemas.ChildGoalProgress(goal_id=child.id, title=child.title, status=child.status, percent_complete=child_progress.percent_complete))
        if child.status == "blocked":
            blockers.append(f"Subgoal blocked: {child.title}")

    next_action = _next_action_item(tasks, steps)

    last_activity = max(
        [_as_aware(t.updated_at) for t in tasks] + [_as_aware(s.created_at) for s in steps if hasattr(s, "created_at")],
        default=None,
    )
    stale = goal.status in ("proposed", "approved", "active") and (
        total == 0 or last_activity is None or (_now() - last_activity) > timedelta(days=_STALENESS_WINDOW_DAYS)
    )

    return schemas.GoalProgressOut(
        goal_id=goal_id,
        percent_complete=percent,
        evidence_task_total=len(tasks),
        evidence_task_done=task_done,
        evidence_plan_step_total=len(steps),
        evidence_plan_step_done=step_done,
        child_goals=child_goals,
        blockers=blockers,
        next_action=next_action,
        stale=stale,
    )


def _next_action_item(tasks: list[Task], steps: list[PlanStep], *, low_energy: bool = False) -> str | None:
    """Deterministic — the first not-yet-done item by creation/order, never
    a model call. low_energy prefers a smaller item (a plain heuristic: an
    ad hoc Task over a formal plan step, since a plan step usually implies
    more surrounding structure) without ever touching persisted state."""
    open_tasks = sorted([t for t in tasks if t.status not in ("done", "cancelled")], key=lambda t: t.created_at)
    open_steps = sorted([s for s in steps if s.status not in ("completed", "cancelled")], key=lambda s: s.order_index)
    if low_energy and open_tasks:
        return open_tasks[0].title
    candidates = open_tasks + open_steps
    if not candidates:
        return None
    # Prefer an item that isn't itself blocked when one exists — otherwise
    # the blocked item IS the practical next action (resolve the blocker).
    unblocked = [c for c in candidates if getattr(c, "status", None) != "blocked"]
    return (unblocked[0] if unblocked else candidates[0]).title


def maybe_mark_achieved(db: Session, goal_id: str) -> Goal | None:
    """Evidence-only auto-completion: a goal reaches 'achieved' only when its
    own progress computation reports 100% against at least one real evidence
    item — never inferred from conversation tone or a manual toggle."""
    goal = db.get(Goal, goal_id)
    if goal is None or goal.status not in ("approved", "active", "blocked"):
        return goal
    progress = compute_progress(db, goal_id)
    total_evidence = progress.evidence_task_total + progress.evidence_plan_step_total
    if total_evidence > 0 and progress.percent_complete >= 100.0:
        goal.status = "achieved"
        goal.achieved_at = _now()
        db.commit()
        db.refresh(goal)
    return goal


# ============================================================================
# Phase 3 — review and next-action engine
# ============================================================================


def _active_goal_set(db: Session, goal_id: str | None) -> list[Goal]:
    if goal_id:
        goal = db.get(Goal, goal_id)
        return [goal] if goal else []
    return db.query(Goal).filter(~Goal.status.in_(_TERMINAL_STATUSES)).all()


def _conflicting_commitment_notes(goals: list[Goal]) -> list[str]:
    """A plain structural heuristic — never a fabricated capacity number:
    flag when two or more high-priority active goals share a target date
    within a week of each other."""
    dated = [g for g in goals if g.target_date is not None and g.priority == "high" and g.status in ("approved", "active")]
    notes: list[str] = []
    for i, a in enumerate(dated):
        for b in dated[i + 1 :]:
            if abs((_as_aware(a.target_date) - _as_aware(b.target_date)).days) <= 7:
                notes.append(f"'{a.title}' and '{b.title}' both target dates within a week of each other — check capacity.")
    return notes


def generate_review(db: Session, request: schemas.GoalReviewRequest, *, low_energy: bool = False) -> GoalReview:
    goals = _active_goal_set(db, request.goal_id)

    stalled: list[str] = []
    missing_next_action: list[str] = []
    unresolved_blockers: list[str] = []
    ranked_candidates: list[tuple[Goal, schemas.GoalProgressOut]] = []

    for goal in goals:
        progress = compute_progress(db, goal.id)
        if progress.stale:
            stalled.append(goal.id)
        if progress.next_action is None and goal.status in ("approved", "active"):
            missing_next_action.append(goal.id)
        if progress.blockers:
            unresolved_blockers.append(goal.id)
        if goal.status in ("approved", "active") and progress.next_action is not None:
            ranked_candidates.append((goal, progress))

    conflicts = _conflicting_commitment_notes(goals)

    # A single practical recommendation — unblocked goals first (a blocked
    # goal's only "next action" is resolving the blocker, which is still
    # worth surfacing if nothing else is actionable), then priority, then
    # earliest target date. Never guilt-inducing framing.
    _priority_rank = {"high": 0, "medium": 1, "low": 2}
    ranked_candidates.sort(
        key=lambda pair: (bool(pair[1].blockers), _priority_rank.get(pair[0].priority, 1), pair[0].target_date or pair[0].created_at)
    )
    recommended_action: str | None = None
    recommended_goal_id: str | None = None
    if ranked_candidates:
        top_goal, _ = ranked_candidates[0]
        tasks = _evidence_tasks(db, top_goal.id)
        steps = _evidence_plan_steps(db, top_goal.id)
        recommended_action = _next_action_item(tasks, steps, low_energy=low_energy)
        recommended_goal_id = top_goal.id if recommended_action else None

    summary = (
        f"{len(goals)} goal(s) reviewed. {len(stalled)} stalled, {len(missing_next_action)} missing a next action, "
        f"{len(unresolved_blockers)} with unresolved blockers."
    )
    if conflicts:
        summary += f" {len(conflicts)} potential scheduling conflict(s) noted."

    review = GoalReview(
        goal_id=request.goal_id,
        review_type=request.review_type,
        summary=summary,
        stalled_goal_ids_json=stalled,
        missing_next_action_goal_ids_json=missing_next_action,
        unresolved_blocker_ids_json=unresolved_blockers,
        conflicting_commitment_notes_json=conflicts,
        recommended_next_action=recommended_action,
        recommended_next_action_goal_id=recommended_goal_id,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


def list_reviews(db: Session, goal_id: str | None = None, limit: int = 20) -> list[GoalReview]:
    q = db.query(GoalReview)
    if goal_id:
        q = q.filter(GoalReview.goal_id == goal_id)
    return q.order_by(GoalReview.created_at.desc()).limit(limit).all()
