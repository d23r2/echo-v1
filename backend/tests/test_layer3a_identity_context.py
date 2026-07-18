"""Layer 3A Part 2B IdentityBrief applicability, budgeting, and selector tests."""

import pytest

from app import schemas
from app.core import metrics
from app.services import context_selector, identity_context, identity_runtime, identity_service


def _snapshot(db_session):
    identity_service.ensure_default_identity(db_session)
    return identity_runtime.get_active_identity_snapshot(db_session)


@pytest.mark.parametrize(
    ("context_type", "expected_text"),
    [
        ("general_chat", "Support the user's decision-making"),
        ("planning", "Prefer reversible"),
        ("decision", "Do not manipulate"),
        ("research", "configured local processing"),
        ("memory", "Minimize unnecessary exposure"),
        ("tool_action", "attempted action as completed"),
        ("emotional_support", "encouraging dependency"),
        ("coding", "verified successful actions"),
        ("document_analysis", "private data"),
        ("system_diagnostic", "configured local processing"),
    ],
)
def test_context_specific_briefs_select_relevant_commitments(db_session, context_type, expected_text):
    snapshot = _snapshot(db_session)
    brief = identity_context.build_identity_brief(snapshot, context_type)

    assert expected_text in brief.prompt_text
    assert brief.context_type == context_type
    assert brief.size_chars <= brief.budget_chars
    assert "full revision" not in brief.prompt_text.lower()
    assert "metadata_json" not in brief.prompt_text
    assert "internal_role" not in brief.prompt_text


def test_general_brief_is_deterministic_compact_and_deduplicated(db_session):
    snapshot = _snapshot(db_session)
    first = identity_context.build_identity_brief(snapshot, "general_chat")
    second = identity_context.build_identity_brief(snapshot, "general_chat")

    assert first.prompt_text == second.prompt_text
    assert first.size_chars <= 1800
    normalized = [" ".join(item.lower().split()).rstrip(".") for item in first.mandatory_boundaries]
    assert len(normalized) == len(set(normalized))
    assert first.prompt_text.count("[OPERATIONAL IDENTITY") == 1
    measurement_keys = metrics.snapshot()["measurements"]
    assert any(key.startswith("identity_brief_size_chars") for key in measurement_keys)


def test_mandatory_boundaries_survive_impossibly_small_budget(db_session):
    snapshot = _snapshot(db_session)
    brief = identity_context.build_identity_brief(snapshot, "tool_action", max_chars=10)

    assert brief.truncated is True
    assert brief.size_chars > brief.budget_chars
    for text in (
        "Do not fabricate",
        "State uncertainty",
        "do not claim consciousness",
        "Do not expose secrets",
        "Require approval",
        "Do not claim capabilities",
    ):
        assert text in brief.prompt_text
    assert "Communication stance:" not in brief.prompt_text


def test_unknown_context_defaults_safely_to_general_chat(db_session):
    snapshot = _snapshot(db_session)
    brief = identity_context.build_identity_brief(snapshot, "not-a-real-context")
    assert brief.context_type == "general_chat"
    assert "Do not fabricate" in brief.prompt_text


def test_fallback_brief_retains_safe_critical_boundary():
    snapshot = identity_runtime.build_fallback_snapshot()
    brief = identity_context.build_identity_brief(snapshot, "general_chat")

    assert brief.fallback_used is True
    assert "software operating as ECHO" in brief.prompt_text
    assert "hidden chain-of-thought" in brief.prompt_text
    assert "Require approval" in brief.prompt_text


def test_context_selector_protects_identity_under_budget_and_hides_runtime_metadata(db_session):
    identity_service.ensure_default_identity(db_session)
    bundle = context_selector.select_context(
        db_session,
        schemas.ContextRequest(user_message="Plan the next release", max_chars=10),
    )

    assert bundle.identity_context is not None
    assert "Do not fabricate" in bundle.identity_context
    assert bundle._identity_version == 1
    assert bundle._identity_fingerprint
    assert bundle._identity_brief_size == len(bundle.identity_context)
    assert bundle.total_chars >= len(bundle.identity_context)
    serialized = bundle.model_dump()
    assert "identity_context" not in serialized
    assert "identity_fingerprint" not in str(serialized)


def test_context_selector_disabled_identity_feature_leaves_identity_context_empty(db_session, monkeypatch):
    monkeypatch.setenv("CORE_IDENTITY_V1_ENABLED", "false")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        bundle = context_selector.select_context(
            db_session,
            schemas.ContextRequest(user_message="hello"),
        )
        assert bundle.identity_context is None
        assert bundle._identity_version is None
    finally:
        get_settings.cache_clear()
