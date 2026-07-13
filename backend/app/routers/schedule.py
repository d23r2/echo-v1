from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_db
from app.models import ScheduleItem

router = APIRouter(prefix="/api/schedule", tags=["schedule"])

_VALID_STATUSES = {"pending", "completed", "cancelled"}


@router.post("", response_model=schemas.ScheduleItemOut)
def create_schedule_item(payload: schemas.ScheduleItemCreate, db: Session = Depends(get_db)):
    if not payload.title.strip():
        raise HTTPException(status_code=400, detail="Title is required")
    item = ScheduleItem(
        title=payload.title.strip(),
        description=payload.description,
        due_at=payload.due_at,
        recurrence_rule=payload.recurrence_rule,
        source_conversation_id=payload.source_conversation_id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("", response_model=list[schemas.ScheduleItemOut])
def list_schedule_items(status: str | None = Query(None), db: Session = Depends(get_db)):
    """Upcoming (pending, soonest due_at first, nulls last) unless a specific
    status is requested, in which case that status is listed newest-first."""
    query = db.query(ScheduleItem)
    if status:
        if status not in _VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"Unknown status '{status}'")
        return query.filter(ScheduleItem.status == status).order_by(ScheduleItem.created_at.desc()).all()
    return (
        query.filter(ScheduleItem.status == "pending")
        .order_by(ScheduleItem.due_at.is_(None), ScheduleItem.due_at.asc())
        .all()
    )


@router.patch("/{item_id}", response_model=schemas.ScheduleItemOut)
def update_schedule_item(item_id: str, payload: schemas.ScheduleItemUpdate, db: Session = Depends(get_db)):
    item = db.get(ScheduleItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Schedule item not found")
    if payload.title is not None:
        if not payload.title.strip():
            raise HTTPException(status_code=400, detail="Title cannot be empty")
        item.title = payload.title.strip()
    if payload.description is not None:
        item.description = payload.description
    if payload.due_at is not None:
        item.due_at = payload.due_at
    if payload.recurrence_rule is not None:
        item.recurrence_rule = payload.recurrence_rule
    db.commit()
    db.refresh(item)
    return item


@router.post("/{item_id}/complete", response_model=schemas.ScheduleItemOut)
def complete_schedule_item(item_id: str, db: Session = Depends(get_db)):
    item = db.get(ScheduleItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Schedule item not found")
    item.status = "completed"
    db.commit()
    db.refresh(item)
    return item


@router.post("/{item_id}/cancel", response_model=schemas.ScheduleItemOut)
def cancel_schedule_item(item_id: str, db: Session = Depends(get_db)):
    item = db.get(ScheduleItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Schedule item not found")
    item.status = "cancelled"
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}")
def delete_schedule_item(item_id: str, db: Session = Depends(get_db)):
    item = db.get(ScheduleItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Schedule item not found")
    db.delete(item)
    db.commit()
    return {"deleted": True}
