"""Phase 5: Library (app/routers/library.py, app/library.py) and Schedule
(app/routers/schedule.py) route-level tests, plus generate-image registering
into Library (Phase 6's "generated images saved to disk + registered in
Library"). Hits the real app DB via TestClient like the other route-level
test files (test_atlas_second_brain.py etc.) — tests use unique title/tag
substrings when asserting on list results so they stay order-independent
even though this DB is shared across the whole test session.
"""

import uuid

from fastapi.testclient import TestClient

from app import library
from app.db import SessionLocal, init_db
from app.main import app
from app.models import LibraryItem

init_db()
client = TestClient(app)


def _unique(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}"


# --- Library -----------------------------------------------------------


def test_register_item_creates_row_with_expected_fields():
    title = _unique("registered-item")
    session = SessionLocal()
    try:
        item = library.register_item(
            session,
            title=title,
            file_path="/tmp/whatever.png",
            file_type="image",
            source="image_generation",
            tags=["generated"],
            description="a test image",
        )
        assert item.id is not None
        assert item.title == title
        assert item.file_type == "image"
        assert item.source == "image_generation"
    finally:
        session.close()


def test_list_library_items_filters_by_query():
    title = _unique("searchable-report")
    session = SessionLocal()
    try:
        library.register_item(
            session, title=title, file_path="/tmp/report.md", file_type="report", source="health_report"
        )
    finally:
        session.close()

    resp = client.get("/api/library", params={"q": title})
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    assert results[0]["title"] == title


def test_list_library_items_filters_by_file_type():
    title = _unique("code-file")
    session = SessionLocal()
    try:
        library.register_item(
            session, title=title, file_path="/tmp/x.py", file_type="code", source="self_improvement"
        )
    finally:
        session.close()

    resp = client.get("/api/library", params={"q": title, "file_type": "report"})
    assert resp.json() == []

    resp = client.get("/api/library", params={"q": title, "file_type": "code"})
    assert len(resp.json()) == 1


def test_get_library_item_404_for_unknown_id():
    resp = client.get("/api/library/does-not-exist")
    assert resp.status_code == 404


def test_download_library_item_serves_file_within_attachments_dir():
    from app.config import get_settings

    attachments_dir = get_settings().attachments_dir
    real_path = f"{attachments_dir}/{_unique('downloadable')}.png"
    from pathlib import Path

    Path(attachments_dir).mkdir(parents=True, exist_ok=True)
    Path(real_path).write_bytes(b"\x89PNG fake bytes")

    title = _unique("download-me")
    session = SessionLocal()
    try:
        item = library.register_item(
            session, title=title, file_path=real_path, file_type="image", source="image_generation"
        )
        item_id = item.id
    finally:
        session.close()

    resp = client.get(f"/api/library/{item_id}/download")
    assert resp.status_code == 200
    assert resp.content == b"\x89PNG fake bytes"


def test_download_library_item_404_when_file_outside_attachments_dir(tmp_path):
    # Same path-traversal guard as delete — a row pointing outside the
    # attachments dir must not be servable, even if the file exists.
    outside_path = tmp_path / "outside.png"
    outside_path.write_bytes(b"nope")
    title = _unique("outside-item")
    session = SessionLocal()
    try:
        item = library.register_item(
            session, title=title, file_path=str(outside_path), file_type="image", source="image_generation"
        )
        item_id = item.id
    finally:
        session.close()

    resp = client.get(f"/api/library/{item_id}/download")
    assert resp.status_code == 404


def test_delete_library_item_removes_row(tmp_path):
    # File path is outside the app's attachments dir, so the delete route's
    # is_relative_to guard skips unlinking it (nothing to clean up) and just
    # removes the DB row — proves the safety guard doesn't block the delete.
    fake_path = tmp_path / "not_in_attachments.png"
    fake_path.write_bytes(b"fake")
    title = _unique("deletable-item")
    session = SessionLocal()
    try:
        item = library.register_item(
            session, title=title, file_path=str(fake_path), file_type="image", source="image_generation"
        )
        item_id = item.id
    finally:
        session.close()

    resp = client.delete(f"/api/library/{item_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    session = SessionLocal()
    try:
        assert session.get(LibraryItem, item_id) is None
    finally:
        session.close()


def test_delete_library_item_404_for_unknown_id():
    resp = client.delete("/api/library/does-not-exist")
    assert resp.status_code == 404


def test_generate_image_registers_library_item(monkeypatch):
    monkeypatch.setattr("app.routers.chat.image_router.select_provider", lambda: ("gemini", None))
    monkeypatch.setattr("app.routers.chat.gemini_provider.generate_image", lambda prompt: b"\x89PNG\r\n fake")

    prompt = _unique("a picture of a cat")
    resp = client.post("/api/chat/generate-image", data={"prompt": prompt})
    assert resp.status_code == 200

    listing = client.get("/api/library", params={"q": prompt[:20]})
    assert listing.status_code == 200
    results = listing.json()
    assert len(results) == 1
    assert results[0]["source"] == "image_generation"
    assert results[0]["file_type"] == "image"


# --- Schedule ------------------------------------------------------------


def test_create_schedule_item():
    title = _unique("water the plants")
    resp = client.post("/api/schedule", json={"title": title, "description": "daily"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == title
    assert body["status"] == "pending"
    assert body["reminder_type"] == "in_app"


def test_create_schedule_item_rejects_empty_title():
    resp = client.post("/api/schedule", json={"title": "   "})
    assert resp.status_code == 400


def test_list_schedule_items_pending_by_default():
    title = _unique("pending-task")
    create = client.post("/api/schedule", json={"title": title})
    item_id = create.json()["id"]

    resp = client.get("/api/schedule")
    assert resp.status_code == 200
    ids = [row["id"] for row in resp.json()]
    assert item_id in ids


def test_complete_then_list_by_status():
    title = _unique("finish-report")
    create = client.post("/api/schedule", json={"title": title})
    item_id = create.json()["id"]

    complete = client.post(f"/api/schedule/{item_id}/complete")
    assert complete.status_code == 200
    assert complete.json()["status"] == "completed"

    pending = client.get("/api/schedule")
    assert item_id not in [row["id"] for row in pending.json()]

    completed = client.get("/api/schedule", params={"status": "completed"})
    assert item_id in [row["id"] for row in completed.json()]


def test_cancel_schedule_item():
    title = _unique("cancel-me")
    create = client.post("/api/schedule", json={"title": title})
    item_id = create.json()["id"]

    resp = client.post(f"/api/schedule/{item_id}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


def test_update_schedule_item_title_and_due_date():
    title = _unique("original-title")
    create = client.post("/api/schedule", json={"title": title})
    item_id = create.json()["id"]

    new_title = _unique("updated-title")
    resp = client.patch(f"/api/schedule/{item_id}", json={"title": new_title, "due_at": "2026-08-01T12:00:00Z"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == new_title
    assert body["due_at"] is not None


def test_delete_schedule_item():
    title = _unique("delete-me")
    create = client.post("/api/schedule", json={"title": title})
    item_id = create.json()["id"]

    resp = client.delete(f"/api/schedule/{item_id}")
    assert resp.status_code == 200

    listing = client.get("/api/schedule", params={"status": "pending"})
    assert item_id not in [row["id"] for row in listing.json()]


def test_schedule_item_404_for_unknown_id():
    assert client.patch("/api/schedule/nope", json={"title": "x"}).status_code == 404
    assert client.post("/api/schedule/nope/complete").status_code == 404
    assert client.post("/api/schedule/nope/cancel").status_code == 404
    assert client.delete("/api/schedule/nope").status_code == 404
