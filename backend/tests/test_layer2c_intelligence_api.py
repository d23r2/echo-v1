"""ECHO Layer 2C — /api/intelligence/decisions and /plans. Uses the real
shared app DB via TestClient, same convention as
test_layer2b_intelligence_api.py / test_layer1_api.py."""

from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app

init_db()
client = TestClient(app)


def _create_decision(**overrides):
    body = {"question": "q", "objective": "o", "options": [{"label": "A"}, {"label": "B"}]}
    body.update(overrides)
    resp = client.post("/api/intelligence/decisions", json=body)
    assert resp.status_code == 200
    return resp.json()


def _create_plan(**overrides):
    body = {"objective": "o", "steps": [{"title": "Step 1"}]}
    body.update(overrides)
    resp = client.post("/api/intelligence/plans", json=body)
    assert resp.status_code == 200
    return resp.json()


# ---- Decisions ----


def test_create_and_get_decision():
    case = _create_decision()
    resp = client.get(f"/api/intelligence/decisions/{case['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == case["id"]


def test_get_decision_404():
    resp = client.get("/api/intelligence/decisions/does-not-exist")
    assert resp.status_code == 404


def test_list_decisions_includes_created():
    case = _create_decision()
    resp = client.get("/api/intelligence/decisions")
    assert resp.status_code == 200
    assert any(c["id"] == case["id"] for c in resp.json())


def test_analyse_decision_returns_report():
    case = _create_decision()
    resp = client.post(f"/api/intelligence/decisions/{case['id']}/analyse")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "analysed"
    assert body["report"] is not None
    assert "decision_summary" in body["report"]


def test_analyse_decision_404():
    resp = client.post("/api/intelligence/decisions/does-not-exist/analyse")
    assert resp.status_code == 404


def test_select_decision_option():
    case = _create_decision()
    option_id = case["options"][0]["id"]
    resp = client.post(f"/api/intelligence/decisions/{case['id']}/select", json={"option_id": option_id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "selected"
    assert body["recommended_option_id"] == option_id


def test_select_decision_option_400_for_foreign_option():
    case1 = _create_decision()
    case2 = _create_decision()
    resp = client.post(f"/api/intelligence/decisions/{case1['id']}/select", json={"option_id": case2["options"][0]["id"]})
    assert resp.status_code == 400


def test_update_criterion_weight():
    case = _create_decision(criteria=[{"name": "speed"}])
    criterion_id = case["criteria"][0]["id"]
    resp = client.patch(f"/api/intelligence/decisions/{case['id']}/criteria/{criterion_id}/weight", json={"weight": 0.5})
    assert resp.status_code == 200
    assert resp.json()["weight"] == 0.5


def test_update_option_ratings():
    case = _create_decision(criteria=[{"name": "speed"}])
    criterion_id = case["criteria"][0]["id"]
    option_id = case["options"][0]["id"]
    resp = client.patch(f"/api/intelligence/decisions/{case['id']}/options/{option_id}/ratings", json={"ratings": {criterion_id: 0.8}})
    assert resp.status_code == 200
    assert resp.json()["criterion_ratings_json"][criterion_id] == 0.8


def test_create_decision_404_for_unknown_simulation():
    resp = client.post("/api/intelligence/decisions", json={"question": "q", "objective": "o", "simulation_id": "does-not-exist"})
    assert resp.status_code == 404


# ---- Plans ----


def test_create_and_get_plan():
    plan = _create_plan()
    resp = client.get(f"/api/intelligence/plans/{plan['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == plan["id"]


def test_get_plan_404():
    resp = client.get("/api/intelligence/plans/does-not-exist")
    assert resp.status_code == 404


def test_list_plans_includes_created():
    plan = _create_plan()
    resp = client.get("/api/intelligence/plans")
    assert resp.status_code == 200
    assert any(p["id"] == plan["id"] for p in resp.json())


def test_patch_plan_scope():
    plan = _create_plan()
    resp = client.patch(f"/api/intelligence/plans/{plan['id']}", json={"scope": "narrower scope"})
    assert resp.status_code == 200
    assert resp.json()["scope"] == "narrower scope"


def test_validate_plan_endpoint():
    plan = _create_plan(steps=[{"title": "A"}, {"title": "B", "depends_on_titles": ["A"]}])
    resp = client.post(f"/api/intelligence/plans/{plan['id']}/validate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert len(body["critical_path_step_ids"]) == 2


def test_approve_plan_endpoint():
    plan = _create_plan()
    resp = client.post(f"/api/intelligence/plans/{plan['id']}/approve")
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


def test_approve_plan_twice_400():
    plan = _create_plan()
    client.post(f"/api/intelligence/plans/{plan['id']}/approve")
    resp = client.post(f"/api/intelligence/plans/{plan['id']}/approve")
    assert resp.status_code == 400


def test_materialise_before_approval_400():
    plan = _create_plan()
    resp = client.post(f"/api/intelligence/plans/{plan['id']}/materialise-tasks")
    assert resp.status_code == 400


def test_materialise_after_approval_creates_tasks():
    plan = _create_plan(steps=[{"title": "Do the thing"}])
    client.post(f"/api/intelligence/plans/{plan['id']}/approve")
    resp = client.post(f"/api/intelligence/plans/{plan['id']}/materialise-tasks")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["created_task_ids"]) == 1


def test_replan_endpoint():
    plan = _create_plan()
    client.post(f"/api/intelligence/plans/{plan['id']}/approve")
    resp = client.post(f"/api/intelligence/plans/{plan['id']}/replan", json={"reason": "needed more detail", "trigger": "user_correction"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "proposed"
    assert body["revision_number"] == 2


def test_replan_before_approval_400():
    plan = _create_plan()
    resp = client.post(f"/api/intelligence/plans/{plan['id']}/replan", json={"reason": "x"})
    assert resp.status_code == 400


def test_add_milestone_risk_resource():
    plan = _create_plan()
    step_id = plan["steps"][0]["id"]

    m_resp = client.post(f"/api/intelligence/plans/{plan['id']}/milestones", json={"name": "Milestone 1", "target_step_ids": [step_id]})
    assert m_resp.status_code == 200
    assert m_resp.json()["target_step_ids_json"] == [step_id]

    r_resp = client.post(f"/api/intelligence/plans/{plan['id']}/risks", json={"description": "Might slip", "likelihood": "medium", "impact": "low"})
    assert r_resp.status_code == 200
    assert r_resp.json()["description"] == "Might slip"

    res_resp = client.post(
        f"/api/intelligence/plans/{plan['id']}/resources", json={"resource_name": "Design review", "resource_type": "skill", "availability_status": "available"}
    )
    assert res_resp.status_code == 200
    assert res_resp.json()["resource_name"] == "Design review"


def test_create_plan_404_for_unknown_decision_case():
    resp = client.post("/api/intelligence/plans", json={"objective": "o", "decision_case_id": "does-not-exist"})
    assert resp.status_code == 404


# ---- No chain-of-thought / no internal exposure ----


def test_decision_and_plan_responses_never_expose_action_system_internals():
    import json

    case = _create_decision()
    analysed = client.post(f"/api/intelligence/decisions/{case['id']}/analyse").json()
    plan = _create_plan()
    assert "action_system" not in json.dumps(analysed)
    assert "action_system" not in json.dumps(plan)
