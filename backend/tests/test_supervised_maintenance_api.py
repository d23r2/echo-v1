"""ECHO Supervised Maintenance Workspace — HTTP/API-layer test pass.

Every existing Supervised Maintenance test (test_supervised_maintenance*.py,
51 tests before this pass) calls service functions directly
(`maintenance_policy.register_repository(db, ...)`), never through FastAPI's
TestClient against the actual router. That means request/response schema
validation, HTTP status-code mapping, and the router's own error-translation
(`_run()`, `_POLICY_ERROR_STATUS`, etc.) had never been exercised — a
genuine gap found during this test pass, not a hypothetical one. Uses the
real shared app DB via TestClient, the same convention
test_layer3a_selfmod_api.py and test_action_reliability_integration.py
already use for their own router-level tests.

Also confirms, at the HTTP boundary, the actual security posture this
system relies on: there is no authentication layer anywhere in this app
(confirmed by reading main.py's middleware stack and every other router),
so `requested_by` is a self-reported string, not a cryptographic identity.
The real boundary against a model-driven bypass is that no Supervised
Maintenance function is registered in action_system.py at all — see
test_maintenance_has_no_action_system_exposure below, and
docs/supervised_maintenance/test_run_plan.md §1 for the full reasoning.
"""

from fastapi.testclient import TestClient

from app.config import Settings
from app.db import init_db
from app.main import app
from app.services import maintenance_policy

init_db()
client = TestClient(app)


def _settings(**overrides):
    base = dict(
        supervised_maintenance_enabled=False,
        supervised_analysis_enabled=False,
        supervised_proposals_enabled=False,
        supervised_sandbox_enabled=False,
        supervised_local_commit_enabled=False,
        supervised_maintenance_frontend_enabled=False,
        supervised_maintenance_max_read_bytes=512_000,
    )
    base.update(overrides)
    return Settings(**base)


