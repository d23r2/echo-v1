"""Layer 3A Part 2B startup preload, feature flag, and safe diagnostics."""

from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal, init_db
from app.main import app
from app.models import AssistantIdentityProfile
from app.services import identity_runtime


def test_startup_preloads_identity_without_provider_network_call(monkeypatch):
    calls = 0

    def forbidden_provider_check(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("startup must not call a provider")

    monkeypatch.setattr("app.providers.ollama_provider.OllamaProvider.available", forbidden_provider_check)
    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert calls == 0
    diagnostics = identity_runtime.get_safe_identity_diagnostics()
    assert diagnostics["status"] in {"healthy", "degraded"}
    assert diagnostics["cache_status"] in {"populated", "cache_error"}


def test_repeated_startup_bootstrap_does_not_duplicate_identity_versions():
    init_db()
    init_db()
    with SessionLocal() as db:
        count = (
            db.query(AssistantIdentityProfile)
            .filter(AssistantIdentityProfile.profile_key == "echo-primary")
            .count()
        )
    assert count == 1


def test_system_status_and_version_expose_only_safe_identity_summary():
    with TestClient(app) as client:
        status = client.get("/api/system/status").json()["identity"]
        version = client.get("/api/system/version").json()["identity_engine"]

    assert set(status) == {"enabled", "status", "fallback_used"}
    assert set(version) == {"enabled", "schema_version", "active_profile_version", "status"}
    serialized = str({"status": status, "version": version})
    for forbidden in ("internal_role", "commitment_keys", "fingerprint", "metadata"):
        assert forbidden not in serialized


def test_developer_diagnostics_can_show_safe_runtime_details(monkeypatch):
    monkeypatch.setenv("DEVELOPER_MODE", "true")
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            identity = client.get("/api/system/diagnostics").json()["identity"]
        assert "fingerprint_prefix" in identity
        assert "commitment_keys" in identity
        assert "internal_role" not in identity
        assert "metadata_json" not in str(identity)
    finally:
        get_settings.cache_clear()


def test_disabled_feature_flag_reports_disabled_and_does_not_inject(monkeypatch):
    monkeypatch.setenv("CORE_IDENTITY_V1_ENABLED", "false")
    get_settings.cache_clear()
    try:
        diagnostics = identity_runtime.get_safe_identity_diagnostics()
        assert diagnostics == {
            "enabled": False,
            "status": "disabled",
            "cache_status": "disabled",
            "fallback_used": False,
        }
    finally:
        get_settings.cache_clear()
