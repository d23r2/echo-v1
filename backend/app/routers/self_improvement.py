from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import SelfImprovementRequest
from app.schemas import SelfImprovementRequestApprove, SelfImprovementRequestCreate, SelfImprovementRequestOut

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

    request.verification_status = "passed"
    request.patch_summary = "Build/test verification placeholder"
    request.verification_notes = "Initial scaffold verified; no code patch applied yet."
    request.status = "approved"
    db.commit()
    db.refresh(request)
    return request