def test_status_endpoint_reports_defaults_all_disabled():
    resp = client.get("/api/governance/supervised-maintenance/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["supervised_maintenance_enabled"] is False
    assert body["supervised_maintenance_frontend_enabled"] is False


def test_policy_endpoint_exposes_protected_paths_and_scope():
    resp = client.get("/api/governance/supervised-maintenance/policy")
    assert resp.status_code == 200
    body = resp.json()
    assert "backend/app/constitution.py" in body["protected_paths"]
    assert "docs/supervised_maintenance/policy.md" in body["protected_paths"]
    assert "backend/app/services/" in body["allowed_path_prefixes"]
    assert body["capability_modes"] == [
        "disabled", "analyse_only", "propose_only", "sandbox_verify", "human_approved_local_commit",
    ]


def test_register_repository_rejects_at_http_layer_when_subsystem_disabled(monkeypatch):
    monkeypatch.setattr(maintenance_policy, "get_settings", lambda: _settings())
    resp = client.post(
        "/api/governance/supervised-maintenance/repositories",
        json={"display_name": "HTTP Test Repo A", "requested_by": "founder"},
    )
    assert resp.status_code == 403
    assert "disabled" in resp.json()["detail"].lower()


def test_register_repository_rejects_at_http_layer_for_model_identity(monkeypatch):
    monkeypatch.setattr(maintenance_policy, "get_settings", lambda: _settings(supervised_maintenance_enabled=True))
    resp = client.post(
        "/api/governance/supervised-maintenance/repositories",
        json={"display_name": "HTTP Test Repo B", "requested_by": "echo"},
    )
    assert resp.status_code == 403


def _shared_repo_id(monkeypatch):
    """register_repository() structurally allows only ONE row per REPO_ROOT
    (see maintenance_policy.py's module docstring), and every test in this
    file shares the real app DB via TestClient — so only the first caller
    across the whole module can actually register; everyone else must reuse
    it. Lists first, registers only if nothing exists yet."""
    monkeypatch.setattr(maintenance_policy, "get_settings", lambda: _settings(supervised_maintenance_enabled=True))
    existing = client.get("/api/governance/supervised-maintenance/repositories").json()
    if existing:
        return existing[0]["id"]
    resp = client.post(
        "/api/governance/supervised-maintenance/repositories",
        json={"display_name": "HTTP Test Shared Repo", "requested_by": "founder"},
    )
    assert resp.status_code == 200
    return resp.json()["id"]


def test_register_repository_succeeds_at_http_layer_for_founder(monkeypatch):
    repo_id = _shared_repo_id(monkeypatch)
    get_resp = client.get(f"/api/governance/supervised-maintenance/repositories/{repo_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["capability_mode"] == "disabled"
    assert get_resp.json()["id"] == repo_id


def test_get_repository_404_at_http_layer():
    resp = client.get("/api/governance/supervised-maintenance/repositories/does-not-exist")
    assert resp.status_code == 404


def test_list_files_rejects_at_http_layer_when_analysis_disabled(monkeypatch):
    repo_id = _shared_repo_id(monkeypatch)

    from app.services import maintenance_code_access

    monkeypatch.setattr(maintenance_code_access, "get_settings", lambda: _settings())
    resp = client.get(f"/api/governance/supervised-maintenance/repositories/{repo_id}/files")
    assert resp.status_code == 403


def test_create_analysis_rejects_at_http_layer_for_disabled_capability_mode(monkeypatch):
    repo_id = _shared_repo_id(monkeypatch)

    from app.services import maintenance_analysis

    monkeypatch.setattr(maintenance_analysis, "get_settings", lambda: _settings(supervised_maintenance_enabled=True))
    resp = client.post(
        "/api/governance/supervised-maintenance/analyses",
        json={"repository_id": repo_id, "objective": "Find dead code."},
    )
    assert resp.status_code == 403  # repository capability_mode is still "disabled"


def test_propose_from_analysis_for_unknown_analysis_fails_closed(monkeypatch):
    """LOW-severity finding from this test pass: create_proposal_from_analysis()
    raises the base MaintenanceProposalError for an unknown analysis_id
    (router maps that to 400), not a dedicated not-found type mapped to 404
    the way get_analysis()/list_findings() are — a REST-semantics
    inconsistency with sibling endpoints, not a security issue. The request
    is still correctly rejected before anything is created; pinned here as
    the real current behavior rather than the ideal one."""
    from app.services import maintenance_proposal

    monkeypatch.setattr(maintenance_proposal, "get_settings", lambda: _settings(
        supervised_maintenance_enabled=True, supervised_proposals_enabled=True,
    ))
    resp = client.post(
        "/api/governance/supervised-maintenance/analyses/does-not-exist/propose",
        json={"title": "t", "description": "d", "rationale": "r" * 20, "patch_text": "diff"},
    )
    assert resp.status_code == 400
    assert "not found" in resp.json()["detail"].lower()


def test_audit_endpoint_returns_list_shape():
    resp = client.get("/api/governance/supervised-maintenance/audit")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ---- The actual self-approval security boundary ----


def test_maintenance_has_no_action_system_exposure():
    """The real reason ECHO cannot register a repository, change its own
    capability mode, or approve its own proposal is not the `requested_by`
    string check (self-reported, unverifiable in this single-user,
    unauthenticated app — confirmed consistent with every other router in
    the codebase, not a maintenance-specific gap). It's that no Supervised
    Maintenance function is reachable through action_system.py's
    model-facing tool-calling loop at all. This pins that structural fact
    as a regression test: if anyone ever adds a `maintenance_*`/
    `supervised_*` ActionSpec, this test starts failing and must be
    deliberately reviewed for the self-approval implications before
    proceeding."""
    from app.services.action_system import ACTIONS

    exposed = [name for name in ACTIONS if "maintenance" in name.lower() or "supervised" in name.lower()]
    assert exposed == [], f"Unexpected model-facing Supervised Maintenance action(s) registered: {exposed}"
