"""Tests for Goal 18b Part 6: the conversation detail API must expose the data
the frontend's Reasoning/Atlas-notes UI needs — reasoning and conversation
snippets are already stored on Message (see models.py), this just confirms
they round-trip through GET /api/conversations/{id}.
"""

from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app
from app.router import ModelRouter
from tests.fake_providers import FakeProvider

init_db()
client = TestClient(app)


def test_conversation_detail_includes_reasoning(monkeypatch):
    provider = FakeProvider("ollama", stream_chunks=["REASONING: because reasons\nANSWER: hi\nMEMORY: NONE"])
    monkeypatch.setattr("app.routers.chat.model_router", ModelRouter(providers=[provider]))

    create = client.post("/api/chat/stream", json={"message": "hello", "provider": "auto"})
    conversation_id = None
    for block in create.text.strip().split("\n\n"):
        if block.startswith("event: done"):
            import json

            data = json.loads(block.split("data: ", 1)[1])
            conversation_id = data["conversation_id"]

    assert conversation_id is not None
    detail = client.get(f"/api/conversations/{conversation_id}")
    echo_messages = [m for m in detail.json()["messages"] if m["role"] == "echo"]
    assert echo_messages[-1]["reasoning"] == "because reasons"


def test_conversation_detail_includes_conversation_snippets_field(monkeypatch):
    provider = FakeProvider("ollama", response_text="a plain reply")
    monkeypatch.setattr("app.routers.chat.model_router", ModelRouter(providers=[provider]))

    resp = client.post("/api/chat", json={"message": "just a normal question", "provider": "auto"})
    conversation_id = resp.json()["conversation_id"]

    detail = client.get(f"/api/conversations/{conversation_id}")
    echo_messages = [m for m in detail.json()["messages"] if m["role"] == "echo"]
    # Field must exist and be a list — empty here since no recall phrase was used.
    assert echo_messages[-1]["conversation_snippets"] == []
