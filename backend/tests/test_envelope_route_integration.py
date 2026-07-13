"""Route-level tests for Phase 1: envelope_status/envelope_degradation_reason
round-trip through /api/chat, /api/chat/stream, and GET /api/conversations/{id}
(confirming they survive a reload, not just the immediate response).
"""

from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app
from app.router import ModelRouter
from tests.fake_providers import FakeProvider

init_db()
client = TestClient(app)


def test_chat_response_includes_envelope_status(monkeypatch):
    provider = FakeProvider("ollama", response_text="plain answer, no envelope at all")
    monkeypatch.setattr("app.routers.chat.model_router", ModelRouter(providers=[provider]))

    resp = client.post("/api/chat", json={"message": "hi", "provider": "auto"})
    body = resp.json()

    assert body["envelope_status"] == "missing"
    assert body["envelope_degradation_reason"] is not None
    assert body["reasoning"] is None  # never invented


def test_envelope_status_persists_across_conversation_reload(monkeypatch):
    provider = FakeProvider("ollama", response_text="plain answer, no envelope at all")
    monkeypatch.setattr("app.routers.chat.model_router", ModelRouter(providers=[provider]))

    resp = client.post("/api/chat", json={"message": "hi", "provider": "auto"})
    conversation_id = resp.json()["conversation_id"]

    detail = client.get(f"/api/conversations/{conversation_id}")
    echo_messages = [m for m in detail.json()["messages"] if m["role"] == "echo"]
    assert echo_messages[-1]["envelope_status"] == "missing"
    assert echo_messages[-1]["envelope_degradation_reason"] is not None
    assert echo_messages[-1]["reasoning"] is None


def test_stream_done_event_includes_envelope_status(monkeypatch):
    provider = FakeProvider("ollama", stream_chunks=["REASONING: ok\nANSWER: hi\nMEMORY: NONE"])
    monkeypatch.setattr("app.routers.chat.model_router", ModelRouter(providers=[provider]))

    resp = client.post("/api/chat/stream", json={"message": "hi", "provider": "auto"})
    assert '"envelope_status": "complete"' in resp.text
