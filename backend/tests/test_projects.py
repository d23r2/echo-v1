"""ECHO Personal OS v1: Projects CRUD (app/routers/projects.py). Hits the real
app DB via TestClient like test_library_and_schedule.py — uses unique title
substrings so assertions stay order-independent on this session-shared DB.
DELETE is a soft-archive, never a hard delete: see
test_delete_project_soft_archives_not_deletes below.
"""

import uuid

from fastapi.testclient import TestClient

from app.db import SessionLocal, init_db
from app.main import app
from app.models import MemoryCandidate

init_db()
client = TestClient(app)


def _unique(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}"


def test_create_project_requires_title():
    resp = client.post("/api/projects", json={"title": "   "})
    assert resp.status_code == 400


def test_create_project_defaults():
    title = _unique("new-project")
    resp = client.post("/api/projects", json={"title": title})
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == title
    assert body["status"] == "active"
    assert body["priority"] == "medium"
    assert body["tags"] == []
    assert body["archived_at"] is None


def test_list_projects_excludes_archived_by_default():
    active_title = _unique("active-project")
    archived_title = _unique("archived-project")
    active = client.post("/api/projects", json={"title": active_title}).json()
    archived = client.post("/api/projects", json={"title": archived_title}).json()
    client.delete(f"/api/projects/{archived['id']}")

    resp = client.get("/api/projects")
    ids = {p["id"] for p in resp.json()}
    assert active["id"] in ids
    assert archived["id"] not in ids


def test_list_projects_status_filter_returns_archived_when_requested():
    title = _unique("to-archive")
    project = client.post("/api/projects", json={"title": title}).json()
    client.delete(f"/api/projects/{project['id']}")

    resp = client.get("/api/projects", params={"status": "archived"})
    ids = {p["id"] for p in resp.json()}
    assert project["id"] in ids


def test_update_project_partial_fields():
    title = _unique("update-me")
    project = client.post("/api/projects", json={"title": title, "priority": "low"}).json()

    resp = client.patch(f"/api/projects/{project['id']}", json={"priority": "high", "status": "paused"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["priority"] == "high"
    assert body["status"] == "paused"
    assert body["title"] == title  # untouched fields survive a partial update


def test_update_project_unknown_status_rejected():
    # Rejected by ProjectUpdate.status's Literal type at the schema layer
    # (422), before the router's own status-set check would ever run.
    project = client.post("/api/projects", json={"title": _unique("bad-status")}).json()
    resp = client.patch(f"/api/projects/{project['id']}", json={"status": "not-a-real-status"})
    assert resp.status_code == 422


def test_delete_project_soft_archives_not_deletes():
    project = client.post("/api/projects", json={"title": _unique("soft-delete")}).json()
    resp = client.delete(f"/api/projects/{project['id']}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"
    assert resp.json()["archived_at"] is not None

    # Still fetchable directly — archiving is not deletion.
    detail = client.get(f"/api/projects/{project['id']}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "archived"


def test_get_project_404_for_unknown_id():
    resp = client.get("/api/projects/does-not-exist")
    assert resp.status_code == 404


def test_project_detail_includes_linked_tasks():
    project = client.post("/api/projects", json={"title": _unique("with-tasks")}).json()
    task_title = _unique("linked-task")
    client.post("/api/tasks", json={"title": task_title, "project_id": project["id"]})

    resp = client.get(f"/api/projects/{project['id']}")
    assert resp.status_code == 200
    tasks = resp.json()["tasks"]
    assert any(t["title"] == task_title for t in tasks)


def test_create_project_queues_a_pending_memory_candidate_not_a_direct_save():
    """Phase 10: a new project is durable enough to be worth Atlas knowing
    about, but it must go through the existing review queue — never saved
    directly, and never surfaced anywhere in the project creation response
    itself (no memory-related field leaks into ProjectOut)."""
    title = _unique("memory-linked-project")
    resp = client.post("/api/projects", json={"title": title})
    assert resp.status_code == 200
    assert "memory" not in resp.json()  # ProjectOut has no memory-candidate field at all

    session = SessionLocal()
    try:
        candidate = (
            session.query(MemoryCandidate)
            .filter(MemoryCandidate.content.contains(title))
            .one_or_none()
        )
        assert candidate is not None
        assert candidate.status == "pending"
        assert candidate.memory_type == "project"
    finally:
        session.close()


def test_list_project_tasks_endpoint():
    project = client.post("/api/projects", json={"title": _unique("task-list-project")}).json()
    task_title = _unique("project-scoped-task")
    client.post("/api/tasks", json={"title": task_title, "project_id": project["id"]})

    resp = client.get(f"/api/projects/{project['id']}/tasks")
    assert resp.status_code == 200
    titles = [t["title"] for t in resp.json()]
    assert task_title in titles
