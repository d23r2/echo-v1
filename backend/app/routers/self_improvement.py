from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import SelfImprovementRequest
from app.schemas import SelfImprovementRequestApprove, SelfImprovementRequestCreate, SelfImprovementRequestOut
from app.self_improvement_verify import run_verification, summarize

router = APIRouter(prefix="/api/self-improvement", tags=["self-improvement"])


@router.get("", response_model=list[SelfImprovementRequestOut])
def list_requests(db: Session = Depends(get_db)):
    return db.query(SelfImprovementRequest).order_by(SelfImprovementRequest.created_at.desc()).all()


@router.post("", response_model=SelfImprovementRequestOut)
def create_request(payload: SelfImprovementRequestCreate, db: Session = Depends(get_db)):
    request = SelfImprovementRequest(
        title=payload.title,
        description=payload.description,
        proposed_by=payload.proposed_by,
        status="proposed",
    )
    db.add(request)
    db.commit()
    db.refresh(request)
    return request


@router.post("/{request_id}/approve", response_model=SelfImprovementRequestOut)
def approve_request(request_id: str, payload: SelfImprovementRequestApprove, db: Session = Depends(get_db)):
    request = db.get(SelfImprovementRequest, request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="Request not found")

    request.status = "approved" if payload.approved else "rejected"
    request.verification_status = "pending"
    request.verification_notes = payload.note
    db.commit()
    db.refresh(request)
    return request


@router.post("/{request_id}/verify", response_model=SelfImprovementRequestOut)
def verify_request(request_id: str, db: Session = Depends(get_db)):
    request = db.get(SelfImprovementRequest, request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="Request not found")
    if request.status != "approved":
        raise HTTPException(
            status_code=400,
            detail="Only founder-approved requests can be verified. Approve this request first.",
        )

    # Read-only: runs git/pytest/ruff/mypy against the current working tree and
    # reports the results. Never edits files, applies a patch, or restarts anything.
    checks = run_verification()
    status, notes = summarize(checks)

    request.verification_checks = checks
    request.verification_status = status
    request.verification_notes = notes
    request.verified_at = datetime.now(timezone.utc)
    request.patch_summary = (
        "No code was modified — this ran read-only checks against the current working tree."
    )
    db.commit()
    db.refresh(request)
    return request
