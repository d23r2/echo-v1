"""ECHO Layer 2E — Context Selection v2 (Phases 4-5).

Deliberately wraps, not replaces, the already-tested per-system retrieval
this app has: context_gatherer.gather_context() (memory/project/task/
schedule/library/wiki/rss/web — already has its own char-budget helper),
cognitive_core.get_cognitive_brief_for_message(), skill_library.suggest_plan(),
and plain scoped lookups against Layer 2B/2C's SystemModel/DecisionCase/Plan
tables. This module's own genuinely new job is assembling those into one
typed ContextBundle, then deduplicating/budgeting/compressing it and
recording (never fabricating) what got excluded and why.
"""

from app import schemas
from app.config import get_settings
from app.models import DecisionCase, Goal, Plan, SystemModel
from app.services import context_gatherer, goal_engine, skill_library
from app.services.cognitive_core import get_cognitive_brief_for_message
from app.services.intent_classifier import classify_intent
from app.services.permission_center import list_permissions

# Priority order, LOWEST first — compression drops/truncates from this end
# before ever touching a higher-priority (more "critical constraint"-like)
# field. cognitive_brief/goal_context/memory_brief are the load-bearing
# pieces of "what does this request actually need" and are compressed last.
_COMPRESSION_ORDER = [
    "provenance_summary",
    "tool_evidence",
    "relevant_documents",
    "system_or_simulation_context",
    "decision_or_plan_context",
    "project_context",
    "memory_brief",
    "goal_context",
    "cognitive_brief",
]

_ACTIVE_GOAL_STATUSES = ("proposed", "approved", "active", "paused", "blocked")
_ACTIVE_PLAN_STATUSES = ("proposed", "approved", "active", "blocked")
_ACTIVE_DECISION_STATUSES = ("draft", "analysed", "selected")


def _goal_context_for(db, goal_id: str | None) -> str | None:
    if not goal_id:
        return None
    goal = db.get(Goal, goal_id)
    if goal is None or goal.status not in _ACTIVE_GOAL_STATUSES:
        return None  # excluded: unknown/terminal goal — never stale context
    progress = goal_engine.compute_progress(db, goal_id)
    return f"Goal: '{goal.title}' ({goal.status}, {progress.percent_complete}% complete, priority {goal.priority})."


def _project_context_for(gathered: context_gatherer.GatheredContext) -> str | None:
    parts = gathered.project_context + gathered.task_context
    return "\n".join(parts) if parts else None


def _system_context_for(db, project_id: str | None) -> str | None:
    if not project_id:
        return None
    model = (
        db.query(SystemModel)
        .filter(SystemModel.project_id == project_id, SystemModel.archived_at.is_(None))
        .order_by(SystemModel.updated_at.desc())
        .first()
    )
    if model is None:
        return None
    return f"System model: '{model.name}' ({model.scope})."


def _decision_or_plan_context_for(db, project_id: str | None, goal_id: str | None) -> str | None:
    """DecisionCase only has a project_id scoping column (no goal_id) —
    unscoped calls (neither project_id nor goal_id set) deliberately return
    no decision/plan context rather than picking an arbitrary, unrelated
    'most recent' row from across the whole app."""
    lines: list[str] = []
    decision = None
    if project_id:
        decision = (
            db.query(DecisionCase)
            .filter(DecisionCase.status.in_(_ACTIVE_DECISION_STATUSES), DecisionCase.project_id == project_id)
            .order_by(DecisionCase.updated_at.desc())
            .first()
        )
    if decision is not None:
        status_note = "selected" if decision.status == "selected" else decision.status
        lines.append(f"Decision: '{decision.question}' ({status_note}).")

    plan_q = db.query(Plan).filter(Plan.status.in_(_ACTIVE_PLAN_STATUSES))
    if goal_id:
        plan_q = plan_q.filter(Plan.goal_id == goal_id)
    elif project_id:
        plan_q = plan_q.filter(Plan.project_id == project_id)
    else:
        plan_q = None
    plan = plan_q.order_by(Plan.updated_at.desc()).first() if plan_q is not None else None
    if plan is not None:
        done = sum(1 for s in plan.steps if s.status == "completed")
        lines.append(f"Active plan: '{plan.objective[:80]}' ({plan.status}, {done}/{len(plan.steps)} step(s) complete).")

    return "\n".join(lines) if lines else None


def _active_permission_summary(db) -> list[str]:
    return [p.permission_key for p in list_permissions(db) if p.level == "allowed"]


