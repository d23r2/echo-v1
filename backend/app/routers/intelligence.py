"""ECHO Layer 2A — /api/intelligence/* (Cognitive Core v2 / Task Understanding).

Additive alongside the pre-existing /api/cognitive/* (which stays exactly as
it is — the current CognitiveCoreView.tsx page keeps working unchanged).
This router exposes the new Layer 2A capabilities: task-understanding with
the v2 fields, correction, re-analysis, a compact clarification-aware
context preview, and the task-type taxonomy.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_db
from app.models import CognitiveConcept, DecisionCase, Simulation, TaskUnderstanding
from app.services import cognitive_core, plan_engine
from app.services import decision_engine as dec_engine
from app.services import simulation_engine as sim_engine
from app.services import systems_thinking as st
from app.services import task_understanding_v2 as tuv2

router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])


@router.post("/task-understanding", response_model=schemas.TaskUnderstandingOut | None)
def create_task_understanding(payload: schemas.TaskUnderstandingRequest, db: Session = Depends(get_db)):
    """Returns null for simple messages — not an error, the message just
    didn't need the structured read (same convention as /api/cognitive/understand)."""
    return cognitive_core.build_task_understanding(
        db, payload.user_message, payload.conversation_id, project_id=payload.project_id
    )


@router.get("/tasks/{task_id}", response_model=schemas.TaskUnderstandingOut)
def get_task(task_id: str, db: Session = Depends(get_db)):
    tu = db.get(TaskUnderstanding, task_id)
    if tu is None:
        raise HTTPException(status_code=404, detail="Task understanding not found")
    return tu


@router.patch("/tasks/{task_id}", response_model=schemas.TaskUnderstandingOut)
def correct_task(task_id: str, payload: schemas.TaskUnderstandingCorrection, db: Session = Depends(get_db)):
    """User-driven correction of a misunderstood goal/constraint/scope —
    never a blind overwrite of internal fields."""
    updated = cognitive_core.apply_task_correction(db, task_id, payload.model_dump(exclude_unset=True))
    if updated is None:
        raise HTTPException(status_code=404, detail="Task understanding not found")
    return updated


