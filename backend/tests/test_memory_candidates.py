"""Tests for Goal 8: memory-candidate review queue and conflict detection.
No model calls anywhere — conflict detection is plain word/tag-overlap over
existing AtlasEntry rows (app/memory_conflicts.py).
"""

from fastapi.testclient import TestClient

from app import atlas, memory_conflicts, schemas
from app.main import app
from app.models import MemoryCandidate
from app.providers.base import ChatResult
from app.routers.chat import _extract_memory

# ---- conflict detection ----


def test_no_conflicts_when_atlas_is_empty(db_session):
    conflicts = memory_conflicts.find_conflicts(
        db_session, content="User likes tea.", memory_type="fact", tags=["preference"]
    )
    assert conflicts == []


def test_shared_tag_is_flagged_as_a_conflict(db_session):
    atlas.create_entry(
        db_session,
        schemas.AtlasEntryCreate(
            content="User's favorite drink is coffee.", memory_type="fact", tags=["drink", "preference"]
        ),
    )

    conflicts = memory_conflicts.find_conflicts(
        db_session,
        content="User now prefers tea over coffee.",
        memory_type="fact",
        tags=["drink", "preference"],
    )

    assert len(conflicts) == 1
    assert conflicts[0].content == "User's favorite drink is coffee."


def test_significant_word_overlap_is_flagged_even_without_shared_tags(db_session):
    atlas.create_entry(
        db_session,
        schemas.AtlasEntryCreate(
            content="User works as a backend developer at a startup.", memory_type="fact", tags=["job"]
        ),
    )

    conflicts = memory_conflicts.find_conflicts(
        db_session,
        content="User works as a backend developer remotely.",
        memory_type="fact",
        tags=["career"],
    )

    assert len(conflicts) == 1


def test_unrelated_memory_is_not_flagged(db_session):
    atlas.create_entry(
        db_session,
        schemas.AtlasEntryCreate(
            content="User's favorite color is blue.", memory_type="fact", tags=["color", "preference"]
        ),
    )

    conflicts = memory_conflicts.find_conflicts(
        db_session, content="User is learning to play the guitar.", memory_type="fact", tags=["hobby"]
    )

    assert conflicts == []


def test_identical_content_is_not_flagged_as_a_conflict(db_session):
    atlas.create_entry(
        db_session,
        schemas.AtlasEntryCreate(content="User's favorite color is blue.", memory_type="fact", tags=["color"]),
    )

    conflicts = memory_conflicts.find_conflicts(
        db_session, content="User's favorite color is blue.", memory_type="fact", tags=["color"]
    )

    assert conflicts == []  # identical content is a duplicate, not a "conflict"


def test_different_memory_type_is_not_flagged(db_session):
    atlas.create_entry(
        db_session,
        schemas.AtlasEntryCreate(
            content="User's favorite drink is coffee.", memory_type="preference", tags=["drink"]
        ),
    )

    conflicts = memory_conflicts.find_conflicts(
        db_session, content="User now prefers tea.", memory_type="fact", tags=["drink"]
    )

    assert conflicts == []  # find_conflicts scopes by memory_type


# ---- candidate creation via the real chat-turn code path ----


def test_valid_extraction_creates_pending_candidate_not_atlas_entry(db_session):
    result = ChatResult(
        text="ok",
        reasoning=None,
        memory_json='{"content": "User likes tea.", "epistemic_status": "Inferred", '
        '"confidence": 0.6, "tags": ["preference"]}',
    )
    update = _extract_memory(db_session, "hello", result, conversation_id="conv-x")

    assert update.saved is False
    assert update.pending_review is True
    assert atlas.list_entries(db_session) == []  # not saved directly to Atlas

    candidates = db_session.query(MemoryCandidate).all()
    assert len(candidates) == 1
    assert candidates[0].status == "pending"
    assert candidates[0].content == "User likes tea."


