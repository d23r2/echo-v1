"""ECHO Supervised Maintenance Workspace v1 — MaintenancePolicyService.

Owner-controlled ApprovedRepository registration. Nothing here scans the
filesystem or infers a root path automatically. Version 1 does not accept a
client-supplied filesystem path at all — the one repository worth analysing
is the actual codebase this backend process is running from
(self_improvement_verify.REPO_ROOT, the same path resolution
self_improvement_verify.py already uses), so that is the only root this
service will ever register. This is the safest way to satisfy "the owner
must explicitly register an approved repository... never automatically
include home directory, Documents, unrelated repositories, system
directories" (protected_scope.md) — there is no path-parsing surface for an
adversarial path to exploit in the first place.
"""

import logging
import subprocess
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.logging import log_event
from app.models import ApprovedRepository, MaintenanceAuditEvent
from app.self_improvement_verify import REPO_ROOT
from app.services import permission_center
from app.services.self_modification_governance import ALLOWED_PATH_PREFIXES

logger = logging.getLogger(__name__)

_HUMAN_APPROVER_ROLES = frozenset({"founder", "guardian_a", "guardian_b", "guardian_c", "verifier"})

_DEFAULT_READ_PATHS = list(ALLOWED_PATH_PREFIXES) + ["*.md", "backend/requirements.txt", "frontend/package.json"]
_DEFAULT_PROPOSAL_PATHS = list(ALLOWED_PATH_PREFIXES)
_DEFAULT_BLOCKED_PATTERNS = [
    ".env*", "*.pem", "*.key", "*.p12", "*.pfx", "credentials.*", "secrets.*",
    "id_rsa*", "id_ed25519*", "*.db", "*.sqlite*",
]


class MaintenancePolicyError(Exception):
    pass


class MaintenanceNotFoundError(MaintenancePolicyError):
    pass


class MaintenancePermissionError(MaintenancePolicyError):
    pass


def ensure_defaults(db: Session) -> None:
    permission_center.ensure_defaults(db)


def _record_audit_event(
    db: Session, *, repository_id: str | None, event_type: str, actor_role: str | None, summary: str,
    safe_context: dict | None = None,
) -> None:
    event = MaintenanceAuditEvent(
        repository_id=repository_id, analysis_id=None, event_type=event_type,
        actor_role=actor_role or "system", summary=summary, safe_context_json=safe_context or {},
    )
    db.add(event)
    db.commit()
    log_event(logger, f"supervised_maintenance.{event_type}")


def _compute_fingerprint(root: Path) -> str:
    import hashlib

    material = str(root.resolve())
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=10
        )
        if proc.returncode == 0:
            material += proc.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def register_repository(
    db: Session, *, display_name: str, requested_by: str, approved_branches: list[str] | None = None,
) -> ApprovedRepository:
    permission = permission_center.check(db, "supervised_maintenance_register_repository")
    if not permission.allowed:
        raise MaintenancePermissionError(permission.reason)
    if requested_by not in _HUMAN_APPROVER_ROLES:
        raise MaintenancePermissionError(
            "Repository registration is owner-only; the model identity may not register a repository."
        )
    if not display_name.strip():
        raise MaintenancePolicyError("A display name is required.")

    existing = db.query(ApprovedRepository).filter(ApprovedRepository.root_path_reference == str(REPO_ROOT.resolve())).first()
    if existing is not None:
        raise MaintenancePolicyError("This repository is already registered.")

    repo = ApprovedRepository(
        display_name=display_name.strip(),
        root_path_reference=str(REPO_ROOT.resolve()),
        fingerprint=_compute_fingerprint(REPO_ROOT),
        approved_branches=approved_branches or ["master"],
        permitted_read_paths=list(_DEFAULT_READ_PATHS),
        permitted_proposal_paths=list(_DEFAULT_PROPOSAL_PATHS),
        blocked_file_patterns=list(_DEFAULT_BLOCKED_PATTERNS),
        capability_mode="disabled",
        owner=requested_by,
        enabled=True,
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)
    _record_audit_event(
        db, repository_id=repo.id, event_type="repository_registered", actor_role=requested_by,
        summary=f"Registered '{display_name}'.",
    )
    return repo


def get_repository(db: Session, repository_id: str) -> ApprovedRepository:
    repo = db.get(ApprovedRepository, repository_id)
    if repo is None:
        raise MaintenanceNotFoundError(f"Repository '{repository_id}' not found.")
    return repo


def list_repositories(db: Session) -> list[ApprovedRepository]:
    return db.query(ApprovedRepository).order_by(ApprovedRepository.created_at.desc()).all()


def set_capability_mode(db: Session, repository_id: str, mode: str, *, requested_by: str) -> ApprovedRepository:
    if requested_by not in _HUMAN_APPROVER_ROLES:
        raise MaintenancePermissionError(
            "Capability-mode changes are owner-only; the model identity may not change its own access level."
        )
    if mode not in ("disabled", "analyse_only", "propose_only", "sandbox_verify", "human_approved_local_commit"):
        raise MaintenancePolicyError(f"Unknown capability mode '{mode}'.")
    repo = get_repository(db, repository_id)
    previous = repo.capability_mode
    repo.capability_mode = mode
    db.commit()
    db.refresh(repo)
    _record_audit_event(
        db, repository_id=repo.id, event_type="capability_mode_changed", actor_role=requested_by,
        summary=f"Capability mode changed from '{previous}' to '{mode}'.",
    )
    return repo


def verify_repository(db: Session, repository_id: str) -> tuple[ApprovedRepository, bool]:
    """Recomputes the fingerprint and reports whether it drifted from what
    was recorded at registration (e.g. the codebase moved to a different
    commit). Drift is informational in v1 — it does not itself change the
    capability mode — but is always visible in /status and the audit trail."""
    from datetime import UTC, datetime

    repo = get_repository(db, repository_id)
    current = _compute_fingerprint(Path(repo.root_path_reference))
    drifted = current != repo.fingerprint
    repo.last_verified_at = datetime.now(UTC)
    db.commit()
    db.refresh(repo)
    _record_audit_event(
        db, repository_id=repo.id, event_type="repository_verified", actor_role="system",
        summary="Fingerprint drift detected." if drifted else "Fingerprint unchanged.",
        safe_context={"drifted": drifted},
    )
    return repo, drifted
