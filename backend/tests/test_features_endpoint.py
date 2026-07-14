"""Tests for Goal 18b Part 5: GET /api/features — tells the frontend which
features actually work right now so it can disable things cleanly instead of
letting the user hit a failure. No real provider calls: FakeProvider throughout.
"""

from fastapi.testclient import TestClient

from app.db import init_db
from app.image_router import ImageProviderStatus
from app.main import app
from app.router import ModelRouter
from tests.fake_providers import FakeProvider

init_db()
client = TestClient(app)

_UNAVAILABLE_IMAGE_STATUSES = {
    "gemini": ImageProviderStatus(False, "GEMINI_API_KEY not set"),
    "ollama": ImageProviderStatus(False, "Ollama does not support image generation in this build"),
    "comfyui": ImageProviderStatus(False, "COMFYUI_BASE_URL not set"),
}


def test_image_generation_false_when_gemini_not_configured(monkeypatch):
    fake_router = ModelRouter(
        providers=[FakeProvider("gemini", available=False, unavailable_reason="GEMINI_API_KEY not set")]
    )
    monkeypatch.setattr("app.routers.features.model_router", fake_router)
    # image_generation is driven by app.image_router (Phase 6), independent of
    # the chat/vision provider mock above — patch it too so this test isn't
    # accidentally dependent on the real GEMINI_API_KEY in the dev .env.
    monkeypatch.setattr(
        "app.routers.features.image_router.select_provider", lambda: (None, "GEMINI_API_KEY not set")
    )
    monkeypatch.setattr(
        "app.routers.features.image_router.statuses", lambda: _UNAVAILABLE_IMAGE_STATUSES
    )

    resp = client.get("/api/features")
    assert resp.status_code == 200
    body = resp.json()

    assert body["image_generation"] is False
    assert body["vision"]["available"] is False
    assert body["vision"]["provider"] == "gemini"
    assert "not set" in body["vision"]["reason"].lower()
    assert body["providers"]["gemini"] == "not_configured"
    assert body["image_generation_detail"]["active_provider"] is None
    # image_generation_detail.providers is per-provider API/log detail, never
    # rendered directly by the frontend (see ChatView.tsx) — raw reason text
    # like this is fine here.
    assert body["image_generation_detail"]["providers"]["gemini"] == "GEMINI_API_KEY not set"
    # .reason, by contrast, IS what the chat "+" menu displays directly — it
    # must never contain a raw env var/config name (regression test: this
    # used to interpolate select_provider()'s raw reason unchanged).
    assert "GEMINI_API_KEY" not in body["image_generation_detail"]["reason"]
    assert "COMFYUI_BASE_URL" not in body["image_generation_detail"]["reason"]


def test_image_generation_true_when_gemini_configured(monkeypatch):
    fake_router = ModelRouter(providers=[FakeProvider("gemini", available=True)])
    monkeypatch.setattr("app.routers.features.model_router", fake_router)
    monkeypatch.setattr("app.routers.features.image_router.select_provider", lambda: ("gemini", None))
    monkeypatch.setattr(
        "app.routers.features.image_router.statuses",
        lambda: {**_UNAVAILABLE_IMAGE_STATUSES, "gemini": ImageProviderStatus(True, None)},
    )

    resp = client.get("/api/features")
    body = resp.json()

    assert body["image_generation"] is True
    assert body["vision"]["available"] is True
    assert body["providers"]["gemini"] == "available"
    assert body["image_generation_detail"]["active_provider"] == "gemini"


def test_chat_false_when_no_providers_available(monkeypatch):
    fake_router = ModelRouter(
        providers=[FakeProvider("ollama", available=False, unavailable_reason="Ollama not reachable")]
    )
    monkeypatch.setattr("app.routers.features.model_router", fake_router)

    resp = client.get("/api/features")
    assert resp.json()["chat"] is False


def test_chat_true_when_at_least_one_provider_available(monkeypatch):
    fake_router = ModelRouter(
        providers=[
            FakeProvider("gemini", available=False, unavailable_reason="GEMINI_API_KEY not set"),
            FakeProvider("ollama", available=True),
        ]
    )
    monkeypatch.setattr("app.routers.features.model_router", fake_router)

    resp = client.get("/api/features")
    assert resp.json()["chat"] is True


def test_voice_and_file_upload_always_reported_available(monkeypatch):
    fake_router = ModelRouter(providers=[FakeProvider("gemini", available=False, unavailable_reason="no key")])
    monkeypatch.setattr("app.routers.features.model_router", fake_router)

    resp = client.get("/api/features")
    body = resp.json()
    assert body["voice_input"] is True  # browser-native, not a backend concern
    assert body["file_upload"] is True  # attachments are always stored
