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
    # image_router.select_provider() must resolve to "gemini" for this test to
    # reach gemini_provider.generate_image() at all — it otherwise depends on
    # whether GEMINI_API_KEY happens to be set in the real backend/.env, which
    # in turn depends on pydantic-settings' CWD-relative env_file lookup (so
    # this test previously passed or failed depending on whether pytest was
    # invoked from backend/ or the repo root — the exact opposite of a
    # deterministic, no-real-keys-required test). Monkeypatching the router's
    # own selection decouples this test from any real environment/CWD state.
    monkeypatch.setattr("app.routers.chat.image_router.select_provider", lambda: ("gemini", None))

    def _raise_not_configured(prompt: str) -> bytes:
        raise RuntimeError("GEMINI_API_KEY not set")

    monkeypatch.setattr("app.routers.chat.gemini_provider.generate_image", _raise_not_configured)

    resp = client.post("/api/chat/generate-image", data={"prompt": "a cat"})

    assert resp.status_code == 502
    assert resp.json()["detail"] == "Image generation is unavailable — Gemini isn't configured."


def test_image_generation_api_failure_returns_clean_error_not_raw(monkeypatch):
    # See test_image_generation_unconfigured_returns_clean_error's comment —
    # same fix, same reason.
    monkeypatch.setattr("app.routers.chat.image_router.select_provider", lambda: ("gemini", None))

    def _raise_api_error(prompt: str) -> bytes:
        raise RuntimeError(_RAW_TECHNICAL_STRING)

    monkeypatch.setattr("app.routers.chat.gemini_provider.generate_image", _raise_api_error)

    resp = client.post("/api/chat/generate-image", data={"prompt": "a cat"})

    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert _RAW_TECHNICAL_STRING not in detail
    assert detail == "Image generation is unavailable right now."


def test_image_generation_no_provider_configured_hides_env_var_names(monkeypatch):
    """Regression test: image_router.select_provider()'s reason for "nothing
    is configured" is 'No image generation provider is available (configure
    GEMINI_API_KEY or COMFYUI_BASE_URL)' — genuinely useful in server logs,
    but that raw string was previously interpolated straight into this
    endpoint's HTTP response, putting literal env var names in front of the
    user. Must now go through image_router.clean_unavailable_reason()."""
    monkeypatch.setattr(
        "app.routers.chat.image_router.select_provider",
        lambda: (None, "No image generation provider is available (configure GEMINI_API_KEY or COMFYUI_BASE_URL)"),
    )

    resp = client.post("/api/chat/generate-image", data={"prompt": "a cat"})

    assert resp.status_code == 502
    detail = resp.json()["detail"]
    assert "GEMINI_API_KEY" not in detail
    assert "COMFYUI_BASE_URL" not in detail
    assert detail == "Image generation is unavailable — Image generation isn't configured yet."
