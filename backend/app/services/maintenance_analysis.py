"""ECHO Supervised Maintenance Workspace v1 — MaintenanceAnalysisService.

Turns CodeAccessService output into structured, reviewable findings. Never
stores hidden chain-of-thought — description is the reviewable engineering
statement; evidence_reference points at a real file:line rather than
duplicating file content into the row.
"""

import logging

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.logging import log_event
from app.models import ApprovedRepository, MaintenanceAnalysis, MaintenanceAuditEvent, MaintenanceFinding
from app.services import permission_center

logger = logging.getLogger(__name__)

_EPISTEMIC_STATUSES = frozenset({"verified", "inferred", "hypothesis", "unknown"})
_ACTIVE_MODES = frozenset({"analyse_only", "propose_only", "sandbox_verify", "human_approved_local_commit"})


class MaintenanceAnalysisError(Exception):
    pass


class MaintenanceAnalysisNotFoundError(MaintenanceAnalysisError):
    pass


class MaintenanceAnalysisPermissionError(MaintenanceAnalysisError):
    pass


class MaintenanceAnalysisStateError(MaintenanceAnalysisError):
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


def _require_repository(db: Session, repository_id: str) -> ApprovedRepository:
    repo = db.get(ApprovedRepository, repository_id)
    if repo is None:
        raise MaintenanceAnalysisNotFoundError(f"Repository '{repository_id}' not found.")
    return repo


def _require_analysis(db: Session, analysis_id: str) -> MaintenanceAnalysis:
    analysis = db.get(MaintenanceAnalysis, analysis_id)
    if analysis is None:
        raise MaintenanceAnalysisNotFoundError(f"Analysis '{analysis_id}' not found.")
    return analysis


def create_analysis(
    db: Session, *, repository_id: str, objective: str, requested_by: str = "echo",
    problem_statement: str = "",
) -> MaintenanceAnalysis:
    settings = get_settings()
    if not settings.supervised_maintenance_enabled or not settings.supervised_analysis_enabled:
        raise MaintenanceAnalysisPermissionError(
            "Supervised Maintenance analysis is disabled (SUPERVISED_MAINTENANCE_ENABLED / "
            "SUPERVISED_ANALYSIS_ENABLED)."
        )
    permission = permission_center.check(db, "supervised_maintenance_create_analysis")
    if not permission.allowed:
        raise MaintenanceAnalysisPermissionError(permission.reason)

    repo = _require_repository(db, repository_id)
    if not repo.enabled:
        raise MaintenanceAnalysisPermissionError("This repository is disabled.")
    if repo.capability_mode not in _ACTIVE_MODES:
        raise MaintenanceAnalysisPermissionError(
            f"This repository's capability mode is '{repo.capability_mode}' — analysis requires at "
            "least analyse_only."
        )
    if not objective.strip():
        raise MaintenanceAnalysisError("An analysis objective is required.")

    analysis = MaintenanceAnalysis(
        repository_id=repo.id, objective=objective.strip(), requested_by=requested_by,
        status="analysing", problem_statement=problem_statement.strip(),
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    _record_audit_event(
        db, repository_id=repo.id, analysis_id=analysis.id, event_type="analysis_created",
        actor_role=requested_by, summary=f"Analysis started: {objective.strip()[:200]}",
    )
    return analysis


def add_finding(
    db: Session, analysis_id: str, *, epistemic_status: str, description: str,
    affected_files: list[str] | None = None, evidence_reference: str = "",
) -> MaintenanceFinding:
    analysis = _require_analysis(db, analysis_id)
    if analysis.status not in ("draft", "analysing"):
        raise MaintenanceAnalysisStateError(f"Analysis is '{analysis.status}' — cannot add findings.")
    if epistemic_status not in _EPISTEMIC_STATUSES:
        raise MaintenanceAnalysisError(
            f"epistemic_status must be one of {sorted(_EPISTEMIC_STATUSES)}, got '{epistemic_status}'."
        )
    if not description.strip():
        raise MaintenanceAnalysisError("A finding description is required.")

    finding = MaintenanceFinding(
        analysis_id=analysis.id, epistemic_status=epistemic_status, description=description.strip(),
        affected_files=affected_files or [], evidence_reference=evidence_reference.strip(),
    )
    db.add(finding)
    db.commit()
    db.refresh(finding)
    _record_audit_event(
        db, repository_id=analysis.repository_id, analysis_id=analysis.id, event_type="finding_added",
        actor_role=analysis.requested_by,
        summary=description.strip()[:200],
        safe_context={"epistemic_status": epistemic_status, "affected_files": affected_files or []},
    )
    return finding


def complete_analysis(db: Session, analysis_id: str) -> MaintenanceAnalysis:
    analysis = _require_analysis(db, analysis_id)
    if analysis.status != "analysing":
        raise MaintenanceAnalysisStateError(f"Analysis is '{analysis.status}' — cannot complete.")
    analysis.status = "analysis_complete"
    db.commit()
    db.refresh(analysis)
    _record_audit_event(
        db, repository_id=analysis.repository_id, analysis_id=analysis.id, event_type="analysis_completed",
        actor_role=analysis.requested_by, summary="Analysis marked complete.",
    )
    return analysis


def cancel_analysis(db: Session, analysis_id: str, *, reason: str = "") -> MaintenanceAnalysis:
    analysis = _require_analysis(db, analysis_id)
    if analysis.status == "cancelled":
        return analysis
    analysis.status = "cancelled"
    db.commit()
    db.refresh(analysis)
    _record_audit_event(
        db, repository_id=analysis.repository_id, analysis_id=analysis.id, event_type="analysis_cancelled",
        actor_role=analysis.requested_by, summary=reason or "Analysis cancelled.",
    )
    return analysis


def list_analyses(db: Session, repository_id: str | None = None) -> list[MaintenanceAnalysis]:
    query = db.query(MaintenanceAnalysis)
    if repository_id:
        query = query.filter(MaintenanceAnalysis.repository_id == repository_id)
    return query.order_by(MaintenanceAnalysis.created_at.desc()).all()


def get_analysis(db: Session, analysis_id: str) -> MaintenanceAnalysis:
    return _require_analysis(db, analysis_id)


def list_findings(db: Session, analysis_id: str) -> list[MaintenanceFinding]:
    _require_analysis(db, analysis_id)
    return (
        db.query(MaintenanceFinding)
        .filter(MaintenanceFinding.analysis_id == analysis_id)
        .order_by(MaintenanceFinding.created_at.asc())
        .all()
    )


def get_health(db: Session) -> dict:
    settings = get_settings()
    from app.models import ApprovedRepository as _Repo

    return {
        "supervised_maintenance_enabled": settings.supervised_maintenance_enabled,
        "supervised_analysis_enabled": settings.supervised_analysis_enabled,
        "supervised_proposals_enabled": settings.supervised_proposals_enabled,
        "supervised_sandbox_enabled": settings.supervised_sandbox_enabled,
        "supervised_local_commit_enabled": settings.supervised_local_commit_enabled,
        "supervised_maintenance_frontend_enabled": settings.supervised_maintenance_frontend_enabled,
        "registered_repository_count": db.query(_Repo).count(),
        "open_analysis_count": (
            db.query(MaintenanceAnalysis)
            .filter(MaintenanceAnalysis.status.in_(("draft", "analysing")))
            .count()
        ),
    }
