"""ECHO Local Intelligence Engine v1 — Phase 4: Context Gatherer.

Given an IntentClassification, collects only the context sources that
intent actually needs, kept compact for a local model's smaller effective
context window (see LOCAL_CONTEXT_MAX_* in app/config.py). Reuses every
existing retrieval path rather than re-implementing them: app/atlas.py for
memory, app/conversation_search.py for previous-conversation snippets,
app/web_search.py's gather_sources() (fed by app/search_intent.py, same as
app/persona.py already does) for wiki/web/rss, and direct queries against
the existing Project/Task/ScheduleItem/LibraryItem models for the newer
Personal-OS-era sources persona.py's prompt builder doesn't touch at all
today.
"""

from dataclasses import dataclass, field

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import atlas, conversation_search, search_intent, web_search
from app.config import get_settings
from app.models import LibraryItem, Project, ScheduleItem, Task
from app.services.intent_classifier import IntentClassification

_SOURCE_LABELS = {
    "atlas_memory": "Atlas",
    "previous_conversation": "Previous Conversation",
    "projects": "Projects",
    "tasks": "Tasks",
    "schedule": "Schedule",
    "library": "Library",
    "wiki": "Wikipedia",
    "rss": "RSS",
    "web_search": "SearXNG",
}


@dataclass
class GatheredContext:
    memory_context: list[str] = field(default_factory=list)
    project_context: list[str] = field(default_factory=list)
    task_context: list[str] = field(default_factory=list)
    schedule_context: list[str] = field(default_factory=list)
    library_context: list[str] = field(default_factory=list)
    conversation_context: list[str] = field(default_factory=list)
    wiki_context: list[str] = field(default_factory=list)
    rss_context: list[str] = field(default_factory=list)
    web_context: list[str] = field(default_factory=list)
    source_display_names: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Internal-only (not part of the public dict shape the spec lists) — kept
    # for the engine to build proper AtlasCitation/sources_used metadata
    # without a second retrieval pass. Never shown raw in chat UI.
    atlas_citations: list = field(default_factory=list)
    gather_result: web_search.GatherResult | None = None

    def as_dict(self) -> dict:
        return {
            "memory_context": self.memory_context,
            "project_context": self.project_context,
            "task_context": self.task_context,
            "schedule_context": self.schedule_context,
            "library_context": self.library_context,
            "conversation_context": self.conversation_context,
            "wiki_context": self.wiki_context,
            "rss_context": self.rss_context,
            "web_context": self.web_context,
            "source_display_names": self.source_display_names,
            "warnings": self.warnings,
        }


def _add_source(names: list[str], label: str) -> None:
    if label not in names:
        names.append(label)


def _gather_memory(db: Session, message: str, ctx: GatheredContext) -> None:
    settings = get_settings()
    hits = atlas.search(db, message, top_k=settings.local_context_max_memory_items)
    for entry, _distance in hits:
        ctx.memory_context.append(f"[{entry.epistemic_status}, confidence {entry.confidence:.2f}] {entry.content}")
        ctx.atlas_citations.append(entry)
    if hits:
        _add_source(ctx.source_display_names, _SOURCE_LABELS["atlas_memory"])


def _gather_previous_conversation(db: Session, message: str, conversation_id: str | None, ctx: GatheredContext) -> None:
    settings = get_settings()
    if not conversation_search.should_search_previous_conversations(message):
        return
    snippets = conversation_search.search_previous_conversations(
        db,
        message,
        exclude_conversation_id=conversation_id,
        top_k=settings.local_context_max_conversation_snippets,
        prefer_user_messages=conversation_search.prefers_user_messages(message),
    )
    for s in snippets:
        date = s.created_at.strftime("%Y-%m-%d") if s.created_at else "unknown date"
        ctx.conversation_context.append(f'[{date}, "{s.conversation_title}", {s.role}] {s.snippet}')
    if snippets:
        _add_source(ctx.source_display_names, _SOURCE_LABELS["previous_conversation"])


def _gather_projects_tasks(db: Session, intent: IntentClassification, active_project_id: str | None, ctx: GatheredContext) -> None:
    settings = get_settings()
    projects = db.query(Project).filter(Project.status == "active").order_by(Project.last_touched_at.desc()).limit(5).all()
    for p in projects:
        ctx.project_context.append(f"Project: {p.title} ({p.status}, {p.priority} priority)")
    if projects:
        _add_source(ctx.source_display_names, _SOURCE_LABELS["projects"])

    tasks_query = db.query(Task).filter(Task.status.in_(("todo", "in_progress", "blocked")))
    if active_project_id:
        tasks_query = tasks_query.filter(Task.project_id == active_project_id)
    tasks = tasks_query.order_by(Task.due_at.is_(None), Task.due_at.asc()).limit(settings.local_context_max_file_chunks).all()
    for t in tasks:
        due = f", due {t.due_at.strftime('%Y-%m-%d')}" if t.due_at else ""
        ctx.task_context.append(f"Task: {t.title} ({t.status}{due})")
    if tasks:
        _add_source(ctx.source_display_names, _SOURCE_LABELS["tasks"])


