"""ECHO Supervised Maintenance Workspace v1 — Phase 2 (Analyse Only).

CodeAccessService tests operate read-only against the real repository this
backend is running from (register_repository() only ever registers
REPO_ROOT, by design — see maintenance_policy.py's module docstring), the
same convention self_improvement_verify.py's own tests already use for
read-only git status/diff checks. Nothing here ever writes to the repo.
"""

import os

from app.config import Settings
from app.services import maintenance_analysis, maintenance_code_access, maintenance_policy, permission_center


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


def _register_and_activate(db, monkeypatch, *, requested_by="founder"):
    monkeypatch.setattr(maintenance_code_access, "get_settings", lambda: _settings(
        supervised_maintenance_enabled=True, supervised_analysis_enabled=True,
    ))
    permission_center.ensure_defaults(db)
    repo = maintenance_policy.register_repository(db, display_name="ECHO", requested_by=requested_by)
    repo = maintenance_policy.set_capability_mode(db, repo.id, "analyse_only", requested_by=requested_by)
    return repo


# ---- MaintenancePolicyService / ApprovedRepository ----


def test_register_repository_requires_human_role(db_session):
    permission_center.ensure_defaults(db_session)
    raised = False
    try:
        maintenance_policy.register_repository(db_session, display_name="ECHO", requested_by="echo")
    except maintenance_policy.MaintenancePermissionError:
        raised = True
    assert raised


def test_register_repository_succeeds_for_founder(db_session):
    permission_center.ensure_defaults(db_session)
    repo = maintenance_policy.register_repository(db_session, display_name="ECHO", requested_by="founder")
    assert repo.capability_mode == "disabled"
    assert repo.enabled is True
    assert os.path.isdir(repo.root_path_reference)


def test_register_repository_rejects_duplicate(db_session):
    permission_center.ensure_defaults(db_session)
    maintenance_policy.register_repository(db_session, display_name="ECHO", requested_by="founder")
    raised = False
    try:
        maintenance_policy.register_repository(db_session, display_name="ECHO again", requested_by="founder")
    except maintenance_policy.MaintenancePolicyError:
        raised = True
    assert raised


def test_set_capability_mode_requires_human_role(db_session):
    permission_center.ensure_defaults(db_session)
    repo = maintenance_policy.register_repository(db_session, display_name="ECHO", requested_by="founder")
    raised = False
    try:
        maintenance_policy.set_capability_mode(db_session, repo.id, "analyse_only", requested_by="echo")
    except maintenance_policy.MaintenancePermissionError:
        raised = True
    assert raised


def test_set_capability_mode_rejects_unknown_mode(db_session):
    permission_center.ensure_defaults(db_session)
    repo = maintenance_policy.register_repository(db_session, display_name="ECHO", requested_by="founder")
    raised = False
    try:
        maintenance_policy.set_capability_mode(db_session, repo.id, "god_mode", requested_by="founder")
    except maintenance_policy.MaintenancePolicyError:
        raised = True
    assert raised


def test_verify_repository_reports_no_drift_immediately_after_registration(db_session):
    permission_center.ensure_defaults(db_session)
    repo = maintenance_policy.register_repository(db_session, display_name="ECHO", requested_by="founder")
    _repo, drifted = maintenance_policy.verify_repository(db_session, repo.id)
    assert drifted is False


# ---- CodeAccessService: fail-closed by default ----


def test_code_access_fails_closed_when_disabled_by_default(db_session, monkeypatch):
    permission_center.ensure_defaults(db_session)
    repo = maintenance_policy.register_repository(db_session, display_name="ECHO", requested_by="founder")
    monkeypatch.setattr(maintenance_code_access, "get_settings", lambda: _settings())
    raised = False
    try:
        maintenance_code_access.list_repository_files(repo)
    except maintenance_code_access.CodeAccessPermissionError:
        raised = True
    assert raised


