"""Integration tests for Goal 17: _extract_memory() now has three paths —
explicit "remember that..." (unchanged), the new deterministic preference/
learning-style detector, and the model's own opportunistic MEMORY: block —
checked in that order. No model calls: ChatResult is constructed directly.
"""

from app.models import MemoryCandidate
from app.providers.base import ChatResult
from app.routers.chat import _extract_memory

_NO_MEMORY_RESULT = ChatResult(text="ok", reasoning=None, memory_json="NONE")


def test_when_you_explain_statement_creates_preference_candidate(db_session):
    message = "When you explain technical things to me, lead with a concrete example before the theory."
    update = _extract_memory(db_session, message, _NO_MEMORY_RESULT, conversation_id="conv-1")

    assert update is not None
    assert update.saved is False
    assert update.pending_review is True
    assert update.content == message

    candidate = db_session.query(MemoryCandidate).filter_by(conversation_id="conv-1").one()
    assert candidate.memory_type == "preference"
    assert candidate.epistemic_status == "Verified"
    assert candidate.confidence == 0.9
    assert candidate.source == "learning_style_detection"
    assert "learning_style" in candidate.tags
    assert candidate.status == "pending"


def test_i_learn_better_statement_creates_preference_candidate(db_session):
    message = "I learn better when you show me an example first."
    update = _extract_memory(db_session, message, _NO_MEMORY_RESULT, conversation_id="conv-2")

    assert update.pending_review is True
    candidate = db_session.query(MemoryCandidate).filter_by(conversation_id="conv-2").one()
    assert candidate.memory_type == "preference"
    assert candidate.source == "learning_style_detection"


def test_explicit_remember_still_saves_directly_not_as_candidate(db_session):
    message = "Remember that I prefer examples before theory."
    update = _extract_memory(db_session, message, _NO_MEMORY_RESULT, conversation_id="conv-3")

    assert update.saved is True
    assert update.explicit is True
    # The explicit path must win over the new preference detector and the old
    # behavior (direct save, no candidate row) must be unchanged.
    assert db_session.query(MemoryCandidate).filter_by(conversation_id="conv-3").count() == 0


def test_casual_request_does_not_become_a_preference_candidate(db_session):
    message = "Can you explain this with an example?"
    update = _extract_memory(db_session, message, _NO_MEMORY_RESULT, conversation_id="conv-4")

    # Falls through to the model's own MEMORY: judgment, which said NONE here —
    # so nothing gets saved or queued.
    assert update is None
    assert db_session.query(MemoryCandidate).filter_by(conversation_id="conv-4").count() == 0


def test_preference_candidate_has_correct_fields(db_session):
    message = "From now on, explain code with examples first."
    _extract_memory(db_session, message, _NO_MEMORY_RESULT, conversation_id="conv-5")

    candidate = db_session.query(MemoryCandidate).filter_by(conversation_id="conv-5").one()
    assert candidate.content == message
    assert candidate.memory_type == "preference"
    assert candidate.epistemic_status == "Verified"
    assert candidate.confidence == 0.9
    assert candidate.source in ("learning_style_detection", "explicit_user_preference")
    assert isinstance(candidate.tags, list) and len(candidate.tags) > 0
    assert candidate.status == "pending"


def test_preference_detection_takes_priority_over_model_memory_json(db_session):
    # Even if the model *also* emitted a MEMORY: block this turn, the
    # deterministic preference detector (based on the user's own words) wins —
    # avoids creating two candidates for the same underlying fact.
    message = "I prefer step-by-step explanations."
    model_result = ChatResult(
        text="ok",
        reasoning=None,
        memory_json='{"content": "some other fact", "epistemic_status": "Inferred", "confidence": 0.5, "tags": []}',
    )
    _extract_memory(db_session, message, model_result, conversation_id="conv-6")

    candidates = db_session.query(MemoryCandidate).filter_by(conversation_id="conv-6").all()
    assert len(candidates) == 1
    assert candidates[0].content == message
