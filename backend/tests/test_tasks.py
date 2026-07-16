"""ECHO Personal OS v1: Tasks CRUD (app/routers/tasks.py). Same real-DB /
TestClient / unique-title pattern as test_projects.py. Covers: creating a
task with and without a project, filters, completing, and DELETE being a
soft-cancel rather than a hard delete.
"""

import uuid

from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app

init_db()
client = TestClient(app)


def _unique(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}"


def test_create_task_requires_title():
    resp = client.post("/api/tasks", json={"title": ""})
    assert resp.status_code == 400


def test_create_task_without_project_works():
    title = _unique("standalone-task")
    resp = client.post("/api/tasks", json={"title": title})
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == title
    assert body["project_id"] is None
    assert body["project_title"] is None
    assert body["status"] == "todo"


def test_create_task_linked_to_project_includes_project_title():
    project_title = _unique("linked-project")
    project = client.post("/api/projects", json={"title": project_title}).json()

    resp = client.post("/api/tasks", json={"title": _unique("linked-task"), "project_id": project["id"]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == project["id"]
    assert body["project_title"] == project_title


def test_create_task_unknown_project_404s():
    resp = client.post("/api/tasks", json={"title": _unique("orphan"), "project_id": "does-not-exist"})
    assert resp.status_code == 404


def test_list_tasks_filters_by_status():
    title = _unique("done-task")
    task = client.post("/api/tasks", json={"title": title}).json()
    client.post(f"/api/tasks/{task['id']}/complete")

    resp = client.get("/api/tasks", params={"status": "done"})
    titles = [t["title"] for t in resp.json()]
    assert title in titles

    resp = client.get("/api/tasks", params={"status": "todo"})
    titles = [t["title"] for t in resp.json()]
    assert title not in titles


def test_list_tasks_filters_by_project_id():
    project = client.post("/api/projects", json={"title": _unique("filter-project")}).json()
    in_project = _unique("in-project-task")
    outside_project = _unique("outside-project-task")
    client.post("/api/tasks", json={"title": in_project, "project_id": project["id"]})
    client.post("/api/tasks", json={"title": outside_project})

    resp = client.get("/api/tasks", params={"project_id": project["id"]})
    titles = [t["title"] for t in resp.json()]
    assert in_project in titles
    assert outside_project not in titles


def test_complete_task_sets_status_and_completed_at():
    task = client.post("/api/tasks", json={"title": _unique("to-complete")}).json()
    resp = client.post(f"/api/tasks/{task['id']}/complete")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "done"
    assert body["completed_at"] is not None


def test_update_task_status_back_to_todo_clears_completed_at():
    task = client.post("/api/tasks", json={"title": _unique("re-open")}).json()
    client.post(f"/api/tasks/{task['id']}/complete")

    resp = client.patch(f"/api/tasks/{task['id']}", json={"status": "todo"})
    assert resp.status_code == 200
    assert resp.json()["completed_at"] is None


def test_delete_task_soft_cancels_not_deletes():
    task = client.post("/api/tasks", json={"title": _unique("to-cancel")}).json()
    resp = client.delete(f"/api/tasks/{task['id']}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"

    # Still fetchable — cancelling is not deletion.
    detail = client.get(f"/api/tasks/{task['id']}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "cancelled"


def test_completed_task_does_not_disappear_from_unfiltered_list():
    task = client.post("/api/tasks", json={"title": _unique("stays-visible")}).json()
    client.post(f"/api/tasks/{task['id']}/complete")

    resp = client.get("/api/tasks")
    ids = {t["id"] for t in resp.json()}
    assert task["id"] in ids


def test_get_task_404_for_unknown_id():
    resp = client.get("/api/tasks/does-not-exist")
    assert resp.status_code == 404


def test_due_before_and_due_after_filters():
    early = client.post(
        "/api/tasks", json={"title": _unique("early-task"), "due_at": "2020-01-01T00:00:00Z"}
    ).json()
    late = client.post(
        "/api/tasks", json={"title": _unique("late-task"), "due_at": "2099-01-01T00:00:00Z"}
    ).json()

    resp = client.get("/api/tasks", params={"due_before": "2050-01-01T00:00:00Z"})
    ids = {t["id"] for t in resp.json()}
    assert early["id"] in ids
    assert late["id"] not in ids

    resp = client.get("/api/tasks", params={"due_after": "2050-01-01T00:00:00Z"})
    ids = {t["id"] for t in resp.json()}
    assert late["id"] in ids
    assert early["id"] not in ids
