"""ECHO Layer 1 (Phase 4/16) — capture pipeline: sensitivity gating,
do-not-remember, and richer candidate/entry field population. Uses the same
_extract_memory()-direct-call pattern as test_memory_candidates.py."""

from app import atlas
from app.models import MemoryCandidate
from app.providers.base import ChatResult
from app.routers.chat import _extract_memory, _save_memory


def test_do_not_remember_blocks_all_capture(db_session):
    result = ChatResult(text="ok", reasoning=None, memory_json="NONE")
    update = _extract_memory(
        db_session, "do not remember the next thing I say: my cat's name is Whiskers", result,
        conversation_id="conv-1",
    )
    assert update is None
    assert atlas.list_entries(db_session) == []
    assert db_session.query(MemoryCandidate).count() == 0


def test_explicit_remember_of_a_secret_is_refused(db_session):
    result = ChatResult(text="ok", reasoning=None, memory_json="NONE")
    update = _extract_memory(
        db_session, "please remember my api_key: sk-abcdefghijklmnopqrstuvwx", result,
        conversation_id="conv-2",
    )
    assert update.saved is False
    assert update.error
    assert atlas.list_entries(db_session) == []


def test_explicit_remember_of_highly_sensitive_is_allowed(db_session):
    result = ChatResult(text="ok", reasoning=None, memory_json="NONE")
    update = _extract_memory(
        db_session, "please remember that I was diagnosed with asthma", result,
        conversation_id="conv-3",
    )
    assert update.saved is True
    entries = atlas.list_entries(db_session)
    assert len(entries) == 1
    assert entries[0].capture_method == "explicit_user_request"
    assert entries[0].verification_status == "verified"


def test_opportunistic_highly_sensitive_extraction_is_dropped_not_queued(db_session):
    result = ChatResult(
        text="ok",
        reasoning=None,
        memory_json='{"content": "User was diagnosed with anxiety last year.", '
        '"epistemic_status": "Inferred", "confidence": 0.6, "tags": []}',
    )
    update = _extract_memory(db_session, "hello", result, conversation_id="conv-4")
    assert update is None
    assert db_session.query(MemoryCandidate).count() == 0


def test_opportunistic_ordinary_candidate_gets_layer1_fields(db_session):
    result = ChatResult(
        text="ok",
        reasoning=None,
        memory_json='{"content": "User likes tea.", "epistemic_status": "Inferred", '
        '"confidence": 0.6, "tags": ["preference"]}',
    )
    _extract_memory(db_session, "hello", result, conversation_id="conv-5")
    candidate = db_session.query(MemoryCandidate).one()
    assert candidate.category == "semantic"
    assert candidate.sensitivity_level == "ordinary_personal"
    assert candidate.recommendation == "ask_user"
    assert candidate.capture_reason


def test_preference_candidate_gets_layer1_fields(db_session):
    result = ChatResult(text="ok", reasoning=None, memory_json="NONE")
    _extract_memory(
        db_session, "I prefer step-by-step explanations from now on", result, conversation_id="conv-6"
    )
    candidate = db_session.query(MemoryCandidate).one()
    assert candidate.category == "preference"
    assert candidate.sensitivity_level == "ordinary_personal"
    assert candidate.recommendation == "ask_user"


def test_save_memory_refuses_secret_even_when_explicit_true():
    # Direct unit test of _save_memory's own gate (not just via _extract_memory).
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        update = _save_memory(
            db, content="password=hunter22222", explicit=True, epistemic_status="Verified",
            confidence=0.95, tags=["user-stated"], source="explicit user request",
        )
        assert update.saved is False
        assert update.error
    finally:
        db.close()
