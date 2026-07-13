"""Tests for Goal 14: honest attachment status labels + auto-routing image turns
to Gemini when available. No real provider calls — FakeProvider throughout.
"""

import io

from fastapi.testclient import TestClient

from app import attachments as attachments_lib
from app.db import init_db
from app.main import app
from app.router import ModelRouter
from tests.fake_providers import FakeProvider

init_db()
client = TestClient(app)


# ---- determine_analysis_status() — pure function ----


def test_unsupported_when_not_understood():
    status = attachments_lib.determine_analysis_status(
        mime_type="application/x-msdownload", understood=False, extracted=None, vision_capable=False
    )
    assert status == "unsupported"


def test_image_with_vision_capable_provider_is_vision_analyzed():
    status = attachments_lib.determine_analysis_status(
        mime_type="image/png", understood=True, extracted=None, vision_capable=True
    )
    assert status == "vision_analyzed"


def test_image_without_vision_capable_provider_is_stored_not_understood_lie():
    status = attachments_lib.determine_analysis_status(
        mime_type="image/png", understood=True, extracted=None, vision_capable=False
    )
    assert status == "stored"


def test_text_file_with_extracted_content_is_text_extracted():
    status = attachments_lib.determine_analysis_status(
        mime_type="text/plain", understood=True, extracted="hello world", vision_capable=False
    )
    assert status == "text_extracted"


def test_audio_file_is_stored_not_analyzed():
    status = attachments_lib.determine_analysis_status(
        mime_type="audio/mpeg", understood=True, extracted=None, vision_capable=False
    )
    assert status == "stored"


# ---- /api/chat/send-with-files — route-level, real image bytes, fake providers ----

_TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100e2216bc70000000049454e44ae426082"
)


def test_auto_mode_routes_image_turn_to_gemini_when_available(monkeypatch):
    gemini = FakeProvider("gemini", response_text="I see the image")
    ollama = FakeProvider("ollama", response_text="text only reply")
    fake_router = ModelRouter(providers=[gemini, ollama])
    monkeypatch.setattr("app.routers.chat.model_router", fake_router)

    resp = client.post(
        "/api/chat/send-with-files",
        data={"message": "what is this?", "provider": "auto"},
        files={"files": ("pic.png", io.BytesIO(_TINY_PNG), "image/png")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["message"]["provider"] == "gemini"
    assert gemini.chat_call_count == 1
    assert ollama.chat_call_count == 0
    attachment = body["message"]["attachments"][0]
    assert attachment["analysis_status"] == "vision_analyzed"


def test_auto_mode_with_image_falls_back_honestly_when_gemini_unavailable(monkeypatch):
    ollama = FakeProvider("ollama", response_text="text only reply")
    fake_router = ModelRouter(providers=[ollama])
    monkeypatch.setattr("app.routers.chat.model_router", fake_router)

    resp = client.post(
        "/api/chat/send-with-files",
        data={"message": "what is this?", "provider": "auto"},
        files={"files": ("pic.png", io.BytesIO(_TINY_PNG), "image/png")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["message"]["provider"] == "ollama"
    attachment = body["message"]["attachments"][0]
    assert attachment["analysis_status"] == "stored"


def test_explicit_pin_to_non_vision_provider_is_not_silently_overridden(monkeypatch):
    gemini = FakeProvider("gemini", response_text="should not be used")
    ollama = FakeProvider("ollama", response_text="text only reply")
    fake_router = ModelRouter(providers=[gemini, ollama])
    monkeypatch.setattr("app.routers.chat.model_router", fake_router)

    resp = client.post(
        "/api/chat/send-with-files",
        data={"message": "what is this?", "provider": "ollama"},
        files={"files": ("pic.png", io.BytesIO(_TINY_PNG), "image/png")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["message"]["provider"] == "ollama"
    assert gemini.chat_call_count == 0
    attachment = body["message"]["attachments"][0]
    assert attachment["analysis_status"] == "stored"


def test_text_attachment_reports_text_extracted(monkeypatch):
    fake_router = ModelRouter(providers=[FakeProvider("ollama", response_text="ok")])
    monkeypatch.setattr("app.routers.chat.model_router", fake_router)

    resp = client.post(
        "/api/chat/send-with-files",
        data={"message": "summarize this", "provider": "auto"},
        files={"files": ("notes.txt", io.BytesIO(b"hello world"), "text/plain")},
    )
    assert resp.status_code == 200
    attachment = resp.json()["message"]["attachments"][0]
    assert attachment["analysis_status"] == "text_extracted"


def test_unsupported_attachment_reports_unsupported(monkeypatch):
    fake_router = ModelRouter(providers=[FakeProvider("ollama", response_text="ok")])
    monkeypatch.setattr("app.routers.chat.model_router", fake_router)

    resp = client.post(
        "/api/chat/send-with-files",
        data={"message": "what is this file", "provider": "auto"},
        files={"files": ("archive.bin", io.BytesIO(b"\x00\x01\x02"), "application/octet-stream")},
    )
    assert resp.status_code == 200
    attachment = resp.json()["message"]["attachments"][0]
    assert attachment["analysis_status"] == "unsupported"
