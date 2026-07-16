"""Phase 3: FREE_MODE provider ordering + Azure OpenAI safe-by-default usage.

No real Azure/OpenAI calls anywhere — AzureOpenAIProvider itself is only
imported for its available()/name/label; wherever a chat() call is needed a
FakeProvider stands in for "azure" so nothing touches the network or needs a
real endpoint/key. FREE_MODE and Azure settings are overridden via
monkeypatching app.router.get_settings, not real env vars, so tests never
depend on a .env file.
"""

from types import SimpleNamespace

from app import usage
from app.providers.azure_openai_provider import AzureOpenAIProvider
from app.providers.base import ChatMessage
from app.router import ModelRouter, NoProviderAvailableError
from tests.fake_providers import FakeProvider, FakeProviderError

_MSG = [ChatMessage(role="user", content="hi")]


def _free_mode_settings(**overrides):
    base = dict(
        free_mode=True,
        ollama_always_available_fallback=True,
        azure_daily_request_limit=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# 1. Azure is unavailable out of the box — disabled by default, no config needed.
def test_azure_provider_unavailable_by_default():
    available, reason = AzureOpenAIProvider().available()
    assert available is False
    assert "disabled" in reason.lower()


# 2. Azure stays unavailable even with AZURE_OPENAI_ENABLED=true if endpoint/key/deployment are missing.
def test_azure_provider_unavailable_when_enabled_but_incomplete(monkeypatch):
    monkeypatch.setattr(
        "app.providers.azure_openai_provider.get_settings",
        lambda: SimpleNamespace(
            azure_openai_enabled=True,
            azure_openai_endpoint=None,
            azure_openai_api_key=None,
            azure_openai_deployment=None,
        ),
    )
    available, reason = AzureOpenAIProvider().available()
    assert available is False
    assert "endpoint" in reason.lower()


# 3. FREE_MODE prefers Ollama first, ahead of Gemini, even though normal auto
#    order would try Gemini as a top-tier cloud provider.
def test_free_mode_prefers_ollama_first(monkeypatch, db_session):
    monkeypatch.setattr("app.router.get_settings", _free_mode_settings)
    ollama = FakeProvider("ollama", response_text="local first")
    gemini = FakeProvider("gemini", response_text="cloud")
    router = ModelRouter(providers=[ollama, gemini])

    result, provider_used, fallback_note = router.chat("auto", "sys", _MSG, db=db_session)

    assert provider_used == "ollama"
    assert result.text == "local first"
    assert fallback_note is None  # ollama winning immediately isn't a "fallback"
    assert gemini.chat_call_count == 0


# 4. FREE_MODE excludes paid-only providers (anthropic/openai/grok) from auto
#    mode entirely, even when their keys are configured — only Ollama/Gemini/
#    Azure participate.
def test_free_mode_excludes_paid_only_providers_from_auto_chain(monkeypatch, db_session):
    monkeypatch.setattr("app.router.get_settings", _free_mode_settings)
    ollama = FakeProvider("ollama", raises=FakeProviderError("down"))
    anthropic = FakeProvider("anthropic", response_text="should not be reached")
    gemini = FakeProvider("gemini", response_text="free tier reply")
    router = ModelRouter(providers=[ollama, anthropic, gemini])

    result, provider_used, _ = router.chat("auto", "sys", _MSG, db=db_session)

    assert provider_used == "gemini"
    assert anthropic.chat_call_count == 0


# 5. FREE_MODE still reaches an explicitly-pinned paid provider — the
#    exclusion only applies to auto mode's own chain.
def test_free_mode_pinned_paid_provider_still_works(monkeypatch, db_session):
    monkeypatch.setattr("app.router.get_settings", _free_mode_settings)
    anthropic = FakeProvider("anthropic", response_text="pinned reply")
    router = ModelRouter(providers=[anthropic])

    result, provider_used, _ = router.chat("anthropic", "sys", _MSG, db=db_session)

    assert provider_used == "anthropic"
    assert result.text == "pinned reply"


# 6. FREE_MODE uses a configured, working Azure provider as a fallback when
#    Ollama and Gemini both fail.
def test_free_mode_falls_back_to_azure_when_ollama_and_gemini_fail(monkeypatch, db_session):
    monkeypatch.setattr("app.router.get_settings", _free_mode_settings)
    ollama_fail = FakeProvider("ollama", raises=FakeProviderError("down"))
    gemini_fail = FakeProvider("gemini", raises=FakeProviderError("also down"))
    azure = FakeProvider("azure", response_text="azure reply")
    router = ModelRouter(providers=[ollama_fail, gemini_fail, azure])

    result, provider_used, _ = router.chat("auto", "sys", _MSG, db=db_session)

    assert provider_used == "azure"
    assert result.text == "azure reply"


# 7. Azure's own daily request cap (AZURE_DAILY_REQUEST_LIMIT) is enforced by
#    the router — once reached, Azure is skipped like an unconfigured provider,
#    and the final Ollama-again slot in FREE_MODE's chain picks it up.
def test_azure_skipped_once_daily_request_limit_reached(monkeypatch, db_session):
    monkeypatch.setattr(
        "app.router.get_settings", lambda: _free_mode_settings(azure_daily_request_limit=2)
    )
    usage.record_request(db_session, "azure")
    usage.record_request(db_session, "azure")  # 2 requests already used today

    ollama_fail = FakeProvider("ollama", raises=FakeProviderError("down"))
    gemini_fail = FakeProvider("gemini", raises=FakeProviderError("also down"))
    azure = FakeProvider("azure", response_text="should be skipped")
    ollama_retry = ollama_fail  # same object tried twice in the free-mode chain
    router = ModelRouter(providers=[ollama_fail, gemini_fail, azure])

    try:
        router.chat("auto", "sys", _MSG, db=db_session)
        raise AssertionError("expected NoProviderAvailableError")
    except NoProviderAvailableError:
        pass
    assert azure.chat_call_count == 0
    assert ollama_retry.chat_call_count == 2  # tried first, then again as the final fallback slot


# 8. GET /api/features reports Azure's daily-limit-reached state distinctly
#    from a plain "unavailable"/"not_configured".
def test_features_endpoint_reports_azure_daily_limit_reached(monkeypatch):
    from fastapi.testclient import TestClient

    from app.db import SessionLocal, init_db
    from app.main import app

    init_db()
    client = TestClient(app)

    fake_router = ModelRouter(providers=[FakeProvider("azure", available=True)])
    monkeypatch.setattr("app.routers.features.model_router", fake_router)
    monkeypatch.setattr(
        "app.routers.features.get_settings",
        lambda: SimpleNamespace(
            azure_daily_request_limit=1,
            web_search_enabled=False,
            web_search_provider="searxng",
            searxng_base_url=None,
            wiki_search_enabled=True,
            wiki_provider="wikimedia",
            rss_search_enabled=False,
            rss_feed_url_list=[],
        ),
    )

    session = SessionLocal()
    try:
        usage.clear_cooldown(session, "azure")
        usage.record_request(session, "azure")
    finally:
        session.close()

    resp = client.get("/api/features")
    assert resp.status_code == 200
    assert resp.json()["providers"]["azure"] == "daily_limit_reached"
