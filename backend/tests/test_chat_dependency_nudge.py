"""Route-level test for Goal 12: /api/chat surfaces independence_nudge_reason
end-to-end (persona.build_system_prompt -> chat route -> response + stored
Message row), using a FakeProvider so no real API calls happen.
"""

from fastapi.testclient import TestClient

from app.main import app
from app.router import ModelRouter
from tests.fake_providers import FakeProvider


def test_repeated_decide_for_me_sets_nudge_reason_on_second_turn(monkeypatch):
    fake_router = ModelRouter(providers=[FakeProvider("ollama", response_text="ok")])
    monkeypatch.setattr("app.routers.chat.model_router", fake_router)

    with TestClient(app) as client:
        first = client.post(
            "/api/chat", json={"message": "You decide, I don't mind either way.", "provider": "auto"}
        )
        assert first.status_code == 200
        conversation_id = first.json()["conversation_id"]
        assert first.json()["independence_nudge_reason"] is None  # only one occurrence so far

        second = client.post(
            "/api/chat",
            json={
                "message": "Just you choose, whatever you think is best.",
                "provider": "auto",
                "conversation_id": conversation_id,
            },
        )

    assert second.status_code == 200
    body = second.json()
    assert body["independence_nudge_reason"] == "decide_for_me"

    with TestClient(app) as client:
        detail = client.get(f"/api/conversations/{conversation_id}")
    echo_messages = [m for m in detail.json()["messages"] if m["role"] == "echo"]
    assert echo_messages[-1]["independence_nudge_reason"] == "decide_for_me"


def test_no_pattern_leaves_nudge_reason_none(monkeypatch):
    fake_router = ModelRouter(providers=[FakeProvider("ollama", response_text="ok")])
    monkeypatch.setattr("app.routers.chat.model_router", fake_router)

    with TestClient(app) as client:
        resp = client.post("/api/chat", json={"message": "What's a good book to read?", "provider": "auto"})

    assert resp.status_code == 200
    assert resp.json()["independence_nudge_reason"] is None
