from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_db
from app.services import operational_self_model

router = APIRouter(prefix="/api", tags=["operational-self-model"])


@router.get("/interface-settings", response_model=schemas.InterfaceSettingsOut)
def get_interface_settings(db: Session = Depends(get_db)):
    return operational_self_model.get_or_create_interface_settings(db)


@router.patch("/interface-settings", response_model=schemas.InterfaceSettingsOut)
def update_interface_settings(payload: schemas.InterfaceSettingsUpdate, db: Session = Depends(get_db)):
    return operational_self_model.update_interface_settings(db, payload.model_dump(exclude_unset=True))


@router.get("/self-model/recent", response_model=list[schemas.OperationalStateSnapshotOut])
def list_recent_self_model_snapshots(conversation_id: str | None = None, db: Session = Depends(get_db)):
    """Developer-mode-only surface (gated in the frontend, not here — same
    convention as Cognitive Core's /briefs endpoint) for inspecting recent
    operational state snapshots. Never called from the normal chat UI."""
    return operational_self_model.list_recent_snapshots(db, conversation_id=conversation_id)
