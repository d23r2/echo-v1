"""ECHO Layer 2C — Planning Engine.

Deliberately does not duplicate Tasks/Projects: a PlanStep only becomes a
real Task row after explicit plan approval AND an explicit materialise call
(materialise_plan()), which reuses action_system.run_action() — the same
permission-gated funnel every other real action in this app goes through.
Nothing here ever executes anything itself. Deterministic, no model call.
"""

from sqlalchemy.orm import Session

from app import schemas
from app.models import (
    DecisionCase,
    Milestone,
    Plan,
    PlanDependency,
    PlanResourceRequirement,
    PlanRevision,
    PlanRisk,
    PlanStep,
    Task,
    _now,
)
from app.services import action_system
from app.services import skill_library as skill_library_service

# ============================================================================
# Phase 4/5 — Plan model, generation, and validation
# ============================================================================


def _generate_mvp_steps(db: Session, payload: schemas.PlanCreate) -> list[schemas.PlanStepCreate]:
    """Minimum-viable-plan generation (Phase 5's own instruction: 'produce a
    minimum viable plan first, then optional detail'). Priority order:
    1) the selected/recommended option of a linked DecisionCase, 2) a
    matching Skill Library template, 3) a single honest placeholder step —
    never fabricated detail beyond what's actually known."""
    if payload.decision_case_id:
        case = db.get(DecisionCase, payload.decision_case_id)
        if case is not None and case.recommended_option_id:
            option = next((o for o in case.options if o.id == case.recommended_option_id), None)
            if option is not None:
                steps = [schemas.PlanStepCreate(title=f"Address dependency: {dep}") for dep in option.dependencies_json]
                steps.append(schemas.PlanStepCreate(title=f"Implement: {option.label}", description=option.description))
                return steps

    skill = skill_library_service.suggest_plan(db, payload.objective)
    if skill is not None and skill.steps_json:
        return [schemas.PlanStepCreate(title=step_text) for step_text in skill.steps_json]

    return [schemas.PlanStepCreate(title=f"Complete: {payload.objective}")]


def create_plan(db: Session, payload: schemas.PlanCreate) -> Plan:
    plan = Plan(
        objective=payload.objective,
        scope=payload.scope,
        assumptions_json=payload.assumptions,
        constraints_json=payload.constraints,
        success_criteria_json=payload.success_criteria,
        decision_case_id=payload.decision_case_id,
        system_model_id=payload.system_model_id,
        task_id=payload.task_id,
        project_id=payload.project_id,
        goal_id=payload.goal_id,
    )
    db.add(plan)
    db.flush()

    step_payloads = payload.steps or _generate_mvp_steps(db, payload)
    _add_steps(db, plan, step_payloads)

    db.commit()
    db.refresh(plan)
    return plan


def _add_steps(db: Session, plan: Plan, step_payloads: list[schemas.PlanStepCreate]) -> list[PlanStep]:
    title_to_step: dict[str, PlanStep] = {}
    created: list[PlanStep] = []
    for i, sp in enumerate(step_payloads):
        step = PlanStep(
            plan_id=plan.id,
            order_index=i,
            title=sp.title,
            description=sp.description,
            estimated_effort=sp.estimated_effort,
            owner=sp.owner,
            verification_criteria_json=sp.verification_criteria,
        )
        db.add(step)
        db.flush()
        title_to_step[sp.title] = step
        created.append(step)

    for sp, step in zip(step_payloads, created, strict=True):
        for dep_title in sp.depends_on_titles:
            dep_step = title_to_step.get(dep_title)
            if dep_step is not None:
                db.add(PlanDependency(plan_id=plan.id, from_step_id=dep_step.id, to_step_id=step.id))

    db.flush()
    _assign_parallel_groups(db, plan.id, created)
    return created


def get_plan(db: Session, plan_id: str) -> Plan | None:
    return db.get(Plan, plan_id)


def list_plans(db: Session, *, project_id: str | None = None, status: str | None = None) -> list[Plan]:
    q = db.query(Plan)
    if project_id:
        q = q.filter(Plan.project_id == project_id)
    if status:
        q = q.filter(Plan.status == status)
    return q.order_by(Plan.created_at.desc()).all()


def update_plan(db: Session, plan_id: str, payload: schemas.PlanUpdate) -> Plan | None:
    plan = db.get(Plan, plan_id)
    if plan is None:
        return None
    if payload.scope is not None:
        plan.scope = payload.scope
    if payload.assumptions is not None:
        plan.assumptions_json = payload.assumptions
    if payload.constraints is not None:
        plan.constraints_json = payload.constraints
    if payload.success_criteria is not None:
        plan.success_criteria_json = payload.success_criteria
    if "goal_id" in payload.model_fields_set:
        plan.goal_id = payload.goal_id
    db.commit()
    db.refresh(plan)
    return plan


