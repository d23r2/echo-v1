"""ECHO Supervised Maintenance Workspace v1 — Phase 7 (local commit reuse
confirmation).

Per docs/supervised_maintenance/architecture.md's component-reuse table
(K, L), the local-branch deployment and rollback machinery is *reused
unmodified* from Layer 3A Part 2D: `self_modification_governance.deploy()`
+ `self_modification_sandbox.deploy_to_local_branch()` as the
LocalCommitController, and `rollback()` + `RollbackEvent` as the
RollbackRecordService. Neither reads `CodeModificationProposal.analysis_id`
anywhere (confirmed by source inspection — no `analysis_id` reference
exists in self_modification_sandbox.py, and deploy()/rollback() in
self_modification_governance.py operate only on proposal_id/revision_id/
approval_id).

This file is the evidence for that claim: it drives one analysis-originated
proposal and one directly-created proposal through identical deploy() and
rollback() calls and asserts they produce structurally identical results —
same status transitions, same branch-naming scheme (derived from
proposal.id/revision_number, never analysis_id), same rollback shape. No
analysis-specific behavior exists in either code path.
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


def _run_pipeline_to_deploy_and_rollback(db_session, monkeypatch, proposal):
    """Drives an already-created proposal through the unmodified Part 2D
    pipeline stages 1-7 and returns (attempt, rollback_event)."""
    revision = governance._require_active_revision(db_session, proposal)
    governance.run_scope_check(db_session, revision.id)
    governance.run_compliance_check(db_session, revision.id)
    governance.mark_ready_for_sandbox(db_session, proposal.id)

    monkeypatch.setattr(governance, "get_settings", lambda: _settings(
        supervised_self_modification_enabled=True, self_modification_sandbox_enabled=True,
    ))
    _fake_sandbox_pass(monkeypatch)
    governance.run_sandbox(db_session, proposal.id, confirmed=True)

    governance.request_review(db_session, proposal.id)
    approval = governance.approve_revision(
        db_session, proposal.id, approver_role="founder", decision="approved",
        test_evidence_summary="Sandbox passed; reviewed the diff.",
        acknowledgement_text=f"APPROVE EXACT PATCH {revision.patch_hash}",
    )
    assert approval.decision == "approved"

    monkeypatch.setattr(governance, "get_settings", lambda: _settings(
        supervised_self_modification_enabled=True, self_modification_sandbox_enabled=True,
        self_modification_deployment_enabled=True,
    ))
    permission_center.set_permission_level(db_session, "self_modification_deploy", "allowed")
    _fake_deploy_success(monkeypatch)
    attempt = governance.deploy(db_session, proposal.id, confirmed=True)

    event = governance.rollback(db_session, proposal.id, reason="Phase 7 reuse confirmation.")
    return attempt, event


def test_local_commit_and_rollback_are_identical_for_analysis_and_direct_proposals(db_session, monkeypatch):
    monkeypatch.setattr(maintenance_analysis, "get_settings", lambda: _settings())
    permission_center.ensure_defaults(db_session)
    repo = maintenance_policy.register_repository(db_session, display_name="ECHO", requested_by="founder")
    repo = maintenance_policy.set_capability_mode(db_session, repo.id, "human_approved_local_commit", requested_by="founder")

    # Proposal A: analysis-originated, via the maintenance wrapper.
    analysis = maintenance_analysis.create_analysis(db_session, repository_id=repo.id, objective="Find dead code.")
    maintenance_analysis.add_finding(
        db_session, analysis.id, epistemic_status="verified",
        description="Helper `_unused_thing_a` has no callers.",
        affected_files=["backend/tests/test_local_commit_reuse_dummy_a.py"],
        evidence_reference="backend/tests/test_local_commit_reuse_dummy_a.py:1",
    )
    maintenance_analysis.complete_analysis(db_session, analysis.id)
    monkeypatch.setattr(maintenance_proposal, "get_settings", lambda: _settings())
    proposal_a = maintenance_proposal.create_proposal_from_analysis(
        db_session, analysis_id=analysis.id, title="Remove dead helper A", description="d", rationale=_RATIONALE,
        patch_text=_patch_touching("backend/tests/test_local_commit_reuse_dummy_a.py"),
    )
    assert proposal_a.analysis_id == analysis.id

    # Proposal B: created directly through governance, with no analysis link
    # at all — the same code path a pre-existing Self-Modification user hits.
    proposal_b = governance.create_proposal(
        db_session, title="Remove dead helper B", description="d", rationale=_RATIONALE,
        proposed_by="echo",
    )
    governance.submit_revision(
        db_session, proposal_b.id,
        patch_text=_patch_touching("backend/tests/test_local_commit_reuse_dummy_b.py"),
    )
    db_session.refresh(proposal_b)
    assert proposal_b.analysis_id is None

    attempt_a, event_a = _run_pipeline_to_deploy_and_rollback(db_session, monkeypatch, proposal_a)
    attempt_b, event_b = _run_pipeline_to_deploy_and_rollback(db_session, monkeypatch, proposal_b)

    # Deployment: identical status/target regardless of analysis origin;
    # branch naming is derived only from proposal.id/revision_number.
    assert attempt_a.status == attempt_b.status == "deployed"
    assert attempt_a.target == attempt_b.target
    assert attempt_a.branch_name == f"echo/self-modification/{proposal_a.id}/1"
    assert attempt_b.branch_name == f"echo/self-modification/{proposal_b.id}/1"
    assert "analysis" not in attempt_a.branch_name
    assert "analysis" not in attempt_b.branch_name

    # Rollback: identical status/shape regardless of analysis origin.
    assert event_a.status == event_b.status == "completed"
    assert event_a.deployment_attempt_id == attempt_a.id
    assert event_b.deployment_attempt_id == attempt_b.id

    db_session.refresh(proposal_a)
    db_session.refresh(proposal_b)
    assert proposal_a.status == proposal_b.status == "rolled_back"

    # DeploymentAttempt/RollbackEvent columns are a fixed set with no
    # analysis-aware field at all (confirms no schema drift was needed).
    assert not hasattr(attempt_a, "analysis_id")
    assert not hasattr(event_a, "analysis_id")
