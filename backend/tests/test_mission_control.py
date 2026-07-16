"""ECHO Personal OS v1: GET /api/mission-control (app/routers/mission_control.py).

The "empty DB" test uses the isolated db_session fixture (via a dependency
override) rather than the real shared session-DB the other route-level test
files use — that shared DB accumulates rows from every other test file in
the same pytest run, so it can never be asserted truly empty. The
"with active data" test uses the normal shared-DB TestClient and only
asserts that our own uniquely-titled rows show up, staying
order-independent like test_projects.py / test_tasks.py.
"""

import uuid

from fastapi.testclient import TestClient

from app.db import get_db, init_db
from app.main import app

init_db()
client = TestClient(app)


def _unique(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}"


def test_mission_control_valid_structure_with_empty_db(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        resp = client.get("/api/mission-control")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    body = resp.json()
    for key in (
        "today_tasks",
        "overdue_tasks",
        "upcoming_tasks",
        "active_projects",
        "recently_touched_projects",
        "recent_conversations",
        "recent_library_files",
        "upcoming_schedule_items",
        "pending_memory_candidates",
        "continue_where_left_off",
        "warnings",
    ):
        assert body[key] == []
    assert body["system_status"] is not None
    assert body["warnings"] == []


def test_mission_control_with_active_data_includes_our_project_and_task():
    project_title = _unique("mc-active-project")
    project = client.post("/api/projects", json={"title": project_title}).json()
    task_title = _unique("mc-overdue-task")
    client.post(
        "/api/tasks",
        json={"title": task_title, "project_id": project["id"], "due_at": "2020-01-01T00:00:00Z"},
    )

    resp = client.get("/api/mission-control")
    assert resp.status_code == 200
    body = resp.json()

    active_project_ids = {p["id"] for p in body["active_projects"]}
    assert project["id"] in active_project_ids

    overdue_titles = {t["title"] for t in body["overdue_tasks"]}
    assert task_title in overdue_titles

    assert body["warnings"] == []
    assert body["system_status"] is not None


def test_mission_control_never_leaks_raw_exception_text():
    """No section failure is simulated here (nothing to monkeypatch safely
    without real provider config), but the response contract itself must
    never include a raw traceback/exception string — warnings are always
    short, clean, pre-written messages."""
    resp = client.get("/api/mission-control")
    assert resp.status_code == 200
    for warning in resp.json()["warnings"]:
        assert "Traceback" not in warning
        assert "Error" not in warning or "temporarily unavailable" in warning


def test_continue_where_left_off_is_capped_at_five_and_well_formed():
    # Create more than 5 overdue tasks (the highest-priority suggestion
    # source) to confirm the cap holds regardless of how much is available.
    for _ in range(7):
        client.post(
            "/api/tasks",
            json={"title": _unique("mc-overdue-cap-task"), "due_at": "2020-01-01T00:00:00Z"},
        )

    resp = client.get("/api/mission-control")
    assert resp.status_code == 200
    suggestions = resp.json()["continue_where_left_off"]
    assert len(suggestions) <= 5
    for s in suggestions:
        assert s["id"]
        assert s["title"]
        assert s["reason"]
        assert s["action_label"]
        assert s["source_type"] in ("task", "project", "conversation", "schedule", "library", "atlas")
