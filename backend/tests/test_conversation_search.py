"""Tests for Goal 18a: searching PAST conversations as a fallback/supplement to
Atlas. Covers the trigger detector and the retrieval functions directly against
the db_session fixture — no real embedding-model network calls (sentence-
transformers runs fully locally, same as Atlas's existing tests).
"""

from app import conversation_search as cs
from app.models import Conversation, Message


def _make_conversation(db, title: str, messages: list[tuple[str, str]]) -> Conversation:
    """messages: list of (role, content)."""
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


# ---- trigger detection ----


def test_explicit_recall_query_triggers_search():
    assert cs.should_search_previous_conversations(
        "Do you remember what I said about my learning style?"
    ) is True


def test_various_trigger_phrases():
    for msg in [
        "What did we discuss earlier about Atlas?",
        "Find where I said something about provider routing.",
        "What was the thing I told you before about explaining with examples?",
        "Look through our previous chats for the self-improvement idea.",
        "As I said, this matters.",
    ]:
        assert cs.should_search_previous_conversations(msg) is True, msg


def test_ordinary_message_does_not_trigger_search():
    assert cs.should_search_previous_conversations("What's the capital of France?") is False


def test_prefers_user_messages_detection():
    assert cs.prefers_user_messages("What did I say about my learning style?") is True
    assert cs.prefers_user_messages("What did we discuss earlier?") is False


# ---- keyword_search() ----


def test_keyword_search_finds_matching_message(db_session):
    _make_conversation(
        db_session,
        "Learning style chat",
        [("user", "When you explain technical things to me, lead with a concrete example first.")],
    )

    results = cs.keyword_search(db_session, "learning style explain example")
    assert len(results) >= 1
    assert "concrete example" in results[0].snippet


def test_keyword_search_returns_empty_list_when_nothing_matches(db_session):
    _make_conversation(db_session, "Unrelated chat", [("user", "What's the weather like?")])
    assert cs.keyword_search(db_session, "provider routing fallback") == []


def test_keyword_search_excludes_current_conversation(db_session):
    conv = _make_conversation(db_session, "Current chat", [("user", "provider routing details here")])
    results = cs.keyword_search(db_session, "provider routing", exclude_conversation_id=conv.id)
    assert results == []


def test_keyword_search_respects_top_k(db_session):
    for i in range(6):
        _make_conversation(db_session, f"Chat {i}", [("user", f"provider routing note number {i}")])
    results = cs.keyword_search(db_session, "provider routing", top_k=2)
    assert len(results) <= 2


def test_keyword_search_does_not_crash_on_empty_database(db_session):
    assert cs.keyword_search(db_session, "anything at all") == []


# ---- search_previous_conversations() (combined) ----


def test_search_previous_conversations_returns_limited_snippets_not_full_dumps(db_session):
    _make_conversation(
        db_session,
        "Long chat",
        [("user", f"message about provider routing number {i}" * 3) for i in range(10)],
    )
    results = cs.search_previous_conversations(db_session, "provider routing", top_k=3)
    assert len(results) <= 3
    for r in results:
        assert len(r.snippet) <= cs._SNIPPET_MAX_CHARS + 1  # +1 for the ellipsis char


def test_search_previous_conversations_prefers_user_messages_when_asked(db_session):
    _make_conversation(
        db_session,
        "Mixed roles",
        [
            ("echo", "I explained provider routing to you in detail."),
            ("user", "I told you about provider routing preferences."),
        ],
    )
    results = cs.search_previous_conversations(
        db_session, "provider routing", prefer_user_messages=True
    )
    assert len(results) >= 1
    assert results[0].role == "user"


def test_search_previous_conversations_no_match_returns_empty_honestly(db_session):
    _make_conversation(db_session, "Some chat", [("user", "hello there")])
    assert cs.search_previous_conversations(db_session, "quantum entanglement gadgets") == []


def test_search_previous_conversations_does_not_crash_on_empty_database(db_session):
    assert cs.search_previous_conversations(db_session, "anything") == []


def test_rebuild_index_reindexes_all_messages(db_session):
    _make_conversation(db_session, "Chat A", [("user", "a fact about provider routing")])
    _make_conversation(db_session, "Chat B", [("user", "another fact about atlas memory")])
    count = cs.rebuild_index(db_session)
    assert count == 2
