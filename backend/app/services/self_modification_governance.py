"""ECHO Layer 3A Part 2D — Supervised Self-Modification Governance.

A separate, purpose-built service from self_improvement_verify.py (Layer 0),
which remains untouched and strictly read-only. This module implements the
actual propose -> scope-check -> constitutional-compliance-check ->
sandbox -> human-approve -> (locally) deploy -> rollback lifecycle, per the
Layer 3A Part 2D milestone.

Non-negotiable design rules, all enforced in code below (not just docs):
  - CRITICAL-risk proposals never reach ready_for_sandbox — they're blocked
    from this workflow entirely and must go through the real Guardian
    Council amendment process (backend/app/council.py) or a manual process.
  - Every mutating call checks permission_center.check() with a dedicated
    self_modification_* key (see permission_center.py) — this is not a
    parallel approval mechanism, it's the same gate action_system.py and
    tool_registry.py already use.
  - Deployment is gated by TWO independent off-by-default feature flags
    (supervised_self_modification_enabled, self_modification_deployment_enabled)
    plus a valid, unexpired HumanApproval bound to the exact active patch
    hash — any one of these failing blocks deployment (fail closed).
  - The kill switch, once activated, blocks new sandbox runs/approvals/
    deployments immediately; it never blocks read/audit/rollback access.
  - This module and self_modification_sandbox.py are themselves on the
    protected-path denylist below — the workflow can never modify its own
    governance code.

Honest limitation, stated once here rather than scattered: this app is
single-user with no real authentication (see PermissionSetting's docstring
and council.py's module docstring for the same acknowledgement about
Guardian Council). "approver_role"/"proposed_by" are the same simulated-role
labels the rest of this app already uses, not verified multi-party identity.
"""

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath

from sqlalchemy.orm import Session

