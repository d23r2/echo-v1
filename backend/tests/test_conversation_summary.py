"""ECHO Action + Reliability Core v1 — Conversation Auto-Summary.

No real Ollama call anywhere — LocalModelRouter is swapped for one backed
by a FakeProvider, same pattern as test_local_intelligence_engine.py.
"""

from app.models import Conversation, Message
from app.services import conversation_summary
from app.services.local_model_router import LocalModelRouter
from tests.fake_providers import FakeProvider


def _make_conversation(db, n_messages=8):
    conversation = Conversation(title="Planning the release")
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    for i in range(n_messages):
        role = "user" if i % 2 == 0 else "echo"
        db.add(Message(conversation_id=conversation.id, role=role, content=f"message {i} about the release checklist"))
    db.commit()
    return conversation


def test_manual_summary_creates_summary(db_session, monkeypatch):
    conversation = _make_conversation(db_session)
    fake = FakeProvider(
        "ollama",
        available=True,
        response_text=(
            '{"title": "Release planning", "summary": "Discussed the release checklist and next steps.", '
            '"decisions": ["Use SearXNG for search"], "tasks": [], "open_questions": [], '
            '"next_steps": ["Run the release checklist"]}'
        ),
    )
    monkeypatch.setattr(conversation_summary, "LocalModelRouter", lambda *a, **k: LocalModelRouter(provider=fake))

    summary = conversation_summary.summarize_conversation(db_session, conversation.id)
    assert summary is not None
    assert summary.title == "Release planning"
    assert "Use SearXNG for search" in summary.decisions_json
    assert "Run the release checklist" in summary.next_steps_json


def test_summary_includes_decisions_and_next_steps(db_session, monkeypatch):
    conversation = _make_conversation(db_session)
    fake = FakeProvider(
        "ollama",
        available=True,
        response_text='{"title": "T", "summary": "S", "decisions": ["D1", "D2"], "tasks": ["Task1"], "open_questions": ["Q1"], "next_steps": ["N1"]}',
    )
    monkeypatch.setattr(conversation_summary, "LocalModelRouter", lambda *a, **k: LocalModelRouter(provider=fake))

    summary = conversation_summary.summarize_conversation(db_session, conversation.id)
    assert summary.decisions_json == ["D1", "D2"]
    assert summary.tasks_json == ["Task1"]
    assert summary.open_questions_json == ["Q1"]
    assert summary.next_steps_json == ["N1"]


def test_short_conversation_not_auto_summarized_unless_forced(db_session):
    conversation = _make_conversation(db_session, n_messages=2)
    assert conversation_summary.should_auto_summarize(db_session, conversation.id) is False


def test_long_conversation_eligible_for_auto_summary(db_session):
    conversation = _make_conversation(db_session, n_messages=10)
    assert conversation_summary.should_auto_summarize(db_session, conversation.id) is True


def test_summary_can_create_knowledge_vault_item(db_session, monkeypatch):
    conversation = _make_conversation(db_session)
    fake = FakeProvider("ollama", available=True, response_text='{"title": "T", "summary": "S", "decisions": [], "tasks": [], "open_questions": [], "next_steps": []}')
    monkeypatch.setattr(conversation_summary, "LocalModelRouter", lambda *a, **k: LocalModelRouter(provider=fake))

    summary = conversation_summary.summarize_conversation(db_session, conversation.id)
    item = conversation_summary.summary_to_knowledge_item(db_session, summary)
    assert item.item_type == "summary"
    assert item.source_id == conversation.id


def test_model_unavailable_degrades_cleanly_no_debug_leak(db_session, monkeypatch):
    conversation = _make_conversation(db_session)
    fake = FakeProvider("ollama", available=False)
    monkeypatch.setattr(conversation_summary, "LocalModelRouter", lambda *a, **k: LocalModelRouter(provider=fake))

    summary = conversation_summary.summarize_conversation(db_session, conversation.id)
    assert summary is not None
    assert "Traceback" not in summary.summary
    assert "{" not in summary.summary


def test_nonexistent_conversation_returns_none(db_session):
    assert conversation_summary.summarize_conversation(db_session, "nonexistent") is None


def test_no_messages_returns_none(db_session):
    conversation = Conversation(title="Empty")
    db_session.add(conversation)
    db_session.commit()
    db_session.refresh(conversation)
    assert conversation_summary.summarize_conversation(db_session, conversation.id) is None
