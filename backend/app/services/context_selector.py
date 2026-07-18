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

import logging
from collections import Counter

from app import schemas
from app.config import get_settings
from app.models import ContextSelectionMetric, DecisionCase, Goal, Plan, SystemModel, TaskUnderstanding
from app.services import context_gatherer, goal_engine, identity_context, identity_runtime, skill_library
from app.services.cognitive_core import get_cognitive_brief_for_message
from app.services.intent_classifier import classify_intent
from app.services.permission_center import list_permissions

logger = logging.getLogger(__name__)

# Priority order, LOWEST first — compression drops/truncates from this end
# before ever touching a higher-priority (more "critical constraint"-like)
# field. cognitive_brief/goal_context/memory_brief are the load-bearing
# pieces of "what does this request actually need" and are compressed last.
_COMPRESSION_ORDER = [
    "provenance_summary",
    "active_permissions",
    "relevant_skills",
    "tool_evidence",
    "relevant_documents",
    "system_or_simulation_context",
    "decision_or_plan_context",
    "schedule_context",
    "project_context",
    "conversation_brief",
    "uncertainty_summary",
    "memory_brief",
    "goal_context",
    "cognitive_brief",
    "success_criteria",
    # Mandatory trusted system context is accounted for last and is never
    # dropped. If a caller supplies an impossibly small budget, lower-trust
    # context is removed first and the safety-floor overage is reported.
    "identity_context",
]

_CONTENT_FIELDS = tuple(_COMPRESSION_ORDER)

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

    if request.freshness_requirement == "current" and not (
        gathered.wiki_context or gathered.rss_context or gathered.web_context
    ):
        excluded.append("current-info requirement not met — no live source available")
        fallback_used = True

    # Phase 4's "deduplicate overlapping ... content" — exact-duplicate
    # strings can legitimately arrive twice when two sources surface the
    # same underlying fact (e.g. a wiki snippet and an RSS item covering the
    # same headline). dict.fromkeys() preserves order while dropping repeats.
    tool_evidence = list(dict.fromkeys(list(gathered.wiki_context) + list(gathered.rss_context) + list(gathered.web_context)))
    relevant_documents = list(dict.fromkeys(gathered.library_context))

    task_understanding = (
        db.get(TaskUnderstanding, brief.task_understanding_id)
        if brief is not None and brief.task_understanding_id
        else None
    )
    identity_snapshot = identity_runtime.get_active_identity_snapshot(db)
    identity_brief = (
        identity_context.build_identity_brief(identity_snapshot, intent.intent)
        if identity_snapshot is not None
        else None
    )
    bundle = schemas.ContextBundle(
        identity_context=identity_brief.prompt_text if identity_brief else None,
        cognitive_brief=brief.brief_text if brief else None,
        success_criteria=list(task_understanding.success_criteria_json or []) if task_understanding else [],
        has_missing_knowledge=bool(task_understanding and task_understanding.unknowns_json),
        memory_brief="\n".join(gathered.memory_context) if gathered.memory_context else None,
        conversation_brief="\n".join(gathered.conversation_context) if gathered.conversation_context else None,
        goal_context=goal_context,
        project_context=_project_context_for(gathered),
        schedule_context="\n".join(gathered.schedule_context) if gathered.schedule_context else None,
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
    bundle._atlas_citations = list(gathered.atlas_citations)
    bundle._gather_result = gathered.gather_result
    if identity_snapshot is not None and identity_brief is not None:
        bundle._identity_profile_id = identity_snapshot.profile_id
        bundle._identity_version = identity_snapshot.version_number
        bundle._identity_fingerprint = identity_snapshot.fingerprint
        bundle._identity_fallback_used = identity_snapshot.fallback_used
        bundle._identity_validation_status = identity_snapshot.validation_status
        bundle._identity_context_type = identity_brief.context_type
        bundle._identity_brief_size = identity_brief.size_chars

    for required_type in request.required_context_types:
        if required_type not in _CONTENT_FIELDS:
            bundle.excluded_context_summary.append(f"{required_type}: unknown required context type")
            bundle.fallback_used = True
        elif not getattr(bundle, required_type):
            bundle.excluded_context_summary.append(f"{required_type}: required context unavailable")
            bundle.fallback_used = True

    budget_chars = request.max_chars or (request.max_tokens * 4 if request.max_tokens else settings.local_context_max_chars)
    _apply_budget(bundle, budget_chars)
    _record_selection_metric(db, request, bundle)
    return bundle


def _category_count(value) -> int:
    if not value:
        return 0
    if isinstance(value, list):
        return len(value)
    return 1


def _record_selection_metric(db, request: schemas.ContextRequest, bundle: schemas.ContextBundle) -> None:
    """Persist counts and sizes only — never the selected private content."""
    included = {
        field: count
        for field in _CONTENT_FIELDS
        if (count := _category_count(getattr(bundle, field))) > 0
    }
    excluded = Counter(
        entry.split(":", 1)[0].strip()
        for entry in bundle.excluded_context_summary
        if entry.strip()
    )
    metric = ContextSelectionMetric(
        task_id=request.task_id,
        purpose=request.purpose,
        included_category_counts_json=included,
        excluded_category_counts_json=dict(excluded),
        total_chars_selected=bundle.total_chars,
        budget_chars=bundle.budget_chars,
        compressed=bundle.compressed,
        fallback_used=bundle.fallback_used,
    )
    try:
        db.add(metric)
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("Could not persist context-selection metric", exc_info=True)


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
        if field == "identity_context":
            bundle.excluded_context_summary.append(
                "identity_context: mandatory safety floor retained beyond requested budget"
            )
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
    for field in (
        "identity_context",
        "cognitive_brief",
        "memory_brief",
        "conversation_brief",
        "goal_context",
        "project_context",
        "schedule_context",
        "system_or_simulation_context",
        "decision_or_plan_context",
    ):
        if getattr(bundle, field):
            included.append(field)
    for field in (
        "success_criteria",
        "relevant_skills",
        "relevant_documents",
        "tool_evidence",
        "active_permissions",
    ):
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
