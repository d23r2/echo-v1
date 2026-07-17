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
from app.models import TaskUnderstanding
from app.services import cognitive_core
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
