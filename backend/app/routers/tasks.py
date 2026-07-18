from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_db
from app.models import Goal, Project, Task, _now

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

_VALID_STATUSES = {"todo", "in_progress", "blocked", "done", "cancelled"}


def _attach_project_title(db: Session, tasks: list[Task]) -> list[Task]:
    project_ids = {t.project_id for t in tasks if t.project_id}
    if not project_ids:
        return tasks
    titles = {p.id: p.title for p in db.query(Project).filter(Project.id.in_(project_ids)).all()}
    for task in tasks:
        task.project_title = titles.get(task.project_id) if task.project_id else None
    return tasks


def _touch_project(db: Session, project_id: str | None) -> None:
    if not project_id:
        return
    project = db.get(Project, project_id)
    if project is not None:
        project.last_touched_at = _now()


@router.post("", response_model=schemas.TaskOut)
def create_task(payload: schemas.TaskCreate, db: Session = Depends(get_db)):
    if not payload.title.strip():
        raise HTTPException(status_code=400, detail="Title is required")
    if payload.project_id is not None and db.get(Project, payload.project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if payload.goal_id is not None and db.get(Goal, payload.goal_id) is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    task = Task(
        title=payload.title.strip(),
        description=payload.description,
        priority=payload.priority,
        project_id=payload.project_id,
        goal_id=payload.goal_id,
        due_at=payload.due_at,
        source_type=payload.source_type,
        source_id=payload.source_id,
        tags=payload.tags,
    )
    db.add(task)
    _touch_project(db, payload.project_id)
    db.commit()
    db.refresh(task)
    return _attach_project_title(db, [task])[0]


@router.get("", response_model=list[schemas.TaskOut])
def list_tasks(
    status: str | None = Query(None),
    project_id: str | None = Query(None),
    goal_id: str | None = Query(None),
    due_before: datetime | None = Query(None),
    due_after: datetime | None = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(Task)
    if status:
        if status not in _VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"Unknown status '{status}'")
        query = query.filter(Task.status == status)
    if project_id:
        query = query.filter(Task.project_id == project_id)
    if goal_id:
        query = query.filter(Task.goal_id == goal_id)
    if due_before:
        query = query.filter(Task.due_at.isnot(None), Task.due_at <= due_before)
    if due_after:
        query = query.filter(Task.due_at.isnot(None), Task.due_at >= due_after)
    tasks = query.order_by(Task.due_at.is_(None), Task.due_at.asc(), Task.sort_order).all()
    return _attach_project_title(db, tasks)


@router.get("/{task_id}", response_model=schemas.TaskOut)
def get_task(task_id: str, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return _attach_project_title(db, [task])[0]


@router.patch("/{task_id}", response_model=schemas.TaskOut)
def update_task(task_id: str, payload: schemas.TaskUpdate, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if payload.title is not None:
        if not payload.title.strip():
            raise HTTPException(status_code=400, detail="Title cannot be empty")
        task.title = payload.title.strip()
    if payload.description is not None:
        task.description = payload.description
    if payload.status is not None:
        if payload.status not in _VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"Unknown status '{payload.status}'")
        task.status = payload.status
        task.completed_at = _now() if payload.status == "done" else None
    if payload.priority is not None:
        task.priority = payload.priority
    if payload.project_id is not None:
        if db.get(Project, payload.project_id) is None:
            raise HTTPException(status_code=404, detail="Project not found")
        task.project_id = payload.project_id
    if "goal_id" in payload.model_fields_set:
        if payload.goal_id is not None and db.get(Goal, payload.goal_id) is None:
            raise HTTPException(status_code=404, detail="Goal not found")
        task.goal_id = payload.goal_id
    if payload.due_at is not None:
        task.due_at = payload.due_at
    if payload.tags is not None:
        task.tags = payload.tags
    if payload.sort_order is not None:
        task.sort_order = payload.sort_order
    _touch_project(db, task.project_id)
    db.commit()
    db.refresh(task)
    return _attach_project_title(db, [task])[0]


@router.post("/{task_id}/complete", response_model=schemas.TaskOut)
def complete_task(task_id: str, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    task.status = "done"
    task.completed_at = _now()
    _touch_project(db, task.project_id)
    db.commit()
    db.refresh(task)
    return _attach_project_title(db, [task])[0]


@router.delete("/{task_id}", response_model=schemas.TaskOut)
def cancel_task(task_id: str, db: Session = Depends(get_db)):
    """Soft-cancel, not a hard delete — same never-lose-data posture as
    Projects. A cancelled task stays queryable via ?status=cancelled."""
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    task.status = "cancelled"
    db.commit()
    db.refresh(task)
    return _attach_project_title(db, [task])[0]
