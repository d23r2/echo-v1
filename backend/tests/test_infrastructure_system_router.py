"""ECHO Layer 0 — /health, /ready, /api/system/* endpoints. Uses the real
shared app DB via TestClient (same convention as test_cognitive_router.py)."""

from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app

init_db()
client = TestClient(app)


def test_health_returns_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_ready_returns_true_with_healthy_database():
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json()["ready"] is True


def test_system_status_has_expected_shape():
    resp = client.get("/api/system/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("green", "yellow", "red")
    assert body["backend_url"] == "http://localhost:8000"
    assert body["frontend_expected_url"] == "http://localhost:5174"
    assert isinstance(body["warnings"], list)


def test_system_status_ollama_offline_gives_yellow_not_crash():
    """Ollama unreachable in this test environment is expected and must
    degrade to yellow, not 500 — the endpoint must always respond."""
    resp = client.get("/api/system/status")
    assert resp.status_code == 200
    assert resp.json()["status"] in ("green", "yellow")


def test_diagnostics_excludes_all_secrets():
    resp = client.get("/api/system/diagnostics")
    assert resp.status_code == 200
    body = resp.json()
    serialized = str(body)
    assert "anthropic_api_key" not in body["configuration"]
    assert "gemini_api_key" not in body["configuration"]
    for suspicious in ("sk-", "Bearer "):
        assert suspicious not in serialized


def test_diagnostics_includes_feature_flags_and_providers():
    resp = client.get("/api/system/diagnostics")
    body = resp.json()
    assert len(body["feature_flags"]) > 0
    assert len(body["providers"]) > 0
    assert "schema_version" in body


def test_features_endpoint_lists_core_subsystems():
    resp = client.get("/api/system/features")
    assert resp.status_code == 200
    keys = {f["key"] for f in resp.json()["features"]}
    assert "atlas" in keys
    assert "cognitive_core" in keys
    assert "developer_mode" in keys


def test_providers_endpoint_no_raw_exception_text():
    resp = client.get("/api/system/providers")
    assert resp.status_code == 200
    serialized = str(resp.json())
    assert "Traceback" not in serialized
    assert "Exception" not in serialized


def test_models_endpoint_includes_local_roles():
    resp = client.get("/api/system/models")
    assert resp.status_code == 200
    body = resp.json()
    roles = {r["role"] for r in body["local_model_roles"]}
    assert {"fast", "reasoning", "coding", "critic", "writing"}.issubset(roles)


def test_metrics_endpoint_reports_enabled_by_default():
    resp = client.get("/api/system/metrics")
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True


def test_version_endpoint_has_expected_fields():
    resp = client.get("/api/system/version")
    assert resp.status_code == 200
    body = resp.json()
    assert "application_version" in body
    assert "schema_version" in body
    assert "api_version" in body


def test_check_provider_unknown_id_reports_not_found_cleanly():
    resp = client.post("/api/system/providers/not-a-real-provider/check")
    assert resp.status_code == 200
    assert resp.json()["found"] is False


def test_check_provider_known_id_reports_result():
    resp = client.post("/api/system/providers/ollama/check")
    assert resp.status_code == 200
    body = resp.json()
    assert body["found"] is True
    assert "available" in body
