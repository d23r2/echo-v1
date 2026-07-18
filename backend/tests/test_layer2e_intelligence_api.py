"""ECHO Layer 2E — /api/goals/* and the new /api/intelligence/* surface
(context select/preview, cross-goal review, overview, evaluations alias).
Uses the real shared app DB via TestClient, same convention as
test_layer2c_intelligence_api.py / test_layer2d_intelligence_api.py."""

from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app

init_db()
client = TestClient(app)


def _create_goal(**overrides):
    body = {"title": "API test goal", "origin": "explicit_user"}
    body.update(overrides)
    resp = client.post("/api/goals", json=body)
    assert resp.status_code == 200
    return resp.json()


# ---- Goals CRUD + lifecycle ----


def test_create_explicit_goal_is_approved():
    goal = _create_goal()
    assert goal["status"] == "approved"


def test_create_system_suggested_goal_is_proposed():
    goal = _create_goal(title="System proposal", origin="system_suggestion")
    assert goal["status"] == "proposed"


def test_get_goal_404():
    resp = client.get("/api/goals/does-not-exist")
    assert resp.status_code == 404


def test_list_goals_includes_created():
    goal = _create_goal()
    resp = client.get("/api/goals")
    assert resp.status_code == 200
    assert any(g["id"] == goal["id"] for g in resp.json())


def test_patch_goal_updates_fields():
    goal = _create_goal()
    resp = client.patch(f"/api/goals/{goal['id']}", json={"priority": "high", "motivation": "it matters"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["priority"] == "high"
    assert body["motivation"] == "it matters"


def test_approve_pause_review_flow():
    goal = _create_goal(title="Lifecycle goal", origin="system_suggestion")
    approve_resp = client.post(f"/api/goals/{goal['id']}/approve")
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"

    pause_resp = client.post(f"/api/goals/{goal['id']}/pause")
    assert pause_resp.status_code == 200
    assert pause_resp.json()["status"] == "paused"

    review_resp = client.post(f"/api/goals/{goal['id']}/review")
    assert review_resp.status_code == 200
    assert "summary" in review_resp.json()


def test_approve_400_when_not_proposed():
    goal = _create_goal()  # already approved
    resp = client.post(f"/api/goals/{goal['id']}/approve")
    assert resp.status_code == 400


def test_abandon_requires_reason():
    goal = _create_goal()
    resp = client.post(f"/api/goals/{goal['id']}/abandon", json={"reason": ""})
    assert resp.status_code == 400
    resp2 = client.post(f"/api/goals/{goal['id']}/abandon", json={"reason": "no longer needed"})
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "abandoned"


def test_goal_progress_endpoint():
    goal = _create_goal()
    resp = client.get(f"/api/goals/{goal['id']}/progress")
    assert resp.status_code == 200
    assert resp.json()["percent_complete"] == 0.0


# ---- Context Selection v2 API ----


def test_context_select_returns_full_bundle():
    resp = client.post("/api/intelligence/context/select", json={"user_message": "hello there"})
    assert resp.status_code == 200
    body = resp.json()
    assert "total_chars" in body
    assert "excluded_context_summary" in body


def test_context_preview_returns_ui_safe_shape():
    resp = client.post("/api/intelligence/context/preview", json={"user_message": "hello there"})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"categories_included", "categories_excluded", "sources_summary", "estimated_chars", "budget_chars", "fallback_used"}


# ---- Cross-goal review ----


def test_cross_goal_review_endpoint():
    _create_goal(title="For cross-goal review")
    resp = client.post("/api/intelligence/goals/review", json={"review_type": "on_demand"})
    assert resp.status_code == 200
    assert "summary" in resp.json()


# ---- Intelligence overview ----


def test_overview_loads():
    resp = client.get("/api/intelligence/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["intelligence_health"] in ("green", "yellow", "red")
    assert "routing_status_summary" in body


# ---- Evaluations alias ----


def test_evaluations_run_alias_matches_existing_endpoint():
    resp = client.post("/api/intelligence/evaluations/run")
    assert resp.status_code == 200
    body = resp.json()
    assert body["result_summary"] in ("green", "yellow", "red")
    assert body["total_cases"] >= 21