def test_candidate_records_conflicts_with_existing_entries(db_session):
    atlas.create_entry(
        db_session,
        schemas.AtlasEntryCreate(
            content="User's favorite drink is coffee.", memory_type="fact", tags=["drink", "preference"]
        ),
    )

    result = ChatResult(
        text="ok",
        reasoning=None,
        memory_json='{"content": "User now prefers tea over coffee.", "epistemic_status": "Inferred", '
        '"confidence": 0.6, "tags": ["drink", "preference"]}',
    )
    _extract_memory(db_session, "hello", result, conversation_id="conv-y")

    candidate = db_session.query(MemoryCandidate).one()
    assert len(candidate.conflict_with) == 1


def test_explicit_remember_still_bypasses_the_candidate_queue(db_session):
    # Explicit requests are unaffected by Goal 8 — they still save directly, no
    # candidate/review step, same as before.
    result = ChatResult(text="ok", reasoning=None, memory_json="NONE")
    update = _extract_memory(
        db_session, "please remember that I prefer dark mode", result, conversation_id="conv-z"
    )

    assert update.saved is True
    assert update.pending_review is False
    assert db_session.query(MemoryCandidate).count() == 0
    assert len(atlas.list_entries(db_session)) == 1


# ---- HTTP endpoints (list / accept / reject / edit) ----


def _make_candidate_in_app_db(**overrides) -> str:
    from app.db import SessionLocal, init_db

    # May run standalone (not after test_app_smoke.py's TestClient, which
    # normally triggers startup/init_db first) — ensure tables exist before
    # writing to the shared app-level DB directly.
    init_db()
    session = SessionLocal()
    try:
        candidate = MemoryCandidate(
            content=overrides.get("content", "Test candidate content."),
            epistemic_status=overrides.get("epistemic_status", "Inferred"),
            memory_type=overrides.get("memory_type", "fact"),
            tags=overrides.get("tags", ["test"]),
            confidence=overrides.get("confidence", 0.6),
            source="auto-extracted from conversation",
        )
        session.add(candidate)
        session.commit()
        session.refresh(candidate)
        return candidate.id
    finally:
        session.close()


def test_list_pending_candidates_endpoint():
    candidate_id = _make_candidate_in_app_db(content="Endpoint list test content.")
    with TestClient(app) as client:
        resp = client.get("/api/memory-candidates?status=pending")
    assert resp.status_code == 200
    assert any(c["id"] == candidate_id for c in resp.json())


def test_accept_candidate_endpoint_creates_atlas_entry():
    candidate_id = _make_candidate_in_app_db(content="Accept endpoint test content.")
    with TestClient(app) as client:
        resp = client.post(f"/api/memory-candidates/{candidate_id}/accept", json={"note": "looks fine"})
        list_resp = client.get("/api/memory-candidates?status=accepted")

    assert resp.status_code == 200
    assert resp.json()["content"] == "Accept endpoint test content."
    assert any(c["id"] == candidate_id for c in list_resp.json())


def test_reject_candidate_endpoint():
    candidate_id = _make_candidate_in_app_db(content="Reject endpoint test content.")
    with TestClient(app) as client:
        resp = client.post(f"/api/memory-candidates/{candidate_id}/reject", json={"note": "not useful"})

    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


def test_edit_candidate_endpoint():
    candidate_id = _make_candidate_in_app_db(content="Original content.")
    with TestClient(app) as client:
        resp = client.patch(f"/api/memory-candidates/{candidate_id}", json={"content": "Edited content."})

    assert resp.status_code == 200
    assert resp.json()["content"] == "Edited content."


def test_cannot_accept_an_already_decided_candidate():
    candidate_id = _make_candidate_in_app_db(content="Double accept test.")
    with TestClient(app) as client:
        client.post(f"/api/memory-candidates/{candidate_id}/accept", json={})
        resp = client.post(f"/api/memory-candidates/{candidate_id}/accept", json={})

    assert resp.status_code == 400
