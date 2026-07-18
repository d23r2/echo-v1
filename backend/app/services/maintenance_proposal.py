"""ECHO Supervised Maintenance Workspace v1 — MaintenanceProposalService.

A thin wrapper: turns an accepted maintenance analysis into a real
self_modification_governance.CodeModificationProposal + Revision, using the
unchanged create_proposal()/submit_revision() functions from Layer 3A
Part 2D. Nothing about scope validation, constitutional compliance,
sandboxing, approval, deployment, or rollback is reimplemented here — this
module's only job is the analysis_id linkage and its own capability-mode
gate (propose_only or higher).
"""

import logging

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.logging import log_event
from app.models import ApprovedRepository, MaintenanceAnalysis, MaintenanceAuditEvent
from app.services import self_modification_governance as governance

logger = logging.getLogger(__name__)

_PROPOSAL_CAPABLE_MODES = frozenset({"propose_only", "sandbox_verify", "human_approved_local_commit"})


class MaintenanceProposalError(Exception):
    pass


class MaintenanceProposalPermissionError(MaintenanceProposalError):
    pass


class MaintenanceProposalStateError(MaintenanceProposalError):
    pass


def _record_audit_event(
    db: Session, *, repository_id: str | None, analysis_id: str | None, event_type: str,
    actor_role: str | None, summary: str, safe_context: dict | None = None,
) -> None:
    event = MaintenanceAuditEvent(
        repository_id=repository_id, analysis_id=analysis_id, event_type=event_type,
        actor_role=actor_role or "system", summary=summary, safe_context_json=safe_context or {},
    )
    db.add(event)
    db.commit()
    log_event(logger, f"supervised_maintenance.{event_type}")


def create_proposal_from_analysis(
    db: Session, *, analysis_id: str, title: str, description: str, rationale: str,
    patch_text: str, proposed_by: str = "echo",
):
    """Creates a CodeModificationProposal + initial CodeModificationRevision
    bound to the given analysis. Returns the same governance.CodeModificationProposal
    the /api/self-modification/* routes already work with — from here on,
    the proposal follows the exact unchanged Part 2D lifecycle (scope check,
    compliance check, sandbox, approval, deploy, rollback)."""
    settings = get_settings()
    if not settings.supervised_maintenance_enabled or not settings.supervised_proposals_enabled:
        raise MaintenanceProposalPermissionError(
            "Supervised Maintenance proposal generation is disabled (SUPERVISED_MAINTENANCE_ENABLED / "
            "SUPERVISED_PROPOSALS_ENABLED)."
        )

    analysis = db.get(MaintenanceAnalysis, analysis_id)
    if analysis is None:
        raise MaintenanceProposalError(f"Analysis '{analysis_id}' not found.")
    if analysis.status not in ("analysing", "analysis_complete"):
        raise MaintenanceProposalStateError(
            f"Analysis is '{analysis.status}' — a proposal can only be generated from an active or "
            "completed analysis."
        )

    repository = db.get(ApprovedRepository, analysis.repository_id)
    if repository is None or not repository.enabled:
        raise MaintenanceProposalPermissionError("The analysis's repository is unavailable or disabled.")
    if repository.capability_mode not in _PROPOSAL_CAPABLE_MODES:
        raise MaintenanceProposalPermissionError(
            f"This repository's capability mode is '{repository.capability_mode}' — proposal "
            "generation requires at least propose_only."
        )

    # create_proposal()/submit_revision() perform their own full validation
    # (permission_center check, rationale-section requirements, patch
    # secret-scan, byte-size limit, hash computation) — nothing here
    # duplicates or weakens any of that.
    proposal = governance.create_proposal(
        db, title=title, description=description, rationale=rationale,
        proposed_by=proposed_by, analysis_id=analysis.id,
    )
    governance.submit_revision(db, proposal.id, patch_text=patch_text)

    _record_audit_event(
        db, repository_id=repository.id, analysis_id=analysis.id, event_type="proposal_generated_from_analysis",
        actor_role=proposed_by, summary=f"Proposal '{title}' generated from analysis {analysis.id}.",
        safe_context={"proposal_id": proposal.id},
    )
    db.refresh(proposal)
    return proposal
