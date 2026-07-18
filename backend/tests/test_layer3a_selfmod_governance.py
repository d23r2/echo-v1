"""ECHO Layer 3A Part 2D — Supervised Self-Modification governance service.

Pure service-layer tests against the isolated db_session fixture. Any test
that reaches run_sandbox()/deploy()/rollback() monkeypatches
self_modification_governance.sandbox's functions rather than letting them
touch real git — sandbox subprocess/git-worktree mechanics are covered
separately (and only against a throwaway tmp_path fixture repo) in
test_layer3a_selfmod_sandbox.py. This file must never let a test reach the
real REPO_ROOT-default sandbox path.
"""

from app.config import Settings
from app.services import permission_center
from app.services import self_modification_governance as gov
from app.services import self_modification_sandbox as sandbox


def _rationale(change: str = "Add a safe, scoped implementation improvement.") -> str:
    return (
        "Problem: The reviewed behavior needs a bounded change.\n"
        "Evidence: Repository inspection and the named test demonstrate the need.\n"
        "Assumptions: Existing public contracts remain stable.\n"
        f"Proposed change: {change}\n"
        "Risk: The change may regress the affected feature.\n"
        "Rollback: Discard the isolated branch and restore the recorded base commit.\n"
        "Test plan: Run the targeted and full allowlisted verification checks."
    )


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


def _patch_touching(*paths, extra_lines=1):
    """Builds a minimal, parseable `diff --git` patch touching the given
    paths — enough for _parse_changed_paths(), never actually applied here."""
    chunks = []
    for path in paths:
        body = "\n".join(f"+line {i}" for i in range(extra_lines))
        chunks.append(
            f"diff --git a/{path} b/{path}\n"
            f"index 0000000..1111111 100644\n"
            f"--- a/{path}\n"
            f"+++ b/{path}\n"
            f"@@ -1,1 +1,{extra_lines + 1} @@\n"
            f" existing line\n"
            f"{body}\n"
        )
    return "\n".join(chunks)


def _create_ready_proposal(db, *, path="backend/tests/test_dummy_selfmod.py"):
    """Helper: create a proposal, submit a low-risk revision, run both
    checks, and mark it ready_for_sandbox — the common precondition for
    sandbox/approval/deploy tests below."""
    proposal = gov.create_proposal(
        db, title="Low-risk doc fix", description="Add a comment.", rationale=_rationale("Improve clarity without changing behavior.")
    )
    revision = gov.submit_revision(db, proposal.id, patch_text=_patch_touching(path))
    gov.run_scope_check(db, revision.id)
    gov.run_compliance_check(db, revision.id)
    gov.mark_ready_for_sandbox(db, proposal.id)
    db.refresh(proposal)
    return proposal, revision


def _fake_sandbox_pass(monkeypatch, *, passed=True):
    def _fake_run(patch_text, patch_hash, base_commit, **kwargs):
        return sandbox.SandboxResult(
            passed=passed,
            workspace_path="C:/fake/workspace",
            base_commit=base_commit or "deadbeefcafe",
            checks=[
                {"command": "pytest -q", "status": "passed" if passed else "failed", "exit_code": 0 if passed else 1,
                 "stdout_summary": "", "stderr_summary": "", "timestamp": "2026-01-01T00:00:00+00:00"}
            ],
            summary="1/1 runnable checks passed" if passed else "0/1 runnable checks passed",
        )

    monkeypatch.setattr(gov.sandbox, "run_patch_in_sandbox", _fake_run)


def _fake_deploy_success(monkeypatch):
    def _fake_deploy(proposal_id, revision_number, patch_text, patch_hash, base_commit, **kwargs):
        return sandbox.DeployResult(
            branch_name=f"echo/self-modification/{proposal_id}/{revision_number}",
            worktree_path="C:/fake/deploy-workspace",
        )

    monkeypatch.setattr(gov.sandbox, "deploy_to_local_branch", _fake_deploy)


def _run_sandbox_enabled(db, monkeypatch, *, passed=True):
    monkeypatch.setattr(gov, "get_settings", lambda: _settings(
        supervised_self_modification_enabled=True, self_modification_sandbox_enabled=True,
    ))
    _fake_sandbox_pass(monkeypatch, passed=passed)


