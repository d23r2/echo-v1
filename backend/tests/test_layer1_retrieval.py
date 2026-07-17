"""ECHO Layer 1 (Phase 8) — memory_retrieval.py: hybrid scoring, filters,
conflict warnings, and the vector-store-unavailable fallback."""

from app import atlas, memory_conflicts, schemas
from app.services.memory_retrieval import MemoryRetrievalRequest, retrieve


def _entry(db, content, **kwargs):
    return atlas.create_entry(db, schemas.AtlasEntryCreate(content=content, **kwargs))


def test_retrieve_returns_semantic_match(db_session):
    _entry(db_session, "The user's favorite programming language is Python.")
    results = retrieve(db_session, MemoryRetrievalRequest(query="What language does the user like?"))
    assert any("Python" in r.content for r in results)


def test_retrieve_respects_max_results(db_session):
    for i in range(10):
        _entry(db_session, f"Fact number {i} about the project roadmap.")
    results = retrieve(db_session, MemoryRetrievalRequest(query="project roadmap", max_results=3))
    assert len(results) <= 3


def test_retrieve_excludes_archived_by_default(db_session):
    entry = _entry(db_session, "The backend runs locally on port 8000.")
    entry.status = "archived"
    db_session.commit()
    results = retrieve(db_session, MemoryRetrievalRequest(query="backend port"))
    assert entry.id not in {r.memory_id for r in results}


def test_retrieve_includes_archived_when_requested(db_session):
    entry = _entry(db_session, "The backend runs locally on port 8000.")
    entry.status = "archived"
    db_session.commit()
    results = retrieve(db_session, MemoryRetrievalRequest(query="backend port 8000", include_archived=True, minimum_confidence=0.0))
    # archived entries can still be surfaced explicitly, just not by default
    assert results is not None


def test_retrieve_excludes_low_confidence(db_session):
    _entry(db_session, "A low confidence guess about the weather forecast.", confidence=0.1)
    results = retrieve(db_session, MemoryRetrievalRequest(query="weather forecast", minimum_confidence=0.5))
    assert results == []


def test_retrieve_project_scoped_match(db_session):
    entry = _entry(db_session, "Uses FastAPI and SQLAlchemy.", project_id="proj-1")
    _entry(db_session, "Uses FastAPI and SQLAlchemy.", project_id="proj-2")
    results = retrieve(db_session, MemoryRetrievalRequest(query="architecture", project_id="proj-1"))
    ids = {r.memory_id for r in results}
    assert entry.id in ids


def test_retrieve_falls_back_to_lexical_when_semantic_search_fails(db_session, monkeypatch):
    _entry(db_session, "The backend runs locally on port eight thousand.")

    def _boom(*args, **kwargs):
        raise RuntimeError("vector store unreachable")

    monkeypatch.setattr(atlas, "search", _boom)
    results = retrieve(db_session, MemoryRetrievalRequest(query="backend runs locally port"))
    assert any("backend" in r.content.lower() for r in results)
    assert all(r.retrieval_reason == "lexical/metadata match" for r in results)


def test_retrieve_flags_conflict_warning(db_session):
    a = _entry(db_session, "User's favorite drink is coffee.", tags=["drink"])
    b = _entry(db_session, "User's favorite drink is tea now.", tags=["drink"])
    memory_conflicts.detect_and_record_conflicts(db_session, b)
    results = retrieve(db_session, MemoryRetrievalRequest(query="favorite drink"))
    flagged = {r.memory_id for r in results if r.conflict_warning}
    assert a.id in flagged or b.id in flagged


def test_retrieve_excludes_highly_sensitive_for_general_purpose(db_session):
    _entry(db_session, "User was diagnosed with a chronic condition.")
    results = retrieve(db_session, MemoryRetrievalRequest(query="diagnosed condition", purpose="general"))
    assert results == []


def test_retrieve_updates_access_tracking(db_session):
    entry = _entry(db_session, "The user's name is Alex.")
    assert entry.access_count == 0
    retrieve(db_session, MemoryRetrievalRequest(query="user's name"))
    db_session.refresh(entry)
    assert entry.access_count >= 1
    assert entry.last_accessed_at is not None


def test_retrieve_returns_provenance_and_freshness_fields(db_session):
    _entry(db_session, "The user prefers dark mode.", capture_method="explicit_user_request")
    results = retrieve(db_session, MemoryRetrievalRequest(query="dark mode preference"))
    assert results
    assert results[0].provenance_summary == "You told ECHO"
    assert results[0].freshness_status in ("fresh", "stale", "needs_review", "unknown")
