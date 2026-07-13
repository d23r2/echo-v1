"""Tests for Phase 2's provider cooldown tracking (usage.py's
set_cooldown/get_active_cooldown/clear_cooldown) — local, deterministic,
no real provider calls.
"""

from datetime import datetime, timedelta, timezone

from app import usage
from app.models import ProviderCooldown


def test_set_cooldown_then_get_active_cooldown_returns_it(db_session):
    usage.set_cooldown(db_session, "gemini", "quota_exceeded")

    row = usage.get_active_cooldown(db_session, "gemini")
    assert row is not None
    assert row.provider == "gemini"
    assert row.category == "quota_exceeded"


def test_get_active_cooldown_returns_none_when_never_set(db_session):
    assert usage.get_active_cooldown(db_session, "openai") is None


def test_expired_cooldown_is_not_active(db_session):
    row = ProviderCooldown(
        provider="anthropic",
        category="rate_limited",
        started_at=datetime.now(timezone.utc) - timedelta(hours=1),
        cooldown_until=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db_session.add(row)
    db_session.commit()

    assert usage.get_active_cooldown(db_session, "anthropic") is None


def test_clear_cooldown_removes_it(db_session):
    usage.set_cooldown(db_session, "grok", "credit_exhausted")
    assert usage.get_active_cooldown(db_session, "grok") is not None

    usage.clear_cooldown(db_session, "grok")
    assert usage.get_active_cooldown(db_session, "grok") is None


def test_setting_cooldown_again_refreshes_it(db_session):
    usage.set_cooldown(db_session, "gemini", "rate_limited")
    first = usage.get_active_cooldown(db_session, "gemini")
    assert first is not None

    usage.set_cooldown(db_session, "gemini", "quota_exceeded")
    second = usage.get_active_cooldown(db_session, "gemini")
    assert second is not None
    assert second.category == "quota_exceeded"