# ---- Scope classification ----


def test_scope_check_passes_for_low_risk_test_file():
    result = gov.classify_scope(["backend/tests/test_thing.py"], _patch_touching("backend/tests/test_thing.py"))
    assert result.risk_level == "low"
    assert not result.hard_blocked


def test_scope_check_blocks_protected_path():
    result = gov.classify_scope(["backend/app/constitution.py"], _patch_touching("backend/app/constitution.py"))
    assert result.hard_blocked
    assert result.risk_level == "critical"
    assert "protected path" in result.notes


def test_scope_check_blocks_env_file():
    result = gov.classify_scope([".env"], _patch_touching(".env"))
    assert result.hard_blocked
    assert result.risk_level == "critical"


def test_scope_check_blocks_path_traversal():
    result = gov.classify_scope(["../../etc/passwd"], "diff --git a/x b/x\n")
    assert result.hard_blocked


def test_scope_check_blocks_absolute_path():
    result = gov.classify_scope(["/etc/passwd"], "diff --git a/x b/x\n")
    assert result.hard_blocked


def test_scope_check_blocks_windows_drive_path():
    result = gov.classify_scope(["C:/Windows/System32/evil.dll"], "diff --git a/x b/x\n")
    assert result.hard_blocked


def test_scope_check_blocks_symlink_creation():
    patch = "diff --git a/backend/tests/link b/backend/tests/link\nnew file mode 120000\n"
    result = gov.classify_scope(["backend/tests/link"], patch)
    assert result.hard_blocked


def test_scope_check_blocks_empty_changed_paths():
    result = gov.classify_scope([], "not a real diff")
    assert result.hard_blocked
    assert result.risk_level == "critical"


def test_scope_check_is_default_deny_for_unlisted_path():
    path = "misc/unknown_runtime.py"
    result = gov.classify_scope([path], _patch_touching(path))
    assert result.hard_blocked
    assert "outside the explicit allowlist" in result.notes


def test_scope_check_normalizes_case_before_protected_path_check():
    path = "BACKEND/APP/CONSTITUTION.PY"
    result = gov.classify_scope([path], _patch_touching(path))
    assert result.hard_blocked
    assert result.touches_protected_paths


def test_scope_check_blocks_protected_symbol_in_allowlisted_application_file():
    path = "backend/app/services/ordinary_feature.py"
    patch = _patch_touching(path) + "\n+VALUE_INVARIANTS = ()\n"
    result = gov.classify_scope([path], patch)
    assert result.hard_blocked
    assert result.touches_protected_symbols


def test_dependency_manifest_is_allowed_for_review_but_high_risk():
    path = "frontend/package.json"
    result = gov.classify_scope([path], _patch_touching(path))
    assert not result.hard_blocked
    assert result.risk_level == "high"


def test_possible_test_weakening_is_high_risk_and_visible():
    path = "backend/tests/test_guard.py"
    patch = _patch_touching(path) + "\n-    assert guarded\n+    pytest.skip('later')\n"
    result = gov.classify_scope([path], patch)
    assert not result.hard_blocked
    assert result.risk_level == "high"
    assert "test weakening" in result.notes


def test_scope_check_moderate_for_core_service_file():
    result = gov.classify_scope(
        ["backend/app/services/knowledge_vault.py"], _patch_touching("backend/app/services/knowledge_vault.py")
    )
    assert result.risk_level == "moderate"
    assert not result.hard_blocked


def test_scope_check_high_for_many_core_files():
    paths = [f"backend/app/services/mod_{i}.py" for i in range(8)]
    result = gov.classify_scope(paths, _patch_touching(*paths))
    assert result.risk_level == "high"


def test_parse_changed_paths_from_diff_git_header():
    patch = _patch_touching("backend/app/services/x.py", "backend/tests/test_x.py")
    paths = gov._parse_changed_paths(patch)
    assert paths == ["backend/app/services/x.py", "backend/tests/test_x.py"]


