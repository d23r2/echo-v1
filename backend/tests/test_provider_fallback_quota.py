"""Phase 2: cloud credit/quota/billing exhaustion must fall back to Ollama.

Covers app/provider_errors.py's classification wired into app/router.py's
actual fallback loops (chat + stream_chat), app/usage.py's cooldown
persistence, and app/routers/features.py's cooldown-aware status labels.
No real provider calls anywhere — every provider is a FakeProvider
(tests/fake_providers.py), and cooldowns are read/written against the
isolated `db_session` fixture (tests/conftest.py), never the real app DB.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import usage
from app.db import init_db
from app.main import app
from app.models import ProviderCooldown
from app.providers.base import ChatMessage
from app.router import ModelRouter, NoProviderAvailableError
from tests.fake_providers import FakeProvider, FakeProviderError, FakeRateLimitError

_MSG = [ChatMessage(role="user", content="hi")]


class _TextError(Exception):
    """A provider failure whose only signal is its message text — mimics SDKs
    that don't expose a typed status code but do return a descriptive string."""


# 1. Plain 429 with no special text -> rate_limited -> cooldown recorded.
def test_plain_429_is_classified_rate_limited_and_cooled_down(db_session):
    first = FakeProvider("gemini", raises=FakeRateLimitError("rate limited"))
    second = FakeProvider("ollama", response_text="from ollama")
    router = ModelRouter(providers=[first, second])

    router.chat("auto", "sys", _MSG, db=db_session)

    cooldown = usage.get_active_cooldown(db_session, "gemini")
    assert cooldown is not None
    assert cooldown.category == "rate_limited"


# 2. "insufficient quota" text -> quota_exceeded -> cooldown recorded.
def test_insufficient_quota_text_is_classified_and_cooled_down(db_session):
    first = FakeProvider("openai", raises=_TextError("Error: insufficient quota for this request"))
    second = FakeProvider("ollama", response_text="from ollama")
    router = ModelRouter(providers=[first, second])

    router.chat("auto", "sys", _MSG, db=db_session)

    cooldown = usage.get_active_cooldown(db_session, "openai")
    assert cooldown is not None
    assert cooldown.category == "quota_exceeded"


# 3. "credits exhausted" text -> credit_exhausted -> cooldown recorded.
def test_credits_exhausted_text_is_classified_and_cooled_down(db_session):
    first = FakeProvider("grok", raises=_TextError("Account credits exhausted"))
    second = FakeProvider("ollama", response_text="from ollama")
    router = ModelRouter(providers=[first, second])

    router.chat("auto", "sys", _MSG, db=db_session)

    cooldown = usage.get_active_cooldown(db_session, "grok")
    assert cooldown is not None
    assert cooldown.category == "credit_exhausted"


# 4. HTTP 402 -> billing_required -> cooldown recorded.
def test_http_402_is_classified_billing_required_and_cooled_down(db_session):
    err = _TextError("payment required")
    err.status_code = 402  # type: ignore[attr-defined]
    first = FakeProvider("anthropic", raises=err)
    second = FakeProvider("ollama", response_text="from ollama")
    router = ModelRouter(providers=[first, second])

    router.chat("auto", "sys", _MSG, db=db_session)

    cooldown = usage.get_active_cooldown(db_session, "anthropic")
    assert cooldown is not None
    assert cooldown.category == "billing_required"


# 5. HTTP 401 -> auth_failed, which is NOT a cooldown category -> no cooldown
#    row is written, so a persistent auth misconfiguration doesn't silently
#    disappear from view the way a transient quota error should.
def test_auth_failed_is_not_cooled_down(db_session):
    err = _TextError("invalid api key")
    err.status_code = 401  # type: ignore[attr-defined]
    first = FakeProvider("anthropic", raises=err)
    second = FakeProvider("ollama", response_text="from ollama")
    router = ModelRouter(providers=[first, second])

    router.chat("auto", "sys", _MSG, db=db_session)

    assert usage.get_active_cooldown(db_session, "anthropic") is None


# 6. A provider already in cooldown is skipped without being called at all.
def test_provider_in_cooldown_is_skipped_without_being_called(db_session):
    usage.set_cooldown(db_session, "gemini", "quota_exceeded")
    first = FakeProvider("gemini", response_text="would have worked")
    second = FakeProvider("ollama", response_text="from ollama")
    router = ModelRouter(providers=[first, second])

    result, provider_used, _ = router.chat("auto", "sys", _MSG, db=db_session)

    assert provider_used == "ollama"
    assert first.chat_call_count == 0


# 7. Once a cooldown has expired, the provider is tried again normally.
def test_expired_cooldown_provider_is_retried(db_session):
    row = ProviderCooldown(
        provider="gemini",
        category="quota_exceeded",
        started_at=datetime.now(UTC) - timedelta(hours=1),
        cooldown_until=datetime.now(UTC) - timedelta(minutes=1),
    )
    db_session.add(row)
    db_session.commit()

    provider = FakeProvider("gemini", response_text="back online")
    router = ModelRouter(providers=[provider])

    result, provider_used, _ = router.chat("auto", "sys", _MSG, db=db_session)

    assert provider_used == "gemini"
    assert provider.chat_call_count == 1


