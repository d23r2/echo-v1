"""ECHO Action + Reliability Core v1 — Internal Plugin / Tool System.

Not a public marketplace, not third-party tool loading — an internal
registry over functions that already exist, same relationship
action_system.py has to its own handlers. Most tools here literally
delegate to action_system.py's handlers (search/create/summarize logic
lives in exactly one place) rather than duplicating them; this module adds
the tool-shaped wrapper (input/output schema metadata, its own risk/
confirmation flow) plus the two placeholder tools that don't belong in the
Action System (camera/voice foundations).
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models import Project, Task, ToolDefinition, ToolRun, _now
from app.services import action_system, permission_center

logger = logging.getLogger(__name__)

Handler = Callable[[Session, dict], dict]


@dataclass(frozen=True)
class ToolSpec:
    tool_name: str
    display_name: str
    description: str
    category: str
    handler: Handler
    risk_level: str = "low"
    requires_confirmation: bool = False
    permission_key: str | None = None
    input_schema: dict = field(default_factory=dict)


def _camera_capture_placeholder(db: Session, input: dict) -> dict:
    return {"available": False, "reason": "Camera/visual analysis is not configured yet — this is a v1 foundation placeholder."}


def _voice_input_placeholder(db: Session, input: dict) -> dict:
    return {"available": False, "reason": "Voice input runs entirely in the browser (Web Speech API) — there is nothing for the backend to do here. This tool exists as a registry placeholder for a future server-side STT adapter."}


def _handle_project_search(db: Session, input: dict) -> dict:
    """ECHO Layer 2D — fills a real gap the Tool Strategy Engine needs
    (context_router.py's "projects" ContextSource had no matching tool
    before this): a plain, read-only project lookup, same query-shape as
    the other read tools above."""
    query = (input.get("query") or "").strip()
    q = db.query(Project).filter(Project.status != "archived")
    if query:
        q = q.filter(Project.title.ilike(f"%{query}%"))
    projects = q.order_by(Project.last_touched_at.desc()).limit(10).all()
    return {"projects": [{"id": p.id, "title": p.title, "status": p.status, "priority": p.priority} for p in projects]}


def _handle_task_search(db: Session, input: dict) -> dict:
    """ECHO Layer 2D — same rationale as _handle_project_search() above,
    for the "tasks" ContextSource."""
    query = (input.get("query") or "").strip()
    q = db.query(Task).filter(Task.status != "done")
    if query:
        q = q.filter(Task.title.ilike(f"%{query}%"))
    tasks = q.order_by(Task.sort_order.asc()).limit(10).all()
    return {"tasks": [{"id": t.id, "title": t.title, "status": t.status, "due_at": t.due_at.isoformat() if t.due_at else None} for t in tasks]}


TOOLS: dict[str, ToolSpec] = {
    t.tool_name: t
    for t in [
        ToolSpec("atlas_search", "Atlas memory search", "Search Atlas memory.", "memory", action_system._handle_search_atlas, input_schema={"query": "str"}),
        ToolSpec(
            "previous_conversation_search",
            "Previous conversation search",
            "Search previous conversations.",
            "memory",
            action_system._handle_search_conversations,
            input_schema={"query": "str"},
        ),
        ToolSpec("library_search", "Library search", "Search Library files.", "library", action_system._handle_summarize_file, permission_key="file_read", input_schema={"library_item_id": "str"}),
        ToolSpec("wiki_search", "Wikipedia search", "Search Wikipedia.", "web", action_system._handle_search_wiki, permission_key="wiki_search", input_schema={"query": "str"}),
        ToolSpec("rss_search", "RSS search", "Search configured RSS feeds.", "web", action_system._handle_search_rss, permission_key="rss_search", input_schema={"query": "str"}),
        ToolSpec("web_search", "Web search", "Search the web via SearXNG.", "web", action_system._handle_search_web, permission_key="web_search", input_schema={"query": "str"}),
        ToolSpec("create_task", "Create task", "Create a new task.", "task", action_system._handle_create_task, permission_key="action_create_task", input_schema={"title": "str"}),
        ToolSpec("create_project", "Create project", "Create a new project.", "project", action_system._handle_create_project, permission_key="action_create_project", input_schema={"title": "str"}),
        ToolSpec(
            "create_schedule_item", "Create schedule item", "Add a reminder/schedule item.", "schedule", action_system._handle_add_reminder, permission_key="action_schedule_reminder", input_schema={"title": "str"}
        ),
        ToolSpec("create_knowledge_item", "Create knowledge item", "Create a Knowledge Vault note.", "report", action_system._handle_create_knowledge_note, input_schema={"title": "str"}),
        ToolSpec(
            "summarize_conversation", "Summarize conversation", "Summarize a conversation.", "report", action_system._handle_create_conversation_summary, input_schema={"conversation_id": "str"}
        ),
        ToolSpec(
            "create_release_check",
            "Create release check",
            "Seed the standard release checklist.",
            "release",
            action_system._handle_run_release_checklist,
            risk_level="medium",
            permission_key="release_build_commands",
            input_schema={"release_id": "str"},
        ),
        ToolSpec("generate_claude_prompt", "Generate Claude Code prompt", "Prepare a structured Claude Code prompt.", "report", action_system._handle_prepare_claude_prompt, input_schema={"task_description": "str"}),
        ToolSpec(
            "camera_capture_placeholder",
            "Camera capture (placeholder)",
            "Foundation placeholder — camera capture is not implemented yet.",
            "camera",
            _camera_capture_placeholder,
            permission_key="camera_input",
        ),
        ToolSpec(
            "voice_input_placeholder",
            "Voice input (placeholder)",
            "Foundation placeholder — voice input runs client-side in the browser.",
            "voice",
            _voice_input_placeholder,
            permission_key="voice_input",
        ),
        ToolSpec("project_search", "Project search", "Search active projects by title.", "project", _handle_project_search, input_schema={"query": "str"}),
        ToolSpec("task_search", "Task search", "Search open tasks by title.", "task", _handle_task_search, input_schema={"query": "str"}),
    ]
}


def ensure_registered(db: Session) -> None:
    """Idempotent — upserts TOOLS into the tool_definitions table. Same
    rationale as action_system.ensure_registered()."""
    existing = {t.tool_name for t in db.query(ToolDefinition).all()}
    for tool in TOOLS.values():
        if tool.tool_name in existing:
            continue
        db.add(
            ToolDefinition(
                tool_name=tool.tool_name,
                display_name=tool.display_name,
                description=tool.description,
                category=tool.category,
                risk_level=tool.risk_level,
                requires_confirmation=tool.requires_confirmation,
                permission_key=tool.permission_key,
            )
        )
    db.commit()


def list_tools(db: Session) -> list[ToolDefinition]:
    ensure_registered(db)
    return db.query(ToolDefinition).order_by(ToolDefinition.category, ToolDefinition.tool_name).all()


def list_runs(db: Session, limit: int = 50) -> list[ToolRun]:
    return db.query(ToolRun).order_by(ToolRun.created_at.desc()).limit(limit).all()


def run_tool(db: Session, tool_name: str, input: dict, confirm: bool = False) -> ToolRun:
    ensure_registered(db)
    spec = TOOLS.get(tool_name)
    definition = db.query(ToolDefinition).filter(ToolDefinition.tool_name == tool_name).first()
    if spec is None or definition is None:
        raise ValueError(f"Unknown tool '{tool_name}'")

    if not definition.enabled:
        run = ToolRun(tool_name=tool_name, status="blocked", input_json=input, error_summary="This tool is currently disabled.")
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    permission_result = permission_center.check(db, spec.permission_key)
    if not permission_result.allowed:
        run = ToolRun(tool_name=tool_name, status="blocked", input_json=input, error_summary=permission_result.reason)
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    needs_confirmation = spec.risk_level in ("high", "destructive") or spec.requires_confirmation or (spec.risk_level == "medium" and permission_result.needs_confirmation)
    if needs_confirmation and not confirm:
        run = ToolRun(tool_name=tool_name, status="blocked", input_json=input, error_summary="This tool requires confirmation before it can run.")
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    run = ToolRun(tool_name=tool_name, status="running", input_json=input)
    db.add(run)
    db.commit()
    db.refresh(run)
    try:
        output = spec.handler(db, input)
        run.status = "completed"
        run.output_json = output
    except Exception as exc:  # noqa: BLE001 — every tool failure must degrade cleanly
        run.status = "failed"
        run.error_summary = action_system._clean_error(exc)
    run.completed_at = _now()
    db.commit()
    db.refresh(run)
    return run
