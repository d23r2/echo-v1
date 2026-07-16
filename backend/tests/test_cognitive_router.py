"""ECHO Cognitive Core v1 — router-level tests via TestClient (the shared
app DB, same pattern as test_local_intelligence_chat_integration.py)."""

from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app

init_db()
client = TestClient(app)


def test_concepts_crud_via_api():
    create_resp = client.post("/api/cognitive/concepts", json={"name": "Router Test Concept", "concept_type": "tool"})
    assert create_resp.status_code == 200
    concept = create_resp.json()
    concept_id = concept["id"]

    get_resp = client.get(f"/api/cognitive/concepts/{concept_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Router Test Concept"

    list_resp = client.get("/api/cognitive/concepts")
    assert list_resp.status_code == 200
    assert any(c["id"] == concept_id for c in list_resp.json())

    patch_resp = client.patch(f"/api/cognitive/concepts/{concept_id}", json={"description": "updated"})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["description"] == "updated"

    delete_resp = client.delete(f"/api/cognitive/concepts/{concept_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["archived_at"] is not None

    list_after = client.get("/api/cognitive/concepts")
    assert all(c["id"] != concept_id for c in list_after.json())


def test_relationships_crud_via_api():
    a = client.post("/api/cognitive/concepts", json={"name": "Rel A"}).json()
    b = client.post("/api/cognitive/concepts", json={"name": "Rel B"}).json()
    rel_resp = client.post(
        "/api/cognitive/relationships", json={"from_concept_id": a["id"], "to_concept_id": b["id"], "relation_type": "uses"}
    )
    assert rel_resp.status_code == 200
    rel_id = rel_resp.json()["id"]

    list_resp = client.get("/api/cognitive/relationships", params={"concept_id": a["id"]})
    assert any(r["id"] == rel_id for r in list_resp.json())

    delete_resp = client.delete(f"/api/cognitive/relationships/{rel_id}")
    assert delete_resp.status_code == 200


def test_graph_search_via_api():
    client.post("/api/cognitive/concepts", json={"name": "Graph Search Target", "description": "unique marker text"})
    resp = client.get("/api/cognitive/graph", params={"query": "Graph Search Target"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["concept"]["name"] == "Graph Search Target"


def test_skills_crud_and_suggest_plan_via_api():
    list_resp = client.get("/api/cognitive/skills")
    assert list_resp.status_code == 200
    names = {s["name"] for s in list_resp.json()}
    assert "Build Android APK" in names  # seeded at init_db()

    skill_id = next(s["id"] for s in list_resp.json() if s["name"] == "Build Android APK")
    plan_resp = client.post(f"/api/cognitive/skills/{skill_id}/suggest-plan", json={"user_message": "build the apk"})
    assert plan_resp.status_code == 200
    assert len(plan_resp.json()["plan_steps"]) > 0


def test_causal_notes_crud_via_api():
    create_resp = client.post(
        "/api/cognitive/causal-notes", json={"title": "Router Test Note", "cause": "X", "effect": "Y", "explanation": "Z"}
    )
    assert create_resp.status_code == 200
    note_id = create_resp.json()["id"]

    list_resp = client.get("/api/cognitive/causal-notes")
    assert any(n["id"] == note_id for n in list_resp.json())

    patch_resp = client.patch(f"/api/cognitive/causal-notes/{note_id}", json={"cause": "X updated"})
    assert patch_resp.json()["cause"] == "X updated"

    delete_resp = client.delete(f"/api/cognitive/causal-notes/{note_id}")
    assert delete_resp.status_code == 200
    list_after = client.get("/api/cognitive/causal-notes")
    assert all(n["id"] != note_id for n in list_after.json())


def test_understand_and_brief_via_api():
    understand_resp = client.post("/api/cognitive/understand", json={"user_message": "Give me a prompt to update Android APK."})
    assert understand_resp.status_code == 200
    tu = understand_resp.json()
    assert tu is not None
    assert tu["domain"] == "Android"

    brief_resp = client.post("/api/cognitive/brief", json={"user_message": "Give me a prompt to update Android APK."})
    assert brief_resp.status_code == 200
    brief = brief_resp.json()
    assert brief is not None
    assert "Goal:" in brief["brief_text"]

    list_resp = client.get("/api/cognitive/task-understandings")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) > 0


def test_understand_returns_null_for_simple_message():
    resp = client.post("/api/cognitive/understand", json={"user_message": "hi"})
    assert resp.status_code == 200
    assert resp.json() is None


def test_settings_get_and_patch_via_api():
    get_resp = client.get("/api/cognitive/settings")
    assert get_resp.status_code == 200
    assert "cognitive_core_enabled" in get_resp.json()

    patch_resp = client.patch("/api/cognitive/settings", json={"cognitive_show_developer_diagnostics": True})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["cognitive_show_developer_diagnostics"] is True

    # Restore for other tests sharing this DB.
    client.patch("/api/cognitive/settings", json={"cognitive_show_developer_diagnostics": False})


def test_no_raw_errors_leak_from_cognitive_endpoints():
    resp = client.post("/api/cognitive/concepts", json={"name": "   "})
    assert resp.status_code == 400
    assert "Traceback" not in resp.text

    resp2 = client.get("/api/cognitive/concepts/nonexistent-id")
    assert resp2.status_code == 404
    assert "Traceback" not in resp2.text
