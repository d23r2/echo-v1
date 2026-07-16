from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_db
from app.services import release_manager

router = APIRouter(prefix="/api/releases", tags=["releases"])


@router.get("", response_model=list[schemas.ReleaseOut])
def list_releases(db: Session = Depends(get_db)):
    return release_manager.list_releases(db)


@router.post("", response_model=schemas.ReleaseOut)
def create_release(payload: schemas.ReleaseCreate, db: Session = Depends(get_db)):
    try:
        return release_manager.create_release(db, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.get("/{release_id}", response_model=schemas.ReleaseDetailOut)
def get_release(release_id: str, db: Session = Depends(get_db)):
    release = release_manager.get_release(db, release_id)
    if release is None:
        raise HTTPException(status_code=404, detail="Release not found")
    return release


@router.patch("/{release_id}", response_model=schemas.ReleaseOut)
def update_release(release_id: str, payload: schemas.ReleaseUpdate, db: Session = Depends(get_db)):
    try:
        return release_manager.update_release(db, release_id, payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.post("/{release_id}/checks", response_model=schemas.ReleaseCheckOut)
def add_check(release_id: str, payload: schemas.ReleaseCheckCreate, db: Session = Depends(get_db)):
    try:
        return release_manager.add_check(db, release_id, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.post("/{release_id}/checklist/seed", response_model=list[schemas.ReleaseCheckOut])
def seed_checklist(release_id: str, db: Session = Depends(get_db)):
    try:
        return release_manager.seed_standard_checklist(db, release_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.post("/{release_id}/artifacts", response_model=schemas.ReleaseArtifactOut)
def add_artifact(release_id: str, payload: schemas.ReleaseArtifactCreate, db: Session = Depends(get_db)):
    try:
        return release_manager.add_artifact(db, release_id, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.post("/{release_id}/mark-status", response_model=schemas.ReleaseOut)
def mark_status(release_id: str, payload: schemas.ReleaseMarkStatusRequest, db: Session = Depends(get_db)):
    try:
        return release_manager.mark_status(db, release_id, payload.status)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