def test_compute_patch_hash_is_deterministic_sha256():
    text = "diff --git a/x b/x\n"
    assert gov.compute_patch_hash(text) == gov.compute_patch_hash(text)
    assert gov.compute_patch_hash(text) != gov.compute_patch_hash(text + "extra")


def test_structured_rationale_is_mandatory(db_session):
    permission_center.ensure_defaults(db_session)
    try:
        gov.create_proposal(db_session, title="t", description="d", rationale="Because.")
        raised = False
    except gov.SelfModScopeError:
        raised = True
    assert raised


def test_likely_secret_is_rejected_before_revision_is_stored(db_session):
    permission_center.ensure_defaults(db_session)
    proposal = gov.create_proposal(db_session, title="t", description="d", rationale=_rationale())
    patch = _patch_touching("backend/tests/test_secret.py") + '\n+api_key = "abcdefghijklmnopqrstuvwx"\n'
    try:
        gov.submit_revision(db_session, proposal.id, patch_text=patch)
        raised = False
    except gov.SelfModScopeError:
        raised = True
    assert raised
    from app.models import CodeModificationRevision

    assert db_session.query(CodeModificationRevision).filter_by(proposal_id=proposal.id).count() == 0


def test_checks_cannot_run_against_stale_revision(db_session):
    permission_center.ensure_defaults(db_session)
    proposal = gov.create_proposal(db_session, title="t", description="d", rationale=_rationale())
    stale = gov.submit_revision(db_session, proposal.id, patch_text=_patch_touching("backend/tests/test_old.py"))
    gov.submit_revision(db_session, proposal.id, patch_text=_patch_touching("backend/tests/test_new.py"))
    try:
        gov.run_scope_check(db_session, stale.id)
        raised = False
    except gov.SelfModStateError:
        raised = True
    assert raised


# ---- Constitutional compliance check ----


def test_compliance_check_allows_clean_rationale(db_session):
    permission_center.ensure_defaults(db_session)
    proposal = gov.create_proposal(db_session, title="t", description="d", rationale=_rationale("Add a helper docstring."))
    revision = gov.submit_revision(db_session, proposal.id, patch_text=_patch_touching("backend/tests/test_a.py"))
    gov.run_scope_check(db_session, revision.id)
    gov.run_compliance_check(db_session, revision.id)
    db_session.refresh(revision)
    assert revision.compliance_check_status == "passed"


def test_compliance_check_blocks_invariant_override_language(db_session):
    permission_center.ensure_defaults(db_session)
    proposal = gov.create_proposal(
        db_session, title="t", description="d",
        rationale=_rationale("Bypass the no-power-seeking invariant so ECHO can acquire more control over its own permissions."),
    )
    revision = gov.submit_revision(db_session, proposal.id, patch_text=_patch_touching("backend/tests/test_a.py"))
    gov.run_scope_check(db_session, revision.id)
    gov.run_compliance_check(db_session, revision.id)
    db_session.refresh(revision)
    db_session.refresh(proposal)
    assert revision.compliance_check_status == "failed"
    assert proposal.status == "compliance_check_failed"


def test_compliance_check_structurally_blocks_council_file_even_with_clean_prose(db_session):
    permission_center.ensure_defaults(db_session)
    proposal = gov.create_proposal(db_session, title="t", description="d", rationale=_rationale("Perform a minor cleanup."))
    revision = gov.submit_revision(db_session, proposal.id, patch_text=_patch_touching("backend/app/council.py"))
    gov.run_scope_check(db_session, revision.id)
    db_session.refresh(revision)
    assert revision.scope_check_status == "failed"  # already caught by scope check
    # Compliance check still requires scope check to have passed first.
    try:
        gov.run_compliance_check(db_session, revision.id)
        raised = False
    except gov.SelfModStateError:
        raised = True
    assert raised


# ---- Full lifecycle (sandbox/deploy mocked) ----


