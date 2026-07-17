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
from app.models import CognitiveConcept, Simulation, TaskUnderstanding
from app.services import cognitive_core
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
