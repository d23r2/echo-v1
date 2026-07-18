from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_db
from app.models import (
    CodeModificationProposal,
    CodeModificationRevision,
    ConstitutionalComplianceCheck,
    DeploymentAttempt,
    HumanApproval,
    ModificationImpactAssessment,
    SandboxExecution,
    SelfModificationAuditEvent,
    SelfModificationKillSwitch,
    VerificationRun,
)
from app.services import self_modification_governance as governance

router = APIRouter(prefix="/api/self-modification", tags=["self-modification"])

_ERROR_STATUS = {
    governance.SelfModNotFoundError: 404,
    governance.SelfModPermissionError: 403,
    governance.SelfModKillSwitchError: 423,
    governance.SelfModAuditError: 503,
    governance.SelfModFeatureDisabledError: 403,
    governance.SelfModScopeError: 400,
    governance.SelfModApprovalError: 400,
    governance.SelfModStateError: 409,
}


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except governance.SelfModError as exc:
        status_code = _ERROR_STATUS.get(type(exc), 400)
        raise HTTPException(status_code=status_code, detail=str(exc)) from None


@router.get("", response_model=list[schemas.SelfModProposalOut])
def list_proposals(db: Session = Depends(get_db)):
    return db.query(CodeModificationProposal).order_by(CodeModificationProposal.created_at.desc()).all()


@router.post("", response_model=schemas.SelfModProposalOut)
def create_proposal(payload: schemas.SelfModProposalCreate, db: Session = Depends(get_db)):
    return _run(
        governance.create_proposal, db,
        title=payload.title, description=payload.description,
        rationale=payload.rationale, proposed_by=payload.proposed_by,
    )


@router.get("/policy")
def get_policy():
    return {
        "allowed_path_prefixes": list(governance.ALLOWED_PATH_PREFIXES),
        "dependency_paths": sorted(governance.DEPENDENCY_PATHS),
        "protected_paths": sorted(governance.PROTECTED_PATHS),
        "protected_path_prefixes": list(governance.PROTECTED_PATH_PREFIXES),
        "protected_symbols": [name for name, _pattern in governance.PROTECTED_SYMBOL_PATTERNS],
        "risk_levels": ["low", "moderate", "high", "critical"],
        "critical_proposals_blocked": True,
        "approval_expiry_hours": governance.get_settings().self_modification_approval_expiry_hours,
    }


@router.get("/health", response_model=schemas.SelfModHealthOut)
def health(db: Session = Depends(get_db)):
    return governance.get_health(db)


@router.post("/kill-switch/activate", response_model=schemas.SelfModKillSwitchOut)
def activate_kill_switch(payload: schemas.SelfModKillSwitchActivate, db: Session = Depends(get_db)):
    return _run(governance.activate_kill_switch, db, activated_by=payload.activated_by, reason=payload.reason)


@router.post("/kill-switch/reset", response_model=schemas.SelfModKillSwitchOut)
def reset_kill_switch(payload: schemas.SelfModKillSwitchActivate, db: Session = Depends(get_db)):
    return _run(governance.reset_kill_switch, db, reset_by=payload.activated_by, reason=payload.reason)


@router.get("/kill-switch", response_model=schemas.SelfModKillSwitchOut)
def get_kill_switch(db: Session = Depends(get_db)):
    row = db.get(SelfModificationKillSwitch, "singleton")
    if row is None:
        return schemas.SelfModKillSwitchOut(
            active=False, activated_at=None, activated_by=None, reason=None, reset_at=None, reset_by=None,
        )
    return row


