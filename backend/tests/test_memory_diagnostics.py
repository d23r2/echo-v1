"""Tests for Goal 7: memory-extraction diagnostics. Every chat turn's
memory-extraction attempt is logged (MemoryExtractionLog) regardless of whether
anything was saved — see routers/chat.py's _log_memory_diagnostic /
_extract_memory, and GET /api/atlas/diagnostics for reading them back.
"""

from fastapi.testclient import TestClient

from app.main import app
from app.models import MemoryExtractionLog
from app.providers.base import ChatResult
from app.routers.chat import _extract_memory


def test_explicit_remember_logs_a_diagnostic_row(db_session):
    result = ChatResult(text="ok", reasoning=None, memory_json="NONE")
    _extract_memory(db_session, "please remember that I like tea", result, conversation_id="conv-1")

    log = db_session.query(MemoryExtractionLog).one()
    assert log.explicit_request is True
    assert log.saved is True
    assert log.conversation_id == "conv-1"


def test_memory_none_logs_was_none_and_not_saved(db_session):
    result = ChatResult(text="ok", reasoning=None, memory_json="NONE")
    _extract_memory(db_session, "haha nice", result, conversation_id="conv-2")

    log = db_session.query(MemoryExtractionLog).one()
    assert log.was_none is True
    assert log.saved is False
    assert log.rejection_reason == "MEMORY was NONE"


def test_malformed_json_logs_malformed_reason(db_session):
    result = ChatResult(text="ok", reasoning=None, memory_json="{not valid json")
    _extract_memory(db_session, "hello", result, conversation_id="conv-3")

    log = db_session.query(MemoryExtractionLog).one()
    assert log.json_detected is True
    assert log.parse_succeeded is False
    assert log.saved is False
    assert "Malformed" in log.rejection_reason


def test_missing_content_field_logs_that_specific_reason(db_session):
    result = ChatResult(text="ok", reasoning=None, memory_json='{"epistemic_status": "Verified"}')
    _extract_memory(db_session, "hello", result, conversation_id="conv-4")

    log = db_session.query(MemoryExtractionLog).one()
    assert log.rejection_reason == "Missing content field"


def test_no_memory_block_at_all_logs_that(db_session):
    result = ChatResult(text="ok", reasoning=None, memory_json=None)
    _extract_memory(db_session, "hello", result, conversation_id="conv-5")

    log = db_session.query(MemoryExtractionLog).one()
    assert log.memory_block_present is False
    assert log.rejection_reason == "No MEMORY: block in the model's reply"


def test_valid_candidate_logs_queued_for_review_not_saved(db_session):
    result = ChatResult(
        text="ok",
        reasoning=None,
        memory_json='{"content": "User likes tea.", "epistemic_status": "Inferred", '
        '"confidence": 0.6, "tags": ["preference"]}',
    )
    _extract_memory(db_session, "hello", result, conversation_id="conv-6")

    log = db_session.query(MemoryExtractionLog).one()
    assert log.parse_succeeded is True
    assert log.saved is False  # queued as a candidate, not saved directly
    assert "candidate" in log.rejection_reason.lower()


def test_parser_failure_never_crashes_the_chat_turn(db_session):
    # Garbage input must not raise — fails closed even on totally malformed
    # provider output.
    result = ChatResult(text="ok", reasoning=None, memory_json="\x00\x01{{{garbage")
    update = _extract_memory(db_session, "hello", result, conversation_id="conv-7")
    assert update is None  # nothing crashed, nothing saved


def test_diagnostics_endpoint_returns_recent_entries():
    from app.db import SessionLocal, init_db

    # This test may run standalone (not after test_app_smoke.py's TestClient,
    # which normally triggers startup/init_db first) — ensure tables exist
    # before writing to the shared app-level DB directly.
    init_db()
    session = SessionLocal()
    try:
        session.add(
            MemoryExtractionLog(
                conversation_id="endpoint-test-conv",
                explicit_request=False,
                memory_block_present=True,
                was_none=True,
                json_detected=False,
                parse_succeeded=False,
                saved=False,
                rejection_reason="MEMORY was NONE",
            )
        )
        session.commit()
    finally:
        session.close()

    with TestClient(app) as client:
        resp = client.get("/api/atlas/diagnostics?limit=5")

    assert resp.status_code == 200
    data = resp.json()
    assert any(d["conversation_id"] == "endpoint-test-conv" for d in data)