def approve_plan(db: Session, plan_id: str) -> Plan | None:
    plan = db.get(Plan, plan_id)
    if plan is None:
        return None
    if plan.status != "proposed":
        raise ValueError(f"Only a proposed plan can be approved (this one is '{plan.status}').")
    plan.status = "approved"
    plan.approved_at = _now()
    db.commit()
    db.refresh(plan)
    return plan


def _dependency_adjacency(plan_id: str, deps: list[PlanDependency]) -> dict[str, list[str]]:
    adj: dict[str, list[str]] = {}
    for d in deps:
        adj.setdefault(d.from_step_id, []).append(d.to_step_id)
    return adj


def _detect_cycle(step_ids: list[str], adj: dict[str, list[str]]) -> list[str] | None:
    WHITE, GRAY, BLACK = 0, 1, 2
    color = dict.fromkeys(step_ids, WHITE)
    path: list[str] = []
    found: list[str] | None = None

    def dfs(u: str) -> None:
        nonlocal found
        if found is not None:
            return
        color[u] = GRAY
        path.append(u)
        for v in adj.get(u, []):
            if found is not None:
                return
            if color.get(v, WHITE) == WHITE:
                dfs(v)
            elif color.get(v) == GRAY:
                idx = path.index(v)
                found = list(path[idx:])
        path.pop()
        color[u] = BLACK

    for sid in step_ids:
        if color.get(sid) == WHITE:
            dfs(sid)
        if found is not None:
            return found
    return None


def _longest_path(step_ids: list[str], adj: dict[str, list[str]]) -> list[str]:
    memo: dict[str, list[str]] = {}

    def longest_from(u: str) -> list[str]:
        if u in memo:
            return memo[u]
        best = [u]
        for v in adj.get(u, []):
            candidate = [u, *longest_from(v)]
            if len(candidate) > len(best):
                best = candidate
        memo[u] = best
        return best

    best_path: list[str] = []
    for sid in step_ids:
        candidate = longest_from(sid)
        if len(candidate) > len(best_path):
            best_path = candidate
    return best_path


def _step_depth(step_ids: list[str], adj: dict[str, list[str]]) -> dict[str, int]:
    """Longest-path depth from any root (no incoming edge) — steps sharing a
    depth with no direct edge between them are the parallel candidates."""
    incoming = {sid: 0 for sid in step_ids}
    for froms in adj.values():
        for to in froms:
            incoming[to] = incoming.get(to, 0) + 1
    depth = dict.fromkeys(step_ids, 0)
    memo: dict[str, int] = {}

    def depth_of(u: str, seen: frozenset) -> int:
        if u in memo:
            return memo[u]
        preds = [s for s in step_ids if u in adj.get(s, [])]
        if not preds:
            memo[u] = 0
            return 0
        if u in seen:
            memo[u] = 0
            return 0
        d = 1 + max((depth_of(p, seen | {u}) for p in preds), default=-1)
        memo[u] = d
        return d

    for sid in step_ids:
        depth[sid] = depth_of(sid, frozenset())
    return depth


def _assign_parallel_groups(db: Session, plan_id: str, steps: list[PlanStep]) -> None:
    step_ids = [s.id for s in steps]
    deps = db.query(PlanDependency).filter(PlanDependency.plan_id == plan_id).all()
    adj = _dependency_adjacency(plan_id, deps)
    if _detect_cycle(step_ids, adj) is not None:
        return  # leave parallel_group unset on a cyclic (invalid) graph
    depth = _step_depth(step_ids, adj)
    by_step = {s.id: s for s in steps}
    for sid, d in depth.items():
        by_step[sid].parallel_group = f"group-{d}"