def _get_proposal_or_404(db: Session, proposal_id: str) -> CodeModificationProposal:
    proposal = db.get(CodeModificationProposal, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return proposal


@router.get("/{proposal_id}", response_model=schemas.SelfModProposalOut)
def get_proposal(proposal_id: str, db: Session = Depends(get_db)):
    return _get_proposal_or_404(db, proposal_id)


@router.post("/{proposal_id}/cancel", response_model=schemas.SelfModProposalOut)
def cancel_proposal(proposal_id: str, reason: str, db: Session = Depends(get_db)):
    return _run(governance.cancel_proposal, db, proposal_id, reason=reason)


@router.get("/{proposal_id}/revisions", response_model=list[schemas.SelfModRevisionOut])
def list_revisions(proposal_id: str, db: Session = Depends(get_db)):
    _get_proposal_or_404(db, proposal_id)
    return (
        db.query(CodeModificationRevision)
        .filter(CodeModificationRevision.proposal_id == proposal_id)
        .order_by(CodeModificationRevision.revision_number.asc())
        .all()
    )


@router.post("/{proposal_id}/revisions", response_model=schemas.SelfModRevisionOut)
def submit_revision(proposal_id: str, payload: schemas.SelfModRevisionCreate, db: Session = Depends(get_db)):
    return _run(governance.submit_revision, db, proposal_id, patch_text=payload.patch_text)


def _get_revision_or_404(db: Session, revision_id: str) -> CodeModificationRevision:
    revision = db.get(CodeModificationRevision, revision_id)
    if revision is None:
        raise HTTPException(status_code=404, detail="Revision not found")
    return revision


@router.post("/revisions/{revision_id}/scope-check", response_model=schemas.SelfModRevisionOut)
def scope_check(revision_id: str, db: Session = Depends(get_db)):
    return _run(governance.run_scope_check, db, revision_id)


@router.post("/revisions/{revision_id}/compliance-check", response_model=schemas.SelfModRevisionOut)
def compliance_check(revision_id: str, db: Session = Depends(get_db)):
    return _run(governance.run_compliance_check, db, revision_id)


@router.get("/revisions/{revision_id}/impact-assessment", response_model=schemas.SelfModImpactAssessmentOut | None)
def get_impact_assessment(revision_id: str, db: Session = Depends(get_db)):
    _get_revision_or_404(db, revision_id)
    return (
        db.query(ModificationImpactAssessment)
        .filter(ModificationImpactAssessment.revision_id == revision_id)
        .order_by(ModificationImpactAssessment.created_at.desc())
        .first()
    )


@router.get("/revisions/{revision_id}/compliance-checks", response_model=list[schemas.SelfModComplianceCheckOut])
def list_compliance_checks(revision_id: str, db: Session = Depends(get_db)):
    _get_revision_or_404(db, revision_id)
    return (
        db.query(ConstitutionalComplianceCheck)
        .filter(ConstitutionalComplianceCheck.revision_id == revision_id)
        .order_by(ConstitutionalComplianceCheck.created_at.desc())
        .all()
    )


@router.post("/{proposal_id}/ready-for-sandbox", response_model=schemas.SelfModProposalOut)
def mark_ready_for_sandbox(proposal_id: str, db: Session = Depends(get_db)):
    return _run(governance.mark_ready_for_sandbox, db, proposal_id)


@router.post("/{proposal_id}/sandbox", response_model=schemas.SelfModSandboxExecutionOut)
def run_sandbox(
    proposal_id: str,
    payload: schemas.SelfModOperationConfirmation,
    db: Session = Depends(get_db),
):
    return _run(governance.run_sandbox, db, proposal_id, confirmed=payload.confirmed)


@router.get("/{proposal_id}/sandbox-executions", response_model=list[schemas.SelfModSandboxExecutionOut])
def list_sandbox_executions(proposal_id: str, db: Session = Depends(get_db)):
    proposal = _get_proposal_or_404(db, proposal_id)
    revision_ids = [
        r.id for r in db.query(CodeModificationRevision).filter(CodeModificationRevision.proposal_id == proposal.id).all()
    ]
    if not revision_ids:
        return []
    return (
        db.query(SandboxExecution)
        .filter(SandboxExecution.revision_id.in_(revision_ids))
        .order_by(SandboxExecution.created_at.desc())
        .all()
    )


@router.get("/sandbox-executions/{execution_id}/verification", response_model=schemas.SelfModVerificationRunOut | None)
def get_verification_run(execution_id: str, db: Session = Depends(get_db)):
    return (
        db.query(VerificationRun)
        .filter(VerificationRun.sandbox_execution_id == execution_id)
        .order_by(VerificationRun.created_at.desc())
        .first()
    )


@router.post("/{proposal_id}/request-review", response_model=schemas.SelfModProposalOut)
def request_review(proposal_id: str, db: Session = Depends(get_db)):
    return _run(governance.request_review, db, proposal_id)


@router.post("/{proposal_id}/approve", response_model=schemas.SelfModApprovalOut)
def approve(proposal_id: str, payload: schemas.SelfModApprovalCreate, db: Session = Depends(get_db)):
    return _run(
        governance.approve_revision, db, proposal_id,
        approver_role=payload.approver_role, decision=payload.decision,
        test_evidence_summary=payload.test_evidence_summary,
        acknowledgement_text=payload.acknowledgement_text,
    )


@router.get("/{proposal_id}/approvals", response_model=list[schemas.SelfModApprovalOut])
def list_approvals(proposal_id: str, db: Session = Depends(get_db)):
    proposal = _get_proposal_or_404(db, proposal_id)
    revision_ids = [
        r.id for r in db.query(CodeModificationRevision).filter(CodeModificationRevision.proposal_id == proposal.id).all()
    ]
    if not revision_ids:
        return []
    return (
        db.query(HumanApproval)
        .filter(HumanApproval.revision_id.in_(revision_ids))
        .order_by(HumanApproval.created_at.desc())
        .all()
    )


@router.post("/{proposal_id}/deploy", response_model=schemas.SelfModDeploymentAttemptOut)
def deploy(
    proposal_id: str,
    payload: schemas.SelfModOperationConfirmation,
    db: Session = Depends(get_db),
):
    return _run(governance.deploy, db, proposal_id, confirmed=payload.confirmed)


@router.get("/{proposal_id}/deployments", response_model=list[schemas.SelfModDeploymentAttemptOut])
def list_deployments(proposal_id: str, db: Session = Depends(get_db)):
    proposal = _get_proposal_or_404(db, proposal_id)
    revision_ids = [
        r.id for r in db.query(CodeModificationRevision).filter(CodeModificationRevision.proposal_id == proposal.id).all()
    ]
    if not revision_ids:
        return []
    return (
        db.query(DeploymentAttempt)
        .filter(DeploymentAttempt.revision_id.in_(revision_ids))
        .order_by(DeploymentAttempt.created_at.desc())
        .all()
    )


@router.post("/{proposal_id}/rollback", response_model=schemas.SelfModRollbackEventOut)
def rollback(proposal_id: str, reason: str, db: Session = Depends(get_db)):
    return _run(governance.rollback, db, proposal_id, reason=reason)


@router.get("/{proposal_id}/audit", response_model=list[schemas.SelfModAuditEventOut])
def get_audit_trail(proposal_id: str, db: Session = Depends(get_db)):
    _get_proposal_or_404(db, proposal_id)
    return (
        db.query(SelfModificationAuditEvent)
        .filter(SelfModificationAuditEvent.proposal_id == proposal_id)
        .order_by(SelfModificationAuditEvent.created_at.asc())
        .all()
    )
