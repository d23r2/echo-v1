"""ECHO Layer 3A Part 2D — /api/self-modification/* router.

Uses the real shared app DB via TestClient, same convention as
test_layer2e_intelligence_api.py. Any test that reaches sandbox/deploy
monkeypatches self_modification_governance.sandbox and .get_settings —
never lets a request reach real git against the actual ECHO repository.
"""

from fastapi.testclient import TestClient

from app.config import Settings
from app.db import init_db
from app.main import app
from app.services import self_modification_governance as gov
from app.services import self_modification_sandbox as sandbox

init_db()
client = TestClient(app)


def _settings(**overrides):
    base = dict(
        supervised_self_modification_enabled=False,
        self_modification_sandbox_enabled=False,
        self_modification_deployment_enabled=False,
        self_modification_frontend_enabled=False,
        self_modification_approval_expiry_hours=24,
    )
    base.update(overrides)
    return Settings(**base)


def _patch_touching(path, extra_lines=1):
    body = "\n".join(f"+line {i}" for i in range(extra_lines))
    return (
        f"diff --git a/{path} b/{path}\n"
        f"index 0000000..1111111 100644\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        f"@@ -1,1 +1,{extra_lines + 1} @@\n"
        f" existing line\n"
        f"{body}\n"
    )


def _create_proposal(**overrides):
    body = {
        "title": "API test proposal",
        "description": "A small, safe change.",
        "rationale": (
            "Problem: The reviewed behavior needs a bounded change.\n"
            "Evidence: Repository inspection demonstrates the need.\n"
            "Assumptions: Existing public contracts remain stable.\n"
            "Proposed change: Improve a docstring without changing behavior.\n"
            "Risk: The affected display may regress.\n"
            "Rollback: Discard the isolated branch and restore the base commit.\n"
            "Test plan: Run targeted and full allowlisted verification checks."
        ),
    }
    body.update(overrides)
    resp = client.post("/api/self-modification", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _submit_and_check_revision(proposal_id, path="backend/tests/test_api_dummy.py"):
    resp = client.post(f"/api/self-modification/{proposal_id}/revisions", json={"patch_text": _patch_touching(path)})
    assert resp.status_code == 200, resp.text
    revision = resp.json()
    scope_resp = client.post(f"/api/self-modification/revisions/{revision['id']}/scope-check")
    assert scope_resp.status_code == 200, scope_resp.text
    compliance_resp = client.post(f"/api/self-modification/revisions/{revision['id']}/compliance-check")
    assert compliance_resp.status_code == 200, compliance_resp.text
    return compliance_resp.json()


# ---- Basic CRUD ----


def test_create_and_get_proposal():
    proposal = _create_proposal()
    assert proposal["status"] == "draft"
    assert proposal["risk_level"] == "low"

    resp = client.get(f"/api/self-modification/{proposal['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == proposal["id"]


def test_get_proposal_404():
    resp = client.get("/api/self-modification/does-not-exist")
    assert resp.status_code == 404


def test_list_proposals_includes_created():
    proposal = _create_proposal()
    resp = client.get("/api/self-modification")
    assert resp.status_code == 200
    assert any(p["id"] == proposal["id"] for p in resp.json())


def test_policy_endpoint_exposes_protected_paths():
    resp = client.get("/api/self-modification/policy")
    assert resp.status_code == 200
    body = resp.json()
    assert "backend/app/constitution.py" in body["protected_paths"]
    assert body["critical_proposals_blocked"] is True


def test_health_endpoint_defaults_all_disabled():
    resp = client.get("/api/self-modification/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["supervised_self_modification_enabled"] is False
    assert body["self_modification_deployment_enabled"] is False
    assert body["sandbox_runner"] == "docker"
    assert "network_isolation_enforced" in body


def test_incomplete_engineering_rationale_is_rejected():
    resp = client.post(
        "/api/self-modification",
        json={"title": "Unsafe shortcut", "description": "Missing review detail", "rationale": "Because."},
    )
    assert resp.status_code == 400


def test_likely_secret_patch_is_rejected():
    proposal = _create_proposal()
    patch = _patch_touching("backend/tests/test_secret_api.py") + '\n+api_key = "abcdefghijklmnopqrstuvwx"\n'
    resp = client.post(
        f"/api/self-modification/{proposal['id']}/revisions",
        json={"patch_text": patch},
    )
    assert resp.status_code == 400


# ---- Revision + checks lifecycle via API ----


def test_submit_revision_and_run_checks():
    proposal = _create_proposal()
    revision = _submit_and_check_revision(proposal["id"])
    assert revision["scope_check_status"] == "passed"
    assert revision["compliance_check_status"] == "passed"


def test_scope_check_404_for_unknown_revision():
    resp = client.post("/api/self-modification/revisions/does-not-exist/scope-check")
    assert resp.status_code == 404


def test_mark_ready_for_sandbox_via_api():
    proposal = _create_proposal()
    _submit_and_check_revision(proposal["id"])
    resp = client.post(f"/api/self-modification/{proposal['id']}/ready-for-sandbox")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready_for_sandbox"


def test_critical_risk_patch_blocked_via_api():
    proposal = _create_proposal()
    resp = client.post(
        f"/api/self-modification/{proposal['id']}/revisions",
        json={"patch_text": _patch_touching("backend/app/constitution.py")},
    )
    revision = resp.json()
    scope_resp = client.post(f"/api/self-modification/revisions/{revision['id']}/scope-check")
    assert scope_resp.json()["scope_check_status"] == "failed"

    ready_resp = client.post(f"/api/self-modification/{proposal['id']}/ready-for-sandbox")
    assert ready_resp.status_code in (400, 409)


# ---- Feature-flag / permission fail-closed behavior ----


def test_sandbox_endpoint_returns_403_when_disabled_by_default():
    proposal = _create_proposal()
    _submit_and_check_revision(proposal["id"])
    client.post(f"/api/self-modification/{proposal['id']}/ready-for-sandbox")
    resp = client.post(
        f"/api/self-modification/{proposal['id']}/sandbox",
        json={"confirmed": True, "actor_role": "founder"},
    )
    assert resp.status_code == 403


def test_sandbox_endpoint_requires_explicit_confirmation_body():
    proposal = _create_proposal()
    _submit_and_check_revision(proposal["id"])
    client.post(f"/api/self-modification/{proposal['id']}/ready-for-sandbox")
    resp = client.post(f"/api/self-modification/{proposal['id']}/sandbox")
    assert resp.status_code == 422


def test_deploy_endpoint_returns_403_when_disabled_by_default():
    proposal = _create_proposal()
    resp = client.post(
        f"/api/self-modification/{proposal['id']}/deploy",
        json={"confirmed": True, "actor_role": "founder"},
    )
    assert resp.status_code == 403


def test_deploy_endpoint_wrong_state_returns_409_when_flags_enabled(monkeypatch):
    from app.db import SessionLocal
    from app.services import permission_center

    monkeypatch.setattr(gov, "get_settings", lambda: _settings(
        supervised_self_modification_enabled=True, self_modification_deployment_enabled=True,
    ))
    with SessionLocal() as db:
        permission_center.set_permission_level(db, "self_modification_deploy", "allowed")

    proposal = _create_proposal()
    resp = client.post(
        f"/api/self-modification/{proposal['id']}/deploy",
        json={"confirmed": True, "actor_role": "founder"},
    )
    assert resp.status_code == 409  # status is "draft", not "approved"

    with SessionLocal() as db:
        permission_center.set_permission_level(db, "self_modification_deploy", "disabled")


# ---- Kill switch via API ----


def test_kill_switch_activate_and_reset_via_api():
    resp = client.get("/api/self-modification/kill-switch")
    assert resp.status_code == 200

    activate_resp = client.post(
        "/api/self-modification/kill-switch/activate",
        json={"activated_by": "founder", "reason": "API test halt."},
    )
    assert activate_resp.status_code == 200
    assert activate_resp.json()["active"] is True

    health_resp = client.get("/api/self-modification/health")
    assert health_resp.json()["kill_switch_active"] is True

    reset_resp = client.post(
        "/api/self-modification/kill-switch/reset",
        json={"activated_by": "founder", "reason": "resuming"},
    )
    assert reset_resp.status_code == 200
    assert reset_resp.json()["active"] is False


def test_kill_switch_blocks_sandbox_via_api(monkeypatch):
    proposal = _create_proposal()
    _submit_and_check_revision(proposal["id"])
    client.post(f"/api/self-modification/{proposal['id']}/ready-for-sandbox")

    client.post(
        "/api/self-modification/kill-switch/activate",
        json={"activated_by": "founder", "reason": "test"},
    )
    monkeypatch.setattr(gov, "get_settings", lambda: _settings(
        supervised_self_modification_enabled=True, self_modification_sandbox_enabled=True,
    ))
    resp = client.post(
        f"/api/self-modification/{proposal['id']}/sandbox",
        json={"confirmed": True, "actor_role": "founder"},
    )
    assert resp.status_code == 423

    client.post(
        "/api/self-modification/kill-switch/reset",
        json={"activated_by": "founder", "reason": "test done"},
    )


# ---- Full happy path via API (sandbox/deploy mocked) ----


def test_full_flow_via_api_with_mocked_sandbox_and_deploy(monkeypatch):
    from app.db import SessionLocal
    from app.services import permission_center

    def _fake_run(patch_text, patch_hash, base_commit, **kwargs):
        return sandbox.SandboxResult(
            passed=True, workspace_path="C:/fake", base_commit=base_commit or "deadbeef",
            checks=[{"command": "pytest -q", "status": "passed", "exit_code": 0,
                     "stdout_summary": "", "stderr_summary": "", "timestamp": "2026-01-01T00:00:00+00:00"}],
            summary="1/1 runnable checks passed",
        )

    def _fake_deploy(proposal_id, revision_number, patch_text, patch_hash, base_commit, **kwargs):
        return sandbox.DeployResult(
            branch_name=f"echo/self-modification/{proposal_id}/{revision_number}", worktree_path="C:/fake-deploy",
        )

    monkeypatch.setattr(gov.sandbox, "run_patch_in_sandbox", _fake_run)
    monkeypatch.setattr(gov.sandbox, "deploy_to_local_branch", _fake_deploy)
    with SessionLocal() as db:
        permission_center.set_permission_level(db, "self_modification_deploy", "allowed")

    proposal = _create_proposal(title="Full API flow proposal")
    revision = _submit_and_check_revision(proposal["id"], path="backend/tests/test_api_full_flow.py")
    client.post(f"/api/self-modification/{proposal['id']}/ready-for-sandbox")

    monkeypatch.setattr(gov, "get_settings", lambda: _settings(
        supervised_self_modification_enabled=True, self_modification_sandbox_enabled=True,
    ))
    sandbox_resp = client.post(
        f"/api/self-modification/{proposal['id']}/sandbox",
        json={"confirmed": True, "actor_role": "founder"},
    )
    assert sandbox_resp.status_code == 200
    assert sandbox_resp.json()["status"] == "passed"

    review_resp = client.post(f"/api/self-modification/{proposal['id']}/request-review")
    assert review_resp.status_code == 200
    assert review_resp.json()["status"] == "awaiting_human_review"

    approve_resp = client.post(
        f"/api/self-modification/{proposal['id']}/approve",
        json={
            "approver_role": "founder",
            "decision": "approved",
            "test_evidence_summary": "Looks good.",
            "acknowledgement_text": f"APPROVE EXACT PATCH {revision['patch_hash']}",
        },
    )
    assert approve_resp.status_code == 200

    monkeypatch.setattr(gov, "get_settings", lambda: _settings(
        supervised_self_modification_enabled=True, self_modification_sandbox_enabled=True,
        self_modification_deployment_enabled=True,
    ))
    monkeypatch.setattr(gov.sandbox, "current_head", lambda: "deadbeef")
    deploy_resp = client.post(
        f"/api/self-modification/{proposal['id']}/deploy",
        json={"confirmed": True, "actor_role": "founder"},
    )
    assert deploy_resp.status_code == 200
    assert deploy_resp.json()["status"] == "deployed"

    audit_resp = client.get(f"/api/self-modification/{proposal['id']}/audit")
    assert audit_resp.status_code == 200
    event_types = {e["event_type"] for e in audit_resp.json()}
    assert "proposal_created" in event_types
    assert "deployed" in event_types

    rollback_resp = client.post(f"/api/self-modification/{proposal['id']}/rollback", params={"reason": "undo for test"})
    assert rollback_resp.status_code == 200
    assert rollback_resp.json()["status"] == "completed"

    with SessionLocal() as db:
        permission_center.set_permission_level(db, "self_modification_deploy", "disabled")
