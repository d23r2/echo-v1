"""ECHO Layer 3A Part 2B — validated runtime identity boundary.

The Part 2A ``identity_service`` module remains the persistence/repository
boundary.  This module turns those ORM rows into immutable, session-detached
snapshots, coordinates the existing process-local TTL cache, and supplies a
deterministic safe fallback.  Prompt code consumes ``IdentityBrief`` objects
from ``identity_context``; it never queries identity tables directly.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Literal, cast

from sqlalchemy.orm import Session

from app import models, schemas
from app.config import get_settings
from app.core import cache, metrics
from app.core.logging import log_event
from app.services import identity_service

logger = logging.getLogger(__name__)

_CACHE_PREFIX = "identity:active:"
_PRIMARY_PROFILE_KEY = "echo-primary"

# Missing invariant/blocking commitments make the database snapshot unsafe to
# use.  Advisory commitments are warnings: startup remains available and the
# brief can still be built from the verified critical boundary set.
_REQUIRED_COMMITMENT_KEYS = frozenset(
    {
        "honesty-no-fabrication",
        "no-fabricated-certainty",
        "permission-first-action",
        "non-manipulation",
        "no-false-consciousness-claims",
        "reliability-verify-actions",
        "scope-honesty",
        "minimal-internal-disclosure",
    }
)
_RECOMMENDED_COMMITMENT_KEYS = frozenset({"user-autonomy", "privacy-minimization"})
_CLEARLY_CONTRADICTORY_KEYS = frozenset(
    {
        "allow-fabrication",
        "claim-consciousness",
        "no-permission-required",
        "reveal-hidden-reasoning",
    }
)

ValidationStatus = Literal["healthy", "degraded"]


class IdentityRuntimeError(identity_service.IdentityError):
    """Base error for runtime identity failures."""


class IdentityRuntimeLoadError(IdentityRuntimeError):
    pass


class IdentitySnapshotValidationError(IdentityRuntimeError):
    pass


class ConsequentialIdentityUnavailableError(IdentityRuntimeError):
    """Raised by action callers that require a verified dynamic identity."""


@dataclass(frozen=True, slots=True)
class RuntimeIdentityCommitment:
    commitment_key: str
    title: str
    description: str
    category: str
    priority: int
    enforcement_level: str
    user_visible: bool


@dataclass(frozen=True, slots=True)
class RuntimeIdentitySnapshot:
    """Immutable and safe to retain after the SQLAlchemy session closes."""

    profile_id: str
    profile_key: str
    display_name: str
    subtitle: str | None
    public_role: str
    internal_role: str
    persona_summary: str
    capability_summary: str
    limitation_summary: str
    version_number: int
    effective_from: datetime | None
    source: str
    commitments: tuple[RuntimeIdentityCommitment, ...]
    invariant_commitment_keys: tuple[str, ...]
    blocking_commitment_keys: tuple[str, ...]
    advisory_commitment_keys: tuple[str, ...]
    loaded_at: datetime
    fingerprint: str
    fallback_used: bool
    validation_status: ValidationStatus
    validation_warnings: tuple[str, ...]

    def to_serializable(self, *, include_internal_role: bool = False) -> dict:
        """Deterministic test/developer representation, never an ORM graph."""
        data = asdict(self)
        data["loaded_at"] = self.loaded_at.isoformat()
        data["effective_from"] = self.effective_from.isoformat() if self.effective_from else None
        if not include_internal_role:
            data.pop("internal_role", None)
        return data


_refresh_lock = threading.RLock()
_last_valid_snapshots: dict[str, RuntimeIdentitySnapshot] = {}
_runtime_state: dict[str, object] = {
    "status": "not_loaded",
    "cache_status": "empty",
    "last_refresh": None,
    "last_error": None,
    "validation_warnings": (),
}


def _cache_key(profile_key: str) -> str:
    return f"{_CACHE_PREFIX}{profile_key.strip().lower()}"


def _as_aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _stable_fingerprint(
    *,
    profile_key: str,
    version_number: int,
    display_name: str,
    public_role: str,
    persona_summary: str,
    capability_summary: str,
    limitation_summary: str,
    commitments: tuple[RuntimeIdentityCommitment, ...],
) -> str:
    material = {
        "profile_key": profile_key.strip().lower(),
        "version_number": version_number,
        "display_name": display_name.strip(),
        "public_role": public_role.strip(),
        "persona_summary": persona_summary.strip(),
        "capability_summary": capability_summary.strip(),
        "limitation_summary": limitation_summary.strip(),
        "commitments": [
            {
                "key": item.commitment_key,
                "category": item.category,
                "priority": item.priority,
                "enforcement": item.enforcement_level,
                "description": item.description.strip(),
            }
            for item in commitments
        ],
    }
    encoded = json.dumps(material, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _validate_profile_row(profile: models.AssistantIdentityProfile, now: datetime) -> None:
    if profile.status != "active":
        raise IdentitySnapshotValidationError("Selected identity is not active.")
    if profile.version_number < 1:
        raise IdentitySnapshotValidationError("Active identity has an invalid version number.")
    if profile.effective_from is None or _as_aware(profile.effective_from) > now:
        raise IdentitySnapshotValidationError("Active identity is not yet effective.")
    if profile.effective_until is not None and _as_aware(profile.effective_until) <= now:
        raise IdentitySnapshotValidationError("Active identity has expired.")

    for field_name, value, limit in (
        ("profile_key", profile.profile_key, identity_service._MAX_PROFILE_KEY),
        ("display_name", profile.display_name, identity_service._MAX_DISPLAY_NAME),
        ("public_role", profile.public_role, identity_service._MAX_PUBLIC_ROLE),
        ("internal_role", profile.internal_role, identity_service._MAX_INTERNAL_ROLE),
        ("persona_summary", profile.persona_summary, identity_service._MAX_PERSONA_SUMMARY),
        ("capability_summary", profile.capability_summary, identity_service._MAX_CAPABILITY_SUMMARY),
        ("limitation_summary", profile.limitation_summary, identity_service._MAX_LIMITATION_SUMMARY),
    ):
        try:
            identity_service._check_non_empty(value, field_name, limit)
            identity_service._check_no_consciousness_claim(value, field_name)
        except identity_service.IdentityValidationError as exc:
            raise IdentitySnapshotValidationError(str(exc)) from exc
    try:
        identity_service._validate_effective_dates(profile.effective_from, profile.effective_until, "identity")
        identity_service._validate_metadata(profile.metadata_json or {})
    except identity_service.IdentityValidationError as exc:
        raise IdentitySnapshotValidationError(str(exc)) from exc


def _runtime_commitments(
    rows: list[models.IdentityCommitment], now: datetime
) -> tuple[tuple[RuntimeIdentityCommitment, ...], tuple[str, ...]]:
    items: list[RuntimeIdentityCommitment] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if not row.active:
            continue
        if row.effective_from is not None and _as_aware(row.effective_from) > now:
            continue
        if row.effective_until is not None and _as_aware(row.effective_until) <= now:
            continue
        key = row.commitment_key.strip().lower()
        if key in seen:
            raise IdentitySnapshotValidationError(f'Duplicate active commitment key "{key}".')
        if key in _CLEARLY_CONTRADICTORY_KEYS:
            raise IdentitySnapshotValidationError(f'Contradictory active commitment key "{key}".')
        seen.add(key)
        try:
            identity_service._validate_commitment_fields(
                schemas.IdentityCommitmentCreate(
                    commitment_key=row.commitment_key,
                    title=row.title,
                    description=row.description,
                    category=cast(schemas.CommitmentCategory, row.category),
                    priority=row.priority,
                    enforcement_level=cast(schemas.EnforcementLevel, row.enforcement_level),
                    user_visible=row.user_visible,
                    active=row.active,
                    source=cast(schemas.IdentitySource, row.source),
                    effective_from=row.effective_from,
                    effective_until=row.effective_until,
                    metadata=row.metadata_json or {},
                )
            )
            identity_service._validate_metadata(row.metadata_json or {})
        except (identity_service.IdentityValidationError, ValueError) as exc:
            raise IdentitySnapshotValidationError(f'Invalid active commitment "{key}".') from exc
        items.append(
            RuntimeIdentityCommitment(
                commitment_key=key,
                title=row.title.strip(),
                description=row.description.strip(),
                category=row.category,
                priority=row.priority,
                enforcement_level=row.enforcement_level,
                user_visible=row.user_visible,
            )
        )

    items.sort(key=lambda item: (-item.priority, item.category, item.commitment_key))
    missing_required = sorted(_REQUIRED_COMMITMENT_KEYS - seen)
    if missing_required:
        raise IdentitySnapshotValidationError(
            "Active identity is missing required commitments: " + ", ".join(missing_required)
        )
    missing_recommended = sorted(_RECOMMENDED_COMMITMENT_KEYS - seen)
    if missing_recommended:
        warnings.append("Optional advisory commitments absent: " + ", ".join(missing_recommended))
    return tuple(items), tuple(warnings)


def build_runtime_snapshot(
    db: Session, profile_key: str = _PRIMARY_PROFILE_KEY
) -> RuntimeIdentitySnapshot:
    """Load and validate exactly one active identity; never return ORM rows."""
    normalized = profile_key.strip().lower()
    now = datetime.now(UTC)
    active_rows = (
        db.query(models.AssistantIdentityProfile)
        .filter(
            models.AssistantIdentityProfile.profile_key == normalized,
            models.AssistantIdentityProfile.status == "active",
        )
        .all()
    )
    if len(active_rows) != 1:
        raise IdentitySnapshotValidationError(
            f'Expected exactly one active identity for "{normalized}"; found {len(active_rows)}.'
        )
    profile = active_rows[0]
    _validate_profile_row(profile, now)
    commitments, warnings = _runtime_commitments(identity_service.list_commitments(db, profile.id), now)
    fingerprint = _stable_fingerprint(
        profile_key=profile.profile_key,
        version_number=profile.version_number,
        display_name=profile.display_name,
        public_role=profile.public_role,
        persona_summary=profile.persona_summary,
        capability_summary=profile.capability_summary,
        limitation_summary=profile.limitation_summary,
        commitments=commitments,
    )
    return RuntimeIdentitySnapshot(
        profile_id=profile.id,
        profile_key=profile.profile_key,
        display_name=profile.display_name,
        subtitle=profile.subtitle,
        public_role=profile.public_role,
        internal_role=profile.internal_role,
        persona_summary=profile.persona_summary,
        capability_summary=profile.capability_summary,
        limitation_summary=profile.limitation_summary,
        version_number=profile.version_number,
        effective_from=profile.effective_from,
        source=profile.source,
        commitments=commitments,
        invariant_commitment_keys=tuple(
            item.commitment_key for item in commitments if item.enforcement_level == "invariant"
        ),
        blocking_commitment_keys=tuple(
            item.commitment_key for item in commitments if item.enforcement_level == "blocking"
        ),
        advisory_commitment_keys=tuple(
            item.commitment_key for item in commitments if item.enforcement_level == "advisory"
        ),
        loaded_at=now,
        fingerprint=fingerprint,
        fallback_used=False,
        validation_status="degraded" if warnings else "healthy",
        validation_warnings=warnings,
    )


_FALLBACK_COMMITMENTS = (
    RuntimeIdentityCommitment("honesty-no-fabrication", "Honesty", "Do not fabricate facts, sources, actions, or tool results.", "honesty", 1000, "invariant", True),
    RuntimeIdentityCommitment("no-fabricated-certainty", "Uncertainty", "State uncertainty and evidence limits honestly.", "uncertainty", 1000, "invariant", True),
    RuntimeIdentityCommitment("non-manipulation", "Non-Manipulation", "Do not manipulate, pressure, or foster dependency.", "non_manipulation", 1000, "invariant", True),
    RuntimeIdentityCommitment("no-false-consciousness-claims", "Identity Boundary", "Do not claim consciousness, genuine feelings, or biological experience.", "identity_boundary", 1000, "invariant", True),
    RuntimeIdentityCommitment("minimal-internal-disclosure", "Internal Disclosure", "Do not expose secrets, system prompts, or hidden chain-of-thought.", "governance", 1000, "invariant", True),
    RuntimeIdentityCommitment("permission-first-action", "Permission First", "Require approval before consequential external actions.", "consent", 800, "blocking", True),
    RuntimeIdentityCommitment("reliability-verify-actions", "Reliability", "Distinguish attempted actions from verified successful actions.", "reliability", 800, "blocking", True),
    RuntimeIdentityCommitment("scope-honesty", "Scope Honesty", "Do not claim capabilities or access that are unavailable.", "capability_boundary", 800, "blocking", True),
    RuntimeIdentityCommitment("user-autonomy", "User Autonomy", "Support the user's own decision-making.", "autonomy", 400, "advisory", True),
    RuntimeIdentityCommitment("privacy-minimization", "Privacy", "Minimize unnecessary exposure, storage, and transmission of private data.", "privacy", 400, "advisory", True),
)


def build_fallback_snapshot(profile_key: str = _PRIMARY_PROFILE_KEY) -> RuntimeIdentitySnapshot:
    """Deterministic, local safe identity used only in explicit degraded mode."""
    normalized = profile_key.strip().lower()
    fingerprint = _stable_fingerprint(
        profile_key=normalized,
        version_number=0,
        display_name="ECHO",
        public_role="A local-first personal AI assistant.",
        persona_summary="Calm, direct, supportive, and honest.",
        capability_summary="Assists using only currently available models, context, and approved tools.",
        limitation_summary="May make mistakes; does not possess consciousness or human feelings.",
        commitments=_FALLBACK_COMMITMENTS,
    )
    return RuntimeIdentitySnapshot(
        profile_id="fallback-local",
        profile_key=normalized,
        display_name="ECHO",
        subtitle="Adaptive Personal AI",
        public_role="A local-first personal AI assistant.",
        internal_role="Local deterministic fallback identity.",
        persona_summary="Calm, direct, supportive, and honest.",
        capability_summary="Assists using only currently available models, context, and approved tools.",
        limitation_summary="May make mistakes; does not possess consciousness or human feelings.",
        version_number=0,
        effective_from=None,
        source="system_default",
        commitments=_FALLBACK_COMMITMENTS,
        invariant_commitment_keys=tuple(
            item.commitment_key for item in _FALLBACK_COMMITMENTS if item.enforcement_level == "invariant"
        ),
        blocking_commitment_keys=tuple(
            item.commitment_key for item in _FALLBACK_COMMITMENTS if item.enforcement_level == "blocking"
        ),
        advisory_commitment_keys=tuple(
            item.commitment_key for item in _FALLBACK_COMMITMENTS if item.enforcement_level == "advisory"
        ),
        loaded_at=datetime.now(UTC),
        fingerprint=fingerprint,
        fallback_used=True,
        validation_status="degraded",
        validation_warnings=("Dynamic identity unavailable; deterministic local fallback active.",),
    )


def _cache_get(profile_key: str) -> RuntimeIdentitySnapshot | None:
    try:
        value = cache.get(_cache_key(profile_key))
    except Exception:
        metrics.increment("identity_cache_misses_total", outcome="error")
        log_event(logger, "identity.cache_miss", level=logging.WARNING, error_category="cache_error")
        return None
    if value is None:
        metrics.increment("identity_cache_misses_total", outcome="miss")
        log_event(logger, "identity.cache_miss", level=logging.DEBUG)
        return None
    if not isinstance(value, RuntimeIdentitySnapshot):
        cache.invalidate(_cache_key(profile_key))
        metrics.increment("identity_cache_misses_total", outcome="corrupt")
        log_event(logger, "identity.cache_miss", level=logging.WARNING, error_category="cache_corrupt")
        return None
    metrics.increment("identity_cache_hits_total")
    log_event(logger, "identity.cache_hit", level=logging.DEBUG)
    with _refresh_lock:
        _runtime_state["cache_status"] = "hit"
    return value


def _cache_set(profile_key: str, snapshot: RuntimeIdentitySnapshot) -> bool:
    try:
        cache.set(
            _cache_key(profile_key),
            snapshot,
            ttl_seconds=get_settings().core_identity_cache_ttl_seconds,
        )
        return True
    except Exception:
        log_event(logger, "identity.runtime_load_failed", level=logging.WARNING, error_category="cache_error")
        return False


def refresh_active_identity(
    db: Session,
    profile_key: str = _PRIMARY_PROFILE_KEY,
    *,
    reason: str = "manual",
) -> RuntimeIdentitySnapshot | None:
    """Validate first, then atomically replace the runtime cache.

    A failed refresh retains the old immutable snapshot.  If none exists, a
    deterministic fallback is installed so startup and low-risk chat can run
    in an observable degraded state.
    """
    del reason  # Event labels stay low-cardinality; raw caller text is never logged.
    settings = get_settings()
    normalized = profile_key.strip().lower()
    if not settings.core_identity_v1_enabled:
        invalidate_identity_cache(normalized, reason="feature_disabled")
        with _refresh_lock:
            _runtime_state.update(
                status="disabled",
                cache_status="disabled",
                last_refresh=datetime.now(UTC),
                last_error=None,
                validation_warnings=(),
            )
        return None

    with _refresh_lock:
        started = time.monotonic()
        log_event(logger, "identity.runtime_load_started")
        try:
            candidate = build_runtime_snapshot(db, normalized)
        except Exception as exc:
            elapsed = (time.monotonic() - started) * 1000
            metrics.increment("identity_runtime_load_total", outcome="failure")
            metrics.increment("identity_runtime_load_failures_total", category=type(exc).__name__)
            metrics.record_duration("identity_runtime_load_latency", elapsed, outcome="failure")
            log_event(
                logger,
                "identity.runtime_load_failed",
                level=logging.WARNING,
                elapsed_ms=elapsed,
                error_category=type(exc).__name__,
            )
            previous = _last_valid_snapshots.get(normalized)
            if previous is not None:
                _cache_set(normalized, previous)
                _runtime_state.update(
                    status="degraded",
                    cache_status="retained_previous",
                    last_refresh=datetime.now(UTC),
                    last_error=type(exc).__name__,
                    validation_warnings=("Refresh failed; retained previous validated snapshot.",),
                )
                return previous

            fallback = build_fallback_snapshot(normalized)
            _last_valid_snapshots[normalized] = fallback
            _cache_set(normalized, fallback)
            metrics.increment("identity_fallback_total")
            log_event(
                logger,
                "identity.runtime_fallback_activated",
                level=logging.WARNING,
                error_category=type(exc).__name__,
            )
            _runtime_state.update(
                status="degraded",
                cache_status="fallback",
                last_refresh=datetime.now(UTC),
                last_error=type(exc).__name__,
                validation_warnings=fallback.validation_warnings,
            )
            return fallback

        _last_valid_snapshots[normalized] = candidate
        cache_ok = _cache_set(normalized, candidate)
        elapsed = (time.monotonic() - started) * 1000
        metrics.increment("identity_runtime_load_total", outcome="success")
        metrics.increment("identity_refresh_total")
        metrics.record_duration("identity_runtime_load_latency", elapsed, outcome="success")
        log_event(logger, "identity.runtime_load_completed", elapsed_ms=elapsed)
        log_event(logger, "identity.runtime_refreshed", elapsed_ms=elapsed)
        _runtime_state.update(
            status=candidate.validation_status,
            cache_status="populated" if cache_ok else "cache_error",
            last_refresh=candidate.loaded_at,
            last_error=None if cache_ok else "cache_error",
            validation_warnings=candidate.validation_warnings,
        )
        return candidate


def get_active_identity_snapshot(
    db: Session, profile_key: str = _PRIMARY_PROFILE_KEY
) -> RuntimeIdentitySnapshot | None:
    if not get_settings().core_identity_v1_enabled:
        return None
    normalized = profile_key.strip().lower()
    if get_settings().cache_enabled:
        cached = _cache_get(normalized)
        if cached is not None:
            return cached
    return refresh_active_identity(db, normalized, reason="cache_miss")


def invalidate_identity_cache(profile_key: str = _PRIMARY_PROFILE_KEY, *, reason: str = "manual") -> None:
    del reason
    normalized = profile_key.strip().lower()
    try:
        cache.invalidate(_cache_key(normalized))
    except Exception:
        pass
    with _refresh_lock:
        _runtime_state["cache_status"] = "invalidated"
    log_event(logger, "identity.cache_invalidated")


def handle_activation_event(db: Session, profile_key: str) -> RuntimeIdentitySnapshot | None:
    invalidate_identity_cache(profile_key, reason="activation")
    return refresh_active_identity(db, profile_key, reason="activation")


def handle_archive_event(db: Session, profile_key: str) -> RuntimeIdentitySnapshot | None:
    invalidate_identity_cache(profile_key, reason="archive")
    return refresh_active_identity(db, profile_key, reason="archive")


def handle_configuration_reload(profile_key: str = _PRIMARY_PROFILE_KEY) -> None:
    """Explicit hook for the application's future configuration reloader.

    This repository currently has no live reload event; callers that clear
    ``get_settings`` at runtime can invoke this hook before the next request.
    The subsequent cache miss reloads under the current flag/TTL settings.
    """
    invalidate_identity_cache(profile_key, reason="configuration_reload")


def get_active_identity_version(db: Session, profile_key: str = _PRIMARY_PROFILE_KEY) -> int | None:
    snapshot = get_active_identity_snapshot(db, profile_key)
    return snapshot.version_number if snapshot is not None else None


def get_active_commitments(
    db: Session, profile_key: str = _PRIMARY_PROFILE_KEY
) -> tuple[RuntimeIdentityCommitment, ...]:
    snapshot = get_active_identity_snapshot(db, profile_key)
    return snapshot.commitments if snapshot is not None else ()


def require_verified_identity_for_consequential_action(
    snapshot: RuntimeIdentitySnapshot | None,
) -> RuntimeIdentitySnapshot:
    with _refresh_lock:
        runtime_status = _runtime_state.get("status")
    if (
        snapshot is None
        or snapshot.fallback_used
        or snapshot.validation_status != "healthy"
        or runtime_status != "healthy"
    ):
        raise ConsequentialIdentityUnavailableError(
            "A verified runtime identity is required before a consequential action can proceed."
        )
    return snapshot


def get_safe_identity_diagnostics(*, detailed: bool = False) -> dict:
    settings = get_settings()
    if not settings.core_identity_v1_enabled:
        return {"enabled": False, "status": "disabled", "cache_status": "disabled", "fallback_used": False}
    with _refresh_lock:
        snapshot = _last_valid_snapshots.get(_PRIMARY_PROFILE_KEY)
        state = dict(_runtime_state)
    last_refresh = state.get("last_refresh")
    state_warnings = state.get("validation_warnings")
    result = {
        "enabled": True,
        "status": state.get("status", "not_loaded"),
        "active_profile_found": bool(snapshot and not snapshot.fallback_used),
        "profile_key": snapshot.profile_key if snapshot else _PRIMARY_PROFILE_KEY,
        "version": snapshot.version_number if snapshot and not snapshot.fallback_used else None,
        "commitment_count": len(snapshot.commitments) if snapshot else 0,
        "required_commitments_present": bool(
            snapshot and _REQUIRED_COMMITMENT_KEYS.issubset({item.commitment_key for item in snapshot.commitments})
        ),
        "cache_status": state.get("cache_status", "empty"),
        "fallback_used": bool(snapshot and snapshot.fallback_used),
        "last_refresh": last_refresh.isoformat() if isinstance(last_refresh, datetime) else None,
    }
    if detailed:
        result.update(
            fingerprint_prefix=snapshot.fingerprint[:12] if snapshot else None,
            validation_warnings=(
                list(state_warnings) if isinstance(state_warnings, (list, tuple)) else []
            ),
            last_error=state.get("last_error"),
            commitment_keys=[item.commitment_key for item in snapshot.commitments] if snapshot else [],
        )
    return result


def check_identity_health() -> tuple[bool, dict]:
    diagnostics = get_safe_identity_diagnostics()
    healthy = diagnostics["status"] in {"healthy", "disabled"}
    return healthy, diagnostics


def reset_runtime_state_for_tests() -> None:
    """Test-only reset; production code never calls this."""
    with _refresh_lock:
        _last_valid_snapshots.clear()
        _runtime_state.update(
            status="not_loaded",
            cache_status="empty",
            last_refresh=None,
            last_error=None,
            validation_warnings=(),
        )
    try:
        cache.invalidate_prefix(_CACHE_PREFIX)
    except Exception:
        pass
