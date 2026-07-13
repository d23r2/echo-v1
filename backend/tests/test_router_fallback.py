"""Tests for ModelRouter's multi-provider fallback behavior (app/router.py).

No real external APIs are called anywhere in this file — every provider is a
FakeProvider (tests/fake_providers.py), so no API keys are required and nothing
here touches the network.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import ProviderUsageDaily
from app.providers.base import ChatMessage
from app.router import ModelRouter, NoProviderAvailableError, ProviderUnavailableError
from tests.fake_providers import FakeProvider, FakeProviderError, FakeRateLimitError

_MSG = [ChatMessage(role="user", content="hi")]


# 1. Auto mode uses the first available working provider.
def test_auto_mode_uses_first_available_working_provider():
    first = FakeProvider("gemini", response_text="from gemini")
    second = FakeProvider("ollama", response_text="from ollama")
    router = ModelRouter(providers=[first, second])

    result, provider_used, fallback_note = router.chat("auto", "sys", _MSG)

    assert provider_used == "gemini"
    assert result.text == "from gemini"
    assert fallback_note is None
    assert first.chat_call_count == 1
    assert second.chat_call_count == 0


# 2. First provider 429s -> router tries the next provider.
def test_falls_back_to_next_provider_on_429():
    first = FakeProvider("gemini", raises=FakeRateLimitError("rate limited"))
    second = FakeProvider("ollama", response_text="from ollama")
    router = ModelRouter(providers=[first, second])

    result, provider_used, fallback_note = router.chat("auto", "sys", _MSG)

    assert provider_used == "ollama"
    assert result.text == "from ollama"
    assert first.chat_call_count == 1
    assert second.chat_call_count == 1
    assert fallback_note is not None
    assert "gemini" in fallback_note


# 3. Two providers fail (one 429, one a generic error) -> router continues until one works.
def test_continues_past_two_failures_until_one_works():
    first = FakeProvider("anthropic", raises=FakeRateLimitError("rate limited"))
    second = FakeProvider("openai", raises=FakeProviderError("bad request"))
    third = FakeProvider("gemini", response_text="from gemini")
    router = ModelRouter(providers=[first, second, third])

    result, provider_used, fallback_note = router.chat("auto", "sys", _MSG)

    assert provider_used == "gemini"
    assert result.text == "from gemini"
    assert first.chat_call_count == 1
    assert second.chat_call_count == 1
    assert third.chat_call_count == 1


# 4. Ollama/local fallback is used when cloud providers fail.
def test_ollama_fallback_used_when_cloud_providers_fail():
    cloud_a = FakeProvider("anthropic", raises=FakeProviderError("down"))
    cloud_b = FakeProvider("gemini", raises=FakeRateLimitError("rate limited"))
    local = FakeProvider("ollama", response_text="local reply")
    router = ModelRouter(providers=[cloud_a, cloud_b, local])

    result, provider_used, _fallback_note = router.chat("auto", "sys", _MSG)

    assert provider_used == "ollama"
    assert result.text == "local reply"


# 5. No providers configured/available -> the chat route returns a clear 503.
def test_no_providers_available_raises_at_router_level():
    unavailable = FakeProvider("gemini", available=False, unavailable_reason="GEMINI_API_KEY not set")
    router = ModelRouter(providers=[unavailable])

    with pytest.raises(NoProviderAvailableError):
        router.chat("auto", "sys", _MSG)


def test_no_providers_available_route_returns_503(monkeypatch):
    unavailable_router = ModelRouter(
        providers=[FakeProvider("gemini", available=False, unavailable_reason="GEMINI_API_KEY not set")]
    )
    monkeypatch.setattr("app.routers.chat.model_router", unavailable_router)

    with TestClient(app) as client:
        resp = client.post("/api/chat", json={"message": "hello", "provider": "auto"})

    assert resp.status_code == 503
    # Clean, user-facing message — no raw exception text (Goal 18b Part 1).
    assert resp.json()["detail"] == "No AI provider is currently available. Check API keys or local Ollama."


# 6. fallback_note is generated when fallback happens (and only then).
def test_fallback_note_only_set_when_fallback_actually_happened():
    first = FakeProvider("gemini", response_text="from gemini")
    router = ModelRouter(providers=[first])
    _result, _provider_used, fallback_note = router.chat("auto", "sys", _MSG)
    assert fallback_note is None  # no fallback happened, first provider just worked


def test_fallback_note_mentions_the_provider_that_was_skipped():
    first = FakeProvider("anthropic", raises=FakeRateLimitError("rate limited"))
    second = FakeProvider("openai", raises=FakeRateLimitError("rate limited"))
    third = FakeProvider("gemini", response_text="ok")
    router = ModelRouter(providers=[first, second, third])

    _result, provider_used, fallback_note = router.chat("auto", "sys", _MSG)

    assert provider_used == "gemini"
    assert "anthropic" in fallback_note
    assert "openai" in fallback_note


# 7. Provider usage logging records real attempts/failures, no hardcoded rate limits.
def test_usage_tracks_a_successful_request(db_session):
    provider = FakeProvider("gemini", response_text="ok")
    router = ModelRouter(providers=[provider])

    router.chat("auto", "sys", _MSG, db=db_session)

    rows = db_session.query(ProviderUsageDaily).filter_by(provider="gemini").all()
    assert len(rows) == 1
    assert rows[0].request_count == 1
    assert rows[0].last_429_at is None


def test_usage_tracks_a_real_429_without_any_hardcoded_limit(db_session):
    provider = FakeProvider("gemini", raises=FakeRateLimitError("rate limited"))
    fallback = FakeProvider("ollama", response_text="ok")
    router = ModelRouter(providers=[provider, fallback])

    router.chat("auto", "sys", _MSG, db=db_session)

    gemini_row = db_session.query(ProviderUsageDaily).filter_by(provider="gemini").one()
    assert gemini_row.last_429_at is not None
    assert gemini_row.request_count == 0  # it failed, never succeeded


def test_local_ollama_usage_is_never_tracked(db_session):
    # Ollama is local/self-hosted with no quota concept — router._USAGE_TRACKED_PROVIDERS
    # deliberately excludes it, and this must hold even when it succeeds or 429s.
    provider = FakeProvider("ollama", response_text="ok")
    router = ModelRouter(providers=[provider])

    router.chat("auto", "sys", _MSG, db=db_session)

    assert db_session.query(ProviderUsageDaily).filter_by(provider="ollama").count() == 0


# 8. Pinned provider mode does not silently fall back to another provider.
def test_pinned_provider_does_not_fall_back_on_failure():
    pinned = FakeProvider("anthropic", raises=FakeProviderError("down"))
    other = FakeProvider("gemini", response_text="should not be used")
    router = ModelRouter(providers=[pinned, other])

    with pytest.raises(ProviderUnavailableError):
        router.chat("anthropic", "sys", _MSG)

    assert other.chat_call_count == 0


def test_pinned_provider_that_is_unavailable_raises_without_trying_others():
    pinned = FakeProvider("anthropic", available=False, unavailable_reason="ANTHROPIC_API_KEY not set")
    other = FakeProvider("gemini", response_text="should not be used")
    router = ModelRouter(providers=[pinned, other])

    with pytest.raises(ProviderUnavailableError):
        router.chat("anthropic", "sys", _MSG)

    assert other.chat_call_count == 0


def test_pinned_provider_that_works_is_used_directly():
    pinned = FakeProvider("anthropic", response_text="pinned reply")
    other = FakeProvider("gemini", response_text="should not be used")
    router = ModelRouter(providers=[pinned, other])

    result, provider_used, fallback_note = router.chat("anthropic", "sys", _MSG)

    assert provider_used == "anthropic"
    assert result.text == "pinned reply"
    assert fallback_note is None
    assert other.chat_call_count == 0
