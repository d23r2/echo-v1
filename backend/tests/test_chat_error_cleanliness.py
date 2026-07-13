"""Tests for Goal 18b Part 1/6: chat and image-generation failures must never
surface raw provider/API exception text to the user — only a clean, generic
message. Full technical detail still reaches server logs (see router.py's
logger.warning calls), just not the HTTP response body.
"""

from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app
from app.router import ModelRouter
from tests.fake_providers import FakeProvider, FakeProviderError

init_db()
client = TestClient(app)

_RAW_TECHNICAL_STRING = "Traceback: Error code 401 raw-secret-looking-token-abc123 at socket 0x7f"


def test_no_providers_available_hides_raw_exception_text(monkeypatch):
    failing = FakeProvider("gemini", raises=FakeProviderError(_RAW_TECHNICAL_STRING))
    fake_router = ModelRouter(providers=[failing])
    monkeypatch.setattr("app.routers.chat.model_router", fake_router)

    resp = client.post("/api/chat", json={"message": "hello", "provider": "auto"})

    assert resp.status_code == 503
    detail = resp.json()["detail"]
    assert _RAW_TECHNICAL_STRING not in detail
    assert detail == (
        "No AI provider is currently available. Cloud providers are unavailable/quota-limited "
        "and Ollama is not running."
    )


def test_pinned_provider_failure_hides_raw_exception_text(monkeypatch):
    failing = FakeProvider("anthropic", raises=FakeProviderError(_RAW_TECHNICAL_STRING))
    fake_router = ModelRouter(providers=[failing])
    monkeypatch.setattr("app.routers.chat.model_router", fake_router)

    resp = client.post("/api/chat", json={"message": "hello", "provider": "anthropic"})

    assert resp.status_code == 503
    detail = resp.json()["detail"]
    assert _RAW_TECHNICAL_STRING not in detail
    assert "Try Auto or another provider" in detail


def test_streaming_no_providers_available_hides_raw_exception_text(monkeypatch):
    failing = FakeProvider("gemini", raises=FakeProviderError(_RAW_TECHNICAL_STRING), stream_raises_after=0)
    fake_router = ModelRouter(providers=[failing])
    monkeypatch.setattr("app.routers.chat.model_router", fake_router)

    resp = client.post("/api/chat/stream", json={"message": "hello", "provider": "auto"})
    assert _RAW_TECHNICAL_STRING not in resp.text


def test_image_generation_unconfigured_returns_clean_error(monkeypatch):
    def _raise_not_configured(prompt: str) -> bytes:
        raise RuntimeError("GEMINI_API_KEY not set")

    monkeypatch.setattr("app.routers.chat.gemini_provider.generate_image", _raise_not_configured)

    resp = client.post("/api/chat/generate-image", data={"prompt": "a cat"})

    assert resp.status_code == 502
    assert resp.json()["detail"] == "Image generation is unavailable — Gemini isn't configured."


def test_image_generation_api_failure_returns_clean_error_not_raw(monkeypatch):
    def _raise_api_error(prompt: str) -> bytes:
        raise RuntimeError(_RAW_TECHNICAL_STRING)

    monkeypatch.setattr("app.routers.chat.gemini_provider.generate_image", _raise_api_error)

    resp = client.post("/api/chat/generate-image", data={"prompt": "a cat"})

    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert _RAW_TECHNICAL_STRING not in detail
    assert detail == "Image generation is unavailable right now."