def select_context(db, request: schemas.ContextRequest) -> schemas.ContextBundle:
    """Never raises — every per-source lookup below is either already
    exception-safe (gather_context's own documented contract) or a plain,
    defensively-guarded query. The one exception: context_gatherer.py's
    memory step calls atlas.search() directly (not memory_retrieval.py's
    newer semantic/lexical-fallback path), which has no try/except of its
    own — a genuine Chroma failure there is caught here and degrades to an
    honest empty-memory fallback rather than crashing context selection
    (Phase 4's explicit 'deterministic fallback when semantic retrieval
    unavailable' requirement)."""
    settings = get_settings()
    intent = classify_intent(request.user_message, request.conversation_id, request.project_id)
    excluded: list[str] = []
    fallback_used = False
    try:
        gathered = context_gatherer.gather_context(db, intent, request.user_message, request.conversation_id, request.project_id)
    except Exception:
        gathered = context_gatherer.GatheredContext()
        excluded.append("memory_brief: semantic retrieval unavailable, fell back to no memory context")
        fallback_used = True

    brief = get_cognitive_brief_for_message(db, request.user_message, request.conversation_id)
    skill = skill_library.suggest_plan(db, request.user_message)

    goal_context = _goal_context_for(db, request.goal_id)
    if request.goal_id and goal_context is None:
        excluded.append("goal_context: goal not found or no longer active")

    if request.freshness_requirement == "current" and not (gathered.wiki_context or gathered.rss_context or gathered.web_context):
        if gathered.warnings:
            excluded.append("current-info requirement not met — no live source available")
            fallback_used = True

    # Phase 4's "deduplicate overlapping ... content" — exact-duplicate
    # strings can legitimately arrive twice when two sources surface the
    # same underlying fact (e.g. a wiki snippet and an RSS item covering the
    # same headline). dict.fromkeys() preserves order while dropping repeats.
    tool_evidence = list(dict.fromkeys(list(gathered.wiki_context) + list(gathered.rss_context) + list(gathered.web_context)))
    relevant_documents = list(dict.fromkeys(gathered.library_context))

    bundle = schemas.ContextBundle(
        cognitive_brief=brief.brief_text if brief else None,
        memory_brief="\n".join(gathered.memory_context) if gathered.memory_context else None,
        goal_context=goal_context,
        project_context=_project_context_for(gathered),
        relevant_skills=[skill.name] if skill else [],
        relevant_documents=relevant_documents,
        system_or_simulation_context=_system_context_for(db, request.project_id),
        decision_or_plan_context=_decision_or_plan_context_for(db, request.project_id, request.goal_id),
        tool_evidence=tool_evidence,
        active_permissions=_active_permission_summary(db),
        uncertainty_summary="; ".join(gathered.warnings) if gathered.warnings else None,
        provenance_summary=list(gathered.source_display_names),
        excluded_context_summary=excluded,
        fallback_used=fallback_used,
    )

    budget_chars = request.max_chars or (request.max_tokens * 4 if request.max_tokens else settings.local_context_max_chars)
    _apply_budget(bundle, budget_chars)
    return bundle


def _field_chars(bundle: schemas.ContextBundle, field: str) -> int:
    value = getattr(bundle, field)
    if value is None:
        return 0
    if isinstance(value, list):
        return sum(len(v) for v in value)
    return len(value)


def _apply_budget(bundle: schemas.ContextBundle, budget_chars: int) -> None:
    """Compress lower-priority fields before ever removing a higher-priority
    one (Phase 5's explicit rule) — truncates list fields item-by-item first,
    then clears the field entirely, recording what was dropped."""
    bundle.budget_chars = budget_chars
    total = sum(_field_chars(bundle, f) for f in _COMPRESSION_ORDER)
    if total <= budget_chars:
        bundle.total_chars = total
        return

    bundle.compressed = True
    for field in _COMPRESSION_ORDER:
        if total <= budget_chars:
            break
        value = getattr(bundle, field)
        field_chars = _field_chars(bundle, field)
        if field_chars == 0:
            continue
        if isinstance(value, list) and value:
            while value and total > budget_chars:
                dropped = value.pop()
                total -= len(dropped)
            bundle.excluded_context_summary.append(f"{field}: truncated to fit budget")
        elif isinstance(value, str):
            setattr(bundle, field, None)
            total -= field_chars
            bundle.excluded_context_summary.append(f"{field}: dropped to fit budget")

    bundle.total_chars = max(total, 0)


def preview_context(db, request: schemas.ContextRequest) -> schemas.ContextSelectionPreviewOut:
    """The UI-facing view — categories and sources, never raw content (Phase
    7's explicit rule)."""
    bundle = select_context(db, request)
    included: list[str] = []
    for field in ("cognitive_brief", "memory_brief", "goal_context", "project_context", "system_or_simulation_context", "decision_or_plan_context"):
        if getattr(bundle, field):
            included.append(field)
    for field in ("relevant_skills", "relevant_documents", "tool_evidence", "active_permissions"):
        if getattr(bundle, field):
            included.append(field)
    excluded_categories = sorted({entry.split(":")[0].strip() for entry in bundle.excluded_context_summary})
    return schemas.ContextSelectionPreviewOut(
        categories_included=included,
        categories_excluded=excluded_categories,
        sources_summary=bundle.provenance_summary,
        estimated_chars=bundle.total_chars,
        budget_chars=bundle.budget_chars,
        fallback_used=bundle.fallback_used,
    )
