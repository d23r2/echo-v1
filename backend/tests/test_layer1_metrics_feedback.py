"""ECHO Layer 1 (Phase 20/21) — memory metrics and adaptive feedback nudging
retrieval ranking (capped, never erasing truth from one negative rating)."""

from app import atlas, schemas
from app.core import metrics as core_metrics
from app.services import memory_retrieval


def _entry(db, content, **kwargs):
    return atlas.create_entry(db, schemas.AtlasEntryCreate(content=content, **kwargs))


def test_record_feedback_persists_row(db_session):
    entry = _entry(db_session, "Feedback test memory.")
    row = memory_retrieval.record_feedback(db_session, memory_id=entry.id, feedback_type="useful")
    assert row.memory_id == entry.id
    assert row.feedback_type == "useful"


def test_positive_feedback_gives_small_ranking_boost(db_session):
    core_metrics.reset()
    boosted = _entry(db_session, "Ranking boost candidate about llamas.")
    unboosted = _entry(db_session, "Ranking boost candidate about alpacas.")
    memory_retrieval.record_feedback(db_session, memory_id=boosted.id, feedback_type="useful")

    bias = memory_retrieval._feedback_bias(db_session)
    assert bias.get(boosted.id, 0.0) > 0
    assert bias.get(unboosted.id, 0.0) == 0.0


def test_negative_feedback_gives_small_ranking_penalty(db_session):
    entry = _entry(db_session, "Penalty candidate about goats.")
    memory_retrieval.record_feedback(db_session, memory_id=entry.id, feedback_type="irrelevant")
    bias = memory_retrieval._feedback_bias(db_session)
    assert bias.get(entry.id, 0.0) < 0


def test_single_negative_rating_does_not_zero_out_score(db_session):
    entry = _entry(db_session, "Single negative rating test memory.", confidence=0.9, importance="high")
    memory_retrieval.record_feedback(db_session, memory_id=entry.id, feedback_type="irrelevant")
    score_with_feedback = memory_retrieval._score(
        entry, memory_retrieval.MemoryRetrievalRequest(query="x"), distance=0.1, conflict_ids=set(),
        feedback_bias=memory_retrieval._feedback_bias(db_session).get(entry.id, 0.0),
    )
    # A single "irrelevant" rating (-0.03) should never erase a strong base score.
    assert score_with_feedback > 0.3


def test_feedback_bias_is_capped_at_max_samples(db_session):
    entry = _entry(db_session, "Capped feedback test memory.")
    for _ in range(10):
        memory_retrieval.record_feedback(db_session, memory_id=entry.id, feedback_type="useful")
    bias = memory_retrieval._feedback_bias(db_session)
    # Capped at _MAX_FEEDBACK_SAMPLES_PER_MEMORY (3) * 0.02 = 0.06, regardless of 10 ratings.
    assert abs(bias[entry.id] - 0.06) < 1e-9
