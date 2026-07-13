"""Tests for Goal 13: Atlas second-brain features — cross-entry conflict
detection, merging similar memories, and the `outdated` flag. No model calls;
conflict detection reuses the same local word/tag-overlap heuristic as Goal 8.
"""

from fastapi.testclient import TestClient

from app import atlas, memory_conflicts, schemas
from app.db import SessionLocal, init_db
from app.main import app
from app.models import AtlasEntry

client = TestClient(app)


# ---- find_all_conflicts() ----


def test_find_all_conflicts_empty_atlas(db_session):
    assert memory_conflicts.find_all_conflicts(db_session) == {}


def test_find_all_conflicts_flags_shared_tag_pair(db_session):
    a = atlas.create_entry(
        db_session,
        schemas.AtlasEntryCreate(content="User's favorite drink is coffee.", memory_type="fact", tags=["drink"]),
    )
    b = atlas.create_entry(
        db_session,
        schemas.AtlasEntryCreate(content="User now prefers tea over soda.", memory_type="fact", tags=["drink"]),
    )

    conflicts = memory_conflicts.find_all_conflicts(db_session)
    assert b.id in conflicts[a.id]
    assert a.id in conflicts[b.id]


def test_find_all_conflicts_ignores_different_memory_types(db_session):
    atlas.create_entry(
        db_session,
        schemas.AtlasEntryCreate(content="User likes coffee.", memory_type="preference", tags=["drink"]),
    )
    atlas.create_entry(
        db_session,
        schemas.AtlasEntryCreate(content="User dislikes coffee.", memory_type="fact", tags=["drink"]),
    )

    assert memory_conflicts.find_all_conflicts(db_session) == {}


def test_find_all_conflicts_ignores_identical_content(db_session):
    atlas.create_entry(
        db_session,
        schemas.AtlasEntryCreate(content="User's favorite color is blue.", memory_type="fact", tags=["color"]),
    )
    atlas.create_entry(
        db_session,
        schemas.AtlasEntryCreate(content="User's favorite color is blue.", memory_type="fact", tags=["color"]),
    )

    assert memory_conflicts.find_all_conflicts(db_session) == {}


def test_find_all_conflicts_ignores_unrelated_entries(db_session):
    atlas.create_entry(
        db_session, schemas.AtlasEntryCreate(content="User's favorite color is blue.", memory_type="fact")
    )
    atlas.create_entry(
        db_session, schemas.AtlasEntryCreate(content="User is learning to play guitar.", memory_type="fact")
    )

    assert memory_conflicts.find_all_conflicts(db_session) == {}


# ---- merge_entries() ----


def test_merge_keeps_higher_confidence(db_session):
    keep = atlas.create_entry(
        db_session, schemas.AtlasEntryCreate(content="User works remotely.", memory_type="fact", confidence=0.5)
    )
    remove = atlas.create_entry(
        db_session, schemas.AtlasEntryCreate(content="User works remotely full time.", memory_type="fact", confidence=0.9)
    )

    merged = atlas.merge_entries(db_session, keep, remove)

    assert merged.id == keep.id
    assert merged.confidence == 0.9
    assert db_session.get(type(remove), remove.id) is None


def test_merge_applies_edited_content_when_provided(db_session):
    keep = atlas.create_entry(db_session, schemas.AtlasEntryCreate(content="User likes tea.", memory_type="fact"))
    remove = atlas.create_entry(db_session, schemas.AtlasEntryCreate(content="User likes coffee.", memory_type="fact"))

    merged = atlas.merge_entries(db_session, keep, remove, merged_content="User likes both tea and coffee.")

    assert merged.content == "User likes both tea and coffee."


# ---- /api/atlas/conflicts and /api/atlas/merge routes ----


def _reset_atlas_via_app_db():
    init_db()
    db = SessionLocal()
    try:
        for entry in db.query(AtlasEntry).all():
            db.delete(entry)
        db.commit()
    finally:
        db.close()


def test_conflicts_route_returns_empty_dict_when_no_conflicts():
    _reset_atlas_via_app_db()
    resp = client.get("/api/atlas/conflicts")
    assert resp.status_code == 200
    assert resp.json() == {}


def test_merge_route_merges_and_deletes(monkeypatch):
    _reset_atlas_via_app_db()
    a = client.post("/api/atlas", json={"content": "User works remotely.", "memory_type": "fact", "confidence": 0.4}).json()
    b = client.post("/api/atlas", json={"content": "User works remotely full time.", "memory_type": "fact", "confidence": 0.8}).json()

    resp = client.post("/api/atlas/merge", json={"keep_id": a["id"], "remove_id": b["id"]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == a["id"]
    assert body["confidence"] == 0.8

    listing = client.get("/api/atlas").json()
    ids = {e["id"] for e in listing}
    assert a["id"] in ids
    assert b["id"] not in ids

    client.delete(f"/api/atlas/{a['id']}")


def test_merge_route_rejects_merging_entry_with_itself():
    _reset_atlas_via_app_db()
    a = client.post("/api/atlas", json={"content": "Some fact.", "memory_type": "fact"}).json()

    resp = client.post("/api/atlas/merge", json={"keep_id": a["id"], "remove_id": a["id"]})
    assert resp.status_code == 400

    client.delete(f"/api/atlas/{a['id']}")


def test_merge_route_404_for_missing_entry():
    resp = client.post("/api/atlas/merge", json={"keep_id": "does-not-exist", "remove_id": "also-missing"})
    assert resp.status_code == 404


def test_outdated_field_defaults_false_and_can_be_patched():
    _reset_atlas_via_app_db()
    a = client.post("/api/atlas", json={"content": "Some fact.", "memory_type": "fact"}).json()
    assert a["outdated"] is False

    resp = client.patch(f"/api/atlas/{a['id']}", json={"outdated": True})
    assert resp.status_code == 200
    assert resp.json()["outdated"] is True

    client.delete(f"/api/atlas/{a['id']}")
