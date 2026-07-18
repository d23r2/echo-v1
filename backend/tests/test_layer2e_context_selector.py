"""ECHO Layer 2E — Context Selection v2 (Phases 4-5). Isolated db_session
fixture; web_search is never triggered by these messages (no network
calls). Semantic memory tests use the real atlas.create_entry() +
atlas.search() path (same established pattern as test_atlas_second_brain.py)
— Chroma collections are wiped before every test by conftest.py's autouse
fixture, so these are order-independent."""

from app import schemas
from app.models import DecisionCase, Plan
from app.services import context_selector, goal_engine


def _atlas_entry(db_session, content, **overrides):
    from app import atlas

    payload = schemas.AtlasEntryCreate(content=content, epistemic_status=overrides.pop("epistemic_status", "Verified"), **overrides)
    return atlas.create_entry(db_session, payload)


# ---- Context includes relevant project/goal/skill/plan ----


def test_context_includes_goal_context_when_linked(db_session):
    goal = goal_engine.create_goal(db_session, schemas.GoalCreate(title="Ship the release", origin="explicit_user"))
    bundle = context_selector.select_context(db_session, schemas.ContextRequest(user_message="how's it going", goal_id=goal.id))
    assert bundle.goal_context is not None
    assert "Ship the release" in bundle.goal_context


def test_context_includes_decision_context_when_project_scoped(db_session):
    db_session.add(DecisionCase(question="Postgres or SQLite?", objective="pick a database", status="selected", project_id="proj-42"))
    db_session.commit()
    bundle = context_selector.select_context(db_session, schemas.ContextRequest(user_message="what did we decide", project_id="proj-42"))
    assert bundle.decision_or_plan_context is not None
    assert "Postgres or SQLite?" in bundle.decision_or_plan_context


def test_context_includes_active_plan_when_project_scoped(db_session):
    db_session.add(Plan(objective="Launch the new feature", status="active", project_id="proj-9"))
    db_session.commit()
    bundle = context_selector.select_context(db_session, schemas.ContextRequest(user_message="what's the plan", project_id="proj-9"))
    assert bundle.decision_or_plan_context is not None
    assert "Launch the new feature" in bundle.decision_or_plan_context


# ---- Privacy / freshness / status filtering ----


def test_unrelated_goal_excluded_from_context(db_session):
    """A goal_id that doesn't exist (or isn't active) must never surface a
    fabricated goal_context — this is the deterministic status/relevance
    filter Phase 4 requires."""
    bundle = context_selector.select_context(db_session, schemas.ContextRequest(user_message="anything", goal_id="does-not-exist"))
    assert bundle.goal_context is None
    assert any("goal_context" in e for e in bundle.excluded_context_summary)


def test_abandoned_goal_excluded_from_context(db_session):
    goal = goal_engine.create_goal(db_session, schemas.GoalCreate(title="Old idea", origin="explicit_user"))
    goal_engine.abandon_goal(db_session, goal.id, "no longer needed")
    bundle = context_selector.select_context(db_session, schemas.ContextRequest(user_message="anything", goal_id=goal.id))
    assert bundle.goal_context is None


def test_cancelled_plan_excluded_from_context(db_session):
    db_session.add(Plan(objective="Abandoned plan", status="cancelled", project_id="proj-1"))
    db_session.commit()
    bundle = context_selector.select_context(db_session, schemas.ContextRequest(user_message="what's the plan", project_id="proj-1"))
    assert bundle.decision_or_plan_context is None


def test_context_includes_stored_memory_when_present(db_session):
    _atlas_entry(db_session, "The user prefers concise answers.")
    bundle = context_selector.select_context(db_session, schemas.ContextRequest(user_message="how should I format replies?"))
    assert bundle.memory_brief is not None
    assert "concise answers" in bundle.memory_brief


