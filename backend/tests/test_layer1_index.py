"""ECHO Layer 1 (Phase 9) — memory_index.py: status/orphan-detection/
rebuild/repair over the existing local Chroma index. Uses the real
(test-isolated, per conftest.py) Chroma collection — never the real user's
vector store."""

from app import atlas, schemas
from app.services import memory_index


def _entry(db, content="Some memory content."):
    return atlas.create_entry(db, schemas.AtlasEntryCreate(content=content))


def test_status_reports_healthy_and_counts(db_session):
    _entry(db_session, "First memory.")
    _entry(db_session, "Second memory.")
    result = memory_index.status(db_session)
    assert result["healthy"] is True
    assert result["backend"] == "chromadb"
    assert result["embedding_model"]
    assert result["sql_row_count"] == 2


def test_find_orphans_none_when_in_sync(db_session):
    _entry(db_session, "A memory that's properly indexed.")
    orphans = memory_index.find_orphans(db_session)
    assert orphans["missing_from_index"] == []
    assert orphans["orphaned_in_index"] == []


def test_find_orphans_detects_orphaned_vector(db_session):
    entry = _entry(db_session, "A memory that will be deleted from SQL only.")
    # Simulate a SQL row being removed without the matching Chroma cleanup
    # (bypassing atlas.delete_entry on purpose, to create the orphan state
    # find_orphans/repair_index are meant to detect and fix).
    db_session.delete(entry)
    db_session.commit()
    orphans = memory_index.find_orphans(db_session)
    assert entry.id in orphans["orphaned_in_index"]


def test_repair_index_removes_orphaned_vectors(db_session):
    entry = _entry(db_session, "Another memory that will be orphaned.")
    db_session.delete(entry)
    db_session.commit()
    result = memory_index.repair_index(db_session)
    assert result["removed"] >= 1
    orphans_after = memory_index.find_orphans(db_session)
    assert entry.id not in orphans_after["orphaned_in_index"]


def test_rebuild_index_reembeds_all_rows(db_session):
    _entry(db_session, "Memory one.")
    _entry(db_session, "Memory two.")
    result = memory_index.rebuild_index(db_session)
    assert result["rebuilt"] == 2
    assert result["failed"] == 0


def test_status_never_raises_when_db_empty(db_session):
    result = memory_index.status(db_session)
    assert result["sql_row_count"] == 0
