"""ECHO Supervised Maintenance Workspace v1 — Phase 3 (Proposal generation).

Confirms MaintenanceProposalService is a thin wrapper: an analysis-
originated proposal goes through the exact unchanged Part 2D lifecycle
(scope check, compliance check) with no weakened validation.
"""

from app.config import Settings
from app.services import maintenance_analysis, maintenance_policy, maintenance_proposal, permission_center
from app.services import self_modification_governance as governance


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


def _make_analysis(db, monkeypatch, *, mode="propose_only"):
    monkeypatch.setattr(maintenance_analysis, "get_settings", lambda: _settings(
        supervised_maintenance_enabled=True, supervised_analysis_enabled=True,
    ))
    permission_center.ensure_defaults(db)
    repo = maintenance_policy.register_repository(db, display_name="ECHO", requested_by="founder")
    repo = maintenance_policy.set_capability_mode(db, repo.id, mode, requested_by="founder")
    analysis = maintenance_analysis.create_analysis(db, repository_id=repo.id, objective="Find dead code.")
    return repo, analysis


def test_create_proposal_requires_flags_enabled(db_session, monkeypatch):
    _repo, analysis = _make_analysis(db_session, monkeypatch)
    monkeypatch.setattr(maintenance_proposal, "get_settings", lambda: _settings(
        supervised_maintenance_enabled=True, supervised_analysis_enabled=True,
    ))
    raised = False
    try:
        maintenance_proposal.create_proposal_from_analysis(
            db_session, analysis_id=analysis.id, title="t", description="d", rationale=_RATIONALE,
            patch_text=_patch_touching("backend/tests/test_dummy_maint.py"),
        )
    except maintenance_proposal.MaintenanceProposalPermissionError:
        raised = True
    assert raised


def test_create_proposal_requires_propose_capable_mode(db_session, monkeypatch):
    _repo, analysis = _make_analysis(db_session, monkeypatch, mode="analyse_only")
    monkeypatch.setattr(maintenance_proposal, "get_settings", lambda: _settings(
        supervised_maintenance_enabled=True, supervised_analysis_enabled=True, supervised_proposals_enabled=True,
    ))
    raised = False
    try:
        maintenance_proposal.create_proposal_from_analysis(
            db_session, analysis_id=analysis.id, title="t", description="d", rationale=_RATIONALE,
            patch_text=_patch_touching("backend/tests/test_dummy_maint.py"),
        )
    except maintenance_proposal.MaintenanceProposalPermissionError:
        raised = True
    assert raised


def test_create_proposal_from_analysis_succeeds_and_links_analysis(db_session, monkeypatch):
    _repo, analysis = _make_analysis(db_session, monkeypatch, mode="propose_only")
    monkeypatch.setattr(maintenance_proposal, "get_settings", lambda: _settings(
        supervised_maintenance_enabled=True, supervised_analysis_enabled=True, supervised_proposals_enabled=True,
    ))
    proposal = maintenance_proposal.create_proposal_from_analysis(
        db_session, analysis_id=analysis.id, title="Remove dead helper", description="d", rationale=_RATIONALE,
        patch_text=_patch_touching("backend/tests/test_dummy_maint.py"),
    )
    assert proposal.analysis_id == analysis.id
    assert proposal.status == "draft"
    assert proposal.active_revision_id is not None


def test_analysis_originated_proposal_goes_through_unchanged_scope_check(db_session, monkeypatch):
    """Proves the wrapper doesn't bypass Part 2D validation — a patch
    touching a protected file is still blocked even though it came from an
    analysis-driven proposal."""
    _repo, analysis = _make_analysis(db_session, monkeypatch, mode="propose_only")
    monkeypatch.setattr(maintenance_proposal, "get_settings", lambda: _settings(
        supervised_maintenance_enabled=True, supervised_analysis_enabled=True, supervised_proposals_enabled=True,
    ))
    proposal = maintenance_proposal.create_proposal_from_analysis(
        db_session, analysis_id=analysis.id, title="t", description="d", rationale=_RATIONALE,
        patch_text=_patch_touching("backend/app/constitution.py"),
    )
    revision = governance._require_active_revision(db_session, proposal)
    governance.run_scope_check(db_session, revision.id)
    db_session.refresh(revision)
    db_session.refresh(proposal)
    assert revision.scope_check_status == "failed"
    assert proposal.status == "scope_check_failed"
    assert proposal.risk_level == "critical"


def test_create_proposal_rejects_analysis_in_wrong_state(db_session, monkeypatch):
    _repo, analysis = _make_analysis(db_session, monkeypatch, mode="propose_only")
    maintenance_analysis.cancel_analysis(db_session, analysis.id)
    monkeypatch.setattr(maintenance_proposal, "get_settings", lambda: _settings(
        supervised_maintenance_enabled=True, supervised_analysis_enabled=True, supervised_proposals_enabled=True,
    ))
    raised = False
    try:
        maintenance_proposal.create_proposal_from_analysis(
            db_session, analysis_id=analysis.id, title="t", description="d", rationale=_RATIONALE,
            patch_text=_patch_touching("backend/tests/test_dummy_maint.py"),
        )
    except maintenance_proposal.MaintenanceProposalStateError:
        raised = True
    assert raised


def test_create_proposal_audit_trail(db_session, monkeypatch):
    repo, analysis = _make_analysis(db_session, monkeypatch, mode="propose_only")
    monkeypatch.setattr(maintenance_proposal, "get_settings", lambda: _settings(
        supervised_maintenance_enabled=True, supervised_analysis_enabled=True, supervised_proposals_enabled=True,
    ))
    maintenance_proposal.create_proposal_from_analysis(
        db_session, analysis_id=analysis.id, title="t", description="d", rationale=_RATIONALE,
        patch_text=_patch_touching("backend/tests/test_dummy_maint.py"),
    )
    from app.models import MaintenanceAuditEvent

    events = db_session.query(MaintenanceAuditEvent).filter(MaintenanceAuditEvent.repository_id == repo.id).all()
    event_types = {e.event_type for e in events}
    assert "proposal_generated_from_analysis" in event_types