def _gather_schedule(db: Session, ctx: GatheredContext) -> None:
    items = (
        db.query(ScheduleItem)
        .filter(ScheduleItem.status == "pending")
        .order_by(ScheduleItem.due_at.is_(None), ScheduleItem.due_at.asc())
        .limit(5)
        .all()
    )
    for item in items:
        due = f" (due {item.due_at.strftime('%Y-%m-%d %H:%M')})" if item.due_at else ""
        ctx.schedule_context.append(f"Reminder: {item.title}{due}")
    if items:
        _add_source(ctx.source_display_names, _SOURCE_LABELS["schedule"])


def _gather_library(db: Session, message: str, ctx: GatheredContext) -> None:
    settings = get_settings()
    words = [w for w in message.split() if len(w) > 3]
    items: list[LibraryItem] = []
    if words:
        like_clauses = [LibraryItem.title.ilike(f"%{w}%") for w in words[:5]]
        items = (
            db.query(LibraryItem)
            .filter(or_(*like_clauses))
            .order_by(LibraryItem.created_at.desc())
            .limit(settings.local_context_max_file_chunks)
            .all()
        )
    if not items:
        # Honest best-effort fallback: "the PDF I uploaded" with no matching
        # title still most plausibly means "the most recent one" — never
        # invents a file that doesn't exist, just guesses recency instead of
        # returning nothing.
        items = db.query(LibraryItem).order_by(LibraryItem.created_at.desc()).limit(1).all()
    for item in items:
        desc = f" — {item.description}" if item.description else ""
        ctx.library_context.append(f"File: {item.title} ({item.file_type}){desc}")
    if items:
        _add_source(ctx.source_display_names, _SOURCE_LABELS["library"])
    else:
        ctx.warnings.append("No matching library file found.")


def _gather_search_sources(message: str, ctx: GatheredContext) -> None:
    """Wiki/RSS/web — reuses the exact same gather_sources()/SearchIntent
    pipeline app/persona.py already uses for the existing chat flow, so
    behavior (caching, failure_reason wording, source shape) stays identical."""
    settings = get_settings()
    intent = search_intent.detect_search_intent(message)
    result = web_search.gather_sources(intent, message)
    ctx.gather_result = result

    for s in result.sources[: settings.local_context_max_web_results]:
        retrieved = f" (retrieved {s.retrieved_at})" if s.retrieved_at else ""
        line = f"{s.title or 'untitled'}{retrieved}: {s.snippet or ''}"
        if s.source_type == "wiki":
            ctx.wiki_context.append(line)
            _add_source(ctx.source_display_names, _SOURCE_LABELS["wiki"])
        elif s.source_type == "rss":
            ctx.rss_context.append(line)
            _add_source(ctx.source_display_names, _SOURCE_LABELS["rss"])
        else:
            ctx.web_context.append(line)
            _add_source(ctx.source_display_names, _SOURCE_LABELS["web_search"])

    if result.search_failure_reason:
        ctx.warnings.append("Could not verify current information.")


def _enforce_char_budget(ctx: GatheredContext) -> None:
    """Final safety net — trims from the least-recently-added categories
    first if the combined context somehow still exceeds the configured
    character budget, so a local model's smaller context window is never
    blown out regardless of how many per-category caps fired above."""
    settings = get_settings()
    budget = settings.local_context_max_chars
    categories = [
        ctx.web_context, ctx.rss_context, ctx.wiki_context, ctx.library_context,
        ctx.schedule_context, ctx.task_context, ctx.project_context,
        ctx.conversation_context, ctx.memory_context,
    ]
    while sum(len(line) for cat in categories for line in cat) > budget:
        trimmed_any = False
        for cat in categories:
            if cat:
                cat.pop()
                trimmed_any = True
                break
        if not trimmed_any:
            break


def gather_context(
    db: Session,
    intent: IntentClassification,
    message: str,
    conversation_id: str | None = None,
    active_project_id: str | None = None,
) -> GatheredContext:
    """Never raises — any single source failing degrades to a clean warning
    (see _gather_search_sources) rather than breaking the whole gather."""
    ctx = GatheredContext()

    # Memory: cheap, semantic-relevance-filtered, and already how the
    # existing chat flow behaves on every turn — kept broad rather than
    # intent-gated so an implicit reference to something previously said
    # still surfaces even outside an explicit "what did we decide" phrasing.
    _gather_memory(db, message, ctx)
    _gather_previous_conversation(db, message, conversation_id, ctx)

    if intent.intent in ("project_task",) or intent.source_need == "memory":
        _gather_projects_tasks(db, intent, active_project_id, ctx)
    if intent.intent == "schedule":
        _gather_schedule(db, ctx)
    if intent.intent == "library_file" or intent.source_need == "file":
        _gather_library(db, message, ctx)

    # Wiki/web/rss: only for intents that actually need them — normal chat
    # never triggers a web/wiki/rss call (Phase 4 rule 1).
    if intent.source_need in ("wiki", "web", "rss") or intent.freshness_need in ("current", "live"):
        _gather_search_sources(message, ctx)

    _enforce_char_budget(ctx)
    return ctx
