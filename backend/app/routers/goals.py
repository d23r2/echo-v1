"""ECHO Layer 2E — Goal Manager API. approve/pause/abandon/review are
dedicated endpoints (not folded into a generic PATCH) since each carries its
own history/evidence rules the milestone spec requires — see
services/goal_engine.py."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_db
from app.services import goal_engine

router = APIRouter(prefix="/api/goals", tags=["goals"])

_MAX_LIST_LIMIT = 200


@router.post("", response_model=schemas.GoalOut)
def create_goal(payload: schemas.GoalCreate, db: Session = Depends(get_db)):
    if not payload.title.strip():
        raise HTTPException(status_code=400, detail="Title is required")
    return goal_engine.create_goal(db, payload)


@router.get("", response_model=list[schemas.GoalOut])
def list_goals(
    status: str | None = Query(None),
    project_id: str | None = Query(None),
    parent_goal_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=_MAX_LIST_LIMIT),
    db: Session = Depends(get_db),
):
    goals = goal_engine.list_goals(db, status=status, project_id=project_id, parent_goal_id=parent_goal_id)
    return goals[:limit]


@router.get("/{goal_id}", response_model=schemas.GoalOut)
def get_goal(goal_id: str, db: Session = Depends(get_db)):
    goal = goal_engine.get_goal(db, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


@router.patch("/{goal_id}", response_model=schemas.GoalOut)
def update_goal(goal_id: str, payload: schemas.GoalUpdate, db: Session = Depends(get_db)):
    try:
        goal = goal_engine.update_goal(db, goal_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


@router.post("/{goal_id}/approve", response_model=schemas.GoalOut)
def approve_goal(goal_id: str, db: Session = Depends(get_db)):
    try:
        goal = goal_engine.approve_goal(db, goal_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


@router.post("/{goal_id}/pause", response_model=schemas.GoalOut)
def pause_goal(goal_id: str, db: Session = Depends(get_db)):
    try:
        goal = goal_engine.pause_goal(db, goal_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


@router.post("/{goal_id}/abandon", response_model=schemas.GoalOut)
def abandon_goal(goal_id: str, payload: schemas.GoalAbandonRequest, db: Session = Depends(get_db)):
    if not payload.reason.strip():
        raise HTTPException(status_code=400, detail="A reason is required to abandon a goal.")
    try:
        goal = goal_engine.abandon_goal(db, goal_id, payload.reason.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


@router.get("/{goal_id}/progress", response_model=schemas.GoalProgressOut)
def get_goal_progress(goal_id: str, db: Session = Depends(get_db)):
    if goal_engine.get_goal(db, goal_id) is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    progress = goal_engine.compute_progress(db, goal_id)
    # Evidence-only auto-completion is a side effect of asking for progress —
    # never inferred from anything else, always re-derived from the same
    # evidence just computed.
    goal_engine.maybe_mark_achieved(db, goal_id)
    return progress


@router.post("/{goal_id}/review", response_model=schemas.GoalReviewOut)
def review_goal(goal_id: str, db: Session = Depends(get_db)):
    if goal_engine.get_goal(db, goal_id) is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal_engine.generate_review(db, schemas.GoalReviewRequest(goal_id=goal_id))
