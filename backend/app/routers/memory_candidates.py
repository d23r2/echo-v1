from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import atlas as atlas_store
from app import schemas
from app.db import get_db
from app.models import MemoryCandidate

router = APIRouter(prefix="/api/memory-candidates", tags=["memory-candidates"])


def _get_or_404(db: Session, candidate_id: str) -> MemoryCandidate:
    candidate = db.get(MemoryCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Memory candidate not found")
    return candidate


@router.get("", response_model=list[schemas.MemoryCandidateOut])
def list_candidates(
    status: schemas.MemoryCandidateStatus | None = Query("pending"), db: Session = Depends(get_db)
):
    query = db.query(MemoryCandidate)
    if status:
        query = query.filter(MemoryCandidate.status == status)
    return query.order_by(MemoryCandidate.created_at.desc()).all()


@router.patch("/{candidate_id}", response_model=schemas.MemoryCandidateOut)
def edit_candidate(candidate_id: str, payload: schemas.MemoryCandidateEdit, db: Session = Depends(get_db)):
    candidate = _get_or_404(db, candidate_id)
    if candidate.status != "pending":
        raise HTTPException(status_code=400, detail=f"Candidate is already '{candidate.status}'; only pending candidates can be edited")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(candidate, field, value)
    db.commit()
    db.refresh(candidate)
    return candidate


@router.post("/{candidate_id}/accept", response_model=schemas.AtlasEntryOut)
def accept_candidate(
    candidate_id: str, payload: schemas.MemoryCandidateDecision, db: Session = Depends(get_db)
):
    candidate = _get_or_404(db, candidate_id)
    if candidate.status != "pending":
        raise HTTPException(status_code=400, detail=f"Candidate is already '{candidate.status}'")

    entry = atlas_store.create_entry(
        db,
        schemas.AtlasEntryCreate(
            content=candidate.content,
            epistemic_status=candidate.epistemic_status,
            memory_type=candidate.memory_type,
            tags=candidate.tags,
            confidence=candidate.confidence,
            source=candidate.source,
            category=candidate.category,
            importance=candidate.importance,
            stability=candidate.stability,
            capture_method="approved_candidate",
        ),
    )
    # A human explicitly reviewed and accepted this — that's real verification,
    # stronger than whatever epistemic_status the candidate started with.
    entry.verification_status = "verified"
    db.commit()
    candidate.status = "accepted"
    candidate.review_note = payload.note
    db.commit()
    return entry


@router.post("/{candidate_id}/reject", response_model=schemas.MemoryCandidateOut)
def reject_candidate(
    candidate_id: str, payload: schemas.MemoryCandidateDecision, db: Session = Depends(get_db)
):
    candidate = _get_or_404(db, candidate_id)
    if candidate.status != "pending":
        raise HTTPException(status_code=400, detail=f"Candidate is already '{candidate.status}'")

    candidate.status = "rejected"
    candidate.review_note = payload.note
    db.commit()
    db.refresh(candidate)
    return candidate