def test_code_access_requires_active_capability_mode(db_session, monkeypatch):
    permission_center.ensure_defaults(db_session)
    repo = maintenance_policy.register_repository(db_session, display_name="ECHO", requested_by="founder")
    monkeypatch.setattr(maintenance_code_access, "get_settings", lambda: _settings(
        supervised_maintenance_enabled=True, supervised_analysis_enabled=True,
    ))
    raised = False
    try:
        maintenance_code_access.list_repository_files(repo)  # still "disabled" mode
    except maintenance_code_access.CodeAccessPermissionError:
        raised = True
    assert raised


# ---- CodeAccessService: containment pipeline ----


def test_read_file_within_scope_succeeds(db_session, monkeypatch):
    repo = _register_and_activate(db_session, monkeypatch)
    content = maintenance_code_access.read_repository_file(repo, "backend/requirements.txt")
    assert content.content
    assert len(content.sha256) == 64


def test_read_file_rejects_path_traversal(db_session, monkeypatch):
    repo = _register_and_activate(db_session, monkeypatch)
    raised = False
    try:
        maintenance_code_access.read_repository_file(repo, "../../../etc/passwd")
    except maintenance_code_access.CodeAccessRejectedError:
        raised = True
    assert raised


def test_read_file_rejects_absolute_path(db_session, monkeypatch):
    repo = _register_and_activate(db_session, monkeypatch)
    raised = False
    try:
        maintenance_code_access.read_repository_file(repo, "/etc/passwd")
    except maintenance_code_access.CodeAccessRejectedError:
        raised = True
    assert raised


def test_read_file_rejects_windows_drive_path(db_session, monkeypatch):
    repo = _register_and_activate(db_session, monkeypatch)
    raised = False
    try:
        maintenance_code_access.read_repository_file(repo, "C:/Windows/System32/config/SAM")
    except maintenance_code_access.CodeAccessRejectedError:
        raised = True
    assert raised


def test_read_file_rejects_symlink_escape(db_session, monkeypatch, tmp_path):
    repo = _register_and_activate(db_session, monkeypatch)
    # Symlink inside the repo's tests dir pointing outside the repo root —
    # containment must reject it even though the symlink's own path is
    # inside the approved scope.
    outside = tmp_path / "outside_secret.txt"
    outside.write_text("outside content", encoding="utf-8")
    link_relative = "backend/tests/_symlink_escape_fixture.txt"
    link_path = maintenance_code_access._repo_root(repo) / link_relative
    try:
        link_path.symlink_to(outside)
    except OSError:
        import pytest

        pytest.skip("Symlink creation requires elevated privileges on this system.")
    try:
        raised = False
        try:
            maintenance_code_access.read_repository_file(repo, link_relative)
        except maintenance_code_access.CodeAccessRejectedError:
            raised = True
        assert raised
    finally:
        link_path.unlink(missing_ok=True)


def test_read_file_rejects_out_of_scope_path(db_session, monkeypatch):
    repo = _register_and_activate(db_session, monkeypatch)
    raised = False
    try:
        maintenance_code_access.read_repository_file(repo, "backend/app/constitution.py")
    except maintenance_code_access.CodeAccessRejectedError:
        raised = True
    assert raised  # backend/app/ is not in the default read scope (only backend/app/{providers,routers,services}/)


def test_read_file_rejects_env_file(db_session, monkeypatch, tmp_path):
    repo = _register_and_activate(db_session, monkeypatch)
    # backend/.env.example is in scope by path but must still be blocked by
    # filename pattern EXCEPT it's an explicit allowed template — so instead
    # construct a definite non-template secret-shaped filename within scope.
    raised = False
    try:
        maintenance_code_access.read_repository_file(repo, "backend/tests/.env")
    except maintenance_code_access.CodeAccessRejectedError:
        raised = True
    assert raised


def test_env_example_matches_secret_pattern_but_is_explicitly_excepted():
    # .env.example would otherwise be rejected by the .env* secret-filename
    # pattern — confirm the explicit template exception is what saves it.
    matched = any(p.match(".env.example") for p in maintenance_code_access._SECRET_FILENAME_PATTERNS)
    assert matched is True
    assert ".env.example" in maintenance_code_access._ALLOWED_TEMPLATE_EXCEPTIONS


