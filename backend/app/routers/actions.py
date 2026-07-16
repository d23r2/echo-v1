from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_db
from app.services import action_system

router = APIRouter(prefix="/api/actions", tags=["actions"])


@router.get("", response_model=list[schemas.ActionDefinitionOut])
def list_actions(db: Session = Depends(get_db)):
    return action_system.list_actions(db)


@router.get("/runs", response_model=list[schemas.ActionRunOut])
def list_runs(db: Session = Depends(get_db)):
    return action_system.list_runs(db)


@router.post("/run", response_model=schemas.ActionRunOut)
def run(payload: schemas.ActionRunRequest, db: Session = Depends(get_db)):
    try:
        return action_system.run_action(db, payload.action_name, payload.input, confirm=payload.confirm)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post("/runs/{run_id}/approve", response_model=schemas.ActionRunOut)
def approve(run_id: str, db: Session = Depends(get_db)):
    try:
        return action_system.approve_run(db, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post("/runs/{run_id}/cancel", response_model=schemas.ActionRunOut)
def cancel(run_id: str, db: Session = Depends(get_db)):
    try:
        return action_system.cancel_run(db, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