@router.post("/tasks/{task_id}/reanalyse", response_model=schemas.TaskUnderstandingOut)
def reanalyse_task(task_id: str, db: Session = Depends(get_db)):
    result = cognitive_core.reanalyse_task_understanding(db, task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Task understanding not found")
    return result


@router.post("/context-preview", response_model=schemas.ContextPreviewOut)
def context_preview(payload: schemas.ContextPreviewRequest, db: Session = Depends(get_db)):
    """What Cognitive Core would produce for this message right now,
    including the compact 'why ECHO needs clarification' view — for
    developer diagnostics / the frontend's clarification preview, never for
    normal chat."""
    tu = cognitive_core.build_task_understanding(
        db, payload.user_message, payload.conversation_id, project_id=payload.project_id
    )
    if tu is None:
        return schemas.ContextPreviewOut(
            task_understanding=None,
            brief_text=None,
            clarification=schemas.ClarificationViewOut(
                needs_clarification=False, questions=[], blocking_items=[], safe_assumptions_made=[]
            ),
        )
    brief = cognitive_core.build_cognitive_brief(db, tu, payload.conversation_id)
    clarification = tuv2.build_clarification_policy(tu.missing_information_json or [])
    return schemas.ContextPreviewOut(
        task_understanding=tu,
        brief_text=brief.brief_text,
        clarification=schemas.ClarificationViewOut(**clarification),
    )


_TASK_TYPE_DESCRIPTIONS: dict[str, str] = {
    "ask_question": "A direct question with a factual or explanatory answer.",
    "build_feature": "Adding new functionality to an existing system.",
    "fix_bug": "Resolving a specific reported failure.",
    "run_test": "Running an existing test/check and reporting the real result.",
    "plan_project": "Turning a goal into a concrete, trackable plan.",
    "research_topic": "Answering using a real, current source.",
    "summarize_file": "Summarizing an actual file's extracted content.",
    "make_decision": "Helping choose between options with a clear recommendation.",
    "create_prompt": "Producing a structured, ready-to-use prompt.",
    "release_build": "Determining actual release readiness from real evidence.",
    "troubleshoot": "Diagnosing and resolving a reported problem.",
    "study_learn": "Helping the user understand a topic.",
    "personal_support": "Responding supportively, without adding pressure.",
    "other": "Anything not covered by a more specific type.",
}

_TASK_CATEGORY_DESCRIPTIONS: dict[str, str] = {
    "question": "A direct question.",
    "explanation": "Explaining a concept or how something works.",
    "research": "Requires a real, current source.",
    "coding": "Writing or changing code.",
    "debugging": "Diagnosing and fixing a failure.",
    "planning": "Turning a goal into concrete steps.",
    "decision": "Choosing between options.",
    "document": "Producing written output.",
    "action": "A real, consequential action (permission-gated).",
    "reminder": "A future scheduled action.",
    "learning": "Helping the user build understanding over time.",
    "emotional_support": "Responding to how the user is feeling.",
    "creative": "Open-ended creative output.",
    "mixed": "Spans more than one category.",
}


@router.get("/task-types", response_model=schemas.TaskTypesOut)
def list_task_types():
    return schemas.TaskTypesOut(
        task_types=[
            schemas.TaskTypeInfo(value=k, label=k.replace("_", " ").title(), description=v)
            for k, v in _TASK_TYPE_DESCRIPTIONS.items()
        ],
        task_categories=[
            schemas.TaskTypeInfo(value=k, label=k.replace("_", " ").title(), description=v)
            for k, v in _TASK_CATEGORY_DESCRIPTIONS.items()
        ],
    )


# ============================================================================
# ECHO Layer 2B — Systems Thinking and Simulation Engine
# ============================================================================


def _node_out(db: Session, node) -> schemas.SystemModelNodeOut:
    concept = db.get(CognitiveConcept, node.concept_id)
    return schemas.SystemModelNodeOut(
        id=node.id,
        system_model_id=node.system_model_id,
        concept_id=node.concept_id,
        concept_name=concept.name if concept else node.concept_id,
        node_role=node.node_role,
        state=node.state,
        owner=node.owner,
        evidence=node.evidence,
        confidence=node.confidence,
        created_at=node.created_at,
    )


@router.post("/systems", response_model=schemas.SystemModelOut)
def create_system(payload: schemas.SystemModelCreate, db: Session = Depends(get_db)):
    return st.create_system_model(db, name=payload.name, scope=payload.scope, description=payload.description, project_id=payload.project_id)


@router.get("/systems", response_model=list[schemas.SystemModelOut])
def list_systems(project_id: str | None = None, db: Session = Depends(get_db)):
    return st.list_system_models(db, project_id=project_id)


@router.get("/systems/{system_model_id}", response_model=schemas.SystemModelOut)
def get_system(system_model_id: str, db: Session = Depends(get_db)):
    model = st.get_system_model(db, system_model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="System model not found")
    return model


@router.patch("/systems/{system_model_id}", response_model=schemas.SystemModelOut)
def update_system(system_model_id: str, payload: schemas.SystemModelUpdate, db: Session = Depends(get_db)):
    updated = st.update_system_model(db, system_model_id, name=payload.name, scope=payload.scope, description=payload.description)
    if updated is None:
        raise HTTPException(status_code=404, detail="System model not found")
    return updated


@router.delete("/systems/{system_model_id}", response_model=schemas.SystemModelOut)
def archive_system(system_model_id: str, db: Session = Depends(get_db)):
    archived = st.archive_system_model(db, system_model_id)
    if archived is None:
        raise HTTPException(status_code=404, detail="System model not found")
    return archived


@router.get("/systems/{system_model_id}/nodes", response_model=list[schemas.SystemModelNodeOut])
def list_system_nodes(system_model_id: str, db: Session = Depends(get_db)):
    if st.get_system_model(db, system_model_id) is None:
        raise HTTPException(status_code=404, detail="System model not found")
    return [_node_out(db, n) for n in st.list_nodes(db, system_model_id)]


@router.post("/systems/{system_model_id}/nodes", response_model=schemas.SystemModelNodeOut)
def add_system_node(system_model_id: str, payload: schemas.SystemModelNodeCreate, db: Session = Depends(get_db)):
    if st.get_system_model(db, system_model_id) is None:
        raise HTTPException(status_code=404, detail="System model not found")
    if db.get(CognitiveConcept, payload.concept_id) is None:
        raise HTTPException(status_code=404, detail="Concept not found")
    node = st.add_node(
        db,
        system_model_id,
        concept_id=payload.concept_id,
        node_role=payload.node_role,
        state=payload.state,
        owner=payload.owner,
        evidence=payload.evidence,
        confidence=payload.confidence,
    )
    return _node_out(db, node)


@router.delete("/systems/{system_model_id}/nodes/{node_id}")
def delete_system_node(system_model_id: str, node_id: str, db: Session = Depends(get_db)):
    if not st.remove_node(db, node_id):
        raise HTTPException(status_code=404, detail="Node not found")
    return {"ok": True}


@router.get("/systems/{system_model_id}/analysis", response_model=schemas.SystemAnalysisOut)
def get_system_analysis(system_model_id: str, db: Session = Depends(get_db)):
    analysis = st.build_system_analysis(db, system_model_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="System model not found")
    return schemas.SystemAnalysisOut(
        system_model=analysis["system_model"],
        nodes=[_node_out(db, n) for n in analysis["nodes"]],
        edges=[
            schemas.DependencyEdgeOut(from_concept_id=e.from_concept_id, to_concept_id=e.to_concept_id, relation_type=e.relation_type)
            for e in analysis["edges"]
        ],
        bottlenecks=[schemas.BottleneckOut(**b) for b in analysis["bottlenecks"]],
        cycles=analysis["cycles"],
        critical_path=schemas.CriticalPathOut(**analysis["critical_path"]) if analysis["critical_path"] else None,
    )


@router.get("/systems/{system_model_id}/counterfactuals")
def get_system_counterfactuals(system_model_id: str, db: Session = Depends(get_db)):
    if st.get_system_model(db, system_model_id) is None:
        raise HTTPException(status_code=404, detail="System model not found")
    return {"counterfactuals": st.build_counterfactuals(db, system_model_id)}


@router.post("/simulations", response_model=schemas.SimulationOut)
def create_simulation(payload: schemas.SimulationCreate, db: Session = Depends(get_db)):
    """Bounded, non-executing simulation — every scenario here is a
    forecast, never a fact, and nothing here ever performs a real action
    (see action_system.py for the separate, permission-gated real path)."""
    if payload.system_model_id and st.get_system_model(db, payload.system_model_id) is None:
        raise HTTPException(status_code=404, detail="System model not found")
    return sim_engine.run_simulation(
        db,
        objective=payload.objective,
        task_id=payload.task_id,
        system_model_id=payload.system_model_id,
        baseline_state=payload.baseline_state,
        constraints=payload.constraints,
        assumptions=payload.assumptions,
        max_scenarios=payload.max_scenarios,
        max_steps=payload.max_steps,
        time_horizon=payload.time_horizon,
        evaluation_criteria=payload.evaluation_criteria,
        risk_tolerance=payload.risk_tolerance,
    )


@router.get("/simulations", response_model=list[schemas.SimulationOut])
def list_simulations(task_id: str | None = None, system_model_id: str | None = None, db: Session = Depends(get_db)):
    return sim_engine.list_simulations(db, task_id=task_id, system_model_id=system_model_id)


@router.get("/simulations/{simulation_id}", response_model=schemas.SimulationOut)
def get_simulation(simulation_id: str, db: Session = Depends(get_db)):
    sim = db.get(Simulation, simulation_id)
    if sim is None:
        raise HTTPException(status_code=404, detail="Simulation not found")
    return sim


@router.get("/simulations/{simulation_id}/decision-handoff", response_model=schemas.DecisionHandoffOut)
def get_decision_handoff(simulation_id: str, db: Session = Depends(get_db)):
    sim = db.get(Simulation, simulation_id)
    if sim is None:
        raise HTTPException(status_code=404, detail="Simulation not found")
    return sim_engine.build_decision_handoff(sim)


# ============================================================================
# ECHO Layer 2C — Decision Engine and Planning Engine
# ============================================================================


def _decision_case_out(case: DecisionCase) -> schemas.DecisionCaseOut:
    report = schemas.DecisionReportOut(**case.report_json) if case.report_json else None
    return schemas.DecisionCaseOut(
        id=case.id,
        question=case.question,
        objective=case.objective,
        constraints_json=case.constraints_json,
        stakeholders_json=case.stakeholders_json,
        evidence_json=case.evidence_json,
        assumptions_json=case.assumptions_json,
        uncertainty=case.uncertainty,
        time_horizon=case.time_horizon,
        reversibility=case.reversibility,
        consequence_level=case.consequence_level,
        status=case.status,
        simulation_id=case.simulation_id,
        task_id=case.task_id,
        project_id=case.project_id,
        recommended_option_id=case.recommended_option_id,
        no_clear_winner=case.no_clear_winner,
        report=report,
        created_at=case.created_at,
        updated_at=case.updated_at,
        options=case.options,
        criteria=case.criteria,
    )


@router.post("/decisions", response_model=schemas.DecisionCaseOut)
def create_decision(payload: schemas.DecisionCaseCreate, db: Session = Depends(get_db)):
    if payload.simulation_id and db.get(Simulation, payload.simulation_id) is None:
        raise HTTPException(status_code=404, detail="Simulation not found")
    case = dec_engine.create_decision_case(db, payload)
    return _decision_case_out(case)


@router.get("/decisions", response_model=list[schemas.DecisionCaseOut])
def list_decisions(project_id: str | None = None, db: Session = Depends(get_db)):
    return [_decision_case_out(c) for c in dec_engine.list_decision_cases(db, project_id=project_id)]


@router.get("/decisions/{decision_case_id}", response_model=schemas.DecisionCaseOut)
def get_decision(decision_case_id: str, db: Session = Depends(get_db)):
    case = dec_engine.get_decision_case(db, decision_case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Decision case not found")
    return _decision_case_out(case)


@router.post("/decisions/{decision_case_id}/analyse", response_model=schemas.DecisionCaseOut)
def analyse_decision(decision_case_id: str, db: Session = Depends(get_db)):
    case = dec_engine.analyse(db, decision_case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Decision case not found")
    return _decision_case_out(case)


@router.post("/decisions/{decision_case_id}/select", response_model=schemas.DecisionCaseOut)
def select_decision_option(decision_case_id: str, payload: schemas.DecisionSelectRequest, db: Session = Depends(get_db)):
    """The user's own explicit, final choice — the Decision Engine only
    ever recommends via /analyse; this is the one call that actually
    commits to an option."""
    try:
        case = dec_engine.select_option(db, decision_case_id, payload.option_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if case is None:
        raise HTTPException(status_code=404, detail="Decision case not found")
    return _decision_case_out(case)


@router.patch("/decisions/{decision_case_id}/criteria/{criterion_id}/weight", response_model=schemas.DecisionCriterionOut)
def update_criterion_weight(decision_case_id: str, criterion_id: str, payload: schemas.DecisionCriterionWeightUpdate, db: Session = Depends(get_db)):
    criterion = dec_engine.set_criterion_weight(db, criterion_id, payload.weight)
    if criterion is None or criterion.decision_case_id != decision_case_id:
        raise HTTPException(status_code=404, detail="Criterion not found")
    return criterion


@router.patch("/decisions/{decision_case_id}/options/{option_id}/ratings", response_model=schemas.DecisionOptionOut)
def update_option_ratings(decision_case_id: str, option_id: str, payload: schemas.DecisionOptionRatingsUpdate, db: Session = Depends(get_db)):
    option = dec_engine.set_option_ratings(db, option_id, payload.ratings)
    if option is None or option.decision_case_id != decision_case_id:
        raise HTTPException(status_code=404, detail="Option not found")
    return option


@router.post("/plans", response_model=schemas.PlanOut)
def create_plan(payload: schemas.PlanCreate, db: Session = Depends(get_db)):
    if payload.decision_case_id and db.get(DecisionCase, payload.decision_case_id) is None:
        raise HTTPException(status_code=404, detail="Decision case not found")
    return plan_engine.create_plan(db, payload)


@router.get("/plans", response_model=list[schemas.PlanOut])
def list_plans(project_id: str | None = None, status: str | None = None, db: Session = Depends(get_db)):
    return plan_engine.list_plans(db, project_id=project_id, status=status)


@router.get("/plans/{plan_id}", response_model=schemas.PlanOut)
def get_plan(plan_id: str, db: Session = Depends(get_db)):
    plan = plan_engine.get_plan(db, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@router.patch("/plans/{plan_id}", response_model=schemas.PlanOut)
def update_plan(plan_id: str, payload: schemas.PlanUpdate, db: Session = Depends(get_db)):
    plan = plan_engine.update_plan(db, plan_id, payload)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@router.post("/plans/{plan_id}/validate", response_model=schemas.PlanValidationOut)
def validate_plan(plan_id: str, db: Session = Depends(get_db)):
    result = plan_engine.validate_plan(db, plan_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return result


@router.post("/plans/{plan_id}/approve", response_model=schemas.PlanOut)
def approve_plan(plan_id: str, db: Session = Depends(get_db)):
    try:
        plan = plan_engine.approve_plan(db, plan_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@router.post("/plans/{plan_id}/replan", response_model=schemas.PlanOut)
def replan_plan(plan_id: str, payload: schemas.ReplanRequest, db: Session = Depends(get_db)):
    try:
        plan = plan_engine.replan(db, plan_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@router.post("/plans/{plan_id}/materialise-tasks", response_model=schemas.MaterialiseTasksOut)
def materialise_tasks(plan_id: str, db: Session = Depends(get_db)):
    """Never called automatically — only this explicit user-triggered call
    ever converts plan steps into real Task rows, and even then only
    through the same permission-gated action_system.run_action() funnel
    every other real action uses."""
    try:
        result = plan_engine.materialise_plan(db, plan_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if result is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return result


@router.post("/plans/{plan_id}/milestones", response_model=schemas.MilestoneOut)
def add_plan_milestone(plan_id: str, payload: dict, db: Session = Depends(get_db)):
    milestone = plan_engine.add_milestone(
        db,
        plan_id,
        name=payload.get("name", ""),
        description=payload.get("description"),
        target_step_ids=payload.get("target_step_ids", []),
        verification_criteria=payload.get("verification_criteria", []),
        due_at=payload.get("due_at"),
    )
    if milestone is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return milestone


@router.post("/plans/{plan_id}/risks", response_model=schemas.PlanRiskOut)
def add_plan_risk(plan_id: str, payload: dict, db: Session = Depends(get_db)):
    risk = plan_engine.add_risk(
        db,
        plan_id,
        description=payload.get("description", ""),
        likelihood=payload.get("likelihood", "unknown"),
        impact=payload.get("impact", "medium"),
        mitigation=payload.get("mitigation"),
        step_id=payload.get("step_id"),
    )
    if risk is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return risk


@router.post("/plans/{plan_id}/resources", response_model=schemas.PlanResourceRequirementOut)
def add_plan_resource(plan_id: str, payload: dict, db: Session = Depends(get_db)):
    req = plan_engine.add_resource_requirement(
        db,
        plan_id,
        resource_name=payload.get("resource_name", ""),
        resource_type=payload.get("resource_type", "other"),
        amount=payload.get("amount"),
        availability_status=payload.get("availability_status", "unknown"),
        step_id=payload.get("step_id"),
    )
    if req is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return req
