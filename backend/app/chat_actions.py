"""Deterministic parser for a small set of explicit chat commands that map
directly onto Projects/Tasks actions (ECHO Personal OS v1, Phase 9) —
bypassing the model entirely, no guessing. Regex-only, same style as
app/search_intent.py: a message either matches one exact pattern and the
action runs immediately, or it doesn't match anything here and falls
through to normal chat unchanged.

Deliberately conservative: no delete/archive commands are exposed through
chat at all (only create-project, add-task, mark-task-done, and two
read-only summaries) — anything destructive stays a UI-only action per the
"ask confirmation for destructive actions" rule, and the smaller safe
command set avoids that question entirely for v1. Ambiguous matches (e.g.
"mark task X done" matching more than one task) are reported back rather
than guessed at.
"""

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app import human_persona
from app.models import Conversation, Project, Task, _now

_ACTIVE_TASK_STATUSES = ("todo", "in_progress", "blocked")


@dataclass(frozen=True)
class ActionResult:
    response_text: str
    action_type: str
    target_id: str | None = None


_ADD_TASK_TO_PROJECT = re.compile(r"^add (?:a )?task to (.+?) called (.+)$", re.IGNORECASE)
_CREATE_PROJECT = re.compile(r"^create a project(?: (?:called|named))? (.+)$", re.IGNORECASE)
_MARK_TASK_DONE = re.compile(r"^mark task (.+?) (?:as )?done$", re.IGNORECASE)
_ADD_TASK = re.compile(r"^add (?:a )?task(?: (?:called|named))? (.+)$", re.IGNORECASE)
_SHOW_TASKS_TODAY = re.compile(
    r"^show (?:my )?tasks(?: for)? today$|^what tasks (?:do i have |are due )?today\??$", re.IGNORECASE
)
_SHOW_ACTIVE_PROJECTS = re.compile(
    r"^show (?:my )?active projects$|^what projects are active\??$", re.IGNORECASE
)
_CONTINUE = re.compile(r"^continue where (?:we|i)(?:'d| had|'ve| have)? left off$", re.IGNORECASE)


def try_handle_action(db: Session, message: str, tester_id: str = "default") -> ActionResult | None:
    """Never raises. Returns None for anything that isn't an exact command
    match — the caller should proceed with normal chat in that case."""
    text = message.strip()
    if not text:
        return None

    m = _ADD_TASK_TO_PROJECT.match(text)
    if m:
        return _add_task_to_project(db, project_name=m.group(1).strip(), title=m.group(2).strip())

    m = _CREATE_PROJECT.match(text)
    if m:
        return _create_project(db, m.group(1).strip())

    m = _MARK_TASK_DONE.match(text)
    if m:
        return _mark_task_done(db, m.group(1).strip())

    m = _ADD_TASK.match(text)
    if m:
        return _add_task(db, m.group(1).strip())

    if _SHOW_TASKS_TODAY.match(text):
        return _show_tasks_today(db)

    if _SHOW_ACTIVE_PROJECTS.match(text):
        return _show_active_projects(db)

    if _CONTINUE.match(text):
        return _continue_where_left_off(db, tester_id)

    return None


def _create_project(db: Session, title: str) -> ActionResult:
    if not title:
        return ActionResult("Which project would you like me to create?", "create_project_missing_title")
    project = Project(title=title)
    db.add(project)
    db.commit()
    db.refresh(project)
    return ActionResult(f"Created project \"{project.title}\".", "create_project", project.id)


def _find_project_by_name(db: Session, name: str) -> Project | None:
    return (
        db.query(Project)
        .filter(Project.status != "archived", Project.title.ilike(name))
        .first()
    )


def _add_task_to_project(db: Session, project_name: str, title: str) -> ActionResult:
    if not title:
        return ActionResult("What should the task be called?", "add_task_missing_title")
    project = _find_project_by_name(db, project_name)
    if project is None:
        return ActionResult(
            f"I couldn't find a project called \"{project_name}\". Create it first, "
            "or check the exact project name in Projects.",
            "add_task_project_not_found",
        )
    task = Task(title=title, project_id=project.id, source_type="chat")
    db.add(task)
    project.last_touched_at = _now()
    db.commit()
    db.refresh(task)
    return ActionResult(f"Added task \"{task.title}\" to project \"{project.title}\".", "add_task_to_project", task.id)


def _add_task(db: Session, title: str) -> ActionResult:
    if not title:
        return ActionResult("What should the task be called?", "add_task_missing_title")
    task = Task(title=title, source_type="chat")
    db.add(task)
    db.commit()
    db.refresh(task)
    return ActionResult(f"Added task \"{task.title}\".", "add_task", task.id)


