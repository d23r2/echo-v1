"""ECHO Supervised Maintenance Workspace v1 — Phase 4-5 (validation and
sandbox reuse confirmation).

Per docs/supervised_maintenance/architecture.md §2, the deterministic
scope validator, constitutional compliance service, sandbox controller,
approval gateway, local-commit controller, and rollback service are all
*reused unmodified* from Layer 3A Part 2D — no new validator or sandbox
code was written for this milestone. This file is the evidence: it drives
an analysis-originated proposal through the complete, real, unmodified
pipeline (scope check -> compliance check -> mark ready -> sandbox
(mocked subprocess only) -> request review -> approve -> deploy (mocked)
-> rollback) and confirms every stage behaves exactly as it already does
for a proposal created directly (not via an analysis).
"""

from app.config import Settings
from app.services import maintenance_analysis, maintenance_policy, maintenance_proposal, permission_center
from app.services import self_modification_governance as governance
from app.services import self_modification_sandbox as sandbox


def _settings(**overrides):
    base = dict(
        supervised_maintenance_enabled=True,
        supervised_analysis_enabled=True,
        supervised_proposals_enabled=True,
        supervised_sandbox_enabled=False,
        supervised_local_commit_enabled=False,
        supervised_maintenance_frontend_enabled=False,
        supervised_maintenance_max_read_bytes=512_000,
        supervised_self_modification_enabled=False,
        self_modification_sandbox_enabled=False,
        self_modification_deployment_enabled=False,
        self_modification_frontend_enabled=False,
        self_modification_approval_expiry_hours=24,
        self_modification_sandbox_image="echo-selfmod-sandbox:local",
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


_RATIONALE = (
    "Problem: dead helper.\nEvidence: no callers found via search.\nAssumptions: search was exhaustive.\n"
    "Proposed change: remove the helper.\nRisk: low.\nRollback: revert commit.\nTest plan: run backend suite."
)


def _fake_sandbox_pass(monkeypatch):
    def _fake_run(patch_text, patch_hash, base_commit, **kwargs):
        return sandbox.SandboxResult(
            passed=True, workspace_path="C:/fake", base_commit=base_commit or "deadbeef",
            checks=[{"command": "pytest -q", "status": "passed", "exit_code": 0,
                     "stdout_summary": "", "stderr_summary": "", "timestamp": "2026-01-01T00:00:00+00:00"}],
            summary="1/1 runnable checks passed", baseline_passed=True, network_disabled=True, runner="docker",
        )

    monkeypatch.setattr(governance.sandbox, "run_patch_in_sandbox", _fake_run)


def _fake_deploy_success(monkeypatch):
    def _fake_deploy(proposal_id, revision_number, patch_text, patch_hash, base_commit, **kwargs):
        return sandbox.DeployResult(
            branch_name=f"echo/self-modification/{proposal_id}/{revision_number}", worktree_path="C:/fake-deploy",
        )

    monkeypatch.setattr(governance.sandbox, "deploy_to_local_branch", _fake_deploy)
    monkeypatch.setattr(governance.sandbox, "current_head", lambda *args, **kwargs: "deadbeef")


def test_analysis_originated_proposal_completes_the_full_unmodified_pipeline(db_session, monkeypatch):
    monkeypatch.setattr(maintenance_analysis, "get_settings", lambda: _settings())
    monkeypatch.setattr(maintenance_policy, "get_settings", lambda: _settings(supervised_maintenance_enabled=True))
    permission_center.ensure_defaults(db_session)
    repo = maintenance_policy.register_repository(db_session, display_name="ECHO", requested_by="founder")
    repo = maintenance_policy.set_capability_mode(db_session, repo.id, "human_approved_local_commit", requested_by="founder")
    analysis = maintenance_analysis.create_analysis(db_session, repository_id=repo.id, objective="Find dead code.")
    maintenance_analysis.add_finding(
        db_session, analysis.id, epistemic_status="verified",
        description="Helper `_unused_thing` has no callers.",
        affected_files=["backend/tests/test_pipeline_reuse_dummy.py"],
        evidence_reference="backend/tests/test_pipeline_reuse_dummy.py:1",
    )
    maintenance_analysis.complete_analysis(db_session, analysis.id)

    monkeypatch.setattr(maintenance_proposal, "get_settings", lambda: _settings())
    proposal = maintenance_proposal.create_proposal_from_analysis(
        db_session, analysis_id=analysis.id, title="Remove dead helper", description="d", rationale=_RATIONALE,
        patch_text=_patch_touching("backend/tests/test_pipeline_reuse_dummy.py"),
    )
    assert proposal.analysis_id == analysis.id

    # Stage 1: deterministic scope validation — the exact unmodified
    # classify_scope() the Part 2D pipeline already uses.
    revision = governance._require_active_revision(db_session, proposal)
    governance.run_scope_check(db_session, revision.id)
    db_session.refresh(revision)
    assert revision.scope_check_status == "passed"

    # Stage 2: deterministic constitutional compliance — the exact
    # unmodified run_compliance_check() reusing constitution.classify_amendment_text().
    governance.run_compliance_check(db_session, revision.id)
    db_session.refresh(revision)
    assert revision.compliance_check_status == "passed"

    governance.mark_ready_for_sandbox(db_session, proposal.id)
    db_session.refresh(proposal)
    assert proposal.status == "ready_for_sandbox"

    # Stage 3: sandbox verification — governance.run_sandbox() unmodified;
    # only the subprocess-executing sandbox.run_patch_in_sandbox() itself is
    # mocked here (real Docker execution is covered by
    # test_layer3a_selfmod_sandbox.py's dedicated fixture-repo tests).
    monkeypatch.setattr(governance, "get_settings", lambda: _settings(
        supervised_self_modification_enabled=True, self_modification_sandbox_enabled=True,
    ))
    _fake_sandbox_pass(monkeypatch)
    execution = governance.run_sandbox(db_session, proposal.id, confirmed=True)
    assert execution.status == "passed"

    # Stage 4: human review request — unmodified.
    governance.request_review(db_session, proposal.id)
    db_session.refresh(proposal)
    assert proposal.status == "awaiting_human_review"

    # Stage 5: approval — unmodified approve_revision(), including the
    # self-approval check (proposed_by="echo" here, approver "founder" —
    # a real human role, not the same as the proposer).
    approval = governance.approve_revision(
        db_session, proposal.id, approver_role="founder", decision="approved",
        test_evidence_summary="Sandbox passed; reviewed the finding and diff.",
        acknowledgement_text=f"APPROVE EXACT PATCH {revision.patch_hash}",
    )
    assert approval.decision == "approved"

    # Stage 6: deployment — unmodified deploy(), local-branch-only; only the
    # subprocess-executing sandbox.deploy_to_local_branch() is mocked.
    monkeypatch.setattr(governance, "get_settings", lambda: _settings(
        supervised_self_modification_enabled=True, self_modification_sandbox_enabled=True,
        self_modification_deployment_enabled=True,
    ))
    permission_center.set_permission_level(db_session, "self_modification_deploy", "allowed")
    _fake_deploy_success(monkeypatch)
    attempt = governance.deploy(db_session, proposal.id, confirmed=True)
    assert attempt.status == "deployed"

    # Stage 7: rollback — unmodified rollback().
    event = governance.rollback(db_session, proposal.id, reason="Confirming rollback for the reuse test.")
    assert event.status == "completed"
    db_session.refresh(proposal)
    assert proposal.status == "rolled_back"

    # The audit trail spans both subsystems' dedicated tables — no shared
    # table, matching the one-table-per-subsystem convention.
    from app.models import MaintenanceAuditEvent, SelfModificationAuditEvent

    maintenance_events = {
        e.event_type
        for e in db_session.query(MaintenanceAuditEvent).filter(MaintenanceAuditEvent.repository_id == repo.id).all()
    }
    assert "proposal_generated_from_analysis" in maintenance_events

    selfmod_events = {
        e.event_type
        for e in db_session.query(SelfModificationAuditEvent).filter(SelfModificationAuditEvent.proposal_id == proposal.id).all()
    }
    assert {"scope_check_completed", "compliance_check_completed", "sandbox_completed", "approval_approved", "deployed", "rolled_back"}.issubset(selfmod_events)


def test_critical_risk_analysis_originated_proposal_still_blocked_before_sandbox(db_session, monkeypatch):
    """CRITICAL-risk proposals never reach ready_for_sandbox regardless of
    origin — confirms the analysis path adds no bypass."""
    monkeypatch.setattr(maintenance_analysis, "get_settings", lambda: _settings())
    monkeypatch.setattr(maintenance_policy, "get_settings", lambda: _settings(supervised_maintenance_enabled=True))
    permission_center.ensure_defaults(db_session)
    repo = maintenance_policy.register_repository(db_session, display_name="ECHO", requested_by="founder")
    repo = maintenance_policy.set_capability_mode(db_session, repo.id, "human_approved_local_commit", requested_by="founder")
    analysis = maintenance_analysis.create_analysis(db_session, repository_id=repo.id, objective="x")

    monkeypatch.setattr(maintenance_proposal, "get_settings", lambda: _settings())
    proposal = maintenance_proposal.create_proposal_from_analysis(
        db_session, analysis_id=analysis.id, title="t", description="d", rationale=_RATIONALE,
        patch_text=_patch_touching("backend/app/services/permission_center.py"),
    )
    revision = governance._require_active_revision(db_session, proposal)
    governance.run_scope_check(db_session, revision.id)
    db_session.refresh(proposal)
    assert proposal.risk_level == "critical"

    raised = False
    try:
        governance.mark_ready_for_sandbox(db_session, proposal.id)
    except (governance.SelfModScopeError, governance.SelfModStateError):
        raised = True
    assert raised
