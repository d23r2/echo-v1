from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import council, schemas
from app.db import get_db
from app.models import Amendment

router = APIRouter(prefix="/api/amendments", tags=["amendments"])


def _to_out(amendment: Amendment) -> schemas.AmendmentOut:
    return schemas.AmendmentOut(
        id=amendment.id,
        title=amendment.title,
        text=amendment.text,
        rationale=amendment.rationale,
        proposed_by=amendment.proposed_by,
        status=amendment.status,
        created_at=amendment.created_at,
        decided_at=amendment.decided_at,
        votes=[schemas.VoteOut.model_validate(v) for v in amendment.votes],
        tally=council.tally(amendment),
    )


def _get_or_404(db: Session, amendment_id: str) -> Amendment:
    amendment = db.get(Amendment, amendment_id)
    if amendment is None:
        raise HTTPException(status_code=404, detail="Amendment not found")
    return amendment


@router.get("", response_model=list[schemas.AmendmentOut])
def list_amendments(db: Session = Depends(get_db)):
    amendments = db.query(Amendment).order_by(Amendment.created_at.desc()).all()
    return [_to_out(a) for a in amendments]


@router.get("/{amendment_id}", response_model=schemas.AmendmentOut)
def get_amendment(amendment_id: str, db: Session = Depends(get_db)):
    return _to_out(_get_or_404(db, amendment_id))


@router.post("", response_model=schemas.AmendmentOut)
def propose_amendment(payload: schemas.AmendmentProposeRequest, db: Session = Depends(get_db)):
    try:
        council.guard_amendment_text(payload.text)
    except council.InvariantGuardError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except council.NeedsHumanReviewError as exc:
        # Distinct from an outright block: 422 (the request is well-formed but
        # can't be processed as-is) rather than 400, so callers can tell "this was
        # flagged as ambiguous" apart from "this was rejected outright".
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    amendment = Amendment(
        title=payload.title,
        text=payload.text,
        rationale=payload.rationale,
        proposed_by=payload.proposed_by,
    )
    db.add(amendment)
    db.commit()
    db.refresh(amendment)
    return _to_out(amendment)


@router.post("/{amendment_id}/vote", response_model=schemas.AmendmentOut)
def vote_on_amendment(amendment_id: str, payload: schemas.VoteRequest, db: Session = Depends(get_db)):
    amendment = _get_or_404(db, amendment_id)
    try:
        amendment = council.cast_vote(db, amendment, payload.role, payload.decision, payload.comment)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_out(amendment)