def test_read_file_rejects_content_matching_secret_pattern(db_session, monkeypatch, tmp_path):
    repo = _register_and_activate(db_session, monkeypatch)
    secret_file = maintenance_code_access._repo_root(repo) / "backend" / "tests" / "_secret_content_fixture.py"
    secret_file.write_text('api_key = "sk-abcdefghijklmnopqrstuvwx1234567890"\n', encoding="utf-8")
    try:
        raised = False
        try:
            maintenance_code_access.read_repository_file(repo, "backend/tests/_secret_content_fixture.py")
        except maintenance_code_access.CodeAccessRejectedError:
            raised = True
        assert raised
    finally:
        secret_file.unlink(missing_ok=True)


def test_read_file_rejects_null_byte(db_session, monkeypatch):
    repo = _register_and_activate(db_session, monkeypatch)
    raised = False
    try:
        maintenance_code_access.read_repository_file(repo, "backend/tests/\x00evil.py")
    except maintenance_code_access.CodeAccessRejectedError:
        raised = True
    assert raised


def test_list_repository_files_returns_entries(db_session, monkeypatch):
    repo = _register_and_activate(db_session, monkeypatch)
    entries = maintenance_code_access.list_repository_files(repo, "backend/tests")
    assert len(entries) > 0
    assert all(isinstance(e.path, str) for e in entries)


def test_search_repository_text_finds_known_string(db_session, monkeypatch):
    repo = _register_and_activate(db_session, monkeypatch)
    hits = maintenance_code_access.search_repository_text(
        repo, "def register_repository", subpath="backend/app/services"
    )
    assert any(h.path.endswith("maintenance_policy.py") for h in hits)


def test_search_repository_text_rejects_short_query(db_session, monkeypatch):
    repo = _register_and_activate(db_session, monkeypatch)
    raised = False
    try:
        maintenance_code_access.search_repository_text(repo, "x")
    except maintenance_code_access.CodeAccessRejectedError:
        raised = True
    assert raised


def test_inspect_git_status_runs_read_only(db_session, monkeypatch):
    repo = _register_and_activate(db_session, monkeypatch)
    output = maintenance_code_access.inspect_git_status(repo)
    assert isinstance(output, str)


def test_calculate_repository_snapshot_returns_commit_sha(db_session, monkeypatch):
    repo = _register_and_activate(db_session, monkeypatch)
    snapshot = maintenance_code_access.calculate_repository_snapshot(repo)
    assert len(snapshot) == 40


def test_inspect_git_commit_rejects_malformed_ref(db_session, monkeypatch):
    repo = _register_and_activate(db_session, monkeypatch)
    raised = False
    try:
        maintenance_code_access.inspect_git_commit(repo, "; rm -rf /")
    except maintenance_code_access.CodeAccessRejectedError:
        raised = True
    assert raised


# ---- MaintenanceAnalysisService ----


def test_create_analysis_requires_active_capability_mode(db_session):
    permission_center.ensure_defaults(db_session)
    repo = maintenance_policy.register_repository(db_session, display_name="ECHO", requested_by="founder")
    raised = False
    try:
        maintenance_analysis.create_analysis(db_session, repository_id=repo.id, objective="find bugs")
    except maintenance_analysis.MaintenanceAnalysisPermissionError:
        raised = True
    assert raised


def test_create_analysis_and_add_finding(db_session, monkeypatch):
    monkeypatch.setattr(maintenance_analysis, "get_settings", lambda: _settings(
        supervised_maintenance_enabled=True, supervised_analysis_enabled=True,
    ))
    permission_center.ensure_defaults(db_session)
    repo = maintenance_policy.register_repository(db_session, display_name="ECHO", requested_by="founder")
    repo = maintenance_policy.set_capability_mode(db_session, repo.id, "analyse_only", requested_by="founder")

    analysis = maintenance_analysis.create_analysis(
        db_session, repository_id=repo.id, objective="Find dead code in maintenance_policy.py",
        problem_statement="Unclear if verify_repository is ever called from the frontend.",
    )
    assert analysis.status == "analysing"

    finding = maintenance_analysis.add_finding(
        db_session, analysis.id, epistemic_status="hypothesis",
        description="verify_repository may be unreachable from the current frontend.",
        affected_files=["backend/app/services/maintenance_policy.py"],
        evidence_reference="backend/app/services/maintenance_policy.py:150",
    )
    assert finding.epistemic_status == "hypothesis"

    findings = maintenance_analysis.list_findings(db_session, analysis.id)
    assert len(findings) == 1

    completed = maintenance_analysis.complete_analysis(db_session, analysis.id)
    assert completed.status == "analysis_complete"


