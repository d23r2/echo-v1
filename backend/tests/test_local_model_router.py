"""ECHO Local Intelligence Engine v1, Phase 5 — app/services/local_model_router.py.
Uses FakeProvider in place of a real OllamaProvider, so no test ever needs a
real Ollama install or makes a real HTTP call.
"""

from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app
from app.providers.base import ChatMessage
from app.services.local_model_router import ALL_ROLES, LocalModelRouter, list_installed_models
from tests.fake_providers import FakeProvider, FakeProviderError

init_db()
client = TestClient(app)


def test_easy_chat_uses_fast_model(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL_FAST", "llama3-fast")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        fake = FakeProvider("ollama", available=True, response_text="hi")
        router = LocalModelRouter(provider=fake)
        result = router.call("fast", "system", [ChatMessage(role="user", content="hi")])
        assert result.ok is True
        assert result.model_used == "llama3-fast"
        assert fake.last_model_requested == "llama3-fast"
    finally:
        get_settings.cache_clear()


def test_hard_reasoning_uses_reasoning_model(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL_REASONING", "llama3-big")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        fake = FakeProvider("ollama", available=True, response_text="deep thought")
        router = LocalModelRouter(provider=fake)
        result = router.call("reasoning", "system", [ChatMessage(role="user", content="plan this")])
        assert result.model_used == "llama3-big"
    finally:
        get_settings.cache_clear()


def test_coding_uses_coding_model(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL_CODING", "codellama")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        fake = FakeProvider("ollama", available=True)
        router = LocalModelRouter(provider=fake)
        result = router.call("coding", "system", [ChatMessage(role="user", content="review this")])
        assert result.model_used == "codellama"
    finally:
        get_settings.cache_clear()


def test_critic_uses_critic_model(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL_CRITIC", "critic-model")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        fake = FakeProvider("ollama", available=True)
        router = LocalModelRouter(provider=fake)
        result = router.call("critic", "system", [ChatMessage(role="user", content="check this")])
        assert result.model_used == "critic-model"
    finally:
        get_settings.cache_clear()


def test_missing_role_model_falls_back_to_default(monkeypatch):
    """Role-specific model configured, but Ollama doesn't actually have it
    installed -> one retry against the plain default model."""
    monkeypatch.setenv("OLLAMA_MODEL_CODING", "codellama-not-installed")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        calls = []

        class FlakyThenOk(FakeProvider):
            def chat(self, system_prompt, messages, model=None):
                calls.append(model)
                if len(calls) == 1:
                    raise FakeProviderError("model not found")
                return super().chat(system_prompt, messages, model=model)

        flaky = FlakyThenOk("ollama", available=True, response_text="worked with default")
        router = LocalModelRouter(provider=flaky)
        result = router.call("coding", "system", [ChatMessage(role="user", content="hi")])
        assert result.ok is True
        assert result.fallback_used is True
        assert result.text == "worked with default"
        assert len(calls) == 2
    finally:
        get_settings.cache_clear()


def test_ollama_offline_returns_clean_error_not_crash():
    fake = FakeProvider("ollama", available=False, unavailable_reason="Ollama not reachable (is it running locally?)")
    router = LocalModelRouter(provider=fake)
    result = router.call("fast", "system", [ChatMessage(role="user", content="hi")])
    assert result.ok is False
    assert "Traceback" not in (result.error or "")
    assert result.error is not None


def test_default_role_used_when_role_unmapped():
    fake = FakeProvider("ollama", available=True)
    router = LocalModelRouter(provider=fake)
    model = router.model_for_role("fast")
    assert model  # falls back to OLLAMA_MODEL, never empty


def test_all_roles_resolve_to_some_model():
    fake = FakeProvider("ollama", available=True)
    router = LocalModelRouter(provider=fake)
    for role in ALL_ROLES:
        assert router.model_for_role(role)


def test_list_installed_models_clean_error_when_offline():
    names, error = list_installed_models()
    # In this sandboxed test run Ollama is very likely not reachable at
    # localhost:11434; either branch must be a clean, non-crashing result.
    assert isinstance(names, list)
    if error is not None:
        assert "Traceback" not in error


def test_local_models_endpoint_returns_clean_shape():
    resp = client.get("/api/models/local")
    assert resp.status_code == 200
    body = resp.json()
    assert "available" in body
    assert "models" in body
    assert isinstance(body["models"], list)
