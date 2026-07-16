from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import schemas
from app.config import get_settings
from app.db import get_db
from app.image_router import image_router
from app.models import Conversation, LibraryItem, MemoryCandidate, Project, ScheduleItem, Task
from app.router import router as model_router

router = APIRouter(prefix="/api", tags=["mission-control"])

_ACTIVE_TASK_STATUSES = ("todo", "in_progress", "blocked")


def _day_bounds(now: datetime) -> tuple[datetime, datetime]:
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def _project_title_map(db: Session, tasks: list[Task]) -> dict[str, str]:
    project_ids = {t.project_id for t in tasks if t.project_id}
    if not project_ids:
        return {}
    return {p.id: p.title for p in db.query(Project).filter(Project.id.in_(project_ids)).all()}


def _with_titles(db: Session, tasks: list[Task]) -> list[Task]:
    titles = _project_title_map(db, tasks)
    for t in tasks:
        t.project_title = titles.get(t.project_id) if t.project_id else None
    return tasks


def _system_status(db: Session) -> schemas.SystemStatusOut:
    statuses = {s["name"]: s for s in model_router.statuses()}
    ollama_available = bool(statuses.get("ollama", {}).get("available"))
    settings = get_settings()
    wiki_enabled = bool(settings.wiki_search_enabled and settings.wiki_provider != "disabled")
    rss_enabled = bool(settings.rss_search_enabled and settings.rss_feed_url_list)
    searxng_enabled = bool(
        settings.web_search_enabled and settings.web_search_provider == "searxng" and settings.searxng_base_url
    )
    image_gen_active, _ = image_router.select_provider()
    return schemas.SystemStatusOut(
        ollama=ollama_available,
        wiki=wiki_enabled,
        rss=rss_enabled,
        searxng=searxng_enabled,
        image_generation=image_gen_active is not None,
    )


def _continue_suggestions(
    db: Session,
    overdue_tasks: list[Task],
    active_projects: list[Project],
    recent_conversations: list[Conversation],
    upcoming_schedule: list[ScheduleItem],
) -> list[schemas.ContinueSuggestion]:
    """Up to 5 suggestions built only from data actually stored — no
    fabricated facts. Priority order: overdue work first (most urgent),
    then in-progress tasks, then recently touched projects, then the most
    recent conversation, then the next upcoming schedule item."""
    suggestions: list[schemas.ContinueSuggestion] = []

    for task in overdue_tasks[:2]:
        suggestions.append(
            schemas.ContinueSuggestion(
                id=task.id,
                title=task.title,
                reason="Overdue task",
                source_type="task",
                source_id=task.id,
                action_label="Open task",
                created_at=task.created_at,
            )
        )

    if len(suggestions) < 5:
        in_progress = (
            db.query(Task)
            .filter(Task.status == "in_progress")
            .order_by(Task.updated_at.desc())
            .limit(5 - len(suggestions))
            .all()
        )
        for task in in_progress:
            suggestions.append(
                schemas.ContinueSuggestion(
                    id=task.id,
                    title=task.title,
                    reason="In progress",
                    source_type="task",
                    source_id=task.id,
                    action_label="Continue task",
                    created_at=task.updated_at,
                )
            )

    if len(suggestions) < 5:
        for project in active_projects[: 5 - len(suggestions)]:
            suggestions.append(
                schemas.ContinueSuggestion(
                    id=project.id,
                    title=project.title,
                    reason="Recently active project",
                    source_type="project",
                    source_id=project.id,
                    action_label="Open project",
                    created_at=project.last_touched_at,
                )
            )

    if len(suggestions) < 5 and recent_conversations:
        conv = recent_conversations[0]
        suggestions.append(
            schemas.ContinueSuggestion(
                id=conv.id,
                title=conv.title,
                reason="Recent conversation",
                source_type="conversation",
                source_id=conv.id,
                action_label="Resume chat",
                created_at=conv.created_at,
            )
        )

    if len(suggestions) < 5 and upcoming_schedule:
        item = upcoming_schedule[0]
        suggestions.append(
            schemas.ContinueSuggestion(
                id=item.id,
                title=item.title,
                reason="Upcoming reminder",
                source_type="schedule",
                source_id=item.id,
                action_label="Open schedule",
                created_at=item.created_at,
            )
        )

    return suggestions[:5]


