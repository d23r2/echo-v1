from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_db
from app.models import CausalNote, CognitiveConcept, CognitiveRelationship, TaskUnderstanding, _now
from app.services import cognitive_core, skill_library

router = APIRouter(prefix="/api/cognitive", tags=["cognitive"])


# ============================================================================
# Task understanding
# ============================================================================


@router.post("/understand", response_model=schemas.TaskUnderstandingOut | None)
def understand(payload: schemas.TaskUnderstandingRequest, db: Session = Depends(get_db)):
    """Returns null for simple messages (Phase 4 rule 5) — not an error,
    just "this message didn't need the structured read.\""""
    return cognitive_core.build_task_understanding(db, payload.user_message, payload.conversation_id)


@router.get("/task-understandings", response_model=list[schemas.TaskUnderstandingOut])
def list_task_understandings(limit: int = Query(20, le=100), db: Session = Depends(get_db)):
    return db.query(TaskUnderstanding).order_by(TaskUnderstanding.created_at.desc()).limit(limit).all()


@router.get("/task-understandings/{tu_id}", response_model=schemas.TaskUnderstandingOut)
def get_task_understanding(tu_id: str, db: Session = Depends(get_db)):
    tu = db.get(TaskUnderstanding, tu_id)
    if tu is None:
        raise HTTPException(status_code=404, detail="Task understanding not found")
    return tu


# ============================================================================
# Cognitive briefs
# ============================================================================


@router.post("/brief", response_model=schemas.CognitiveBriefOut | None)
def create_brief(payload: schemas.CognitiveBriefRequest, db: Session = Depends(get_db)):
    return cognitive_core.get_cognitive_brief_for_message(db, payload.user_message, payload.conversation_id)


@router.get("/briefs", response_model=list[schemas.CognitiveBriefOut])
def list_briefs(limit: int = Query(20, le=100), db: Session = Depends(get_db)):
    from app.models import CognitiveBrief as CognitiveBriefModel

    return db.query(CognitiveBriefModel).order_by(CognitiveBriefModel.created_at.desc()).limit(limit).all()


@router.get("/briefs/{brief_id}", response_model=schemas.CognitiveBriefOut)
def get_brief(brief_id: str, db: Session = Depends(get_db)):
    from app.models import CognitiveBrief as CognitiveBriefModel

    brief = db.get(CognitiveBriefModel, brief_id)
    if brief is None:
        raise HTTPException(status_code=404, detail="Cognitive brief not found")
    return brief


# ============================================================================
# Concepts (World Model)
# ============================================================================


@router.get("/concepts", response_model=list[schemas.CognitiveConceptOut])
def list_concepts(concept_type: str | None = Query(None), q: str | None = Query(None), db: Session = Depends(get_db)):
    query = db.query(CognitiveConcept).filter(CognitiveConcept.archived_at.is_(None))
    if concept_type:
        query = query.filter(CognitiveConcept.concept_type == concept_type)
    if q:
        from sqlalchemy import or_

        like = f"%{q.strip()}%"
        query = query.filter(or_(CognitiveConcept.name.ilike(like), CognitiveConcept.description.ilike(like)))
    return query.order_by(CognitiveConcept.name).all()


