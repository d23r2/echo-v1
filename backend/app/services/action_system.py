"""ECHO Action + Reliability Core v1 — Action System.

ECHO can safely *do* things, not just answer — but every action goes
through the same funnel: look up its risk_level + permission_key, ask the
Permission Center whether it's allowed, decide whether confirmation is
needed, and only then run a small, focused handler that reuses existing
services (never reimplements them). Destructive handlers only ever
soft-archive. Nothing here executes shell commands or writes files.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ActionDefinition, ActionRun, KnowledgeItem, Project, ScheduleItem, Task, _now
from app.services import identity_runtime, permission_center

logger = logging.getLogger(__name__)

Handler = Callable[[Session, dict], dict]


@dataclass(frozen=True)
class ActionSpec:
    name: str
    description: str
    category: str
    risk_level: str  # low | medium | high | destructive
    handler: Handler
    requires_confirmation: bool = False
    permission_key: str | None = None


def _clean_error(exc: Exception) -> str:
    """Never leak a raw stack trace, file path, or exception __repr__ into a
    result the user sees — ValueError is the one exception type this
    module's own handlers raise deliberately with an already-safe message;
    anything else degrades to a generic sentence."""
    if isinstance(exc, ValueError):
        return str(exc)
    logger.warning("Action handler raised an unexpected error", exc_info=True)
    return "This action couldn't be completed due to an internal error."


# ============================================================================
# Handlers — each takes (db, input) and returns a small, clean result dict.
# ============================================================================


def _handle_create_task(db: Session, input: dict) -> dict:
    title = (input.get("title") or "").strip()
    if not title:
        raise ValueError("A task title is required.")
    project_id = input.get("project_id")
    if project_id and db.get(Project, project_id) is None:
        raise ValueError("That project doesn't exist.")
    task = Task(
        title=title,
        description=input.get("description"),
        priority=input.get("priority", "medium"),
        project_id=project_id,
        source_type="action",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return {"task_id": task.id, "title": task.title, "status": task.status}


def _handle_update_task(db: Session, input: dict) -> dict:
    task_id = input.get("task_id")
    task = db.get(Task, task_id) if task_id else None
    if task is None:
        raise ValueError("That task doesn't exist.")
    if "status" in input and input["status"]:
        task.status = input["status"]
    if "title" in input and input["title"]:
        task.title = input["title"].strip()
    if "priority" in input and input["priority"]:
        task.priority = input["priority"]
    if "due_at" in input and input["due_at"]:
        task.due_at = input["due_at"]
    db.commit()
    return {"task_id": task.id, "title": task.title, "status": task.status}


def _handle_complete_task(db: Session, input: dict) -> dict:
    task_id = input.get("task_id")
    task = db.get(Task, task_id) if task_id else None
    if task is None:
        raise ValueError("That task doesn't exist.")
    task.status = "done"
    task.completed_at = _now()
    db.commit()
    return {"task_id": task.id, "title": task.title, "status": task.status}


def _handle_create_project(db: Session, input: dict) -> dict:
    title = (input.get("title") or "").strip()
    if not title:
        raise ValueError("A project title is required.")
    project = Project(
        title=title, description=input.get("description"), priority=input.get("priority", "medium"), category=input.get("category")
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return {"project_id": project.id, "title": project.title, "status": project.status}


def _handle_add_reminder(db: Session, input: dict) -> dict:
    title = (input.get("title") or "").strip()
    if not title:
        raise ValueError("A reminder title is required.")
    item = ScheduleItem(title=title, description=input.get("description"), due_at=input.get("due_at"))
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"schedule_item_id": item.id, "title": item.title, "due_at": item.due_at.isoformat() if item.due_at else None}


def _handle_summarize_file(db: Session, input: dict) -> dict:
    from pathlib import Path

    from app import attachments
    from app.config import get_settings
    from app.models import LibraryItem
    from app.providers.base import ChatMessage
    from app.services import identity_context, persona_service
    from app.services.local_model_router import LocalModelRouter

    item_id = input.get("library_item_id")
    item = db.get(LibraryItem, item_id) if item_id else None
    if item is None:
        raise ValueError("That Library item doesn't exist.")
    settings = get_settings()
    path = Path(item.file_path)
    try:
        resolved = path.resolve()
        resolved.relative_to(Path(settings.attachments_dir).resolve())
    except (ValueError, OSError) as exc:
        raise ValueError("That file can't be read.") from exc
    if not resolved.is_file():
        raise ValueError("That file no longer exists on disk.")
    content = resolved.read_bytes()
    mime = attachments.guess_mime_type(resolved.name, None)
    text = attachments.extract_text_for_prompt(resolved.name, mime, content)
    if not text:
        return {"library_item_id": item.id, "title": item.title, "summary": None, "note": "This file type can't be summarized (not text/PDF/code)."}

    router = LocalModelRouter()
    identity_section, _identity_brief = identity_context.build_identity_prompt_section(
        db, "document_analysis"
    )
    persona_section, _persona_brief, resolved_persona = (
        persona_service.build_persona_prompt_section(
            db,
            "Summarize this document.",
            context_type="document_analysis",
        )
    )
    system_prompt = "Summarize the following document in 3-5 concise sentences. No preamble, no internal notes."
    trusted_context = "\n\n".join(
        section for section in (identity_section, persona_section) if section
    )
    if trusted_context:
        system_prompt = f"{trusted_context}\n\n{system_prompt}"
    result = router.call(
        "fast",
        system_prompt,
        [ChatMessage(role="user", content=text)],
    )
    if not result.ok:
        return {"library_item_id": item.id, "title": item.title, "summary": None, "note": "Local model unavailable — couldn't generate a summary right now."}
    summary_text = result.text
    if resolved_persona is not None:
        summary_text = persona_service.validate_response_style(
            summary_text, resolved_persona
        ).text
    return {"library_item_id": item.id, "title": item.title, "summary": summary_text.strip()}


def _handle_search_web(db: Session, input: dict) -> dict:
    from app import web_search

    query = (input.get("query") or "").strip()
    if not query:
        raise ValueError("A search query is required.")
    outcome = web_search.searxng_search(query)
    return {"query": query, "results": [{"title": r.title, "url": r.url, "snippet": r.snippet} for r in outcome.results], "failure_reason": outcome.failure_reason}


def _handle_search_wiki(db: Session, input: dict) -> dict:
    from app import web_search

    query = (input.get("query") or "").strip()
    if not query:
        raise ValueError("A search query is required.")
    outcome = web_search.wiki_search(query)
    return {"query": query, "results": [{"title": r.title, "url": r.url, "snippet": r.snippet} for r in outcome.results], "failure_reason": outcome.failure_reason}


def _handle_search_rss(db: Session, input: dict) -> dict:
    from app import web_search

    query = (input.get("query") or "").strip()
    if not query:
        raise ValueError("A search query is required.")
    outcome = web_search.rss_search(query)
    return {"query": query, "results": [{"title": r.title, "url": r.url, "feed_title": r.feed_title} for r in outcome.results], "failure_reason": outcome.failure_reason}


def _handle_search_conversations(db: Session, input: dict) -> dict:
    from app import conversation_search

    query = (input.get("query") or "").strip()
    if not query:
        raise ValueError("A search query is required.")
    snippets = conversation_search.search_previous_conversations(db, query, top_k=input.get("top_k", 4))
    return {"query": query, "results": [{"conversation_title": s.conversation_title, "role": s.role, "snippet": s.snippet} for s in snippets]}


def _handle_search_atlas(db: Session, input: dict) -> dict:
    from app import atlas

    query = (input.get("query") or "").strip()
    if not query:
        raise ValueError("A search query is required.")
    hits = atlas.search(db, query, top_k=input.get("top_k", 5))
    return {"query": query, "results": [{"content": e.content, "epistemic_status": e.epistemic_status, "confidence": e.confidence} for e, _dist in hits]}


def _handle_generate_report(db: Session, input: dict) -> dict:
    active_projects = db.query(Project).filter(Project.status == "active").count()
    open_tasks = db.query(Task).filter(Task.status.in_(["todo", "in_progress", "blocked"])).count()
    upcoming = db.query(ScheduleItem).filter(ScheduleItem.status == "pending").count()
    return {
        "active_projects": active_projects,
        "open_tasks": open_tasks,
        "upcoming_reminders": upcoming,
        "summary": f"{active_projects} active project(s), {open_tasks} open task(s), {upcoming} upcoming reminder(s).",
    }


def _handle_prepare_claude_prompt(db: Session, input: dict) -> dict:
    task_description = (input.get("task_description") or "").strip()
    if not task_description:
        raise ValueError("A task description is required.")
    context = (input.get("context") or "").strip()
    prompt = (
        f"# Task\n{task_description}\n\n"
        + (f"# Context\n{context}\n\n" if context else "")
        + "# Instructions\n"
        "- Inspect the relevant code before editing.\n"
        "- Keep changes scoped to what this task actually needs.\n"
        "- Run the existing test suite after changes.\n"
        "- Report what changed and what was verified.\n"
    )
    return {"prompt": prompt}


def _handle_run_release_checklist(db: Session, input: dict) -> dict:
    from app.services import release_manager

    release_id = input.get("release_id")
    if not release_id:
        raise ValueError("A release_id is required.")
    checks = release_manager.seed_standard_checklist(db, release_id)
    return {"release_id": release_id, "checks_added": len(checks)}


def _handle_create_knowledge_note(db: Session, input: dict) -> dict:
    from app.services import knowledge_vault

    title = (input.get("title") or "").strip()
    if not title:
        raise ValueError("A title is required.")
    item = knowledge_vault.create_item(
        db,
        title=title,
        body=input.get("body", ""),
        item_type=input.get("item_type", "note"),
        tags=input.get("tags", []),
    )
    return {"knowledge_item_id": item.id, "title": item.title}


def _handle_create_conversation_summary(db: Session, input: dict) -> dict:
    from app.services import conversation_summary

    conversation_id = input.get("conversation_id")
    if not conversation_id:
        raise ValueError("A conversation_id is required.")
    summary = conversation_summary.summarize_conversation(db, conversation_id)
    if summary is None:
        raise ValueError("That conversation doesn't exist or has no messages yet.")
    return {"summary_id": summary.id, "title": summary.title, "summary": summary.summary}


def _handle_delete_archive_data(db: Session, input: dict) -> dict:
    """Generic soft-archive for the item types this app already treats as
    archivable — never a hard delete, regardless of confirmation."""
    kind = input.get("kind")
    item_id = input.get("id")
    if kind == "project":
        row = db.get(Project, item_id)
        if row is None:
            raise ValueError("That project doesn't exist.")
        row.status = "archived"
        row.archived_at = _now()
    elif kind == "knowledge_item":
        row = db.get(KnowledgeItem, item_id)
        if row is None:
            raise ValueError("That knowledge item doesn't exist.")
        row.archived_at = _now()
    else:
        raise ValueError("Unsupported kind — expected 'project' or 'knowledge_item'.")
    db.commit()
    return {"kind": kind, "id": item_id, "archived": True}


def _handle_selfmod_propose(db: Session, input: dict) -> dict:
    """Model-callable only for proposal metadata; never accepts/applies a patch."""
    from app.services import self_modification_governance as governance

    proposal = governance.create_proposal(
        db,
        title=input.get("title") or "",
        description=input.get("description") or "",
        rationale=input.get("rationale") or "",
        proposed_by="echo",
    )
    return {"proposal_id": proposal.id, "status": proposal.status}


def _handle_selfmod_sandbox(db: Session, input: dict) -> dict:
    from app.services import self_modification_governance as governance

    proposal_id = input.get("proposal_id")
    if not proposal_id:
        raise ValueError("A proposal_id is required.")
    execution = governance.run_sandbox(db, proposal_id, confirmed=True)
    return {"proposal_id": proposal_id, "execution_id": execution.id, "status": execution.status}


def _handle_selfmod_request_review(db: Session, input: dict) -> dict:
    from app.services import self_modification_governance as governance

    proposal_id = input.get("proposal_id")
    if not proposal_id:
        raise ValueError("A proposal_id is required.")
    proposal = governance.request_review(db, proposal_id)
    return {"proposal_id": proposal.id, "status": proposal.status}


def _handle_selfmod_deploy(db: Session, input: dict) -> dict:
    from app.services import self_modification_governance as governance

    proposal_id = input.get("proposal_id")
    if not proposal_id:
        raise ValueError("A proposal_id is required.")
    attempt = governance.deploy(db, proposal_id, confirmed=True)
    return {
        "proposal_id": proposal_id,
        "deployment_attempt_id": attempt.id,
        "status": attempt.status,
        "branch_name": attempt.branch_name,
    }


def _handle_selfmod_rollback(db: Session, input: dict) -> dict:
    from app.services import self_modification_governance as governance

    proposal_id = input.get("proposal_id")
    reason = (input.get("reason") or "").strip()
    if not proposal_id or not reason:
        raise ValueError("proposal_id and reason are required.")
    event = governance.rollback(db, proposal_id, reason=reason)
    return {"proposal_id": proposal_id, "rollback_event_id": event.id, "status": event.status}


# ============================================================================
# Registry
# ============================================================================

ACTIONS: dict[str, ActionSpec] = {
    a.name: a
    for a in [
        ActionSpec("create_task", "Create a new task.", "task", "low", _handle_create_task, permission_key="action_create_task"),
        ActionSpec("update_task", "Update an existing task.", "task", "medium", _handle_update_task, permission_key="action_update_task"),
        ActionSpec("complete_task", "Mark a task as done.", "task", "low", _handle_complete_task, permission_key="action_update_task"),
        ActionSpec("create_project", "Create a new project.", "project", "low", _handle_create_project, permission_key="action_create_project"),
        ActionSpec("add_reminder", "Add a reminder/schedule item.", "schedule", "low", _handle_add_reminder, permission_key="action_schedule_reminder"),
        ActionSpec("summarize_file", "Summarize a Library file using the local model.", "library", "medium", _handle_summarize_file, permission_key="file_read"),
        ActionSpec("search_web", "Search the web via SearXNG.", "web", "low", _handle_search_web, permission_key="web_search"),
        ActionSpec("search_wiki", "Search Wikipedia.", "web", "low", _handle_search_wiki, permission_key="wiki_search"),
        ActionSpec("search_rss", "Search configured RSS feeds.", "web", "low", _handle_search_rss, permission_key="rss_search"),
        ActionSpec("search_previous_conversations", "Search previous conversations.", "memory", "low", _handle_search_conversations),
        ActionSpec("search_atlas_memory", "Search Atlas memory.", "memory", "low", _handle_search_atlas),
        ActionSpec("generate_report", "Generate a quick status report.", "report", "low", _handle_generate_report),
        ActionSpec("prepare_claude_code_prompt", "Prepare a structured Claude Code prompt.", "report", "low", _handle_prepare_claude_prompt),
        ActionSpec(
            "run_release_checklist",
            "Seed the standard release checklist onto a release record.",
            "release",
            "medium",
            _handle_run_release_checklist,
            permission_key="release_build_commands",
        ),
        ActionSpec("create_knowledge_note", "Create a Knowledge Vault note.", "report", "low", _handle_create_knowledge_note),
        ActionSpec("create_conversation_summary", "Summarize a conversation.", "report", "low", _handle_create_conversation_summary),
        ActionSpec(
            "delete_archive_data",
            "Soft-archive a project or knowledge item. Never a hard delete.",
            "system",
            "destructive",
            _handle_delete_archive_data,
            requires_confirmation=True,
            permission_key="delete_archive_data",
        ),
        ActionSpec(
            "self_modification_propose",
            "Create a proposal record with structured engineering rationale; never applies code.",
            "governance",
            "low",
            _handle_selfmod_propose,
            permission_key="self_modification_propose",
        ),
        ActionSpec(
            "self_modification_sandbox_run",
            "Run the active exact patch through the isolated, allowlisted sandbox checks.",
            "governance",
            "high",
            _handle_selfmod_sandbox,
            requires_confirmation=True,
            permission_key="self_modification_sandbox_run",
        ),
        ActionSpec(
            "self_modification_request_review",
            "Move a sandbox-passed proposal to explicit human review.",
            "governance",
            "medium",
            _handle_selfmod_request_review,
            requires_confirmation=True,
            permission_key="self_modification_propose",
        ),
        ActionSpec(
            "self_modification_deploy",
            "Apply an approved exact patch only to a new isolated local branch; never merge or push.",
            "governance",
            "destructive",
            _handle_selfmod_deploy,
            requires_confirmation=True,
            permission_key="self_modification_deploy",
        ),
        ActionSpec(
            "self_modification_rollback",
            "Remove the isolated local deployment worktree and branch.",
            "governance",
            "high",
            _handle_selfmod_rollback,
            requires_confirmation=True,
            permission_key="self_modification_rollback",
        ),
    ]
}


# ============================================================================
# Orchestration
# ============================================================================


def ensure_registered(db: Session) -> None:
    """Idempotent — upserts ACTIONS into the action_definitions table. Called
    by db.py's init_db() at real startup, and directly by tests that use the
    isolated db_session fixture (which only runs Base.metadata.create_all,
    not init_db()'s seeding)."""
    existing = {a.name for a in db.query(ActionDefinition).all()}
    for action in ACTIONS.values():
        if action.name in existing:
            continue
        db.add(
            ActionDefinition(
                name=action.name,
                description=action.description,
                category=action.category,
                risk_level=action.risk_level,
                requires_confirmation=action.requires_confirmation,
                requires_permission_key=action.permission_key,
            )
        )
    db.commit()


def list_actions(db: Session) -> list[ActionDefinition]:
    ensure_registered(db)
    return db.query(ActionDefinition).order_by(ActionDefinition.category, ActionDefinition.name).all()


def list_runs(db: Session, limit: int = 50) -> list[ActionRun]:
    return db.query(ActionRun).order_by(ActionRun.created_at.desc()).limit(limit).all()


def get_run(db: Session, run_id: str) -> ActionRun | None:
    return db.get(ActionRun, run_id)


def _needs_confirmation(spec: ActionSpec, definition: ActionDefinition, permission_result: permission_center.PermissionCheck) -> bool:
    if spec.risk_level == "destructive":
        return True
    if spec.risk_level == "high":
        return True
    if spec.risk_level == "medium":
        # "requires confirmation unless user setting allows" — the Permission
        # Center entry being explicitly "allowed" is that override.
        return permission_result.needs_confirmation or definition.requires_confirmation
    return definition.requires_confirmation


def _identity_requires_confirmation(db: Session, spec: ActionSpec) -> bool:
    """Part 2B fail-safe for consequential (medium+) actions.

    Low-risk local workflows keep ordinary degraded availability. When the
    dynamic identity cannot be verified, a consequential action may still
    proceed only through the Action System's existing explicit-confirmation
    lifecycle; no new consent or moral-policy engine is introduced here.
    """
    if spec.risk_level == "low" or not get_settings().core_identity_v1_enabled:
        return False
    snapshot = identity_runtime.get_active_identity_snapshot(db)
    try:
        identity_runtime.require_verified_identity_for_consequential_action(snapshot)
    except identity_runtime.ConsequentialIdentityUnavailableError:
        return True
    return False


def run_action(db: Session, action_name: str, input: dict, confirm: bool = False) -> ActionRun:
    ensure_registered(db)
    spec = ACTIONS.get(action_name)
    definition = db.query(ActionDefinition).filter(ActionDefinition.name == action_name).first()
    if spec is None or definition is None:
        raise ValueError(f"Unknown action '{action_name}'")
    if not definition.enabled:
        run = ActionRun(action_name=action_name, status="cancelled", risk_level=spec.risk_level, input_json=input, error_summary="This action is currently disabled.")
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    permission_result = permission_center.check(db, spec.permission_key)
    if not permission_result.allowed:
        run = ActionRun(action_name=action_name, status="cancelled", risk_level=spec.risk_level, input_json=input, error_summary=permission_result.reason)
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    identity_confirmation = _identity_requires_confirmation(db, spec)
    needs_confirmation = _needs_confirmation(spec, definition, permission_result) or identity_confirmation

    if needs_confirmation and not confirm:
        run = ActionRun(
            action_name=action_name,
            status="pending",
            risk_level=spec.risk_level,
            input_json=input,
            user_confirmed=False,
            error_summary=(
                "Core identity verification is degraded; explicit confirmation is required."
                if identity_confirmation
                else None
            ),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    run = ActionRun(
        action_name=action_name,
        status="running",
        risk_level=spec.risk_level,
        input_json=input,
        user_confirmed=confirm or not needs_confirmation,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        result = spec.handler(db, input)
        run.status = "completed"
        run.result_json = result
    except Exception as exc:  # noqa: BLE001 — deliberately broad: every handler failure must degrade cleanly
        run.status = "failed"
        run.error_summary = _clean_error(exc)
    run.completed_at = _now()
    db.commit()
    db.refresh(run)
    return run


def approve_run(db: Session, run_id: str) -> ActionRun:
    """Re-runs the same pending ActionRun row (not a new one) now that the
    user has confirmed it — keeps one ActionRun id per user-visible approval
    click instead of spawning a second row."""
    run = db.get(ActionRun, run_id)
    if run is None:
        raise ValueError("That action run doesn't exist.")
    if run.status != "pending":
        raise ValueError(f"Only pending action runs can be approved (this one is '{run.status}').")
    spec = ACTIONS.get(run.action_name)
    if spec is None:
        run.status = "failed"
        run.error_summary = "This action is no longer available."
        db.commit()
        db.refresh(run)
        return run
    run.status = "running"
    run.user_confirmed = True
    run.error_summary = None
    db.commit()
    try:
        result = spec.handler(db, run.input_json)
        run.status = "completed"
        run.result_json = result
    except Exception as exc:  # noqa: BLE001
        run.status = "failed"
        run.error_summary = _clean_error(exc)
    run.completed_at = _now()
    db.commit()
    db.refresh(run)
    return run


def cancel_run(db: Session, run_id: str) -> ActionRun:
    run = db.get(ActionRun, run_id)
    if run is None:
        raise ValueError("That action run doesn't exist.")
    if run.status not in ("pending",):
        raise ValueError(f"Only pending action runs can be cancelled (this one is '{run.status}').")
    run.status = "cancelled"
    run.completed_at = _now()
    db.commit()
    db.refresh(run)
    return run