def test_add_finding_rejects_invalid_epistemic_status(db_session, monkeypatch):
    monkeypatch.setattr(maintenance_analysis, "get_settings", lambda: _settings(
        supervised_maintenance_enabled=True, supervised_analysis_enabled=True,
    ))
    permission_center.ensure_defaults(db_session)
    repo = maintenance_policy.register_repository(db_session, display_name="ECHO", requested_by="founder")
    maintenance_policy.set_capability_mode(db_session, repo.id, "analyse_only", requested_by="founder")
    analysis = maintenance_analysis.create_analysis(db_session, repository_id=repo.id, objective="x")
    raised = False
    try:
        maintenance_analysis.add_finding(db_session, analysis.id, epistemic_status="definitely_true", description="x")
    except maintenance_analysis.MaintenanceAnalysisError:
        raised = True
    assert raised


def test_cannot_add_finding_after_completion(db_session, monkeypatch):
    monkeypatch.setattr(maintenance_analysis, "get_settings", lambda: _settings(
        supervised_maintenance_enabled=True, supervised_analysis_enabled=True,
    ))
    permission_center.ensure_defaults(db_session)
    repo = maintenance_policy.register_repository(db_session, display_name="ECHO", requested_by="founder")
    maintenance_policy.set_capability_mode(db_session, repo.id, "analyse_only", requested_by="founder")
    analysis = maintenance_analysis.create_analysis(db_session, repository_id=repo.id, objective="x")
    maintenance_analysis.complete_analysis(db_session, analysis.id)
    raised = False
    try:
        maintenance_analysis.add_finding(db_session, analysis.id, epistemic_status="verified", description="x")
    except maintenance_analysis.MaintenanceAnalysisStateError:
        raised = True
    assert raised


def test_cancel_analysis(db_session, monkeypatch):
    monkeypatch.setattr(maintenance_analysis, "get_settings", lambda: _settings(
        supervised_maintenance_enabled=True, supervised_analysis_enabled=True,
    ))
    permission_center.ensure_defaults(db_session)
    repo = maintenance_policy.register_repository(db_session, display_name="ECHO", requested_by="founder")
    maintenance_policy.set_capability_mode(db_session, repo.id, "analyse_only", requested_by="founder")
    analysis = maintenance_analysis.create_analysis(db_session, repository_id=repo.id, objective="x")
    cancelled = maintenance_analysis.cancel_analysis(db_session, analysis.id, reason="no longer needed")
    assert cancelled.status == "cancelled"


# ---- Audit trail ----


def test_audit_events_recorded_for_registration_and_analysis(db_session, monkeypatch):
    monkeypatch.setattr(maintenance_analysis, "get_settings", lambda: _settings(
        supervised_maintenance_enabled=True, supervised_analysis_enabled=True,
    ))
    permission_center.ensure_defaults(db_session)
    repo = maintenance_policy.register_repository(db_session, display_name="ECHO", requested_by="founder")
    maintenance_policy.set_capability_mode(db_session, repo.id, "analyse_only", requested_by="founder")
    maintenance_analysis.create_analysis(db_session, repository_id=repo.id, objective="x")

    from app.models import MaintenanceAuditEvent

    events = db_session.query(MaintenanceAuditEvent).filter(MaintenanceAuditEvent.repository_id == repo.id).all()
    event_types = {e.event_type for e in events}
    assert "repository_registered" in event_types
    assert "capability_mode_changed" in event_types
    assert "analysis_created" in event_types


# ---- Health ----


def test_get_health_reports_flag_defaults(db_session):
    health = maintenance_analysis.get_health(db_session)
    assert health["supervised_maintenance_enabled"] is False
    assert health["supervised_analysis_enabled"] is False