def validate_plan(db: Session, plan_id: str) -> schemas.PlanValidationOut | None:
    plan = db.get(Plan, plan_id)
    if plan is None:
        return None

    issues: list[schemas.PlanValidationIssue] = []
    step_ids = [s.id for s in plan.steps]
    steps_by_id = {s.id: s for s in plan.steps}
    deps = list(plan.dependencies)
    adj = _dependency_adjacency(plan_id, deps)

    if not plan.steps:
        issues.append(schemas.PlanValidationIssue(step_id=None, severity="blocking", message="Plan has no steps."))

    cycle = _detect_cycle(step_ids, adj)
    critical_path: list[str] = []
    parallel_groups: dict[str, list[str]] = {}
    if cycle:
        names = [steps_by_id[sid].title for sid in cycle if sid in steps_by_id]
        issues.append(schemas.PlanValidationIssue(step_id=None, severity="blocking", message=f"Circular dependency among steps: {' -> '.join(names)}."))
    else:
        critical_path = _longest_path(step_ids, adj)
        depth = _step_depth(step_ids, adj)
        for sid, d in depth.items():
            parallel_groups.setdefault(f"group-{d}", []).append(sid)

    for step in plan.steps:
        if step.status == "blocked":
            for dependent_id in adj.get(step.id, []):
                dependent = steps_by_id.get(dependent_id)
                if dependent and dependent.status not in ("blocked", "cancelled"):
                    issues.append(
                        schemas.PlanValidationIssue(
                            step_id=dependent.id,
                            severity="warning",
                            message=f"Step '{dependent.title}' depends on blocked step '{step.title}'.",
                        )
                    )

    resource_by_name: dict[str, list[PlanResourceRequirement]] = {}
    for r in plan.resource_requirements:
        resource_by_name.setdefault(r.resource_name, []).append(r)
    for name, reqs in resource_by_name.items():
        group_ids = {steps_by_id[r.step_id].parallel_group for r in reqs if r.step_id and r.step_id in steps_by_id}
        if len(reqs) > 1 and len(group_ids) == 1 and None not in group_ids and any(r.availability_status != "available" for r in reqs):
            issues.append(
                schemas.PlanValidationIssue(step_id=None, severity="warning", message=f"Resource '{name}' is needed by multiple parallel steps and is not confirmed available.")
            )

    return schemas.PlanValidationOut(
        plan_id=plan.id,
        valid=not any(i.severity == "blocking" for i in issues),
        issues=issues,
        critical_path_step_ids=critical_path,
        parallel_groups=parallel_groups,
    )


# ============================================================================
# Phase 6 — Adaptive replanning
# ============================================================================


def replan(db: Session, plan_id: str, payload: schemas.ReplanRequest) -> Plan | None:
    """Never rewrites the old plan's history — creates a new Plan row that
    supersedes it, carrying completed steps forward unchanged and resetting
    only the still-open branches, exactly per Phase 6's rules."""
    old_plan = db.get(Plan, plan_id)
    if old_plan is None:
        return None
    if old_plan.status not in ("approved", "active", "blocked"):
        raise ValueError(f"Only an approved/active/blocked plan can be replanned (this one is '{old_plan.status}').")

    new_plan = Plan(
        objective=old_plan.objective,
        scope=old_plan.scope,
        assumptions_json=old_plan.assumptions_json,
        constraints_json=old_plan.constraints_json,
        success_criteria_json=old_plan.success_criteria_json,
        estimated_effort=old_plan.estimated_effort,
        owner=old_plan.owner,
        status="proposed",  # replanning always requires fresh approval — Phase 6's own rule
        evidence_json=old_plan.evidence_json,
        decision_case_id=old_plan.decision_case_id,
        system_model_id=old_plan.system_model_id,
        task_id=old_plan.task_id,
        project_id=old_plan.project_id,
        goal_id=old_plan.goal_id,
        revision_number=old_plan.revision_number + 1,
    )
    db.add(new_plan)
    db.flush()

    changed_step_ids: list[str] = []
    old_id_to_new_step: dict[str, PlanStep] = {}
    for old_step in old_plan.steps:
        carry_forward = old_step.status != "failed"
        if not carry_forward:
            changed_step_ids.append(old_step.id)
            continue
        new_status = old_step.status if old_step.status == "completed" else "pending"
        if new_status != old_step.status:
            changed_step_ids.append(old_step.id)
        new_step = PlanStep(
            plan_id=new_plan.id,
            order_index=old_step.order_index,
            title=old_step.title,
            description=old_step.description,
            estimated_effort=old_step.estimated_effort,
            owner=old_step.owner,
            status=new_status,
            verification_criteria_json=old_step.verification_criteria_json,
            materialised_task_id=old_step.materialised_task_id,
        )
        db.add(new_step)
        db.flush()
        old_id_to_new_step[old_step.id] = new_step

    for old_dep in old_plan.dependencies:
        new_from = old_id_to_new_step.get(old_dep.from_step_id)
        new_to = old_id_to_new_step.get(old_dep.to_step_id)
        if new_from and new_to:
            db.add(PlanDependency(plan_id=new_plan.id, from_step_id=new_from.id, to_step_id=new_to.id, dependency_type=old_dep.dependency_type))

    db.flush()
    _assign_parallel_groups(db, new_plan.id, list(old_id_to_new_step.values()))

    old_plan.superseded_by_plan_id = new_plan.id
    db.add(
        PlanRevision(
            plan_id=new_plan.id,
            revision_number=new_plan.revision_number,
            reason=payload.reason,
            trigger=payload.trigger,
            changed_step_ids_json=changed_step_ids,
            previous_status=old_plan.status,
            new_status=new_plan.status,
        )
    )
    db.commit()
    db.refresh(new_plan)
    return new_plan