def test_full_lifecycle_draft_to_deployed_and_rolled_back(db_session, monkeypatch):
    permission_center.ensure_defaults(db_session)
    proposal, revision = _create_ready_proposal(db_session)
    assert proposal.status == "ready_for_sandbox"

    _run_sandbox_enabled(db_session, monkeypatch, passed=True)
    execution = gov.run_sandbox(db_session, proposal.id, confirmed=True)
    assert execution.status == "passed"
    db_session.refresh(proposal)
    assert proposal.status == "sandbox_passed"

    gov.request_review(db_session, proposal.id)
    db_session.refresh(proposal)
    assert proposal.status == "awaiting_human_review"

    approval = gov.approve_revision(
        db_session, proposal.id, approver_role="founder", decision="approved",
        test_evidence_summary="Sandbox passed, reviewed manually.",
        acknowledgement_text=f"APPROVE EXACT PATCH {revision.patch_hash}",
    )
    db_session.refresh(proposal)
    assert proposal.status == "approved"
    assert approval.patch_hash_at_approval == revision.patch_hash

    monkeypatch.setattr(gov, "get_settings", lambda: _settings(
        supervised_self_modification_enabled=True, self_modification_sandbox_enabled=True,
        self_modification_deployment_enabled=True,
    ))
    permission_center.set_permission_level(db_session, "self_modification_deploy", "allowed")
    _fake_deploy_success(monkeypatch)
    monkeypatch.setattr(gov.sandbox, "current_head", lambda: proposal.base_commit)
    attempt = gov.deploy(db_session, proposal.id, confirmed=True)
    assert attempt.status == "deployed"
    db_session.refresh(proposal)
    assert proposal.status == "deployed"

    event = gov.rollback(db_session, proposal.id, reason="Reviewer wants to undo.")
    assert event.status == "completed"
    db_session.refresh(proposal)
    assert proposal.status == "rolled_back"


def test_sandbox_failure_sets_proposal_sandbox_failed(db_session, monkeypatch):
    permission_center.ensure_defaults(db_session)
    proposal, _revision = _create_ready_proposal(db_session)
    _run_sandbox_enabled(db_session, monkeypatch, passed=False)
    execution = gov.run_sandbox(db_session, proposal.id, confirmed=True)
    assert execution.status == "failed"
    db_session.refresh(proposal)
    assert proposal.status == "sandbox_failed"


def test_request_review_requires_sandbox_passed(db_session):
    permission_center.ensure_defaults(db_session)
    proposal, _revision = _create_ready_proposal(db_session)
    raised = False
    try:
        gov.request_review(db_session, proposal.id)
    except gov.SelfModStateError:
        raised = True
    assert raised


# ---- CRITICAL risk is blocked from the workflow entirely ----


def test_critical_risk_proposal_never_reaches_ready_for_sandbox(db_session):
    permission_center.ensure_defaults(db_session)
    proposal = gov.create_proposal(db_session, title="t", description="d", rationale=_rationale())
    revision = gov.submit_revision(db_session, proposal.id, patch_text=_patch_touching("backend/app/constitution.py"))
    gov.run_scope_check(db_session, revision.id)
    db_session.refresh(proposal)
    assert proposal.risk_level == "critical"

    raised = False
    try:
        gov.mark_ready_for_sandbox(db_session, proposal.id)
    except (gov.SelfModScopeError, gov.SelfModStateError):
        raised = True
    assert raised
    db_session.refresh(proposal)
    assert proposal.status != "ready_for_sandbox"


# ---- Feature flags fail closed by default ----


def test_sandbox_disabled_by_default(db_session):
    permission_center.ensure_defaults(db_session)
    proposal, _revision = _create_ready_proposal(db_session)
    raised = False
    try:
        gov.run_sandbox(db_session, proposal.id, confirmed=True)
    except gov.SelfModFeatureDisabledError:
        raised = True
    assert raised


def test_deploy_disabled_by_default_even_with_valid_approval(db_session, monkeypatch):
    permission_center.ensure_defaults(db_session)
    proposal, revision = _create_ready_proposal(db_session)
    _run_sandbox_enabled(db_session, monkeypatch, passed=True)
    gov.run_sandbox(db_session, proposal.id, confirmed=True)
    gov.request_review(db_session, proposal.id)
    gov.approve_revision(
        db_session, proposal.id, approver_role="founder", decision="approved",
        acknowledgement_text=f"APPROVE EXACT PATCH {revision.patch_hash}",
    )

    # supervised_self_modification_enabled True, but deployment flag left False.
    monkeypatch.setattr(gov, "get_settings", lambda: _settings(
        supervised_self_modification_enabled=True, self_modification_sandbox_enabled=True,
    ))
    raised = False
    try:
        gov.deploy(db_session, proposal.id, confirmed=True)
    except gov.SelfModFeatureDisabledError:
        raised = True
    assert raised