@router.post("/concepts", response_model=schemas.CognitiveConceptOut)
def create_concept(payload: schemas.CognitiveConceptCreate, db: Session = Depends(get_db)):
    try:
        return cognitive_core.create_or_update_concept(db, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.get("/concepts/{concept_id}", response_model=schemas.CognitiveConceptOut)
def get_concept(concept_id: str, db: Session = Depends(get_db)):
    concept = db.get(CognitiveConcept, concept_id)
    if concept is None:
        raise HTTPException(status_code=404, detail="Concept not found")
    return concept


@router.patch("/concepts/{concept_id}", response_model=schemas.CognitiveConceptOut)
def update_concept(concept_id: str, payload: schemas.CognitiveConceptUpdate, db: Session = Depends(get_db)):
    concept = db.get(CognitiveConcept, concept_id)
    if concept is None:
        raise HTTPException(status_code=404, detail="Concept not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(concept, field, value)
    db.commit()
    db.refresh(concept)
    return concept


@router.delete("/concepts/{concept_id}", response_model=schemas.CognitiveConceptOut)
def archive_concept(concept_id: str, db: Session = Depends(get_db)):
    concept = db.get(CognitiveConcept, concept_id)
    if concept is None:
        raise HTTPException(status_code=404, detail="Concept not found")
    concept.archived_at = _now()
    db.commit()
    db.refresh(concept)
    return concept


# ============================================================================
# Relationships
# ============================================================================


@router.get("/relationships", response_model=list[schemas.CognitiveRelationshipOut])
def list_relationships(concept_id: str | None = Query(None), db: Session = Depends(get_db)):
    from sqlalchemy import or_

    query = db.query(CognitiveRelationship)
    if concept_id:
        query = query.filter(or_(CognitiveRelationship.from_concept_id == concept_id, CognitiveRelationship.to_concept_id == concept_id))
    return query.all()


@router.post("/relationships", response_model=schemas.CognitiveRelationshipOut)
def create_relationship(payload: schemas.CognitiveRelationshipCreate, db: Session = Depends(get_db)):
    try:
        return cognitive_core.create_relationship(db, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.delete("/relationships/{relationship_id}")
def delete_relationship(relationship_id: str, db: Session = Depends(get_db)):
    rel = db.get(CognitiveRelationship, relationship_id)
    if rel is None:
        raise HTTPException(status_code=404, detail="Relationship not found")
    db.delete(rel)
    db.commit()
    return {"deleted": True}


# ============================================================================
# Graph search
# ============================================================================


@router.get("/graph", response_model=list[schemas.GraphNodeOut])
def graph_search(query: str = Query(...), db: Session = Depends(get_db)):
    return cognitive_core.search_world_model(db, query)


# ============================================================================
# Skills
# ============================================================================


@router.get("/skills", response_model=list[schemas.SkillPatternOut])
def list_skills(category: str | None = Query(None), db: Session = Depends(get_db)):
    return skill_library.list_skills(db, category=category)


@router.post("/skills", response_model=schemas.SkillPatternOut)
def create_skill(payload: schemas.SkillPatternCreate, db: Session = Depends(get_db)):
    try:
        return skill_library.create_skill(db, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.get("/skills/{skill_id}", response_model=schemas.SkillPatternOut)
def get_skill(skill_id: str, db: Session = Depends(get_db)):
    from app.models import SkillPattern

    skill = db.get(SkillPattern, skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill


@router.patch("/skills/{skill_id}", response_model=schemas.SkillPatternOut)
def update_skill(skill_id: str, payload: schemas.SkillPatternUpdate, db: Session = Depends(get_db)):
    try:
        return skill_library.update_skill(db, skill_id, payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.delete("/skills/{skill_id}", response_model=schemas.SkillPatternOut)
def archive_skill(skill_id: str, db: Session = Depends(get_db)):
    try:
        return skill_library.archive_skill(db, skill_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.post("/skills/{skill_id}/suggest-plan", response_model=schemas.SuggestPlanOut)
def suggest_plan(skill_id: str, payload: schemas.SuggestPlanRequest, db: Session = Depends(get_db)):
    from app.models import SkillPattern

    skill = db.get(SkillPattern, skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    return schemas.SuggestPlanOut(skill=skill, plan_steps=list(skill.steps_json or []))


# ============================================================================
# Causal notes
# ============================================================================


@router.get("/causal-notes", response_model=list[schemas.CausalNoteOut])
def list_causal_notes(db: Session = Depends(get_db)):
    return db.query(CausalNote).filter(CausalNote.archived_at.is_(None)).order_by(CausalNote.title).all()


@router.post("/causal-notes", response_model=schemas.CausalNoteOut)
def create_causal_note(payload: schemas.CausalNoteCreate, db: Session = Depends(get_db)):
    note = CausalNote(**payload.model_dump())
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


@router.patch("/causal-notes/{note_id}", response_model=schemas.CausalNoteOut)
def update_causal_note(note_id: str, payload: schemas.CausalNoteUpdate, db: Session = Depends(get_db)):
    note = db.get(CausalNote, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Causal note not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(note, field, value)
    db.commit()
    db.refresh(note)
    return note


@router.delete("/causal-notes/{note_id}", response_model=schemas.CausalNoteOut)
def archive_causal_note(note_id: str, db: Session = Depends(get_db)):
    note = db.get(CausalNote, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Causal note not found")
    note.archived_at = _now()
    db.commit()
    db.refresh(note)
    return note


# ============================================================================
# Settings
# ============================================================================


@router.get("/settings", response_model=schemas.CognitiveSettingsOut)
def get_settings(db: Session = Depends(get_db)):
    return cognitive_core.get_or_create_settings(db)


@router.patch("/settings", response_model=schemas.CognitiveSettingsOut)
def update_settings(payload: schemas.CognitiveSettingsUpdate, db: Session = Depends(get_db)):
    return cognitive_core.update_settings(db, payload.model_dump(exclude_unset=True))
