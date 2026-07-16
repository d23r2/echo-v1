"""ECHO Local Intelligence Engine v1, Phase 13 — integration into
POST /api/chat behind LOCAL_INTELLIGENCE_ENGINE_ENABLED. Confirms: the flag
defaults off and existing chat is untouched; the flag-on path actually
routes through the engine (no real Ollama call — FakeProvider swapped in);
POST /api/chat/stream is never affected by the flag either way; metadata
stays clean.
"""

from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app
from app.router import ModelRouter
from app.services.local_model_router import LocalModelRouter
from tests.fake_providers import FakeProvider

init_db()
client = TestClient(app)


def test_flag_off_by_default_existing_chat_path_used(monkeypatch):
    fake_router = ModelRouter(providers=[FakeProvider("gemini", available=True, response_text="a normal reply")])
    monkeypatch.setattr("app.routers.chat.model_router", fake_router)

    resp = client.post("/api/chat", json={"message": "hello there"})
    assert resp.status_code == 200
    assert resp.json()["provider_used"] == "gemini"  # went through the old path, not the engine


def test_flag_on_routes_through_engine_when_provider_is_auto_or_ollama(monkeypatch):
    monkeypatch.setenv("LOCAL_INTELLIGENCE_ENGINE_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        fake_ollama = FakeProvider("ollama", available=True, response_text="Entropy is a measure of disorder.")
        monkeypatch.setattr(
            "app.services.local_intelligence_engine.LocalModelRouter",
            lambda *a, **k: LocalModelRouter(provider=fake_ollama),
        )

        resp = client.post("/api/chat", json={"message": "Explain entropy simply.", "provider": "auto"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["provider_used"] == "ollama"
        assert "Entropy" in body["content"]
        assert fake_ollama.chat_call_count >= 1
    finally:
        get_settings.cache_clear()


def test_flag_on_but_pinned_to_non_ollama_provider_bypasses_engine(monkeypatch):
    monkeypatch.setenv("LOCAL_INTELLIGENCE_ENGINE_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        fake_router = ModelRouter(providers=[FakeProvider("gemini", available=True, response_text="cloud reply")])
        monkeypatch.setattr("app.routers.chat.model_router", fake_router)

        resp = client.post("/api/chat", json={"message": "hello", "provider": "gemini"})
        assert resp.status_code == 200
        assert resp.json()["provider_used"] == "gemini"
    finally:
        get_settings.cache_clear()


def test_flag_on_response_never_leaks_critic_or_pipeline_debug_text(monkeypatch):
    monkeypatch.setenv("LOCAL_INTELLIGENCE_ENGINE_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        fake_ollama = FakeProvider("ollama", available=True, response_text="A clean answer.")
        monkeypatch.setattr(
            "app.services.local_intelligence_engine.LocalModelRouter",
            lambda *a, **k: LocalModelRouter(provider=fake_ollama),
        )

        resp = client.post("/api/chat", json={"message": "hello there", "provider": "ollama"})
        content = resp.json()["content"]
        assert "pipeline_steps" not in content
        assert "critic" not in content.lower()
        assert "{" not in content
        assert "internal_diagnostics" not in content
    finally:
        get_settings.cache_clear()


def test_streaming_route_unaffected_by_flag(monkeypatch):
    """POST /api/chat/stream must behave identically regardless of the flag
    — the engine only integrates into the non-streaming endpoint for v1."""
    monkeypatch.setenv("LOCAL_INTELLIGENCE_ENGINE_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        fake_router = ModelRouter(providers=[FakeProvider("gemini", available=True, response_text="streamed reply")])
        monkeypatch.setattr("app.routers.chat.model_router", fake_router)

        resp = client.post("/api/chat/stream", json={"message": "hello", "provider": "auto"})
        assert resp.status_code == 200
        # Real SSE body — just confirm it's the normal streaming shape, not
        # a JSON engine response.
        assert "event: token" in resp.text or "event: done" in resp.text
    finally:
        get_settings.cache_clear()


def test_cloud_fallback_gate_reachable_through_chat_endpoint(monkeypatch):
    """Regression test for the app/routers/chat.py wiring: the engine's Cloud
    Fallback Gate has its own settings.cloud_fallback_enabled check, but
    generate_response()'s allow_cloud_fallback parameter also has to be
    passed as True from the real call site, or the gate can never actually
    run no matter how CLOUD_FALLBACK_ENABLED is set (a chat.py bug caught
    during live browser verification, not a hypothetical)."""
    monkeypatch.setenv("LOCAL_INTELLIGENCE_ENGINE_ENABLED", "true")
    monkeypatch.setenv("CLOUD_FALLBACK_ENABLED", "true")
    monkeypatch.setenv("CLOUD_FALLBACK_REQUIRE_USER_CONFIRMATION", "false")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        fake_ollama = FakeProvider("ollama", available=True, response_text="a low-confidence local answer")
        monkeypatch.setattr(
            "app.services.local_intelligence_engine.LocalModelRouter",
            lambda *a, **k: LocalModelRouter(provider=fake_ollama),
        )

        class FakeCloudResult:
            text = "a cloud answer"

        def fake_cloud_chat(preferred, system_prompt, history, db=None):
            return FakeCloudResult(), "gemini", None

        fake_cloud_router = ModelRouter(providers=[])
        monkeypatch.setattr(fake_cloud_router, "chat", fake_cloud_chat)
        monkeypatch.setattr("app.router.router", fake_cloud_router)

        resp = client.post("/api/chat", json={"message": "Review this code for bugs", "provider": "auto"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["provider_used"] == "gemini"
        assert body["content"] == "a cloud answer"
        assert body["fallback_note"] == "Answered via cloud fallback (local confidence was low)."
    finally:
        get_settings.cache_clear()


def test_local_intelligence_settings_endpoint_clean_shape():
    resp = client.get("/api/local-intelligence/settings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["local_intelligence_engine_enabled"] is False  # default off
    assert body["cloud_fallback_enabled"] is False  # default off
    assert "installed_models" in body
    assert isinstance(body["installed_models"], list)


def test_persona_settings_quality_mode_defaults_and_updates():
    import uuid

    tid = f"quality-mode-tester-{uuid.uuid4().hex[:8]}"
    resp = client.get("/api/persona-settings", headers={"X-Tester-Id": tid})
    assert resp.json()["local_answer_quality_mode"] == "balanced"

    patch_resp = client.patch(
        "/api/persona-settings", json={"local_answer_quality_mode": "deep"}, headers={"X-Tester-Id": tid}
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["local_answer_quality_mode"] == "deep"