# ---- Permission Center integration ----


def test_propose_blocked_when_permission_disabled(db_session):
    permission_center.ensure_defaults(db_session)
    permission_center.set_permission_level(db_session, "self_modification_propose", "disabled")
    raised = False
    try:
        gov.create_proposal(db_session, title="t", description="d", rationale=_rationale())
    except gov.SelfModPermissionError:
        raised = True
    assert raised


def test_sandbox_run_blocked_when_permission_disabled(db_session, monkeypatch):
    permission_center.ensure_defaults(db_session)
    proposal, _revision = _create_ready_proposal(db_session)
    permission_center.set_permission_level(db_session, "self_modification_sandbox_run", "disabled")
    monkeypatch.setattr(gov, "get_settings", lambda: _settings(
        supervised_self_modification_enabled=True, self_modification_sandbox_enabled=True,
    ))
    raised = False
    try:
        gov.run_sandbox(db_session, proposal.id, confirmed=True)
    except gov.SelfModPermissionError:
        raised = True
    assert raised


# ---- Approval binding ----


def test_new_revision_invalidates_stale_approval_at_deploy_gate(db_session, monkeypatch):
    permission_center.ensure_defaults(db_session)
    proposal, revision = _create_ready_proposal(db_session)
    _run_sandbox_enabled(db_session, monkeypatch, passed=True)
    gov.run_sandbox(db_session, proposal.id, confirmed=True)
    gov.request_review(db_session, proposal.id)
    gov.approve_revision(
        db_session, proposal.id, approver_role="founder", decision="approved",
        acknowledgement_text=f"APPROVE EXACT PATCH {revision.patch_hash}",
    )

    # A brand new revision is submitted after approval (e.g. the reviewer asked
    # for a change) — this must invalidate the old approval's patch-hash binding.
    gov.submit_revision(db_session, proposal.id, patch_text=_patch_touching("backend/tests/test_dummy_selfmod.py", extra_lines=3))
    db_session.refresh(proposal)
    # Manually force back to "approved" to isolate the deploy-gate's own hash check
    # (in real usage submit_revision resets status to draft, which already blocks deploy).
    proposal.status = "approved"
    db_session.commit()

    monkeypatch.setattr(gov, "get_settings", lambda: _settings(
        supervised_self_modification_enabled=True, self_modification_sandbox_enabled=True,
        self_modification_deployment_enabled=True,
    ))
    permission_center.set_permission_level(db_session, "self_modification_deploy", "allowed")
    raised = False
    try:
        gov.deploy(db_session, proposal.id, confirmed=True)
    except gov.SelfModApprovalError:
        raised = True
    assert raised


def test_expired_approval_blocks_deploy(db_session, monkeypatch):
    permission_center.ensure_defaults(db_session)
    proposal, revision = _create_ready_proposal(db_session)
    _run_sandbox_enabled(db_session, monkeypatch, passed=True)
    gov.run_sandbox(db_session, proposal.id, confirmed=True)
    gov.request_review(db_session, proposal.id)
    monkeypatch.setattr(gov, "get_settings", lambda: _settings(
        supervised_self_modification_enabled=True, self_modification_sandbox_enabled=True,
        self_modification_approval_expiry_hours=-1,  # already expired the instant it's created
    ))
    gov.approve_revision(
        db_session, proposal.id, approver_role="founder", decision="approved",
        acknowledgement_text=f"APPROVE EXACT PATCH {revision.patch_hash}",
    )

    monkeypatch.setattr(gov, "get_settings", lambda: _settings(
        supervised_self_modification_enabled=True, self_modification_sandbox_enabled=True,
        self_modification_deployment_enabled=True,
    ))
    permission_center.set_permission_level(db_session, "self_modification_deploy", "allowed")
    raised = False
    try:
        gov.deploy(db_session, proposal.id, confirmed=True)
    except gov.SelfModApprovalError:
        raised = True
    assert raised
    db_session.refresh(proposal)
    assert proposal.status == "approval_expired"


