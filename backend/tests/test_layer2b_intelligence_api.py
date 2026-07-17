"""ECHO Layer 2B — /api/intelligence/systems and /api/intelligence/simulations.
Uses the real shared app DB via TestClient, same convention as
test_layer2a_intelligence_api.py / test_layer1_api.py."""

from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app

init_db()
client = TestClient(app)


def _create_concept(name: str) -> str:
    resp = client.post("/api/cognitive/concepts", json={"name": name, "concept_type": "system"})
    assert resp.status_code == 200
    return resp.json()["id"]


# ---- SystemModel CRUD ----


def test_create_and_get_system():
    resp = client.post("/api/intelligence/systems", json={"name": "API test system", "scope": "software_architecture"})
    assert resp.status_code == 200
    system_id = resp.json()["id"]

    fetched = client.get(f"/api/intelligence/systems/{system_id}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "API test system"


def test_get_system_404():
    resp = client.get("/api/intelligence/systems/does-not-exist")
    assert resp.status_code == 404


def test_list_systems_includes_created():
    created = client.post("/api/intelligence/systems", json={"name": "Listable system"}).json()
    resp = client.get("/api/intelligence/systems")
    assert resp.status_code == 200
    assert any(s["id"] == created["id"] for s in resp.json())


def test_patch_system():
    created = client.post("/api/intelligence/systems", json={"name": "Before rename"}).json()
    resp = client.patch(f"/api/intelligence/systems/{created['id']}", json={"name": "After rename"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "After rename"


def test_archive_system_removes_from_default_list():
    created = client.post("/api/intelligence/systems", json={"name": "To be archived"}).json()
    resp = client.delete(f"/api/intelligence/systems/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["archived_at"] is not None
    listed_ids = [s["id"] for s in client.get("/api/intelligence/systems").json()]
    assert created["id"] not in listed_ids


# ---- SystemModelNode ----


def test_add_and_list_node():
    system = client.post("/api/intelligence/systems", json={"name": "Node test system"}).json()
    concept_id = _create_concept("API Gateway Concept")

    resp = client.post(f"/api/intelligence/systems/{system['id']}/nodes", json={"concept_id": concept_id, "node_role": "component"})
    assert resp.status_code == 200
    assert resp.json()["concept_name"] == "API Gateway Concept"

    nodes = client.get(f"/api/intelligence/systems/{system['id']}/nodes")
    assert nodes.status_code == 200
    assert len(nodes.json()) == 1


def test_add_node_404_for_unknown_concept():
    system = client.post("/api/intelligence/systems", json={"name": "Sys"}).json()
    resp = client.post(f"/api/intelligence/systems/{system['id']}/nodes", json={"concept_id": "does-not-exist"})
    assert resp.status_code == 404


def test_delete_node():
    system = client.post("/api/intelligence/systems", json={"name": "Delete node system"}).json()
    concept_id = _create_concept("Deletable concept")
    node = client.post(f"/api/intelligence/systems/{system['id']}/nodes", json={"concept_id": concept_id}).json()
    resp = client.delete(f"/api/intelligence/systems/{system['id']}/nodes/{node['id']}")
    assert resp.status_code == 200
    assert client.get(f"/api/intelligence/systems/{system['id']}/nodes").json() == []


# ---- Analysis / counterfactuals ----


def test_system_analysis_endpoint():
    system = client.post("/api/intelligence/systems", json={"name": "Analysis system"}).json()
    a_id = _create_concept("Analysis Concept A")
    b_id = _create_concept("Analysis Concept B")
    client.post(f"/api/intelligence/systems/{system['id']}/nodes", json={"concept_id": a_id})
    client.post(f"/api/intelligence/systems/{system['id']}/nodes", json={"concept_id": b_id})
    client.post("/api/cognitive/relationships", json={"from_concept_id": a_id, "to_concept_id": b_id, "relation_type": "depends_on"})

    resp = client.get(f"/api/intelligence/systems/{system['id']}/analysis")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["nodes"]) == 2
    assert len(body["edges"]) == 1
    assert body["cycles"] == []


def test_system_analysis_404_for_unknown_system():
    resp = client.get("/api/intelligence/systems/does-not-exist/analysis")
    assert resp.status_code == 404


def test_system_counterfactuals_endpoint():
    system = client.post("/api/intelligence/systems", json={"name": "Counterfactual system"}).json()
    resp = client.get(f"/api/intelligence/systems/{system['id']}/counterfactuals")
    assert resp.status_code == 200
    assert "counterfactuals" in resp.json()


# ---- Simulations ----


def test_create_simulation_without_system_model():
    resp = client.post("/api/intelligence/simulations", json={"objective": "Improve reliability", "max_scenarios": 2, "max_steps": 3})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert any(s["label"] == "baseline" for s in body["scenarios"])


def test_create_simulation_404_for_unknown_system_model():
    resp = client.post("/api/intelligence/simulations", json={"objective": "x", "system_model_id": "does-not-exist"})
    assert resp.status_code == 404


def test_get_simulation_by_id():
    created = client.post("/api/intelligence/simulations", json={"objective": "Findable via API", "max_scenarios": 1, "max_steps": 2}).json()
    resp = client.get(f"/api/intelligence/simulations/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


def test_get_simulation_404():
    resp = client.get("/api/intelligence/simulations/does-not-exist")
    assert resp.status_code == 404


def test_list_simulations_includes_created():
    created = client.post("/api/intelligence/simulations", json={"objective": "Listable simulation", "max_scenarios": 1, "max_steps": 2}).json()
    resp = client.get("/api/intelligence/simulations")
    assert resp.status_code == 200
    assert any(s["id"] == created["id"] for s in resp.json())


def test_decision_handoff_endpoint():
    created = client.post("/api/intelligence/simulations", json={"objective": "Handoff test", "max_scenarios": 2, "max_steps": 3}).json()
    resp = client.get(f"/api/intelligence/simulations/{created['id']}/decision-handoff")
    assert resp.status_code == 200
    body = resp.json()
    assert body["simulation_id"] == created["id"]
    assert "caveats" in body


def test_decision_handoff_404_for_unknown_simulation():
    resp = client.get("/api/intelligence/simulations/does-not-exist/decision-handoff")
    assert resp.status_code == 404


# ---- No chain-of-thought / no raw internals exposure ----


def test_simulation_response_never_exposes_action_system_internals():
    created = client.post("/api/intelligence/simulations", json={"objective": "Clean response test", "max_scenarios": 1, "max_steps": 2}).json()
    import json

    body_text = json.dumps(created)
    assert "action_system" not in body_text
