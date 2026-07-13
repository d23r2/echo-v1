"""Tests for Goal 18a: build_system_prompt() wiring to previous-conversation
search — snippets are only injected when a recall phrase triggers it, never on
every turn, and Atlas retrieval keeps working unchanged alongside it.
"""

from app import conversation_search as cs
from app import persona
from app.models import Conversation, Message


def _make_conversation(db, title: str, messages: list[tuple[str, str]]) -> Conversation:
    conv = Conversation(title=title)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    for role, content in messages:
        m = Message(conversation_id=conv.id, role=role, content=content)
        db.add(m)
        db.commit()
        db.refresh(m)
        cs.index_message(m)
    return conv


def test_snippets_included_when_atlas_empty_but_history_has_a_match(db_session):
    _make_conversation(
        db_session,
        "Learning style chat",
        [("user", "When you explain technical things to me, lead with a concrete example first.")],
    )

    prompt, citations, _nudge, snippets = persona.build_system_prompt(
        db_session,
        "Do you remember what I said about my learning style?",
        turn_count=1,
    )

    assert citations == []  # nothing in Atlas — confirms this isn't just Atlas doing the work
    assert len(snippets) >= 1
    assert "PREVIOUS_CONVERSATION_SNIPPETS:" in prompt
    assert "concrete example" in prompt


def test_snippets_not_injected_when_not_triggered(db_session):
    _make_conversation(
        db_session,
        "Learning style chat",
        [("user", "When you explain technical things to me, lead with a concrete example first.")],
    )

    # Same underlying content exists in history, but this message doesn't use
    # any recall phrasing — must not trigger a search.
    prompt, _citations, _nudge, snippets = persona.build_system_prompt(
        db_session, "What's a good way to learn Python?", turn_count=1
    )

    assert snippets == []
    assert "PREVIOUS_CONVERSATION_SNIPPETS:" not in prompt


def test_no_match_in_history_means_no_snippets_section(db_session):
    prompt, _citations, _nudge, snippets = persona.build_system_prompt(
        db_session, "Do you remember what I said about my learning style?", turn_count=0
    )

    assert snippets == []
    assert "PREVIOUS_CONVERSATION_SNIPPETS:" not in prompt


def test_atlas_retrieval_still_works_alongside_conversation_search(db_session, monkeypatch):
    from app import models

    # Regression check for the *wiring* (persona still calls atlas.search() and
    # threads citations into the prompt) — isolated from real semantic-ranking
    # quality via monkeypatch, since the real Chroma "atlas" collection is
    # shared (never reset) across the whole test session and accumulates
    # entries from every other Atlas test that ran before this one, which can
    # crowd a specific entry out of the real top-k.
    fake_entry = models.AtlasEntry(
        id="fake-entry-id",
        content="User's favorite color is blue.",
        epistemic_status="Verified",
        memory_type="fact",
        tags=[],
        confidence=1.0,
    )
    monkeypatch.setattr("app.persona.atlas.search", lambda db, query, top_k: [(fake_entry, 0.1)])

    prompt, citations, _nudge, _snippets = persona.build_system_prompt(
        db_session, "What's my favorite color?", turn_count=0
    )

    assert len(citations) == 1
    assert "favorite color is blue" in prompt


def test_current_conversation_excluded_from_snippet_search(db_session):
    conv = _make_conversation(
        db_session, "Current chat", [("user", "provider routing details are here")]
    )

    _prompt, _citations, _nudge, snippets = persona.build_system_prompt(
        db_session,
        "What did we discuss earlier about provider routing?",
        turn_count=1,
        conversation_id=conv.id,
    )

    assert snippets == []