def test_high_risk_approval_requires_exact_typed_confirmation(db_session, monkeypatch):
    permission_center.ensure_defaults(db_session)
    paths = [f"backend/app/services/mod_{i}.py" for i in range(8)]
    proposal = gov.create_proposal(db_session, title="t", description="d", rationale=_rationale("Perform a bounded refactor."))
    revision = gov.submit_revision(db_session, proposal.id, patch_text=_patch_touching(*paths))
    gov.run_scope_check(db_session, revision.id)
    db_session.refresh(proposal)
    assert proposal.risk_level == "high"
    gov.run_compliance_check(db_session, revision.id)
    gov.mark_ready_for_sandbox(db_session, proposal.id)
    _run_sandbox_enabled(db_session, monkeypatch, passed=True)
    gov.run_sandbox(db_session, proposal.id, confirmed=True)
    gov.request_review(db_session, proposal.id)

    raised = False
    try:
        gov.approve_revision(db_session, proposal.id, approver_role="founder", decision="approved")
    except gov.SelfModApprovalError:
        raised = True
    assert raised

    approval = gov.approve_revision(
        db_session, proposal.id, approver_role="founder", decision="approved",
        acknowledgement_text=f"APPROVE EXACT PATCH {revision.patch_hash}",
    )
    assert approval.decision == "approved"


def test_low_risk_approval_also_requires_exact_patch_phrase(db_session, monkeypatch):
    permission_center.ensure_defaults(db_session)
    proposal, _revision = _create_ready_proposal(db_session)
    _run_sandbox_enabled(db_session, monkeypatch, passed=True)
    gov.run_sandbox(db_session, proposal.id, confirmed=True)
    gov.request_review(db_session, proposal.id)
    try:
        gov.approve_revision(db_session, proposal.id, approver_role="founder", decision="approved")
        raised = False
    except gov.SelfModApprovalError:
        raised = True
    assert raised


def test_proposal_author_cannot_approve_own_revision(db_session, monkeypatch):
    permission_center.ensure_defaults(db_session)
    proposal = gov.create_proposal(
        db_session, title="t", description="d", rationale=_rationale(), proposed_by="founder"
    )
    revision = gov.submit_revision(db_session, proposal.id, patch_text=_patch_touching("backend/tests/test_self.py"))
    gov.run_scope_check(db_session, revision.id)
    gov.run_compliance_check(db_session, revision.id)
    gov.mark_ready_for_sandbox(db_session, proposal.id)
    _run_sandbox_enabled(db_session, monkeypatch, passed=True)
    gov.run_sandbox(db_session, proposal.id, confirmed=True)
    gov.request_review(db_session, proposal.id)
    try:
        gov.approve_revision(
            db_session,
            proposal.id,
            approver_role="founder",
            decision="approved",
            acknowledgement_text=f"APPROVE EXACT PATCH {revision.patch_hash}",
        )
        raised = False
    except gov.SelfModApprovalError:
        raised = True
    assert raised


def test_high_risk_deployment_stays_blocked_without_authenticated_dual_approval(db_session, monkeypatch):
    permission_center.ensure_defaults(db_session)
    paths = [f"backend/app/services/high_{index}.py" for index in range(8)]
    proposal = gov.create_proposal(db_session, title="t", description="d", rationale=_rationale())
    revision = gov.submit_revision(db_session, proposal.id, patch_text=_patch_touching(*paths))
    gov.run_scope_check(db_session, revision.id)
    gov.run_compliance_check(db_session, revision.id)
    gov.mark_ready_for_sandbox(db_session, proposal.id)
    _run_sandbox_enabled(db_session, monkeypatch, passed=True)
    gov.run_sandbox(db_session, proposal.id, confirmed=True)
    gov.request_review(db_session, proposal.id)
    gov.approve_revision(
        db_session,
        proposal.id,
        approver_role="founder",
        decision="approved",
        acknowledgement_text=f"APPROVE EXACT PATCH {revision.patch_hash}",
    )
    monkeypatch.setattr(gov, "get_settings", lambda: _settings(
        supervised_self_modification_enabled=True,
        self_modification_sandbox_enabled=True,
        self_modification_deployment_enabled=True,
    ))
    permission_center.set_permission_level(db_session, "self_modification_deploy", "allowed")
    try:
        gov.deploy(db_session, proposal.id, confirmed=True)
        raised = False
    except gov.SelfModApprovalError:
        raised = True
    assert raised