# ============================================================================
# Phase 7 — Execution handoff
# ============================================================================


def materialise_plan(db: Session, plan_id: str) -> schemas.MaterialiseTasksOut | None:
    """Converts approved plan steps into real Task rows and milestone due
    dates into Schedule reminders — via action_system.run_action(), the
    same permission-gated funnel every other real action in this app uses.
    Never executes anything the planner itself decided; if a step's action
    needs confirmation, it stays a pending ActionRun (an honest proposal),
    never silently auto-approved."""
    plan = db.get(Plan, plan_id)
    if plan is None:
        return None
    if plan.status not in ("approved", "active"):
        raise ValueError(f"Only an approved plan can be materialised (this one is '{plan.status}').")

    created_task_ids: list[str] = []
    created_reminder_ids: list[str] = []
    skipped_step_ids: list[str] = []

    for step in plan.steps:
        if step.materialised_task_id or step.status == "cancelled":
            skipped_step_ids.append(step.id)
            continue
        run = action_system.run_action(
            db, "create_task", {"title": step.title, "description": step.description, "project_id": plan.project_id}, confirm=False
        )
        if run.status == "completed" and run.result_json:
            task_id = run.result_json.get("task_id")
            step.materialised_task_id = task_id
            task = db.get(Task, task_id)
            if task is not None:
                task.source_type = "plan_step"
                task.source_id = step.id
            created_task_ids.append(task_id)
        else:
            skipped_step_ids.append(step.id)

    for milestone in plan.milestones:
        if milestone.due_at is None:
            continue
        run = action_system.run_action(
            db, "add_reminder", {"title": f"Milestone: {milestone.name}", "description": milestone.description, "due_at": milestone.due_at}, confirm=False
        )
        created_reminder_ids.append(run.id)

    if plan.status == "approved":
        plan.status = "active"
    db.commit()
    return schemas.MaterialiseTasksOut(
        plan_id=plan.id, created_task_ids=created_task_ids, created_reminder_action_run_ids=created_reminder_ids, skipped_step_ids=skipped_step_ids
    )


# ============================================================================
# Milestones / risks / resource requirements — small CRUD helpers
# ============================================================================


def add_milestone(db: Session, plan_id: str, *, name: str, description: str | None, target_step_ids: list[str], verification_criteria: list[str], due_at=None) -> Milestone | None:
    plan = db.get(Plan, plan_id)
    if plan is None:
        return None
    criteria = verification_criteria or ["All target steps completed."]
    milestone = Milestone(
        plan_id=plan_id, name=name, description=description, target_step_ids_json=target_step_ids, verification_criteria_json=criteria, due_at=due_at
    )
    db.add(milestone)
    db.commit()
    db.refresh(milestone)
    return milestone


def add_risk(db: Session, plan_id: str, *, description: str, likelihood: str, impact: str, mitigation: str | None, step_id: str | None = None) -> PlanRisk | None:
    plan = db.get(Plan, plan_id)
    if plan is None:
        return None
    risk = PlanRisk(plan_id=plan_id, step_id=step_id, description=description, likelihood=likelihood, impact=impact, mitigation=mitigation)
    db.add(risk)
    db.commit()
    db.refresh(risk)
    return risk


def add_resource_requirement(
    db: Session, plan_id: str, *, resource_name: str, resource_type: str, amount: str | None, availability_status: str, step_id: str | None = None
) -> PlanResourceRequirement | None:
    plan = db.get(Plan, plan_id)
    if plan is None:
        return None
    req = PlanResourceRequirement(plan_id=plan_id, step_id=step_id, resource_name=resource_name, resource_type=resource_type, amount=amount, availability_status=availability_status)
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


def update_milestone_status(db: Session, milestone_id: str) -> Milestone | None:
    """Marks a milestone reached once every target step is completed —
    called after a step status changes, never fabricated."""
    milestone = db.get(Milestone, milestone_id)
    if milestone is None:
        return None
    if not milestone.target_step_ids_json:
        return milestone
    steps = db.query(PlanStep).filter(PlanStep.id.in_(milestone.target_step_ids_json)).all()
    if steps and all(s.status == "completed" for s in steps):
        milestone.status = "reached"
        db.commit()
        db.refresh(milestone)
    return milestone
