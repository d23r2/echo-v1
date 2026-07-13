"""Route-level tests for Goal 11's POST /api/chat/stream — real SSE bytes parsed
back out, using FakeProvider so no real provider calls happen anywhere.
"""

import json

from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app
from app.router import ModelRouter
from tests.fake_providers import FakeProvider, FakeProviderError, FakeRateLimitError

init_db()
client = TestClient(app)


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        if not block.strip():
            continue
        lines = block.splitlines()
        event = next((line[len("event: ") :] for line in lines if line.startswith("event: ")), None)
        data_line = next((line[len("data: ") :] for line in lines if line.startswith("data: ")), None)
        events.append((event, json.loads(data_line) if data_line else {}))
    return events


def test_stream_happy_path_emits_token_events_then_done(monkeypatch):
    provider = FakeProvider(
        "gemini",
        stream_chunks=["REASONING: ok\nANSWER: Hi ", "there\nMEMORY: NONE"],
    )
    monkeypatch.setattr("app.routers.chat.model_router", ModelRouter(providers=[provider]))

    resp = client.post("/api/chat/stream", json={"message": "hello", "provider": "auto"})
    assert resp.status_code == 200
    events = _parse_sse(resp.text)

    token_events = [e for e in events if e[0] == "token"]
    done_events = [e for e in events if e[0] == "done"]
    assert len(done_events) == 1

    streamed_text = "".join(e[1]["text"] for e in token_events)
    assert streamed_text == "Hi there"
    assert done_events[0][1]["content"] == "Hi there"
    assert done_events[0][1]["provider_used"] == "gemini"
    assert done_events[0][1]["reasoning"] == "ok"


def test_memory_content_never_appears_in_token_events(monkeypatch):
    provider = FakeProvider(
        "gemini",
        stream_chunks=[
            'REASONING: ok\nANSWER: Sure.\nMEMORY: {"content": "super secret",',
            ' "epistemic_status": "Hypothesis", "confidence": 0.3, "tags": []}',
        ],
    )
    monkeypatch.setattr("app.routers.chat.model_router", ModelRouter(providers=[provider]))

    resp = client.post("/api/chat/stream", json={"message": "remember something", "provider": "auto"})
    events = _parse_sse(resp.text)

    for event, data in events:
        if event == "token":
            assert "super secret" not in data["text"]
            assert "MEMORY" not in data["text"]


def test_stream_falls_back_to_next_provider_before_first_chunk(monkeypatch):
    first = FakeProvider("gemini", raises=FakeRateLimitError("rate limited"), stream_raises_after=0)
    second = FakeProvider("ollama", stream_chunks=["ANSWER: from ollama\nMEMORY: NONE"])
    monkeypatch.setattr("app.routers.chat.model_router", ModelRouter(providers=[first, second]))

    resp = client.post("/api/chat/stream", json={"message": "hi", "provider": "auto"})
    events = _parse_sse(resp.text)
    done = next(d for e, d in events if e == "done")

    assert done["provider_used"] == "ollama"
    assert done["fallback_note"] == "Cloud providers were unavailable or quota-limited, so Echo replied using Ollama."


def test_stream_emits_error_event_when_no_provider_available(monkeypatch):
    unavailable = FakeProvider("gemini", available=False, unavailable_reason="no key")
    monkeypatch.setattr("app.routers.chat.model_router", ModelRouter(providers=[unavailable]))

    resp = client.post("/api/chat/stream", json={"message": "hi", "provider": "auto"})
    assert resp.status_code == 200  # SSE: errors are in-band, not an HTTP status
    events = _parse_sse(resp.text)

    assert events[-1][0] == "error"
    assert not any(e == "done" for e, _ in events)


def test_stream_saves_conversation_and_messages(monkeypatch):
    provider = FakeProvider("gemini", stream_chunks=["ANSWER: saved reply\nMEMORY: NONE"])
    monkeypatch.setattr("app.routers.chat.model_router", ModelRouter(providers=[provider]))

    resp = client.post("/api/chat/stream", json={"message": "please save this", "provider": "auto"})
    done = next(d for e, d in _parse_sse(resp.text) if e == "done")
    conversation_id = done["conversation_id"]

    detail = client.get(f"/api/conversations/{conversation_id}")
    assert detail.status_code == 200
    messages = detail.json()["messages"]
    assert [m["role"] for m in messages] == ["user", "echo"]
    assert messages[0]["content"] == "please save this"
    assert messages[1]["content"] == "saved reply"


def test_stream_mid_stream_failure_emits_error_without_saving(monkeypatch):
    provider = FakeProvider(
        "gemini",
        raises=FakeProviderError("connection dropped"),
        stream_chunks=["ANSWER: partial", " reply"],
        stream_raises_after=1,
    )
    monkeypatch.setattr("app.routers.chat.model_router", ModelRouter(providers=[provider]))

    resp = client.post(
        "/api/chat/stream", json={"message": "will fail mid-stream", "provider": "auto"}
    )
    events = _parse_sse(resp.text)

    assert events[-1][0] == "error"
    assert not any(e == "done" for e, _ in events)
    # Clean, generic message — never the raw exception text (e.g. "connection
    # dropped") from whatever actually failed underneath.
    assert events[-1][1]["detail"] == "Streaming failed. Please try again."
    assert "connection dropped" not in events[-1][1]["detail"]

    # The partial answer text ("partial reply") must never have been persisted —
    # only the conversation itself gets created up front (before streaming
    # starts), so search by the *answer* text (not the user's own message,
    # which becomes the conversation title regardless of outcome) confirms no
    # echo message was saved.
    search = client.get("/api/chat/search", params={"q": "partial reply"})
    assert search.json() == []


def test_stream_save_failure_after_full_reply_emits_clean_error(monkeypatch):
    """Regression test: the completed-reply-failed-to-save branch (distinct
    from the mid-stream provider failure above — this fires *after* a full
    reply was received, while persisting it) used to interpolate the raw
    exception directly into the SSE error event. It must not leak that text,
    even though the underlying failure (forced here via a monkeypatched
    conversation_search.index_message) can be arbitrary internal detail."""
    provider = FakeProvider("gemini", stream_chunks=["ANSWER: a full reply\nMEMORY: NONE"])
    monkeypatch.setattr("app.routers.chat.model_router", ModelRouter(providers=[provider]))
    monkeypatch.setattr(
        "app.routers.chat.conversation_search.index_message",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("raw-secret-looking-db-detail-xyz")),
    )

    resp = client.post("/api/chat/stream", json={"message": "trigger a save failure", "provider": "auto"})
    events = _parse_sse(resp.text)

    assert events[-1][0] == "error"
    assert events[-1][1]["detail"] == "The completed reply could not be saved. Please try again."
    assert "raw-secret-looking-db-detail-xyz" not in events[-1][1]["detail"]