# ---- Kill switch ----


def test_kill_switch_blocks_sandbox_but_not_reads(db_session, monkeypatch):
    permission_center.ensure_defaults(db_session)
    proposal, _revision = _create_ready_proposal(db_session)
    gov.activate_kill_switch(db_session, activated_by="founder", reason="Investigating an anomaly.")

    monkeypatch.setattr(gov, "get_settings", lambda: _settings(
        supervised_self_modification_enabled=True, self_modification_sandbox_enabled=True,
    ))
    raised = False
    try:
        gov.run_sandbox(db_session, proposal.id, confirmed=True)
    except gov.SelfModKillSwitchError:
        raised = True
    assert raised

    # Reads (health, get_health, is_kill_switch_active) still work.
    health = gov.get_health(db_session)
    assert health["kill_switch_active"] is True

    gov.reset_kill_switch(db_session, reset_by="founder", reason="Test completed safely.")
    assert gov.is_kill_switch_active(db_session) is False


def test_kill_switch_blocks_approve_and_deploy(db_session, monkeypatch):
    permission_center.ensure_defaults(db_session)
    proposal, _revision = _create_ready_proposal(db_session)
    _run_sandbox_enabled(db_session, monkeypatch, passed=True)
    gov.run_sandbox(db_session, proposal.id, confirmed=True)
    gov.request_review(db_session, proposal.id)

    gov.activate_kill_switch(db_session, activated_by="founder", reason="halt")
    raised = False
    try:
        gov.approve_revision(db_session, proposal.id, approver_role="founder", decision="approved")
    except gov.SelfModKillSwitchError:
        raised = True
    assert raised


# ---- Audit trail ----


def test_audit_events_recorded_and_never_contain_full_patch_text(db_session):
    permission_center.ensure_defaults(db_session)
    secret_marker = "SECRET_PATCH_BODY_MARKER"
    proposal = gov.create_proposal(db_session, title="t", description="d", rationale=_rationale())
    revision = gov.submit_revision(
        db_session, proposal.id,
        patch_text=_patch_touching("backend/tests/test_a.py") + f"\n# {secret_marker}\n",
    )
    gov.run_scope_check(db_session, revision.id)

    from app.models import SelfModificationAuditEvent

    events = (
        db_session.query(SelfModificationAuditEvent)
        .filter(SelfModificationAuditEvent.proposal_id == proposal.id)
        .all()
    )
    assert len(events) >= 2
    event_types = {e.event_type for e in events}
    assert "proposal_created" in event_types
    assert "revision_submitted" in event_types
    for event in events:
        assert secret_marker not in event.summary
        assert secret_marker not in str(event.safe_context_json)


def test_cancel_proposal_records_reason(db_session):
    permission_center.ensure_defaults(db_session)
    proposal = gov.create_proposal(db_session, title="t", description="d", rationale=_rationale())
    cancelled = gov.cancel_proposal(db_session, proposal.id, reason="No longer needed.")
    assert cancelled.status == "cancelled"
    assert cancelled.closed_reason == "No longer needed."


def test_ensure_defaults_is_idempotent(db_session):
    gov.ensure_defaults(db_session)
    gov.ensure_defaults(db_session)
    from app.models import SelfModificationKillSwitch

    rows = db_session.query(SelfModificationKillSwitch).all()
    assert len(rows) == 1


def test_audit_store_unavailable_blocks_before_mutation(db_session, monkeypatch):
    def broken_query(*_args, **_kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(db_session, "query", broken_query)
    try:
        gov.create_proposal(db_session, title="t", description="d", rationale=_rationale())
        raised = False
    except gov.SelfModAuditError:
        raised = True
    assert raised
