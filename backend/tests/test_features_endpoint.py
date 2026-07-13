"""Tests for Goal 18b Part 5: GET /api/features — tells the frontend which
features actually work right now so it can disable things cleanly instead of
letting the user hit a failure. No real provider calls: FakeProvider throughout.
"""

from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app
from app.router import ModelRouter
from tests.fake_providers import FakeProvider

init_db()
client = TestClient(app)


def test_image_generation_false_when_gemini_not_configured(monkeypatch):
    fake_router = ModelRouter(
        providers=[FakeProvider("gemini", available=False, unavailable_reason="GEMINI_API_KEY not set")]
    )
    monkeypatch.setattr("app.routers.features.model_router", fake_router)

    resp = client.get("/api/features")
    assert resp.status_code == 200
    body = resp.json()

    assert body["image_generation"] is False
    assert body["vision"]["available"] is False
    assert body["vision"]["provider"] == "gemini"
    assert "not set" in body["vision"]["reason"].lower()
    assert body["providers"]["gemini"] == "not_configured"


def test_image_generation_true_when_gemini_configured(monkeypatch):
    fake_router = ModelRouter(providers=[FakeProvider("gemini", available=True)])
    monkeypatch.setattr("app.routers.features.model_router", fake_router)

    resp = client.get("/api/features")
    body = resp.json()

    assert body["image_generation"] is True
    assert body["vision"]["available"] is True
    assert body["providers"]["gemini"] == "available"


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
