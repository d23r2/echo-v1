"""ECHO Layer 2D — /api/intelligence/orchestration/*, /api/intelligence/tools/plan,
and /api/system/models/roles. Uses the real shared app DB via TestClient, same
convention as test_layer2c_intelligence_api.py. Never calls real Ollama or a
real cloud provider — monkeypatches LocalModelRouter the same way the
execution-level tests do."""

from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app
from app.services.local_model_router import LocalModelRouter
from tests.fake_providers import FakeProvider

init_db()
client = TestClient(app)


def _patch_simple_router(monkeypatch, fake_provider):
    monkeypatch.setattr("app.services.orchestration_engine.LocalModelRouter", lambda *a, **k: LocalModelRouter(provider=fake_provider))


# ---- Preview (pure planning, no model call) ----


def test_preview_orchestration_returns_a_plan():
    resp = client.post("/api/intelligence/orchestration/preview", json={"user_message": "I really appreciate your patience and kindness."})
    assert resp.status_code == 200
    body = resp.json()
    assert body["task_category"] == "question"
    assert body["stage_profile"] == "simple"
    assert body["cloud_allowed"] is False


def test_preview_orchestration_complex_task_has_multiple_stages():
    resp = client.post("/api/intelligence/orchestration/preview", json={"user_message": "Fix the failing backend test for the login flow"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["stage_profile"] == "deep"
    assert len(body["stages"]) > 1


# ---- Run (real endpoint wiring, fake local model underneath) ----


def test_run_orchestration_returns_completed_run(monkeypatch):
    fake = FakeProvider("ollama", available=True, response_text="a clean, direct answer")
    _patch_simple_router(monkeypatch, fake)

    resp = client.post("/api/intelligence/orchestration/run", json={"user_message": "I really appreciate your patience and kindness."})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["answer"] == "a clean, direct answer"
    assert body["total_model_calls"] == 1
    assert body["cloud_used"] is False


def test_get_orchestration_run_roundtrip(monkeypatch):
    fake = FakeProvider("ollama", available=True, response_text="another answer")
    _patch_simple_router(monkeypatch, fake)

    created = client.post("/api/intelligence/orchestration/run", json={"user_message": "What a lovely day, thank you."}).json()
    resp = client.get(f"/api/intelligence/orchestration/runs/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


def test_get_orchestration_run_404():
    resp = client.get("/api/intelligence/orchestration/runs/does-not-exist")
    assert resp.status_code == 404


def test_list_orchestration_runs_includes_created(monkeypatch):
    fake = FakeProvider("ollama", available=True, response_text="listed answer")
    _patch_simple_router(monkeypatch, fake)

    created = client.post("/api/intelligence/orchestration/run", json={"user_message": "Much appreciated, that's very kind."}).json()
    resp = client.get("/api/intelligence/orchestration/runs")
    assert resp.status_code == 200
    assert any(r["id"] == created["id"] for r in resp.json())


# ---- Policies ----


def test_list_orchestration_policies_seeds_defaults():
    resp = client.get("/api/intelligence/orchestration/policies")
    assert resp.status_code == 200
    categories = {p["task_category"] for p in resp.json()}
    assert "question" in categories
    assert "coding" in categories


def test_patch_orchestration_policy_updates_field():
    policies = client.get("/api/intelligence/orchestration/policies").json()
    policy = next(p for p in policies if p["task_category"] == "question")
    resp = client.patch(f"/api/intelligence/orchestration/policies/{policy['id']}", json={"max_model_calls": 3})
    assert resp.status_code == 200
    assert resp.json()["max_model_calls"] == 3


def test_patch_orchestration_policy_404():
    resp = client.patch("/api/intelligence/orchestration/policies/does-not-exist", json={"max_model_calls": 3})
    assert resp.status_code == 404


# ---- Tool plan ----


def test_plan_tools_endpoint_returns_typed_plan():
    resp = client.post("/api/intelligence/tools/plan", json={"user_message": "Write me a short poem about the ocean."})
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert "routing_reason" in body


# ---- Capability-enriched role list ----


def test_system_models_roles_endpoint_returns_capability_tagged_roles():
    resp = client.get("/api/system/models/roles")
    assert resp.status_code == 200
    roles = resp.json()["roles"]
    role_names = {r["role"] for r in roles}
    assert role_names == {"fast", "reasoning", "coding", "critic", "writing"}
    for role in roles:
        assert isinstance(role["capabilities"], list)