# 8. Manual clear_cooldown lets a provider be retried immediately.
def test_clear_cooldown_allows_immediate_retry(db_session):
    usage.set_cooldown(db_session, "gemini", "rate_limited")
    usage.clear_cooldown(db_session, "gemini")

    provider = FakeProvider("gemini", response_text="works now")
    router = ModelRouter(providers=[provider])

    result, provider_used, _ = router.chat("auto", "sys", _MSG, db=db_session)

    assert provider_used == "gemini"
    assert provider.chat_call_count == 1


# 9. All configured cloud providers fail -> Ollama answers -> exact spec-mandated note.
def test_all_cloud_providers_fail_falls_back_to_ollama_with_exact_note(db_session):
    cloud_a = FakeProvider("anthropic", raises=FakeRateLimitError("rate limited"))
    cloud_b = FakeProvider("gemini", raises=_TextError("insufficient quota"))
    local = FakeProvider("ollama", response_text="local reply")
    router = ModelRouter(providers=[cloud_a, cloud_b, local])

    result, provider_used, fallback_note = router.chat("auto", "sys", _MSG, db=db_session)

    assert provider_used == "ollama"
    assert result.text == "local reply"
    assert fallback_note == "Cloud providers were unavailable or quota-limited, so Echo replied using Ollama."


# 10. Cloud fails AND Ollama also fails -> the more specific "tried and failed" message.
def test_cloud_and_ollama_both_fail_raises_providers_failed_message(db_session):
    cloud = FakeProvider("gemini", raises=_TextError("insufficient quota"))
    local = FakeProvider("ollama", raises=FakeProviderError("connection refused"))
    router = ModelRouter(providers=[cloud, local])

    try:
        router.chat("auto", "sys", _MSG, db=db_session)
        raise AssertionError("expected NoProviderAvailableError")
    except NoProviderAvailableError as exc:
        assert str(exc) == (
            "No AI provider is currently available. Cloud providers are unavailable/quota-limited "
            "and Ollama is not running."
        )


# 11. OLLAMA_ALWAYS_AVAILABLE_FALLBACK=false removes Ollama from auto mode's chain.
def test_ollama_excluded_from_auto_chain_when_fallback_disabled(monkeypatch, db_session):
    monkeypatch.setattr(
        "app.router.get_settings",
        lambda: SimpleNamespace(ollama_always_available_fallback=False, free_mode=False),
    )
    cloud = FakeProvider("gemini", raises=_TextError("insufficient quota"))
    local = FakeProvider("ollama", response_text="should not be reached")
    router = ModelRouter(providers=[cloud, local])

    try:
        router.chat("auto", "sys", _MSG, db=db_session)
        raise AssertionError("expected NoProviderAvailableError")
    except NoProviderAvailableError:
        pass
    assert local.chat_call_count == 0


# 12. Streaming: a provider in cooldown is skipped before any chunk is requested.
def test_stream_skips_provider_in_cooldown_before_first_chunk(db_session):
    usage.set_cooldown(db_session, "gemini", "rate_limited")
    first = FakeProvider("gemini", stream_chunks=["would have streamed"])
    second = FakeProvider("ollama", stream_chunks=["from ollama"])
    router = ModelRouter(providers=[first, second])

    chunks = list(router.stream_chat("auto", "sys", _MSG, db=db_session))

    assert [c[0] for c in chunks] == ["from ollama"]
    assert first.stream_call_count == 0


# 13. Streaming: cloud failure -> Ollama success carries the exact fallback note.
def test_stream_falls_back_to_ollama_with_exact_note(db_session):
    first = FakeProvider("gemini", raises=_TextError("insufficient quota"), stream_raises_after=0)
    second = FakeProvider("ollama", stream_chunks=["from ollama"])
    router = ModelRouter(providers=[first, second])

    chunks = list(router.stream_chat("auto", "sys", _MSG, db=db_session))

    assert chunks[0][2] == "Cloud providers were unavailable or quota-limited, so Echo replied using Ollama."
    assert usage.get_active_cooldown(db_session, "gemini").category == "quota_exceeded"


# 14. GET /api/features reports the cooldown category as the provider's status,
#     and reports Ollama as "available_local" rather than a bare "available".
init_db()
client = TestClient(app)


def test_features_endpoint_reports_cooldown_category_and_local_ollama(monkeypatch):
    fake_router = ModelRouter(
        providers=[
            FakeProvider("gemini", available=True),
            FakeProvider("ollama", available=True),
        ]
    )
    monkeypatch.setattr("app.routers.features.model_router", fake_router)

    from app.db import SessionLocal

    session = SessionLocal()
    try:
        usage.set_cooldown(session, "gemini", "quota_exceeded")
    finally:
        session.close()

    resp = client.get("/api/features")
    assert resp.status_code == 200
    body = resp.json()

    assert body["providers"]["gemini"] == "quota_exceeded"
    assert body["providers"]["ollama"] == "available_local"
    assert body["vision"]["available"] is False
    assert "quota exceeded" in body["vision"]["reason"].lower()