def _mark_task_done(db: Session, title: str) -> ActionResult:
    matches = (
        db.query(Task)
        .filter(Task.status.in_(_ACTIVE_TASK_STATUSES), Task.title.ilike(title))
        .all()
    )
    if not matches:
        return ActionResult(f"I couldn't find an open task called \"{title}\".", "mark_task_done_not_found")
    if len(matches) > 1:
        return ActionResult(
            f"I found more than one open task called \"{title}\" — please mark it done from Tasks instead.",
            "mark_task_done_ambiguous",
        )
    task = matches[0]
    task.status = "done"
    task.completed_at = _now()
    db.commit()
    return ActionResult(f"Marked \"{task.title}\" as done.", "mark_task_done", task.id)


def _show_tasks_today(db: Session) -> ActionResult:
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    tasks = (
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
    if not tasks:
        return ActionResult("No tasks due today.", "show_tasks_today")
    lines = "\n".join(f"- {t.title}" for t in tasks)
    return ActionResult(f"Tasks due today:\n{lines}", "show_tasks_today")


def _show_active_projects(db: Session) -> ActionResult:
    projects = db.query(Project).filter(Project.status == "active").order_by(Project.last_touched_at.desc()).all()
    if not projects:
        return ActionResult("No active projects yet. Create one to get started.", "show_active_projects")
    lines = "\n".join(f"- {p.title}" for p in projects)
    return ActionResult(f"Active projects:\n{lines}", "show_active_projects")


def _continue_where_left_off(db: Session, tester_id: str) -> ActionResult:
    overdue = (
        db.query(Task)
        .filter(Task.status.in_(_ACTIVE_TASK_STATUSES), Task.due_at.isnot(None))
        .order_by(Task.due_at.asc())
        .limit(3)
        .all()
    )
    projects = db.query(Project).filter(Project.status == "active").order_by(Project.last_touched_at.desc()).limit(3).all()
    # Phase 12: recent conversation threads, real content only (topic/summary
    # are the conversation's own title/last exchange — never a fabricated
    # next step, see human_persona.upsert_thread_state).
    threads = human_persona.get_recent_thread_states(db, tester_id, exclude_conversation_id=None, limit=2)

    if not overdue and not projects and not threads:
        return ActionResult("No active work yet. Create a project or task to begin.", "continue_where_left_off")

    lines: list[str] = []
    for t in overdue:
        lines.append(f"- Task: {t.title}")
    for p in projects:
        lines.append(f"- Project: {p.title}")
    for th in threads:
        lines.append(f"- Conversation: {th.topic}")
    return ActionResult("Here's where you left off:\n" + "\n".join(lines), "continue_where_left_off")


# ---- ECHO Human Persona Layer v1: mode-switch / session-style commands ----
# Deliberately separate from try_handle_action() above (different concern —
# these mutate the current Conversation row's session state rather than
# Projects/Tasks) but tried the same way: exact deterministic match or fall
# through to normal chat unchanged. Both are style-only — neither can touch
# the Constitution/Character Code.

_MODE_LABELS = {
    "normal": "Normal",
    "coding_assistant": "Coding Assistant",
    "research": "Research",
    "planning": "Planning",
    "low_energy_support": "Low-Energy Support",
    "strict_coach": "Strict Coach",
    "study_tutor": "Study Tutor",
    "release_testing": "Release Testing",
    "troubleshooting": "Troubleshooting",
    "quick_answer": "Quick Answer",
}


def try_handle_persona_action(
    db: Session, conversation: Conversation, tester_id: str, message: str
) -> ActionResult | None:
    """Handles "switch to X mode" and "keep replies short/detailed today"
    style commands — updates the conversation's session-only state and
    returns a short confirmation, same pattern as try_handle_action(). Never
    touches RelationshipProfile or any permanent tester data unless the
    message explicitly asks to remember the mode as default."""
    text = message.strip()
    if not text:
        return None

    mode_switch = human_persona.detect_mode_switch(text)
    if mode_switch is not None:
        conversation.active_operational_mode = mode_switch.mode
        label = _MODE_LABELS.get(mode_switch.mode, mode_switch.mode)
        note = ""
        if mode_switch.remember_as_default:
            settings = human_persona.get_or_create_persona_settings(db, tester_id)
            settings.default_operational_mode = mode_switch.mode
            note = " and set as your default"
        db.commit()
        return ActionResult(f"Switched to {label} mode for this conversation{note}.", "mode_switch")

    style_override = human_persona.detect_session_style_directive(text)
    if style_override is not None:
        merged = {**(conversation.session_style_override or {}), **style_override}
        conversation.session_style_override = merged
        db.commit()
        length = style_override["length"]
        confirmation = (
            "Got it — I'll keep replies short for the rest of this conversation."
            if length == "short"
            else "Got it — I'll go into more detail for the rest of this conversation."
        )
        return ActionResult(confirmation, "session_style_override")

    return None
