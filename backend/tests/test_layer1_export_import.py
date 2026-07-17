"""ECHO Layer 1 (Phase 19) — memory_export.py: export/import/preview/commit,
dry-run, duplicate/secret handling, schema validation, round-trip."""

from app import atlas, schemas
from app.models import MemoryCandidate
from app.services import memory_export


def _entry(db, content, **kwargs):
    return atlas.create_entry(db, schemas.AtlasEntryCreate(content=content, **kwargs))


def test_export_includes_active_memories(db_session):
    _entry(db_session, "User's favorite language is Python.")
    export = memory_export.export_memories(db_session)
    assert export["schema_version"] == memory_export.EXPORT_SCHEMA_VERSION
    assert export["memory_count"] == 1
    assert export["memories"][0]["content"] == "User's favorite language is Python."


def test_export_excludes_no_embeddings_or_secrets_fields(db_session):
    _entry(db_session, "Ordinary preference statement.")
    export = memory_export.export_memories(db_session)
    record = export["memories"][0]
    assert "embedding" not in record
    assert "embedding_id" not in record


def test_export_excludes_highly_sensitive_by_default(db_session):
    _entry(db_session, "User was diagnosed with a chronic illness.")
    export = memory_export.export_memories(db_session)
    assert export["memory_count"] == 0
    assert export["excluded_sensitive_count"] == 1


def test_export_excludes_archived_by_default(db_session):
    entry = _entry(db_session, "Archived memory.")
    entry.status = "archived"
    db_session.commit()
    export = memory_export.export_memories(db_session)
    assert export["memory_count"] == 0


def test_preview_import_rejects_invalid_schema(db_session):
    result = memory_export.preview_import(db_session, {"schema_version": 999, "memories": []})
    assert result["valid"] is False


def test_preview_import_is_dry_run(db_session):
    payload = {"schema_version": 1, "memories": [{"content": "A brand new imported fact.", "memory_type": "fact"}]}
    result = memory_export.preview_import(db_session, payload)
    assert result["valid"] is True
    assert result["new"] == 1
    assert atlas.list_entries(db_session) == []
    assert db_session.query(MemoryCandidate).count() == 0


def test_preview_import_detects_duplicate(db_session):
    _entry(db_session, "User's favorite color is blue.")
    payload = {"schema_version": 1, "memories": [{"content": "User's favorite color is blue.", "memory_type": "fact"}]}
    result = memory_export.preview_import(db_session, payload)
    assert result["new"] == 0
    assert len(result["duplicates"]) == 1


def test_preview_import_flags_secret_rejection(db_session):
    payload = {"schema_version": 1, "memories": [{"content": "api_key=abcd1234efgh5678", "memory_type": "fact"}]}
    result = memory_export.preview_import(db_session, payload)
    assert result["secrets_rejected"] == 1
    assert result["new"] == 0


def test_commit_import_stages_candidates_not_active_memories(db_session):
    payload = {"schema_version": 1, "memories": [{"content": "A newly imported fact for review.", "memory_type": "fact"}]}
    result = memory_export.commit_import(db_session, payload)
    assert result["staged"] == 1
    assert atlas.list_entries(db_session) == []  # never written directly to active memory
    candidate = db_session.query(MemoryCandidate).one()
    assert candidate.status == "pending"
    assert candidate.source == "imported"


def test_commit_import_skips_duplicates_by_default(db_session):
    _entry(db_session, "User's favorite color is blue.")
    payload = {"schema_version": 1, "memories": [{"content": "User's favorite color is blue.", "memory_type": "fact"}]}
    result = memory_export.commit_import(db_session, payload)
    assert result["skipped_duplicates"] == 1
    assert result["staged"] == 0


def test_commit_import_rejects_secrets(db_session):
    payload = {"schema_version": 1, "memories": [{"content": "password=hunter22222", "memory_type": "fact"}]}
    result = memory_export.commit_import(db_session, payload)
    assert result["skipped_secrets"] == 1
    assert result["staged"] == 0


def test_export_import_round_trip_via_preview(db_session):
    _entry(db_session, "A durable fact worth exporting.")
    export = memory_export.export_memories(db_session)
    # A round trip into a *different* (empty) DB context is emulated here by
    # asserting the exported record is well-formed enough to feed straight
    # back into preview_import()'s expected shape.
    result = memory_export.preview_import(db_session, {"schema_version": export["schema_version"], "memories": export["memories"]})
    assert result["valid"] is True
    # It's a duplicate of itself (same DB), which is exactly correct behavior.
    assert result["new"] == 0
    assert len(result["duplicates"]) == 1
