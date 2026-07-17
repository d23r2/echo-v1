import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import memory_conflicts, schemas
from app.db import get_db
from app.models import MemoryCandidate, Project, Task, _now

router = APIRouter(prefix="/api/projects", tags=["projects"])
logger = logging.getLogger(__name__)

_VALID_STATUSES = {"active", "paused", "completed", "archived"}


def _queue_project_memory_candidate(db: Session, project: Project) -> None:
    """A new project is durable, decision-level information ("the user
    started X") worth Atlas knowing about — unlike individual tasks, which
    are too granular to be worth a memory candidate each. Best-effort only:
    never blocks project creation, and always goes through the existing
    review queue (see app/memory_candidates.py) rather than being saved to
    Atlas directly — nothing here is ever surfaced in the chat UI."""
    try:
        content = f"Started a project: {project.title}"
        if project.description:
            content += f" — {project.description}"
        conflicts = memory_conflicts.find_conflicts(
            db, content=content, memory_type="project", tags=["project"]
        )
        db.add(
            MemoryCandidate(
                content=content,
                epistemic_status="Inferred",
                memory_type="project",
                tags=["project", "auto-extracted"],
                confidence=0.6,
                source="project creation",
                conflict_with=[c.id for c in conflicts],
            )
        )
        db.commit()
    except Exception:
        logger.warning("Failed to queue memory candidate for new project", exc_info=True)
        db.rollback()


@router.post("", response_model=schemas.ProjectOut)
def create_project(payload: schemas.ProjectCreate, db: Session = Depends(get_db)):
    if not payload.title.strip():
        raise HTTPException(status_code=400, detail="Title is required")
    project = Project(
        title=payload.title.strip(),
        description=payload.description,
        priority=payload.priority,
        category=payload.category,
        tags=payload.tags,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    _queue_project_memory_candidate(db, project)
    return project


@router.get("", response_model=list[schemas.ProjectOut])
def list_projects(status: str | None = Query(None), db: Session = Depends(get_db)):
    """Active/paused/completed projects, most recently touched first, unless a
    specific status is requested. Archived projects are excluded by default —
    DELETE soft-archives rather than hard-deleting, so this keeps the normal
    list from silently accumulating dead projects."""
    query = db.query(Project)
    if status:
        if status not in _VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"Unknown status '{status}'")
        return query.filter(Project.status == status).order_by(Project.last_touched_at.desc()).all()
    return query.filter(Project.status != "archived").order_by(Project.last_touched_at.desc()).all()


@router.get("/{project_id}", response_model=schemas.ProjectDetailOut)
def get_project(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/{project_id}", response_model=schemas.ProjectOut)
def update_project(project_id: str, payload: schemas.ProjectUpdate, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if payload.title is not None:
        if not payload.title.strip():
            raise HTTPException(status_code=400, detail="Title cannot be empty")
        project.title = payload.title.strip()
    if payload.description is not None:
        project.description = payload.description
    if payload.status is not None:
        if payload.status not in _VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"Unknown status '{payload.status}'")
        project.status = payload.status
        if payload.status == "archived":
            project.archived_at = _now()
    if payload.priority is not None:
        project.priority = payload.priority
    if payload.category is not None:
        project.category = payload.category
    if payload.tags is not None:
        project.tags = payload.tags
    # ECHO Layer 1 (Phase 12) — lightweight project memory profile fields.
    reviewed = False
    if payload.objective is not None:
        project.objective = payload.objective
        reviewed = True
    if payload.constraints_json is not None:
        project.constraints_json = payload.constraints_json
        reviewed = True
    if payload.decisions_json is not None:
        project.decisions_json = payload.decisions_json
        reviewed = True
    if payload.blockers_json is not None:
        project.blockers_json = payload.blockers_json
        reviewed = True
    if reviewed:
        project.last_reviewed_at = _now()
    project.last_touched_at = _now()
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", response_model=schemas.ProjectOut)
def archive_project(project_id: str, db: Session = Depends(get_db)):
    """Soft-archive, never a hard delete — matches the never-lose-data
    posture used everywhere else in this app. The project's tasks are left
    untouched (still linked, still visible from the project detail page)."""
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    project.status = "archived"
    project.archived_at = _now()
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}/tasks", response_model=list[schemas.TaskOut])
def list_project_tasks(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    tasks = db.query(Task).filter(Task.project_id == project_id).order_by(Task.sort_order, Task.created_at).all()
    for task in tasks:
        task.project_title = project.title
    return tasks