def test_freshness_current_without_live_source_triggers_fallback(db_session, monkeypatch):
    """freshness_requirement="current" demands live/current-info sources;
    when gather_context reports it couldn't satisfy that (a warning, no
    wiki/rss/web hits), Context Selection v2 must mark the bundle as a
    fallback rather than silently presenting stale context as current —
    this is the deterministic freshness filter Phase 4 requires. (Semantic
    relevance ranking of memory_brief content is atlas.search()'s job, a
    pre-existing Layer 1 concern with no similarity threshold — not
    something Context Selection v2 adds or is responsible for.)"""
    from app.services import context_gatherer as cg

    def fake_gather(*args, **kwargs):
        return cg.GatheredContext(warnings=["current-info source unavailable"])

    monkeypatch.setattr(cg, "gather_context", fake_gather)
    bundle = context_selector.select_context(
        db_session, schemas.ContextRequest(user_message="what's happening today", freshness_requirement="current")
    )
    assert bundle.fallback_used is True
    assert any("current-info requirement not met" in e for e in bundle.excluded_context_summary)


# ---- Budget / compression / deduplication ----


def test_context_budget_respected(db_session):
    goal = goal_engine.create_goal(db_session, schemas.GoalCreate(title="A goal with a reasonably long title for budget testing", origin="explicit_user"))
    bundle = context_selector.select_context(db_session, schemas.ContextRequest(user_message="status check", goal_id=goal.id, max_chars=10))
    assert bundle.compressed is True
    assert bundle.budget_chars == 10


def test_duplicate_tool_evidence_deduplicated(db_session, monkeypatch):
    from app.web_search import GatherResult, SourceResult

    def fake_gather_sources(intent, message):
        dup = SourceResult(source_type="wiki", provider="wikimedia", title="Same fact", url="https://example.com", retrieved_at="2026-07-16T00:00:00Z", snippet="identical snippet")
        return GatherResult(sources=[dup, dup], wiki_search_used=True, task_type="encyclopedia_lookup")

    monkeypatch.setattr("app.services.context_gatherer.web_search.gather_sources", fake_gather_sources)
    bundle = context_selector.select_context(db_session, schemas.ContextRequest(user_message="Who was Nikola Tesla?"))
    assert len(bundle.tool_evidence) >= 1
    assert len(bundle.tool_evidence) == len(set(bundle.tool_evidence))


def test_no_context_request_never_crashes(db_session):
    bundle = context_selector.select_context(db_session, schemas.ContextRequest(user_message="hello there"))
    assert bundle.total_chars >= 0


# ---- Vector-search fallback ----


def test_vector_failure_falls_back_cleanly(db_session, monkeypatch):
    from app.services import context_gatherer as cg

    def boom(*args, **kwargs):
        raise RuntimeError("Chroma unavailable")

    monkeypatch.setattr(cg, "gather_context", boom)
    bundle = context_selector.select_context(db_session, schemas.ContextRequest(user_message="anything at all"))
    assert bundle.fallback_used is True
    assert bundle.memory_brief is None
    assert any("semantic retrieval unavailable" in e for e in bundle.excluded_context_summary)


# ---- Preview (UI-facing, categories/sources only) ----


def test_preview_never_exposes_raw_content(db_session):
    goal = goal_engine.create_goal(db_session, schemas.GoalCreate(title="Secret internal goal text", origin="explicit_user"))
    preview = context_selector.preview_context(db_session, schemas.ContextRequest(user_message="status", goal_id=goal.id))
    assert "goal_context" in preview.categories_included
    serialized = str(preview.model_dump())
    assert "Secret internal goal text" not in serialized


# ---- Prompt integration: one compact bundle ----


def test_bundle_has_single_compact_shape():
    """Structural check that the schema itself is the one, typed, compact
    bundle the milestone requires (not a bag of raw retrieval objects)."""
    bundle = schemas.ContextBundle()
    fields = set(bundle.model_dump().keys())
    assert fields == {
        "cognitive_brief",
        "memory_brief",
        "goal_context",
        "project_context",
        "relevant_skills",
        "relevant_documents",
        "system_or_simulation_context",
        "decision_or_plan_context",
        "tool_evidence",
        "active_permissions",
        "uncertainty_summary",
        "provenance_summary",
        "excluded_context_summary",
        "total_chars",
        "budget_chars",
        "compressed",
        "fallback_used",
    }
