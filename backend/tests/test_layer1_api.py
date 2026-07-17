"""ECHO Layer 1 (Phase 18) — /api/memory/* consolidated router. Uses the
real shared app DB via TestClient, same pattern as test_memory_candidates.py's
HTTP section (isolated per test run by conftest.py's DATABASE_URL redirect)."""

from fastapi.testclient import TestClient

from app import atlas, memory_conflicts, schemas
from app.db import SessionLocal, init_db
from app.main import app

init_db()
client = TestClient(app)


def _create_memory(content="A memory created via the API test.", **kwargs):
    db = SessionLocal()
    try:
        entry = atlas.create_entry(db, schemas.AtlasEntryCreate(content=content, **kwargs))
        return entry.id
    finally:
        db.close()


def test_list_memories_returns_created_entry():
    memory_id = _create_memory("List endpoint test memory.")
    resp = client.get("/api/memory")
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.json()}
    assert memory_id in ids


def test_get_memory_by_id():
    memory_id = _create_memory("Get-by-id test memory.")
    resp = client.get(f"/api/memory/{memory_id}")
    assert resp.status_code == 200
    assert resp.json()["content"] == "Get-by-id test memory."


def test_get_memory_404_for_unknown_id():
    resp = client.get("/api/memory/does-not-exist")
    assert resp.status_code == 404


def test_patch_memory_updates_content():
    memory_id = _create_memory("Original content.")
    resp = client.patch(f"/api/memory/{memory_id}", json={"content": "Updated content."})
    assert resp.status_code == 200
    assert resp.json()["content"] == "Updated content."


def test_archive_then_restore_memory():
    memory_id = _create_memory("Archive/restore test memory.")
    archived = client.post(f"/api/memory/{memory_id}/archive")
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    restored = client.post(f"/api/memory/{memory_id}/restore")
    assert restored.status_code == 200
    assert restored.json()["status"] == "active"


def test_confirm_memory_sets_verified():
    memory_id = _create_memory("Confirm test memory.")
    resp = client.post(f"/api/memory/{memory_id}/confirm")
    assert resp.status_code == 200
    assert resp.json()["verification_status"] == "verified"


def test_mark_outdated_endpoint():
    memory_id = _create_memory("Outdated test memory.")
    resp = client.post(f"/api/memory/{memory_id}/mark-outdated")
    assert resp.status_code == 200
    assert resp.json()["outdated"] is True


def test_delete_memory_is_permanent():
    memory_id = _create_memory("Delete test memory.")
    resp = client.delete(f"/api/memory/{memory_id}")
    assert resp.status_code == 204
    assert client.get(f"/api/memory/{memory_id}").status_code == 404


def test_search_endpoint_returns_results():
    _create_memory("The API search endpoint test targets Python programming.")
    resp = client.post("/api/memory/search", json={"query": "Python programming"})
    assert resp.status_code == 200
    assert any("Python" in r["content"] for r in resp.json())


def test_context_preview_returns_brief_text():
    _create_memory("Context preview endpoint test memory about Rust.")
    resp = client.post("/api/memory/context-preview", json={"query": "Rust"})
    assert resp.status_code == 200
    body = resp.json()
    assert "brief_text" in body
    assert "results" in body


def test_conflicts_list_and_resolve():
    db = SessionLocal()
    try:
        a = atlas.create_entry(db, schemas.AtlasEntryCreate(content="User's favorite drink is coffee.", tags=["drink-api-test"]))
        b = atlas.create_entry(db, schemas.AtlasEntryCreate(content="User's favorite drink is tea now.", tags=["drink-api-test"]))
        memory_conflicts.detect_and_record_conflicts(db, b)
        db.commit()
        a_id, b_id = a.id, b.id
    finally:
        db.close()

    resp = client.get("/api/memory/conflicts")
    assert resp.status_code == 200
    matching = [c for c in resp.json() if set(c["memory_ids_json"]) == {a_id, b_id}]
    assert len(matching) == 1

    conflict_id = matching[0]["id"]
    resolve_resp = client.post(f"/api/memory/conflicts/{conflict_id}/resolve", json={"resolution": "retain_both_with_scope"})
    assert resolve_resp.status_code == 200
    assert resolve_resp.json()["status"] == "resolved"


def test_maintenance_run_endpoint():
    resp = client.post("/api/memory/maintenance/run")
    assert resp.status_code == 200
    body = resp.json()
    assert "checked" in body and "expired" in body and "needs_review" in body


def test_index_status_endpoint():
    resp = client.get("/api/memory/index/status")
    assert resp.status_code == 200
    assert resp.json()["backend"] == "chromadb"


def test_index_rebuild_and_repair_endpoints():
    assert client.post("/api/memory/index/rebuild").status_code == 200
    assert client.post("/api/memory/index/repair").status_code == 200


def test_export_endpoint():
    _create_memory("Export endpoint test memory.")
    resp = client.get("/api/memory/export")
    assert resp.status_code == 200
    assert resp.json()["schema_version"] == 1


def test_import_preview_and_commit_endpoints():
    # Distinctive wording, deliberately avoiding generic words like "test
    # memory" that collide with dozens of other short entries created
    # elsewhere in this shared-DB test file (find_duplicates() uses
    # containment ratio, which a short entry can hit 1.0 on against any
    # other short entry sharing just two or three words).
    payload = {
        "schema_version": 1,
        "memories": [{"content": "Xylophone zeppelin quokka import scenario.", "memory_type": "fact"}],
    }
    preview = client.post("/api/memory/import/preview", json=payload)
    assert preview.status_code == 200
    assert preview.json()["new"] == 1

    commit = client.post("/api/memory/import/commit", json=payload)
    assert commit.status_code == 200
    assert commit.json()["staged"] == 1


def test_metrics_endpoint():
    _create_memory("Metrics endpoint test memory.")
    resp = client.get("/api/memory/metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert "provenance_coverage_pct" in body
    assert "unresolved_conflict_pct" in body


def test_feedback_endpoint():
    memory_id = _create_memory("Feedback endpoint test memory.")
    resp = client.post(f"/api/memory/{memory_id}/feedback", json={"feedback_type": "useful"})
    assert resp.status_code == 200
    assert resp.json()["feedback_type"] == "useful"


def test_stats_endpoint():
    _create_memory("Stats endpoint test memory.")
    resp = client.get("/api/memory/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert "by_category" in body
    assert "pending_candidates" in body