@router.get("/mission-control", response_model=schemas.MissionControlOut)
def get_mission_control(db: Session = Depends(get_db)):
    """Aggregates today's tasks, overdue work, active projects, and recent
    activity into one dashboard payload. Each section is isolated in its own
    try/except: if one query fails, its list stays empty and a clean message
    is appended to `warnings` instead of the whole endpoint 500ing."""
    result = schemas.MissionControlOut()
    now = datetime.now(UTC)
    day_start, day_end = _day_bounds(now)

    try:
        overdue = (
            db.query(Task)
            .filter(Task.status.in_(_ACTIVE_TASK_STATUSES), Task.due_at.isnot(None), Task.due_at < now)
            .order_by(Task.due_at.asc())
            .all()
        )
        result.overdue_tasks = _with_titles(db, overdue)
    except Exception:
        result.warnings.append("Overdue tasks are temporarily unavailable.")
        overdue = []

    try:
        today = (
            db.query(Task)
            .filter(
                Task.status.in_(_ACTIVE_TASK_STATUSES),
                Task.due_at.isnot(None),
                Task.due_at >= day_start,
                Task.due_at < day_end,
            )
            .order_by(Task.due_at.asc())
            .all()
        )
        result.today_tasks = _with_titles(db, today)
    except Exception:
        result.warnings.append("Today's tasks are temporarily unavailable.")

    try:
        upcoming = (
            db.query(Task)
            .filter(Task.status.in_(_ACTIVE_TASK_STATUSES), Task.due_at.isnot(None), Task.due_at >= day_end)
            .order_by(Task.due_at.asc())
            .limit(10)
            .all()
        )
        result.upcoming_tasks = _with_titles(db, upcoming)
    except Exception:
        result.warnings.append("Upcoming tasks are temporarily unavailable.")

    active_projects: list[Project] = []
    try:
        active_projects = db.query(Project).filter(Project.status == "active").order_by(Project.last_touched_at.desc()).all()
        result.active_projects = active_projects
    except Exception:
        result.warnings.append("Active projects are temporarily unavailable.")

    try:
        result.recently_touched_projects = (
            db.query(Project).filter(Project.status != "archived").order_by(Project.last_touched_at.desc()).limit(5).all()
        )
    except Exception:
        result.warnings.append("Recently touched projects are temporarily unavailable.")

    recent_conversations: list[Conversation] = []
    try:
        recent_conversations = db.query(Conversation).order_by(Conversation.created_at.desc()).limit(5).all()
        result.recent_conversations = recent_conversations
    except Exception:
        result.warnings.append("Recent conversations are temporarily unavailable.")

    try:
        result.recent_library_files = db.query(LibraryItem).order_by(LibraryItem.created_at.desc()).limit(5).all()
    except Exception:
        result.warnings.append("Recent library files are temporarily unavailable.")

    upcoming_schedule: list[ScheduleItem] = []
    try:
        upcoming_schedule = (
            db.query(ScheduleItem)
            .filter(ScheduleItem.status == "pending")
            .order_by(ScheduleItem.due_at.is_(None), ScheduleItem.due_at.asc())
            .limit(5)
            .all()
        )
        result.upcoming_schedule_items = upcoming_schedule
    except Exception:
        result.warnings.append("Upcoming schedule items are temporarily unavailable.")

    try:
        result.pending_memory_candidates = (
            db.query(MemoryCandidate)
            .filter(MemoryCandidate.status == "pending")
            .order_by(MemoryCandidate.created_at.desc())
            .limit(5)
            .all()
        )
    except Exception:
        result.warnings.append("Pending memory candidates are temporarily unavailable.")

    try:
        result.system_status = _system_status(db)
    except Exception:
        result.warnings.append("System status is temporarily unavailable.")

    try:
        result.continue_where_left_off = _continue_suggestions(
            db, overdue, active_projects, recent_conversations, upcoming_schedule
        )
    except Exception:
        result.warnings.append("Continue Where We Left Off is temporarily unavailable.")

    return result