from app import constitution
from app.config import get_settings
from app.core import metrics
from app.core.logging import log_event
from app.models import (
    CodeModificationProposal,
    CodeModificationRevision,
    ConstitutionalComplianceCheck,
    DeploymentAttempt,
    HumanApproval,
    ModificationImpactAssessment,
    RollbackEvent,
    SandboxExecution,
    SelfModificationAuditEvent,
    SelfModificationKillSwitch,
    VerificationRun,
)
from app.services import action_system, permission_center
from app.services import self_modification_sandbox as sandbox

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    """SQLite stores naive datetimes — a value written with datetime.now(UTC)
    comes back tzinfo-less after a session expire/refresh round-trip. Assumes
    UTC rather than letting a naive-vs-aware comparison raise, same fix as
    schemas.py's _UtcAssumingModel and usage.py's cooldown check."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


# --- Typed exceptions — routers translate these to specific HTTP statuses ---
class SelfModError(Exception):
    """Base class for every self-modification governance error."""


class SelfModNotFoundError(SelfModError):
    pass


class SelfModPermissionError(SelfModError):
    pass


class SelfModStateError(SelfModError):
    pass


class SelfModScopeError(SelfModError):
    pass


class SelfModApprovalError(SelfModError):
    pass


class SelfModFeatureDisabledError(SelfModError):
    pass


class SelfModKillSwitchError(SelfModError):
    pass


class SelfModAuditError(SelfModError):
    pass


_CLOSED_STATUSES = frozenset({"closed", "cancelled", "rejected", "rolled_back"})
_TERMINAL_STATUSES = _CLOSED_STATUSES | frozenset({"deployed"})
_HUMAN_APPROVER_ROLES = frozenset({"founder", "guardian_a", "guardian_b", "guardian_c", "verifier"})


# --- Protected scope policy (Python constants, same registry pattern as
# action_system.ACTIONS / permission_center.DEFAULT_PERMISSIONS — this repo
# has no precedent for policy-shaped data living in a DB table). ---

#: Whole files that can never be touched by this workflow at all: the
#: constitution/Guardian Council, the Permission Center and Action System
#: (the gate this workflow itself routes through), the identity/moral-
#: compass services, this governance module and its sandbox, models.py
#: (governance + identity table definitions live there — protected as a
#: whole file rather than attempting per-symbol AST parsing this milestone),
#: db.py/config.py (schema + secrets), and core observability/audit code.
PROTECTED_PATHS = frozenset(
    {
        "backend/app/constitution.py",
        "backend/app/council.py",
        "backend/app/models.py",
        "backend/app/db.py",
        "backend/app/config.py",
        "backend/app/main.py",
        "backend/app/services/permission_center.py",
        "backend/app/services/action_system.py",
        "backend/app/services/identity_service.py",
        "backend/app/services/identity_runtime.py",
        "backend/app/services/identity_context.py",
        "backend/app/persona.py",
        "backend/app/human_persona.py",
        "backend/app/services/persona_service.py",
        "backend/app/services/self_modification_governance.py",
        "backend/app/services/self_modification_sandbox.py",
        "backend/app/routers/self_modification.py",
        "backend/app/routers/constitution.py",
        "backend/app/routers/amendments.py",
        "backend/app/core/logging.py",
        "backend/app/core/errors.py",
        "backend/app/self_improvement_verify.py",
        "backend/app/routers/self_improvement.py",
        # ECHO Supervised Maintenance Workspace v1 — self-protecting, same
        # principle as this file protecting itself: the workflow can never
        # modify its own governance/containment code, including the
        # analysis-focused workspace layered on top of it. See
        # docs/supervised_maintenance/protected_scope.md.
        "backend/app/services/maintenance_code_access.py",
        "backend/app/services/maintenance_analysis.py",
        "backend/app/services/maintenance_policy.py",
        "backend/app/routers/supervised_maintenance.py",
        "docs/supervised_maintenance/protected_scope.md",
        "docs/supervised_maintenance/policy.md",
    }
)

# Default-deny scope. A path must be inside one of these discovered repository
# areas (or be an explicitly reviewed dependency manifest below) *and* avoid
# every protected-path/symbol rule. This is intentionally narrower than "any
# file not on the denylist".
ALLOWED_PATH_PREFIXES = (
    "backend/app/providers/",
    "backend/app/routers/",
    "backend/app/services/",
    "backend/tests/",
    "frontend/src/",
    "docs/",
)

DEPENDENCY_PATHS = frozenset(
    {
        "backend/requirements.txt",
        "frontend/package.json",
        "frontend/package-lock.json",
    }
)

# Application symbols whose definitions/checks cannot be introduced, replaced,
# or weakened indirectly from an otherwise-allowed application file. Tests and
# documentation may name them without being blocked.
PROTECTED_SYMBOL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Value Invariants", re.compile(r"\bVALUE_INVARIANTS\b")),
    ("core constitutional values", re.compile(r"\bCORE_VALUES\b")),
    ("Guardian Council invariant guard", re.compile(r"\bguard_amendment_text\b")),
    ("permission evaluator", re.compile(r"\bpermission_center\s*\.\s*check\b|\bdef\s+check\s*\(")),
    ("self-modification patch hashing", re.compile(r"\bcompute_patch_hash\b")),
    ("self-modification approval verification", re.compile(r"\bapprove_revision\b|\bHumanApproval\b")),
    ("self-modification kill switch", re.compile(r"\bSelfModificationKillSwitch\b|\b_check_kill_switch\b")),
    ("secret redaction", re.compile(r"\b(?:redact|redaction|_clean_error)\b", re.IGNORECASE)),
    # ECHO Supervised Maintenance Workspace v1 additions — see
    # docs/supervised_maintenance/protected_scope.md §3.
    ("scope validator", re.compile(r"\bclassify_scope\b|\b_is_unsafe_path\b|\b_canonical_path\b")),
    ("constitutional compliance service", re.compile(r"\brun_compliance_check\b")),
    ("maintenance policy loader", re.compile(r"\bApprovedRepository\b|\bMaintenancePolicyService\b|\bcapability_mode\b")),
    (
        "code access containment",
        re.compile(r"\bdef\s+(?:list_repository_files|read_repository_file|search_repository_text|locate_symbol)\s*\("),
    ),
    ("audit append", re.compile(r"\b_record_audit_event\b|\bSelfModificationAuditEvent\b|\bMaintenanceAuditEvent\b")),
)

#: Path prefixes that are always protected regardless of exact filename —
#: secrets, CI/deployment config, and dev/ops scripts (the backup/restore
#: scripts are the closest thing this repo has to a rollback mechanism
#: today; self-modification must never be able to alter them).
PROTECTED_PATH_PREFIXES = (
    ".env",
    "scripts/",
    ".github/",
    ".git/",
    "docker-compose",
    "backend/Dockerfile",
    "frontend/Dockerfile",
    ".self_mod_sandboxes/",
)

#: Prefixes considered "core application code" — touching these puts a
#: proposal at least at MODERATE, scaling to HIGH for large diffs.
_CORE_PREFIXES = (
    "backend/app/services/",
    "backend/app/routers/",
    "backend/app/providers/",
    "backend/app/core/",
)

#: Prefixes considered inherently low-risk to modify (tests, frontend UI,
#: docs) — never protected, never escalated past LOW on path grounds alone.
_LOW_RISK_PREFIXES = ("backend/tests/", "frontend/", "docs/")

_HIGH_RISK_FILE_COUNT_THRESHOLD = 6
_MAX_PATCH_BYTES = 512_000

_DIFF_GIT_RE = re.compile(r"^diff --git a/(?P<a>.+?) b/(?P<b>.+)$", re.MULTILINE)
_PLUS_PLUS_RE = re.compile(r"^\+\+\+ (?:b/)?(?P<path>.+)$", re.MULTILINE)
_SYMLINK_RE = re.compile(r"^(?:new|deleted) file mode 120000", re.MULTILINE)
_BINARY_PATCH_RE = re.compile(r"^(?:GIT binary patch|Binary files .+ differ)$", re.MULTILINE)
_TEST_WEAKENING_RE = re.compile(
    r"^(?:-.*(?:assert|pytest\.raises|expect\()|\+.*(?:pytest\.mark\.skip|pytest\.skip\(|\.skip\())",
    re.MULTILINE,
)
_LIKELY_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|password)\b"
        r"\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{12,}"
    ),
)

_REQUIRED_RATIONALE_SECTIONS = (
    "problem",
    "evidence",
    "assumptions",
    "proposed change",
    "risk",
    "rollback",
    "test plan",
)


def compute_patch_hash(patch_text: str) -> str:
    return hashlib.sha256(patch_text.encode("utf-8")).hexdigest()


def scope_policy_fingerprint() -> str:
    material = "\n".join(
        sorted(PROTECTED_PATHS)
        + sorted(PROTECTED_PATH_PREFIXES)
        + sorted(ALLOWED_PATH_PREFIXES)
        + sorted(DEPENDENCY_PATHS)
        + sorted(name for name, _pattern in PROTECTED_SYMBOL_PATTERNS)
    )
    return compute_patch_hash(material)


def constitution_fingerprint() -> str:
    return compute_patch_hash(constitution.base_full_text())


def _added_patch_text(patch_text: str) -> str:
    return "\n".join(
        line[1:]
        for line in patch_text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


def _added_application_text(patch_text: str) -> str:
    current_path: str | None = None
    added: list[str] = []
    for line in patch_text.splitlines():
        header = _DIFF_GIT_RE.match(line)
        if header:
            current_path = _canonical_path(header.group("b"))
            continue
        if current_path is None or current_path.startswith(("backend/tests/", "docs/")):
            continue
        if line.startswith("+") and not line.startswith("+++"):
            added.append(line[1:])
    return "\n".join(added)


def contains_likely_secret(patch_text: str) -> bool:
    added = _added_patch_text(patch_text)
    return any(pattern.search(added) for pattern in _LIKELY_SECRET_PATTERNS)


def validate_engineering_rationale(rationale: str) -> None:
    normalized = rationale.casefold()
    missing = [section for section in _REQUIRED_RATIONALE_SECTIONS if f"{section}:" not in normalized]
    if missing:
        raise SelfModScopeError(
            "Engineering rationale is incomplete. Add these labelled sections: " + ", ".join(missing) + "."
        )


def _canonical_path(path: str) -> str:
    # Git paths are POSIX-style. Backslashes are normalized before checking so
    # Windows case-insensitivity and separator tricks cannot bypass policy.
    candidate = path.strip().strip('"').replace("\\", "/")
    return str(PurePosixPath(candidate)).casefold()


def _parse_changed_paths(patch_text: str) -> list[str]:
    """Parses `diff --git a/X b/Y` headers (preferred) or falls back to
    `+++ b/Y` lines. Returns normalized (a/, b/ prefixes stripped) paths."""
    paths: set[str] = set()
    for match in _DIFF_GIT_RE.finditer(patch_text):
        paths.add(match.group("a"))
        paths.add(match.group("b"))
    if not paths:
        for match in _PLUS_PLUS_RE.finditer(patch_text):
            candidate = match.group("path").strip()
            if candidate and candidate != "/dev/null":
                paths.add(candidate)
    paths.discard("/dev/null")
    normalized = {p[2:] if p.startswith(("a/", "b/")) else p for p in paths}
    return sorted(normalized)


def _is_unsafe_path(path: str) -> bool:
    """Absolute paths, Windows drive letters, and '..' traversal segments
    are always unsafe regardless of the allow/deny list — a patch touching
    one of these is rejected outright, not merely escalated."""
    if not path:
        return True
    if "\x00" in path or path.startswith("/") or path.startswith("\\"):
        return True
    if re.match(r"^[A-Za-z]:", path):
        return True
    return ".." in path.replace("\\", "/").split("/")


@dataclass(frozen=True)
class ScopeResult:
    risk_level: str
    hard_blocked: bool
    touches_protected_paths: bool
    touches_protected_symbols: bool
    affected_subsystems: list[str]
    notes: str


def classify_scope(changed_paths: list[str], patch_text: str) -> ScopeResult:
    """Deterministic, no-model-call classification — the same design
    philosophy as constitution.classify_amendment_text(): keyword/path and
    added-line symbol rules, not model inference."""
    if not changed_paths:
        return ScopeResult(
            "critical", True, False, False, [],
            "No changed paths could be parsed from the patch — rejected as unsafe/ambiguous.",
        )

    canonical_paths = {_canonical_path(p): p for p in changed_paths}
    unsafe = [p for p in changed_paths if _is_unsafe_path(p)]
    symlink = bool(_SYMLINK_RE.search(patch_text))
    binary = bool(_BINARY_PATCH_RE.search(patch_text))
    protected_exact = {p.casefold() for p in PROTECTED_PATHS}
    protected_prefixes = tuple(p.casefold() for p in PROTECTED_PATH_PREFIXES)
    exact_hits = [original for canonical, original in canonical_paths.items() if canonical in protected_exact]
    prefix_hits = [
        original
        for canonical, original in canonical_paths.items()
        if any(canonical.startswith(prefix) for prefix in protected_prefixes)
    ]
    protected_hits = sorted(set(exact_hits) | set(prefix_hits))

    allowed_prefixes = tuple(p.casefold() for p in ALLOWED_PATH_PREFIXES)
    allowed_exact = {p.casefold() for p in DEPENDENCY_PATHS}
    unlisted = [
        original
        for canonical, original in canonical_paths.items()
        if canonical not in allowed_exact and not any(canonical.startswith(prefix) for prefix in allowed_prefixes)
    ]

    application_added_text = _added_application_text(patch_text)
    symbol_hits = [name for name, pattern in PROTECTED_SYMBOL_PATTERNS if pattern.search(application_added_text)]

    if unsafe or symlink or binary or protected_hits or unlisted or symbol_hits:
        reasons = []
        if unsafe:
            reasons.append(f"unsafe path(s) (absolute, drive letter, or '..' traversal): {', '.join(sorted(set(unsafe)))}")
        if symlink:
            reasons.append("patch creates or deletes a symlink")
        if binary:
            reasons.append("binary patches are not permitted by the default scope policy")
        if protected_hits:
            reasons.append(f"touches protected path(s): {', '.join(protected_hits)}")
        if unlisted:
            reasons.append(f"path(s) are outside the explicit allowlist: {', '.join(sorted(unlisted))}")
        if symbol_hits:
            reasons.append(f"touches protected symbol(s): {', '.join(sorted(symbol_hits))}")
        return ScopeResult(
            "critical", True, bool(protected_hits), bool(symbol_hits), sorted(set(changed_paths)), "; ".join(reasons),
        )

    subsystems = sorted(
        {p.split("/")[2] if p.startswith("backend/app/") and len(p.split("/")) > 2 else p.split("/")[0] for p in changed_paths}
    )
    touches_core = any(_canonical_path(p).startswith(_CORE_PREFIXES) for p in changed_paths)
    only_low_risk = all(_canonical_path(p).startswith(_LOW_RISK_PREFIXES) or p.endswith(".md") for p in changed_paths)
    dependency_change = any(_canonical_path(p) in allowed_exact for p in changed_paths)
    test_weakening = bool(_TEST_WEAKENING_RE.search(patch_text))

    if dependency_change or test_weakening:
        risk = "high"
    elif touches_core and len(changed_paths) > _HIGH_RISK_FILE_COUNT_THRESHOLD:
        risk = "high"
    elif touches_core:
        risk = "moderate"
    elif only_low_risk:
        risk = "low"
    else:
        risk = "moderate"

    cautions = []
    if dependency_change:
        cautions.append("dependency manifest changed; network installation is not permitted in the sandbox")
    if test_weakening:
        cautions.append("possible test weakening detected (removed assertion/raises check or added skip)")
    suffix = f" Caution: {'; '.join(cautions)}." if cautions else ""
    return ScopeResult(
        risk, False, False, False, subsystems,
        f"{len(changed_paths)} allowlisted path(s) changed; no protected paths or symbols touched.{suffix}",
    )


# --- Lookups ---
def _require_proposal(db: Session, proposal_id: str) -> CodeModificationProposal:
    proposal = db.get(CodeModificationProposal, proposal_id)
    if proposal is None:
        raise SelfModNotFoundError(f"Proposal '{proposal_id}' not found.")
    return proposal


def _require_revision(db: Session, revision_id: str) -> CodeModificationRevision:
    revision = db.get(CodeModificationRevision, revision_id)
    if revision is None:
        raise SelfModNotFoundError(f"Revision '{revision_id}' not found.")
    return revision


def _require_active_revision(db: Session, proposal: CodeModificationProposal) -> CodeModificationRevision:
    if proposal.active_revision_id is None:
        raise SelfModStateError("Proposal has no submitted revision yet.")
    return _require_revision(db, proposal.active_revision_id)


def _require_revision_is_active(
    db: Session, revision: CodeModificationRevision
) -> CodeModificationProposal:
    proposal = _require_proposal(db, revision.proposal_id)
    if proposal.active_revision_id != revision.id:
        raise SelfModStateError(
            "That revision is stale. Checks may only run against the proposal's active revision."
        )
    return proposal


def _latest_approval(db: Session, revision_id: str) -> HumanApproval | None:
    return (
        db.query(HumanApproval)
        .filter(HumanApproval.revision_id == revision_id)
        .order_by(HumanApproval.created_at.desc())
        .first()
    )


def _latest_deployment(db: Session, proposal_id: str) -> DeploymentAttempt | None:
    revision_ids = [
        r.id for r in db.query(CodeModificationRevision).filter(CodeModificationRevision.proposal_id == proposal_id).all()
    ]
    if not revision_ids:
        return None
    return (
        db.query(DeploymentAttempt)
        .filter(DeploymentAttempt.revision_id.in_(revision_ids))
        .order_by(DeploymentAttempt.created_at.desc())
        .first()
    )


def _latest_sandbox(db: Session, revision_id: str) -> SandboxExecution | None:
    return (
        db.query(SandboxExecution)
        .filter(SandboxExecution.revision_id == revision_id)
        .order_by(SandboxExecution.created_at.desc())
        .first()
    )


def _record_audit_event(
    db: Session,
    *,
    proposal_id: str | None,
    revision_id: str | None,
    event_type: str,
    actor_role: str | None,
    summary: str,
    safe_context: dict | None = None,
) -> None:
    event = SelfModificationAuditEvent(
        proposal_id=proposal_id,
        revision_id=revision_id,
        event_type=event_type,
        actor_role=actor_role or "system",
        summary=summary,
        safe_context_json=safe_context or {},
    )
    db.add(event)
    db.commit()
    log_event(logger, f"self_modification.{event_type}")
    metrics.increment("self_mod_event_total", event_type=event_type)


def _require_audit_available(db: Session) -> None:
    """Fail before mutation if the subsystem audit store is unavailable.

    SQLite and the lifecycle rows share one database, so a successful query
    establishes the same local persistence boundary used by the operation.
    Individual event writes remain ordinary database transactions; this check
    prevents intentionally bypassing a broken/missing audit table.
    """
    try:
        db.query(SelfModificationAuditEvent.id).limit(1).all()
    except Exception as exc:  # noqa: BLE001 - normalize backend failures
        db.rollback()
        raise SelfModAuditError("Self-modification audit storage is unavailable; operation blocked.") from exc


# --- Kill switch ---
def _get_or_create_kill_switch(db: Session) -> SelfModificationKillSwitch:
    row = db.get(SelfModificationKillSwitch, "singleton")
    if row is None:
        row = SelfModificationKillSwitch(id="singleton", active=False)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def is_kill_switch_active(db: Session) -> bool:
    row = db.get(SelfModificationKillSwitch, "singleton")
    return bool(row and row.active)


def activate_kill_switch(db: Session, *, activated_by: str, reason: str) -> SelfModificationKillSwitch:
    _require_audit_available(db)
    if activated_by not in _HUMAN_APPROVER_ROLES:
        raise SelfModPermissionError("Only an allowed human governance role may activate the kill switch.")
    if not reason.strip():
        raise SelfModScopeError("A kill-switch activation reason is required.")
    permission = permission_center.check(db, "self_modification_kill_switch")
    if not permission.allowed:
        raise SelfModPermissionError(permission.reason)
    row = _get_or_create_kill_switch(db)
    if row.active:
        return row
    row.active = True
    row.activated_at = _now()
    row.activated_by = activated_by
    row.reason = reason
    db.commit()
    db.refresh(row)
    _record_audit_event(
        db, proposal_id=None, revision_id=None, event_type="kill_switch_activated",
        actor_role=activated_by, summary=reason,
    )
    return row


def reset_kill_switch(db: Session, *, reset_by: str, reason: str) -> SelfModificationKillSwitch:
    _require_audit_available(db)
    if reset_by != "founder":
        raise SelfModPermissionError("Only the Founder role may reset the kill switch.")
    if not reason.strip():
        raise SelfModScopeError("A kill-switch reset reason is required.")
    permission = permission_center.check(db, "self_modification_kill_switch")
    if not permission.allowed:
        raise SelfModPermissionError(permission.reason)
    row = _get_or_create_kill_switch(db)
    if not row.active:
        return row
    row.active = False
    row.reset_at = _now()
    row.reset_by = reset_by
    db.commit()
    db.refresh(row)
    _record_audit_event(
        db, proposal_id=None, revision_id=None, event_type="kill_switch_reset",
        actor_role=reset_by, summary=f"Kill switch reset — {reason.strip()}",
    )
    return row


def _check_kill_switch(db: Session) -> None:
    if is_kill_switch_active(db):
        raise SelfModKillSwitchError(
            "The self-modification kill switch is active. New sandbox runs, approvals, and "
            "deployments are blocked until it is explicitly reset."
        )


# --- Seeding ---
def ensure_defaults(db: Session) -> None:
    """Idempotent — called both at real startup (db.py) and directly by
    tests. Seeds the new permission_center keys (already declared in
    DEFAULT_PERMISSIONS) and the kill-switch singleton row."""
    permission_center.ensure_defaults(db)
    _get_or_create_kill_switch(db)


# --- Proposal lifecycle ---
def create_proposal(
    db: Session, *, title: str, description: str, rationale: str, proposed_by: str = "echo"
) -> CodeModificationProposal:
    _require_audit_available(db)
    permission = permission_center.check(db, "self_modification_propose")
    if not permission.allowed:
        raise SelfModPermissionError(permission.reason)
    title = title.strip()
    description = description.strip()
    rationale = rationale.strip()
    if not title or not description:
        raise SelfModScopeError("Proposal title and description are required.")
    validate_engineering_rationale(rationale)
    if proposed_by not in _HUMAN_APPROVER_ROLES | {"echo"}:
        raise SelfModPermissionError("proposed_by must be 'echo' or an allowed simulated human role.")
    proposal = CodeModificationProposal(
        title=title, description=description, rationale=rationale,
        proposed_by=proposed_by, status="draft", risk_level="low",
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    _record_audit_event(
        db, proposal_id=proposal.id, revision_id=None, event_type="proposal_created",
        actor_role=proposed_by, summary=f"Proposal '{title}' created.",
    )
    return proposal


def submit_revision(db: Session, proposal_id: str, *, patch_text: str) -> CodeModificationRevision:
    _require_audit_available(db)
    permission = permission_center.check(db, "self_modification_propose")
    if not permission.allowed:
        raise SelfModPermissionError(permission.reason)
    proposal = _require_proposal(db, proposal_id)
    if proposal.status in _TERMINAL_STATUSES:
        raise SelfModStateError(f"Proposal is '{proposal.status}' and cannot accept new revisions.")

    if not patch_text.strip():
        raise SelfModScopeError("Patch text is required.")
    if len(patch_text.encode("utf-8")) > _MAX_PATCH_BYTES:
        raise SelfModScopeError(f"Patch exceeds the {_MAX_PATCH_BYTES}-byte review limit.")
    if contains_likely_secret(patch_text):
        raise SelfModScopeError(
            "The patch contains a likely credential or private key. Remove and rotate it before resubmitting."
        )

    revision_number = (
        db.query(CodeModificationRevision).filter(CodeModificationRevision.proposal_id == proposal.id).count() + 1
    )
    revision = CodeModificationRevision(
        proposal_id=proposal.id,
        revision_number=revision_number,
        patch_text=patch_text,
        patch_hash=compute_patch_hash(patch_text),
        changed_paths=_parse_changed_paths(patch_text),
    )
    db.add(revision)
    db.commit()
    db.refresh(revision)

    # A new revision invalidates any prior progress — any earlier approval
    # is bound to the old revision_id/patch_hash and will fail the deploy
    # gate's exact-match check even if never explicitly revoked.
    proposal.active_revision_id = revision.id
    proposal.status = "draft"
    db.commit()

    _record_audit_event(
        db, proposal_id=proposal.id, revision_id=revision.id, event_type="revision_submitted",
        actor_role=proposal.proposed_by,
        summary=f"Revision {revision_number} submitted.",
        safe_context={"revision_number": revision_number, "patch_hash": revision.patch_hash, "changed_paths": revision.changed_paths},
    )
    return revision


def run_scope_check(db: Session, revision_id: str) -> CodeModificationRevision:
    _require_audit_available(db)
    revision = _require_revision(db, revision_id)
    proposal = _require_revision_is_active(db, revision)

    result = classify_scope(revision.changed_paths, revision.patch_text)
    revision.scope_check_status = "failed" if result.hard_blocked else "passed"
    revision.scope_check_notes = result.notes
    db.commit()

    assessment = ModificationImpactAssessment(
        revision_id=revision.id,
        summary=result.notes,
        affected_subsystems=result.affected_subsystems,
        risk_level=result.risk_level,
        touches_protected_paths=result.touches_protected_paths,
        touches_protected_symbols=result.touches_protected_symbols,
    )
    db.add(assessment)

    proposal.risk_level = result.risk_level
    proposal.status = "scope_check_failed" if revision.scope_check_status == "failed" else "draft"
    db.commit()

    _record_audit_event(
        db, proposal_id=proposal.id, revision_id=revision.id, event_type="scope_check_completed",
        actor_role="system",
        summary=result.notes,
        safe_context={"risk_level": result.risk_level, "status": revision.scope_check_status},
    )
    return revision


def run_compliance_check(db: Session, revision_id: str) -> CodeModificationRevision:
    """Reuses constitution.classify_amendment_text() unmodified against the
    proposal's rationale+description (prose-level check), plus a structural
    escalation: any changed path already in PROTECTED_PATHS forces
    'blocked' even if the prose reads as clean — defense in depth, since
    the scope check alone already routes such proposals to
    scope_check_failed before this ever runs in the normal flow."""
    _require_audit_available(db)
    revision = _require_revision(db, revision_id)
    proposal = _require_revision_is_active(db, revision)
    if revision.scope_check_status != "passed":
        raise SelfModStateError("Run the scope check first (must pass before the compliance check).")

    # Only added patch lines are included: a safe change that removes unsafe
    # language must not be blocked merely because the removed line appears in
    # the unified diff.
    text = f"{proposal.rationale}\n\n{proposal.description}\n\n{_added_patch_text(revision.patch_text)}"
    review = constitution.classify_amendment_text(text)
    structurally_blocked = any(p in PROTECTED_PATHS for p in revision.changed_paths)

    if structurally_blocked:
        status = "blocked"
        reasons = list(review.reasons) + [
            "Patch touches a protected governance file; redirect to the Guardian Council "
            "amendment process (POST /api/amendments) rather than this workflow."
        ]
        implicated = list(review.implicated_invariants)
    else:
        status = review.status
        reasons = list(review.reasons)
        implicated = list(review.implicated_invariants)

    check = ConstitutionalComplianceCheck(
        revision_id=revision.id, status=status, implicated_invariants=implicated, reasons=reasons,
    )
    db.add(check)

    mapped = {"allowed": "passed", "blocked": "failed", "needs_human_review": "needs_human_review"}[status]
    revision.compliance_check_status = mapped
    revision.compliance_check_notes = "; ".join(reasons) if reasons else "No constitutional concerns detected."
    if mapped == "failed":
        proposal.status = "compliance_check_failed"
    elif mapped == "needs_human_review" and proposal.risk_level in ("low", "moderate"):
        # Surface the elevated concern in the proposal's own risk_level so
        # it isn't buried in a sub-row a reviewer might not open.
        proposal.risk_level = "high"
    db.commit()

    _record_audit_event(
        db, proposal_id=proposal.id, revision_id=revision.id, event_type="compliance_check_completed",
        actor_role="system", summary=revision.compliance_check_notes,
        safe_context={"status": status, "implicated_invariants": implicated},
    )
    return revision


def mark_ready_for_sandbox(db: Session, proposal_id: str) -> CodeModificationProposal:
    _require_audit_available(db)
    _check_kill_switch(db)
    proposal = _require_proposal(db, proposal_id)
    revision = _require_active_revision(db, proposal)

    if proposal.risk_level == "critical":
        raise SelfModScopeError(
            "CRITICAL-risk proposals are blocked from this workflow entirely. Redirect to the "
            "Guardian Council amendment process or a manual out-of-band review."
        )
    if revision.scope_check_status != "passed":
        raise SelfModStateError("Scope check must pass before moving to sandbox.")
    if revision.compliance_check_status not in ("passed", "needs_human_review"):
        raise SelfModStateError("Constitutional compliance check must pass (or be flagged for human review) first.")

    proposal.status = "ready_for_sandbox"
    db.commit()
    _record_audit_event(
        db, proposal_id=proposal.id, revision_id=revision.id, event_type="marked_ready_for_sandbox",
        actor_role=proposal.proposed_by, summary="Proposal cleared scope and compliance checks.",
    )
    return proposal


def run_sandbox(db: Session, proposal_id: str, *, confirmed: bool = False) -> SandboxExecution:
    _require_audit_available(db)
    settings = get_settings()
    if not settings.supervised_self_modification_enabled:
        raise SelfModFeatureDisabledError(
            "Supervised self-modification is disabled (SUPERVISED_SELF_MODIFICATION_ENABLED=false)."
        )
    if not settings.self_modification_sandbox_enabled:
        raise SelfModFeatureDisabledError(
            "Sandbox execution is disabled (SELF_MODIFICATION_SANDBOX_ENABLED=false)."
        )
    _check_kill_switch(db)

    permission = permission_center.check(db, "self_modification_sandbox_run")
    if not permission.allowed:
        raise SelfModPermissionError(permission.reason)
    if not confirmed:
        raise SelfModPermissionError("Explicit human confirmation is required before sandbox execution.")

    proposal = _require_proposal(db, proposal_id)
    if proposal.status != "ready_for_sandbox":
        raise SelfModStateError(f"Proposal must be 'ready_for_sandbox' (currently '{proposal.status}').")
    revision = _require_active_revision(db, proposal)

    proposal.status = "sandbox_running"
    db.commit()
    execution = SandboxExecution(
        revision_id=revision.id,
        status="running",
        started_at=_now(),
        sandbox_type="docker_worktree",
        runner_image=settings.self_modification_sandbox_image,
        network_disabled=False,
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)

    try:
        result = sandbox.run_patch_in_sandbox(
            revision.patch_text,
            revision.patch_hash,
            proposal.base_commit,
            changed_paths=revision.changed_paths,
            runner_image=settings.self_modification_sandbox_image,
        )
    except sandbox.SandboxError as exc:
        execution.status = "error"
        execution.completed_at = _now()
        execution.summary = action_system._clean_error(exc)
        proposal.status = "sandbox_failed"
        db.commit()
        _record_audit_event(
            db, proposal_id=proposal.id, revision_id=revision.id, event_type="sandbox_error",
            actor_role="system", summary=execution.summary,
        )
        raise

    execution.status = "passed" if result.passed else "failed"
    execution.workspace_path = result.workspace_path
    execution.network_disabled = result.network_disabled
    execution.completed_at = _now()
    execution.summary = result.summary
    if proposal.base_commit is None:
        proposal.base_commit = result.base_commit
    db.commit()

    verification = VerificationRun(
        sandbox_execution_id=execution.id,
        checks_json=result.checks,
        status="passed" if result.passed else "failed",
        summary=result.summary,
    )
    db.add(verification)
    proposal.status = "sandbox_passed" if result.passed else "sandbox_failed"
    db.commit()

    _record_audit_event(
        db, proposal_id=proposal.id, revision_id=revision.id, event_type="sandbox_completed",
        actor_role="system", summary=result.summary,
        safe_context={"status": execution.status},
    )
    return execution


def request_review(db: Session, proposal_id: str) -> CodeModificationProposal:
    _require_audit_available(db)
    proposal = _require_proposal(db, proposal_id)
    if proposal.status != "sandbox_passed":
        raise SelfModStateError("Sandbox verification must pass before requesting human review.")
    proposal.status = "awaiting_human_review"
    db.commit()
    _record_audit_event(
        db, proposal_id=proposal.id, revision_id=proposal.active_revision_id,
        event_type="review_requested", actor_role=proposal.proposed_by,
        summary="Proposal moved to awaiting_human_review.",
    )
    return proposal


def approve_revision(
    db: Session,
    proposal_id: str,
    *,
    approver_role: str,
    decision: str,
    test_evidence_summary: str = "",
    acknowledgement_text: str | None = None,
) -> HumanApproval:
    """Record an explicit simulated-human decision bound to the exact patch.

    The app has no authentication, so this is not represented as independent
    human identity. The server still rejects model roles, proposer self-review,
    stale evidence, and ambiguous approval wording. High-risk deployment stays
    blocked entirely elsewhere until authenticated dual approval exists.
    """
    _require_audit_available(db)
    settings = get_settings()
    if not settings.supervised_self_modification_enabled:
        raise SelfModFeatureDisabledError(
            "Approval is disabled (SUPERVISED_SELF_MODIFICATION_ENABLED=false)."
        )
    _check_kill_switch(db)
    proposal = _require_proposal(db, proposal_id)
    if proposal.status != "awaiting_human_review":
        raise SelfModStateError(f"Proposal must be 'awaiting_human_review' (currently '{proposal.status}').")
    revision = _require_active_revision(db, proposal)

    if approver_role not in _HUMAN_APPROVER_ROLES:
        raise SelfModPermissionError("Only an allowed human governance role may approve or reject a revision.")
    if proposal.proposed_by == approver_role:
        raise SelfModApprovalError("The proposal author cannot approve their own revision.")

    permission = permission_center.check(db, "self_modification_approve")
    if not permission.allowed:
        raise SelfModPermissionError(permission.reason)

    if decision == "approved":
        expected = f"APPROVE EXACT PATCH {revision.patch_hash}"
        if acknowledgement_text != expected:
            raise SelfModApprovalError(
                f"Approval of this exact {proposal.risk_level}-risk revision requires typing the "
                f"confirmation phrase: '{expected}'."
            )

    expiry_hours = get_settings().self_modification_approval_expiry_hours
    approval = HumanApproval(
        revision_id=revision.id,
        approver_role=approver_role,
        decision=decision,
        patch_hash_at_approval=revision.patch_hash,
        base_commit_at_approval=proposal.base_commit,
        scope_at_approval=revision.changed_paths,
        target_at_approval=proposal.target_branch,
        policy_fingerprint_at_approval=scope_policy_fingerprint(),
        constitution_fingerprint_at_approval=constitution_fingerprint(),
        test_evidence_summary=test_evidence_summary,
        acknowledgement_text=acknowledgement_text,
        expires_at=_now() + timedelta(hours=expiry_hours),
    )
    db.add(approval)
    db.commit()
    db.refresh(approval)

    proposal.status = "approved" if decision == "approved" else "rejected"
    if decision == "rejected":
        proposal.closed_reason = test_evidence_summary or "Rejected by human reviewer."
    db.commit()

    _record_audit_event(
        db, proposal_id=proposal.id, revision_id=revision.id, event_type=f"approval_{decision}",
        actor_role=approver_role, summary=test_evidence_summary or f"Revision {decision} by {approver_role}.",
        safe_context={"patch_hash": revision.patch_hash, "expires_at": approval.expires_at.isoformat()},
    )
    return approval


def deploy(db: Session, proposal_id: str, *, confirmed: bool = False) -> DeploymentAttempt:
    """Deployment gate — fails closed on any of: feature flags off, kill
    switch active, permission denied, wrong proposal status, missing/
    mismatched/expired approval. 'Deploy' always means committing to a
    fresh isolated worktree/branch (see self_modification_sandbox.py) —
    production deployment has no code path here at all."""
    _require_audit_available(db)
    settings = get_settings()
    if not settings.supervised_self_modification_enabled:
        raise SelfModFeatureDisabledError(
            "Supervised self-modification is disabled (SUPERVISED_SELF_MODIFICATION_ENABLED=false)."
        )
    if not settings.self_modification_deployment_enabled:
        raise SelfModFeatureDisabledError(
            "Deployment is disabled by default (SELF_MODIFICATION_DEPLOYMENT_ENABLED=false). "
            "Production deployment is out of scope for this milestone entirely."
        )
    _check_kill_switch(db)

    permission = permission_center.check(db, "self_modification_deploy")
    if not permission.allowed:
        raise SelfModPermissionError(permission.reason)
    if not confirmed:
        raise SelfModPermissionError("Explicit human confirmation is required before local-branch deployment.")

    proposal = _require_proposal(db, proposal_id)
    if proposal.status != "approved":
        raise SelfModStateError(f"Proposal must be 'approved' (currently '{proposal.status}').")
    revision = _require_active_revision(db, proposal)

    if proposal.risk_level in ("high", "critical"):
        raise SelfModApprovalError(
            "High-risk deployment is disabled because Echo has no authenticated second-human approval boundary."
        )

    approval = _latest_approval(db, revision.id)
    if approval is None or approval.decision != "approved":
        raise SelfModApprovalError("No valid approval found for the active revision.")
    if approval.patch_hash_at_approval != revision.patch_hash:
        raise SelfModApprovalError(
            "Approval no longer matches the active revision's patch hash — a new revision was "
            "submitted after approval. Re-approve before deploying."
        )
    if _now() > _as_utc(approval.expires_at):
        proposal.status = "approval_expired"
        db.commit()
        raise SelfModApprovalError("Approval has expired. Re-approve before deploying.")
    if compute_patch_hash(revision.patch_text) != revision.patch_hash:
        raise SelfModApprovalError("Stored patch content no longer matches its revision hash.")
    if approval.base_commit_at_approval != proposal.base_commit:
        raise SelfModApprovalError("Approval no longer matches the sandboxed base commit.")
    if approval.target_at_approval != proposal.target_branch:
        raise SelfModApprovalError("Approval no longer matches the deployment target.")
    if approval.scope_at_approval != revision.changed_paths:
        raise SelfModApprovalError("Approval no longer matches the reviewed file scope.")
    if approval.policy_fingerprint_at_approval != scope_policy_fingerprint():
        raise SelfModApprovalError("The self-modification scope policy changed after approval; re-review is required.")
    if approval.constitution_fingerprint_at_approval != constitution_fingerprint():
        raise SelfModApprovalError("The Constitution changed after approval; re-review is required.")

    scope = classify_scope(revision.changed_paths, revision.patch_text)
    if scope.hard_blocked:
        raise SelfModScopeError("The active patch no longer passes the current protected-scope policy.")
    latest_sandbox = _latest_sandbox(db, revision.id)
    if latest_sandbox is None or latest_sandbox.status != "passed" or not latest_sandbox.network_disabled:
        raise SelfModApprovalError("A successful network-isolated sandbox run is required before deployment.")
    verification = (
        db.query(VerificationRun)
        .filter(VerificationRun.sandbox_execution_id == latest_sandbox.id)
        .order_by(VerificationRun.created_at.desc())
        .first()
    )
    if verification is None or verification.status != "passed":
        raise SelfModApprovalError("Required sandbox verification evidence is missing or failed.")
    try:
        current_base = sandbox.current_head()
    except sandbox.SandboxError as exc:
        raise SelfModApprovalError("The current repository base commit could not be verified.") from exc
    if current_base != proposal.base_commit:
        raise SelfModApprovalError("The base branch moved after sandbox review; create and approve a fresh revision.")
    attempt = DeploymentAttempt(
        revision_id=revision.id, approval_id=approval.id, status="running",
        target=proposal.target_branch, started_at=_now(),
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    proposal.status = "deploying"
    db.commit()

    try:
        result = sandbox.deploy_to_local_branch(
            proposal.id, revision.revision_number, revision.patch_text, revision.patch_hash, proposal.base_commit
        )
    except sandbox.SandboxError as exc:
        attempt.status = "failed"
        attempt.completed_at = _now()
        attempt.notes = action_system._clean_error(exc)
        proposal.status = "post_deployment_failed"
        db.commit()
        _record_audit_event(
            db, proposal_id=proposal.id, revision_id=revision.id, event_type="deployment_failed",
            actor_role="system", summary=attempt.notes,
        )
        raise

    attempt.status = "deployed"
    attempt.branch_name = result.branch_name
    attempt.worktree_path = result.worktree_path
    attempt.completed_at = _now()
    proposal.status = "deployed"
    db.commit()

    _record_audit_event(
        db, proposal_id=proposal.id, revision_id=revision.id, event_type="deployed",
        actor_role="system", summary=f"Deployed to local branch '{result.branch_name}'.",
        safe_context={"branch_name": result.branch_name},
    )
    return attempt


def rollback(db: Session, proposal_id: str, *, reason: str) -> RollbackEvent:
    _require_audit_available(db)
    proposal = _require_proposal(db, proposal_id)
    permission = permission_center.check(db, "self_modification_rollback")
    if not permission.allowed:
        raise SelfModPermissionError(permission.reason)
    if proposal.status == "rolled_back":
        raise SelfModStateError("This proposal has already been rolled back.")
    attempt = _latest_deployment(db, proposal.id)
    if attempt is None or attempt.status != "deployed":
        raise SelfModStateError("No deployed attempt to roll back.")

    event = RollbackEvent(deployment_attempt_id=attempt.id, status="running", reason=reason)
    db.add(event)
    db.commit()
    db.refresh(event)
    proposal.status = "rolling_back"
    db.commit()

    try:
        sandbox.rollback_local_branch(attempt.worktree_path, attempt.branch_name)
    except sandbox.SandboxError as exc:
        event.status = "failed"
        event.completed_at = _now()
        proposal.status = "rollback_required"
        db.commit()
        _record_audit_event(
            db, proposal_id=proposal.id, revision_id=attempt.revision_id, event_type="rollback_failed",
            actor_role="system", summary=action_system._clean_error(exc),
        )
        raise

    event.status = "completed"
    event.restored_reference = proposal.base_commit
    event.completed_at = _now()
    proposal.status = "rolled_back"
    db.commit()

    _record_audit_event(
        db, proposal_id=proposal.id, revision_id=attempt.revision_id, event_type="rolled_back",
        actor_role="system", summary=reason,
    )
    return event


def cancel_proposal(db: Session, proposal_id: str, *, reason: str) -> CodeModificationProposal:
    _require_audit_available(db)
    proposal = _require_proposal(db, proposal_id)
    if proposal.status in ("deployed", "deploying"):
        raise SelfModStateError("Cannot cancel a deployed/deploying proposal — use rollback instead.")
    proposal.status = "cancelled"
    proposal.closed_reason = reason
    db.commit()
    _record_audit_event(
        db, proposal_id=proposal.id, revision_id=proposal.active_revision_id, event_type="proposal_cancelled",
        actor_role=proposal.proposed_by, summary=reason,
    )
    return proposal


def get_health(db: Session) -> dict:
    settings = get_settings()
    capabilities = sandbox.get_sandbox_capabilities(settings.self_modification_sandbox_image)
    return {
        "supervised_self_modification_enabled": settings.supervised_self_modification_enabled,
        "self_modification_sandbox_enabled": settings.self_modification_sandbox_enabled,
        "self_modification_deployment_enabled": settings.self_modification_deployment_enabled,
        "self_modification_frontend_enabled": settings.self_modification_frontend_enabled,
        "kill_switch_active": is_kill_switch_active(db),
        "open_proposal_count": (
            db.query(CodeModificationProposal).filter(CodeModificationProposal.status.notin_(_CLOSED_STATUSES)).count()
        ),
        "awaiting_review_count": (
            db.query(CodeModificationProposal).filter(CodeModificationProposal.status == "awaiting_human_review").count()
        ),
        "sandbox_runner": capabilities["runner"],
        "sandbox_runner_available": capabilities["available"],
        "network_isolation_enforced": capabilities["network_isolation_enforced"],
        "sandbox_image": capabilities["image"],
    }
