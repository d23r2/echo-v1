"""ECHO Layer 2A — /api/intelligence/* router. Uses the real shared app DB
via TestClient, same convention as test_layer1_api.py."""

from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app

init_db()
client = TestClient(app)


def test_task_understanding_endpoint_returns_null_for_simple_message():
    resp = client.post("/api/intelligence/task-understanding", json={"user_message": "hi"})
    assert resp.status_code == 200
    assert resp.json() is None


def test_task_understanding_endpoint_returns_task_for_complex_message():
    resp = client.post(
        "/api/intelligence/task-understanding",
        json={"user_message": "Fix the failing backend test", "conversation_id": "api-conv-1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body is not None
    assert body["task_category"] in ("debugging", "coding")
    assert "acceptance_tests_json" in body


def test_get_task_by_id():
    created = client.post(
        "/api/intelligence/task-understanding",
        json={"user_message": "Fix the failing backend test", "conversation_id": "api-conv-2"},
    ).json()
    resp = client.get(f"/api/intelligence/tasks/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


def test_get_task_404_for_unknown_id():
    resp = client.get("/api/intelligence/tasks/does-not-exist")
    assert resp.status_code == 404


def test_patch_task_correction():
    created = client.post(
        "/api/intelligence/task-understanding",
        json={"user_message": "Fix the failing backend test", "conversation_id": "api-conv-3"},
    ).json()
    resp = client.patch(f"/api/intelligence/tasks/{created['id']}", json={"primary_goal": "Actually write the docs"})
    assert resp.status_code == 200
    assert resp.json()["primary_goal"] == "Actually write the docs"


def test_reanalyse_endpoint():
    created = client.post(
        "/api/intelligence/task-understanding",
        json={"user_message": "Fix the failing backend test", "conversation_id": "api-conv-4"},
    ).json()
    resp = client.post(f"/api/intelligence/tasks/{created['id']}/reanalyse")
    assert resp.status_code == 200
    assert resp.json()["parent_task_id"] == created["id"]


def test_reanalyse_404_for_unknown_id():
    resp = client.post("/api/intelligence/tasks/does-not-exist/reanalyse")
    assert resp.status_code == 404


def test_context_preview_for_complex_message():
    resp = client.post(
        "/api/intelligence/context-preview",
        json={"user_message": "Fix the failing backend test", "conversation_id": "api-conv-5"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["task_understanding"] is not None
    assert body["brief_text"] is not None
    assert "needs_clarification" in body["clarification"]


def test_context_preview_for_simple_message():
    resp = client.post("/api/intelligence/context-preview", json={"user_message": "hi"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["task_understanding"] is None
    assert body["clarification"]["needs_clarification"] is False


def test_task_types_endpoint():
    resp = client.get("/api/intelligence/task-types")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["task_types"]) > 0
    assert len(body["task_categories"]) == 14  # the milestone's full taxonomy


def test_no_raw_json_dump_in_context_preview_brief():
    resp = client.post(
        "/api/intelligence/context-preview",
        json={"user_message": "Fix the failing backend test", "conversation_id": "api-conv-6"},
    )
    brief_text = resp.json()["brief_text"]
    assert "{" not in brief_text and "tier" not in brief_text
