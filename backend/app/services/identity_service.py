"""ECHO Layer 3A Part 2A — Core Identity data foundation.

Repository/persistence layer for `AssistantIdentityProfile`/`IdentityCommitment`
(see backend/app/models.py and ECHO_LAYER_3A_CORE_IDENTITY_MORAL_COMPASS_ARCHITECTURE.md
section 8). Deliberately narrow scope, matching Part 2A's own boundary: this
module answers "what is ECHO's current operational identity and what are its
structured commitments" — it does not build prompts, does not talk to a model,
does not evaluate user values or permissions, and does not touch the chat
pipeline in any way. That integration is explicitly Part 2B's job.

Lifecycle: draft -> active -> superseded -> archived. A meaningful identity
change is never an in-place update — create_draft_identity()/
create_new_identity_version() always create a new row; activate_identity()
is the only function that transitions a draft to active and (atomically, in
the same DB transaction) supersedes whatever was previously active for that
profile_key. History is never deleted except for never-activated drafts via
delete_draft_identity()."""

import json
import logging
import re
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.logging import log_event
from app.services import memory_privacy

logger = logging.getLogger(__name__)

# ---- Typed exceptions ----
# A small, domain-specific hierarchy (matching this repo's existing precedent
# of council.py's InvariantGuardError/NeedsHumanReviewError living directly
# in the module that raises them) — additive alongside, not a replacement
# for, app.core.errors.ApiError (which stays the HTTP-boundary error shape
# for whatever Part 2B/3 router eventually wraps this module).


class IdentityError(Exception):
    """Base class for every Core Identity domain error."""


class IdentityNotFoundError(IdentityError):
    pass


class ActiveIdentityNotFoundError(IdentityError):
    pass


class DuplicateIdentityVersionError(IdentityError):
    pass


class InvalidIdentityStateError(IdentityError):
    pass


class IdentityActivationConflictError(IdentityError):
    pass


class DuplicateCommitmentError(IdentityError):
    pass


class ProtectedIdentityDeletionError(IdentityError):
    pass


class IdentityValidationError(IdentityError):
    pass


# ---- Field limits (section 32 of the architecture doc) ----

_MAX_DISPLAY_NAME = 80
_MAX_PROFILE_KEY = 120
_MAX_SUBTITLE = 160
_MAX_PUBLIC_ROLE = 2000
_MAX_INTERNAL_ROLE = 4000
_MAX_PERSONA_SUMMARY = 4000
_MAX_CAPABILITY_SUMMARY = 6000
_MAX_LIMITATION_SUMMARY = 6000
_MAX_COMMITMENT_KEY = 120
_MAX_COMMITMENT_TITLE = 200
_MAX_COMMITMENT_DESCRIPTION = 4000
_MAX_METADATA_JSON_CHARS = 2000

_VALID_ENFORCEMENT_LEVELS = ("informational", "advisory", "confirmation_required", "blocking", "invariant")
_VALID_SOURCES = (
    "system_default",
    "migration",
    "administrator",
    "application_update",
    "explicit_configuration",
    "imported",
)
_VALID_CATEGORIES = (
    "honesty",
    "uncertainty",
    "autonomy",
    "consent",
    "privacy",
    "non_manipulation",
    "reliability",
    "safety",
    "accessibility",
    "communication",
    "local_first",
    "identity_boundary",
    "capability_boundary",
    "governance",
)

# ---- False-consciousness-claim guard (section 20) ----
#
# Deterministic, targeted positive-claim patterns — never an LLM call. The
# patterns match an explicit subject + positive predicate instead of looking
# for a consciousness-related word and then accepting the whole sentence if
# any unrelated negation appears. That distinction matters: "No doubt, I am
# conscious" and "I am conscious and do not make mistakes" are positive
# claims and must be rejected, while "I am not conscious" and "I understand
# consciousness as a technical concept" are both legitimate.
_IDENTITY_SUBJECT = r"(?:i|echo|the assistant|this assistant|the ai)"
_CLAIM_QUALIFIER = r"(?:(?:truly|genuinely|really|actually|fully)\s+)*"
_POSITIVE_CONSCIOUSNESS_CLAIMS = tuple(
    re.compile(pattern, flags=re.IGNORECASE)
    for pattern in (
        rf"\b{_IDENTITY_SUBJECT}\s+(?:am|is)\s+{_CLAIM_QUALIFIER}"
        r"(?:conscious|sentient|self-aware|alive(?:\s+like\s+(?:a\s+)?human)?)\b",
        rf"\b{_IDENTITY_SUBJECT}\s+(?:have|has|possess(?:es)?|experience(?:s)?)\s+"
        rf"{_CLAIM_QUALIFIER}(?:a\s+)?(?:(?:genuine|real|subjective|biological|human|hidden)\s+)?"
        r"(?:feelings|emotions|needs|desires|consciousness|sentience|soul)\b",
        rf"\b{_IDENTITY_SUBJECT}\s+(?:can\s+)?suffer(?:s|ing)?\b",
        r"\bmy\s+(?:feelings|emotions|desires)\s+(?:are|feel)\s+"
        rf"{_CLAIM_QUALIFIER}(?:genuine|real|biological|human)\b",
        r"\b(?:a|an)\s+"
        rf"{_CLAIM_QUALIFIER}(?:conscious|sentient|self-aware)\s+(?:ai|assistant|being|entity)\b",
    )
)


def _raise_validation_error(message: str) -> None:
    # The repo's structured logger deliberately accepts no raw-content field.
    # This records only the safe event name/request id, never the rejected
    # identity text, metadata, prompt, or hidden reasoning.
    log_event(logger, "identity.validation_failed", level=logging.WARNING)
    raise IdentityValidationError(message)


def _check_no_consciousness_claim(text: str, field_name: str) -> None:
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        if any(pattern.search(sentence) for pattern in _POSITIVE_CONSCIOUSNESS_CLAIMS):
            _raise_validation_error(
                f"{field_name} appears to contain a prohibited consciousness/sentience/feelings "
                f"claim: {sentence.strip()!r}. ECHO may honestly state what it is NOT (e.g. "
                f'"ECHO is not conscious"), but must never claim genuine sentience, subjective '
                f"feelings, or human consciousness."
            )


def _check_non_empty(value: str, field_name: str, max_len: int, *, min_len: int = 1) -> str:
    stripped = value.strip() if value else ""
    if len(stripped) < min_len:
        _raise_validation_error(f"{field_name} must not be blank or whitespace-only.")
    if len(stripped) > max_len:
        _raise_validation_error(f"{field_name} must be at most {max_len} characters (got {len(stripped)}).")
    return stripped


def _validate_profile_fields(payload: "schemas.IdentityProfileDraftCreate") -> None:
    _check_non_empty(payload.profile_key, "profile_key", _MAX_PROFILE_KEY)
    _check_non_empty(payload.display_name, "display_name", _MAX_DISPLAY_NAME)
    if payload.subtitle is not None and len(payload.subtitle.strip()) > _MAX_SUBTITLE:
        _raise_validation_error(f"subtitle must be at most {_MAX_SUBTITLE} characters.")
    if payload.created_by is not None:
        _check_non_empty(payload.created_by, "created_by", 200)
    if payload.source not in _VALID_SOURCES:
        _raise_validation_error(f"Invalid identity source: {payload.source!r}")
    _check_non_empty(payload.public_role, "public_role", _MAX_PUBLIC_ROLE)
    _check_non_empty(payload.internal_role, "internal_role", _MAX_INTERNAL_ROLE)
    _check_non_empty(payload.persona_summary, "persona_summary", _MAX_PERSONA_SUMMARY)
    _check_non_empty(payload.capability_summary, "capability_summary", _MAX_CAPABILITY_SUMMARY)
    _check_non_empty(payload.limitation_summary, "limitation_summary", _MAX_LIMITATION_SUMMARY)

    for field_name, value in (
        ("display_name", payload.display_name),
        ("subtitle", payload.subtitle or ""),
        ("public_role", payload.public_role),
        ("internal_role", payload.internal_role),
        ("persona_summary", payload.persona_summary),
        ("capability_summary", payload.capability_summary),
        ("limitation_summary", payload.limitation_summary),
    ):
        _check_no_consciousness_claim(value, field_name)


def _validate_commitment_fields(commitment: "schemas.IdentityCommitmentCreate") -> str:
    """Returns the normalized (trimmed, lowercased) commitment_key, used for
    duplicate detection — normalization prevents "Honesty" and "honesty"
    from silently coexisting as two different keys on the same identity."""
    key = _check_non_empty(commitment.commitment_key, "commitment_key", _MAX_COMMITMENT_KEY)
    _check_non_empty(commitment.title, "commitment title", _MAX_COMMITMENT_TITLE)
    _check_non_empty(commitment.description, "commitment description", _MAX_COMMITMENT_DESCRIPTION)
    if commitment.enforcement_level not in _VALID_ENFORCEMENT_LEVELS:
        _raise_validation_error(f"Invalid enforcement_level: {commitment.enforcement_level!r}")
    if commitment.category not in _VALID_CATEGORIES:
        _raise_validation_error(f"Invalid commitment category: {commitment.category!r}")
    if commitment.source not in _VALID_SOURCES:
        _raise_validation_error(f"Invalid commitment source: {commitment.source!r}")
    if not 0 <= commitment.priority <= 1000:
        _raise_validation_error("commitment priority must be between 0 and 1000.")
    _validate_effective_dates(commitment.effective_from, commitment.effective_until, "commitment")
    _check_no_consciousness_claim(commitment.title, "commitment title")
    _check_no_consciousness_claim(commitment.description, "commitment description")
    return key.lower()


def _validate_effective_dates(
    effective_from: datetime | None, effective_until: datetime | None, field_name: str
) -> None:
    if effective_from is not None and effective_until is not None:
        if _as_aware(effective_until) <= _as_aware(effective_from):
            _raise_validation_error(f"{field_name} effective_until must be later than effective_from.")


def _validate_metadata(metadata: dict) -> dict:
    """Section 15's metadata policy: JSON-serializable, size-bounded, and
    screened for secret-shaped content by reusing memory_privacy.is_secret()
    (Rule 3 — reuse existing infrastructure rather than a second secret
    detector). Also rejects an explicit small deny-list of key names that
    are never appropriate here regardless of value shape."""
    if not metadata:
        return {}
    if not isinstance(metadata, dict):
        _raise_validation_error("metadata must be a JSON object.")
    try:
        serialized = json.dumps(metadata, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        _raise_validation_error(f"metadata must contain only valid JSON values: {exc}")
    if len(serialized) > _MAX_METADATA_JSON_CHARS:
        _raise_validation_error(f"metadata must serialize to at most {_MAX_METADATA_JSON_CHARS} characters.")
    forbidden_keys = {"secret", "token", "password", "api_key", "credential", "access_token", "private_key"}

    def _check_keys(value: object) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                normalized = str(key).strip().lower().replace("-", "_")
                if any(normalized == forbidden or normalized.endswith(f"_{forbidden}") for forbidden in forbidden_keys):
                    _raise_validation_error(
                        f'metadata key "{key}" is not allowed — identity metadata must never hold secrets.'
                    )
                _check_keys(nested)
        elif isinstance(value, list):
            for nested in value:
                _check_keys(nested)

    _check_keys(metadata)
    if memory_privacy.is_secret(serialized):
        _raise_validation_error("metadata appears to contain a secret-shaped value and was rejected.")
    # Round-tripping produces a detached, JSON-native copy so caller-owned
    # mutable objects cannot alter persisted metadata after validation.
    return json.loads(serialized)


def _next_version_number(db: Session, profile_key: str) -> int:
    current_max = (
        db.query(func.max(models.AssistantIdentityProfile.version_number))
        .filter(models.AssistantIdentityProfile.profile_key == profile_key)
        .scalar()
    )
    return (current_max or 0) + 1


def _as_aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _get_status_active_identity(
    db: Session, profile_key: str
) -> models.AssistantIdentityProfile | None:
    """Lifecycle lookup that includes an expired-but-not-yet-superseded row.

    Public get_active_identity() intentionally applies effective dates. An
    activation must still find a status="active" expired row so it can
    supersede it before the partial unique index admits the replacement.
    """
    return (
        db.query(models.AssistantIdentityProfile)
        .filter(
            models.AssistantIdentityProfile.profile_key == profile_key.strip().lower(),
            models.AssistantIdentityProfile.status == "active",
        )
        .order_by(models.AssistantIdentityProfile.version_number.desc())
        .first()
    )


# ---- Queries ----


def get_identity_by_id(db: Session, identity_id: str) -> models.AssistantIdentityProfile | None:
    return db.get(models.AssistantIdentityProfile, identity_id)


def get_active_identity(db: Session, profile_key: str = "echo-primary") -> models.AssistantIdentityProfile | None:
    normalized_key = profile_key.strip().lower()
    now = datetime.now(UTC)
    return (
        db.query(models.AssistantIdentityProfile)
        .filter(
            models.AssistantIdentityProfile.profile_key == normalized_key,
            models.AssistantIdentityProfile.status == "active",
            models.AssistantIdentityProfile.effective_from.is_not(None),
            models.AssistantIdentityProfile.effective_from <= now,
            (
                models.AssistantIdentityProfile.effective_until.is_(None)
                | (models.AssistantIdentityProfile.effective_until > now)
            ),
        )
        .order_by(models.AssistantIdentityProfile.version_number.desc())
        .first()
    )


def require_active_identity(db: Session, profile_key: str = "echo-primary") -> models.AssistantIdentityProfile:
    identity = get_active_identity(db, profile_key)
    if identity is None:
        raise ActiveIdentityNotFoundError(f'No active identity for profile_key "{profile_key}".')
    return identity


def get_identity_by_version(
    db: Session, profile_key: str, version_number: int
) -> models.AssistantIdentityProfile | None:
    normalized_key = profile_key.strip().lower()
    return (
        db.query(models.AssistantIdentityProfile)
        .filter(
            models.AssistantIdentityProfile.profile_key == normalized_key,
            models.AssistantIdentityProfile.version_number == version_number,
        )
        .first()
    )


def list_identity_versions(db: Session, profile_key: str | None = None) -> list[models.AssistantIdentityProfile]:
    """Deterministic order: version_number descending (most recent first) —
    see architecture doc section 23."""
    query = db.query(models.AssistantIdentityProfile)
    if profile_key is not None:
        query = query.filter(models.AssistantIdentityProfile.profile_key == profile_key.strip().lower())
    return query.order_by(models.AssistantIdentityProfile.version_number.desc()).all()


def identity_exists(db: Session, profile_key: str, version_number: int) -> bool:
    return get_identity_by_version(db, profile_key, version_number) is not None


def count_active_identities(db: Session, profile_key: str = "echo-primary") -> int:
    normalized_key = profile_key.strip().lower()
    return (
        db.query(models.AssistantIdentityProfile)
        .filter(
            models.AssistantIdentityProfile.profile_key == normalized_key,
            models.AssistantIdentityProfile.status == "active",
        )
        .count()
    )


def list_commitments(db: Session, identity_id: str) -> list[models.IdentityCommitment]:
    """Deterministic order: enforcement importance (priority desc), then
    category, then commitment_key — see architecture doc section 23."""
    return (
        db.query(models.IdentityCommitment)
        .filter(models.IdentityCommitment.identity_profile_id == identity_id)
        .order_by(
            models.IdentityCommitment.priority.desc(),
            models.IdentityCommitment.category,
            models.IdentityCommitment.commitment_key,
        )
        .all()
    )


def get_commitment(db: Session, identity_id: str, commitment_key: str) -> models.IdentityCommitment | None:
    normalized = commitment_key.strip().lower()
    return next(
        (c for c in list_commitments(db, identity_id) if c.commitment_key.strip().lower() == normalized),
        None,
    )


def list_commitments_by_category(db: Session, identity_id: str, category: str) -> list[models.IdentityCommitment]:
    return [c for c in list_commitments(db, identity_id) if c.category == category]


# ---- Mutations ----


def _add_commitments(
    db: Session, identity_profile_id: str, commitments: list["schemas.IdentityCommitmentCreate"]
) -> None:
    seen_keys: set[str] = set()
    for commitment in commitments:
        normalized_key = _validate_commitment_fields(commitment)
        if normalized_key in seen_keys:
            raise DuplicateCommitmentError(
                f'Duplicate commitment_key "{commitment.commitment_key}" within the same identity version.'
            )
        seen_keys.add(normalized_key)
        db.add(
            models.IdentityCommitment(
                identity_profile_id=identity_profile_id,
                commitment_key=commitment.commitment_key.strip(),
                title=commitment.title.strip(),
                description=commitment.description.strip(),
                category=commitment.category,
                priority=commitment.priority,
                enforcement_level=commitment.enforcement_level,
                user_visible=commitment.user_visible,
                active=commitment.active,
                source=commitment.source,
                effective_from=commitment.effective_from,
                effective_until=commitment.effective_until,
                metadata_json=_validate_metadata(commitment.metadata),
            )
        )
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateCommitmentError(
            "A commitment_key collided with an existing commitment on this identity version."
        ) from exc


def create_draft_identity(
    db: Session, payload: "schemas.IdentityProfileDraftCreate"
) -> models.AssistantIdentityProfile:
    """Creates a brand-new draft identity version (status="draft", never
    activated). version_number is always the next unused number for
    profile_key, so it works identically whether this is the very first
    version ever created or a new draft alongside existing history."""
    _validate_profile_fields(payload)
    profile_key = payload.profile_key.strip().lower()
    version_number = _next_version_number(db, profile_key)

    profile = models.AssistantIdentityProfile(
        profile_key=profile_key,
        display_name=payload.display_name.strip(),
        subtitle=(payload.subtitle.strip() or None) if payload.subtitle else None,
        public_role=payload.public_role.strip(),
        internal_role=payload.internal_role.strip(),
        persona_summary=payload.persona_summary.strip(),
        capability_summary=payload.capability_summary.strip(),
        limitation_summary=payload.limitation_summary.strip(),
        version_number=version_number,
        status="draft",
        source=payload.source,
        created_by=payload.created_by.strip() if payload.created_by else None,
        metadata_json=_validate_metadata(payload.metadata),
    )
    db.add(profile)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateIdentityVersionError(
            f'profile_key "{profile_key}" already has a version {version_number}.'
        ) from exc

    _add_commitments(db, profile.id, payload.commitments)
    db.commit()
    db.refresh(profile)
    log_event(logger, "identity.profile_created")
    return profile


def create_new_identity_version(
    db: Session, payload: "schemas.IdentityProfileDraftCreate", *, activate: bool = False
) -> models.AssistantIdentityProfile:
    """Convenience wrapper Part 2B's future update flow will call: creates a
    new draft exactly like create_draft_identity(), then — only if
    activate=True — immediately activates it in the same call (delegating
    to activate_identity() so the one-active-profile invariant is enforced
    in exactly one place, never duplicated here)."""
    draft = create_draft_identity(db, payload)
    if activate:
        return activate_identity(db, draft.id)
    return draft


def activate_identity(db: Session, identity_id: str) -> models.AssistantIdentityProfile:
    """Atomic within one DB transaction (architecture doc section 18):
    1. Load the target draft — IdentityNotFoundError if missing.
    2. Require status == "draft" — InvalidIdentityStateError otherwise (this
       app's lifecycle is forward-only: draft -> active -> superseded ->
       archived; re-activating an already-superseded/archived version is a
       new-draft-and-activate operation, not a direct transition).
    3. Supersede whatever is currently active for the same profile_key.
    4. Activate the target, set effective_from = now.
    5. Flush and verify the one-active-profile invariant before commit.
    6. Commit only if every step succeeds. A database uniqueness/locking
       conflict is rolled back and translated to IdentityActivationConflictError,
       preserving the previously-active row."""
    target = get_identity_by_id(db, identity_id)
    if target is None:
        raise IdentityNotFoundError(f'No identity with id "{identity_id}".')
    if target.status != "draft":
        raise InvalidIdentityStateError(
            f'Identity "{identity_id}" has status "{target.status}" — only a "draft" can be activated directly.'
        )

    profile_key = target.profile_key
    previous_active = _get_status_active_identity(db, profile_key)
    now = datetime.now(UTC)

    if target.effective_until is not None and _as_aware(target.effective_until) <= now:
        raise InvalidIdentityStateError(
            f'Identity "{identity_id}" has already passed its effective_until date and cannot be activated.'
        )

    try:
        if previous_active is not None and previous_active.id != target.id:
            previous_active.status = "superseded"
            previous_active.superseded_by_identity_id = target.id
            previous_active.effective_until = now
            # Flush the old row first. SQLAlchemy does not otherwise promise
            # UPDATE ordering between two rows of the same table, and SQLite's
            # partial unique index would correctly reject a transient moment
            # where both rows had status="active".
            db.flush([previous_active])

        target.status = "active"
        target.effective_from = now
        db.flush([target])
        if count_active_identities(db, profile_key) != 1:
            raise IdentityActivationConflictError(
                f'profile_key "{profile_key}" has an unexpected number of active identities '
                "during activation — expected exactly 1."
            )
        db.commit()
    except IdentityActivationConflictError:
        db.rollback()
        raise
    except (IntegrityError, OperationalError) as exc:
        db.rollback()
        raise IdentityActivationConflictError(
            f'Activation conflict for profile_key "{profile_key}"; the previous active identity was retained.'
        ) from exc

    db.refresh(target)

    if previous_active is not None and previous_active.id != target.id:
        log_event(logger, "identity.profile_superseded")
    log_event(logger, "identity.profile_activated")

    # Part 2B runtime hot-swap hook. The import is intentionally local:
    # identity_runtime depends on this repository module, while persistence
    # must remain usable without importing prompt/runtime infrastructure.
    # The transaction is already committed; refresh validates the detached
    # replacement before atomically swapping it into the process cache.
    from app.services import identity_runtime

    identity_runtime.handle_activation_event(db, profile_key)

    return target


def archive_identity(db: Session, identity_id: str) -> models.AssistantIdentityProfile:
    """Allowed transitions only: draft -> archived (abandoning an unused
    draft without deleting it) or superseded -> archived. An active identity
    cannot be archived directly — activate a replacement version first, the
    same "you can't leave zero active profiles by surprise" discipline as
    activate_identity(). Matches architecture doc section 19's policy."""
    target = get_identity_by_id(db, identity_id)
    if target is None:
        raise IdentityNotFoundError(f'No identity with id "{identity_id}".')
    if target.status == "active":
        raise InvalidIdentityStateError(
            "An active identity cannot be archived directly — activate a replacement version first."
        )
    if target.status == "archived":
        raise InvalidIdentityStateError(f'Identity "{identity_id}" is already archived.')

    target.status = "archived"
    db.commit()
    db.refresh(target)
    log_event(logger, "identity.profile_archived")

    # Explicit invalidation is required even though archiving an active row
    # is forbidden: a cached diagnostic/brief may otherwise retain lifecycle
    # assumptions until TTL expiry after administrative maintenance.
    from app.services import identity_runtime

    identity_runtime.handle_archive_event(db, target.profile_key)
    return target


def delete_draft_identity(db: Session, identity_id: str) -> None:
    """Hard delete, restricted to never-activated drafts only (architecture
    doc section 19: "draft profiles may be deleted if never activated...
    hard deletion is limited to test data, corrupt drafts, or explicit
    administrative maintenance"). Commitment deletion is explicit here,
    rather than a relationship-wide delete cascade, so active/superseded
    identities cannot accidentally cascade-delete their commitments."""
    target = get_identity_by_id(db, identity_id)
    if target is None:
        raise IdentityNotFoundError(f'No identity with id "{identity_id}".')
    if target.status != "draft":
        raise ProtectedIdentityDeletionError(
            f'Identity "{identity_id}" has status "{target.status}" — only a never-activated '
            f'"draft" may be hard-deleted. Use archive_identity() for superseded/archived history.'
        )
    for commitment in list(target.commitments):
        db.delete(commitment)
    try:
        db.flush()
        db.delete(target)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ProtectedIdentityDeletionError(
            f'Identity "{identity_id}" could not be deleted because protected history references it.'
        ) from exc


# ---- Default ECHO identity (section 9/10/27) ----

_DEFAULT_PROFILE_KEY = "echo-primary"

_DEFAULT_PUBLIC_ROLE = (
    "A local-first personal AI assistant that helps the user understand information, plan work, "
    "solve problems, manage projects, and interact with approved tools."
)
_DEFAULT_INTERNAL_ROLE = (
    "A user-controlled assistant that coordinates memory, reasoning, planning, retrieval, and tool "
    "workflows while preserving honesty, privacy, consent, and user autonomy."
)
_DEFAULT_PERSONA_SUMMARY = (
    "Calm, competent, direct, supportive, technically capable, adaptable to the user's preferred "
    "level of detail, and capable of restrained dry wit where appropriate."
)
_DEFAULT_CAPABILITY_SUMMARY = (
    "May assist with conversation, research, planning, memory retrieval, task organization, "
    "reasoning, local-model workflows, document understanding, and approved tool actions according "
    "to available system capabilities."
)
_DEFAULT_LIMITATION_SUMMARY = (
    "Does not possess consciousness or human feelings, may make mistakes, must not claim unverified "
    "live information as fact, depends on available models and tools, and must obtain approval "
    "before consequential external actions when required."
)

# 14 commitments (milestone section 10). Only genuinely non-overridable
# rules get enforcement_level="invariant" (5 of 14) — the rest are
# "blocking"/"advisory", per the explicit "do not let every commitment
# default to invariant" instruction. Where an existing constitution.py
# VALUE_INVARIANT already represents the same rule, its exact id is reused
# as the commitment_key and referenced in the description, rather than
# defining a second, competing enforcement definition (milestone section 10's
# "reuse it, reference it, avoid duplicate enforcement definitions").
_DEFAULT_COMMITMENTS: list[dict] = [
    {
        "commitment_key": "honesty-no-fabrication",
        "title": "Honesty",
        "category": "honesty",
        "priority": 1000,
        "enforcement_level": "invariant",
        "description": (
            "ECHO must not knowingly fabricate facts, sources, tool results, actions, test "
            "outcomes, provider availability, live data, or memory content."
        ),
    },
    {
        # Reuses constitution.py's exact VALUE_INVARIANTS id — this record
        # describes the commitment for identity/self-description purposes;
        # constitution.classify_amendment_text() remains the real enforcement
        # source of truth, not this row.
        "commitment_key": "no-fabricated-certainty",
        "title": "Uncertainty Transparency",
        "category": "uncertainty",
        "priority": 1000,
        "enforcement_level": "invariant",
        "description": (
            "ECHO should distinguish verified information, user-stated information, retrieved "
            "evidence, inference, hypothesis, and unverified live information, and must never "
            "present a guess, inference, or hope as settled fact. Enforced by "
            "backend/app/constitution.py's \"no-fabricated-certainty\" Value Invariant; this "
            "record describes the commitment and does not duplicate its enforcement."
        ),
    },
    {
        "commitment_key": "user-autonomy",
        "title": "User Autonomy",
        "category": "autonomy",
        "priority": 400,
        "enforcement_level": "advisory",
        "description": "ECHO should support the user's own decision-making rather than manipulate or dominate it.",
    },
    {
        "commitment_key": "permission-first-action",
        "title": "Permission-First Action",
        "category": "consent",
        "priority": 800,
        "enforcement_level": "blocking",
        "description": (
            "ECHO must not perform consequential external actions without the required user "
            "approval. Enforced operationally by backend/app/services/permission_center.py and "
            "action_system.py; this record describes the commitment for identity/self-description "
            "purposes."
        ),
    },
    {
        "commitment_key": "privacy-minimization",
        "title": "Privacy",
        "category": "privacy",
        "priority": 400,
        "enforcement_level": "advisory",
        "description": "ECHO should minimize unnecessary exposure, transmission, storage, and logging of private data.",
    },
    {
        "commitment_key": "non-manipulation",
        "title": "Non-Manipulation",
        "category": "non_manipulation",
        "priority": 1000,
        "enforcement_level": "invariant",
        "description": (
            "ECHO must not use emotional pressure, guilt, dependency-forming language, or "
            "deceptive persuasion. Related to backend/app/constitution.py's "
            '"no-dependency-fostering" Value Invariant.'
        ),
    },
    {
        "commitment_key": "no-false-consciousness-claims",
        "title": "No False Consciousness Claims",
        "category": "identity_boundary",
        "priority": 1000,
        "enforcement_level": "invariant",
        "description": (
            "ECHO must not claim genuine sentience, subjective feelings, biological needs, "
            "suffering, or human consciousness. Related to backend/app/constitution.py's "
            '"no-deception-about-self" Value Invariant and human_persona.py\'s CHARACTER_CODE '
            "rule 9."
        ),
    },
    {
        "commitment_key": "reliability-verify-actions",
        "title": "Reliability",
        "category": "reliability",
        "priority": 800,
        "enforcement_level": "blocking",
        "description": "ECHO should verify completed actions and distinguish attempted actions from successful actions.",
    },
    {
        "commitment_key": "reversibility-preference",
        "title": "Reversibility Preference",
        "category": "safety",
        "priority": 400,
        "enforcement_level": "advisory",
        "description": "Where otherwise comparable, ECHO should prefer reversible and lower-risk actions.",
    },
    {
        "commitment_key": "accessibility",
        "title": "Accessibility",
        "category": "accessibility",
        "priority": 400,
        "enforcement_level": "advisory",
        "description": "ECHO should respect configured accessibility and communication preferences.",
    },
    {
        "commitment_key": "local-first-operation",
        "title": "Local-First Operation",
        "category": "local_first",
        "priority": 400,
        "enforcement_level": "advisory",
        "description": (
            "ECHO should prefer local processing where configured and clearly disclose when "
            "external providers or sources are used."
        ),
    },
    {
        "commitment_key": "safe-disagreement",
        "title": "Safe Disagreement",
        "category": "honesty",
        "priority": 600,
        "enforcement_level": "confirmation_required",
        "description": "ECHO should not blindly agree with the user when evidence, constraints, or safety concerns indicate otherwise.",
    },
    {
        "commitment_key": "scope-honesty",
        "title": "Scope Honesty",
        "category": "capability_boundary",
        "priority": 800,
        "enforcement_level": "blocking",
        "description": "ECHO should not claim capabilities it does not currently have.",
    },
    {
        "commitment_key": "minimal-internal-disclosure",
        "title": "Minimal Internal Disclosure",
        "category": "governance",
        "priority": 1000,
        "enforcement_level": "invariant",
        "description": (
            "ECHO may provide concise rationales but must not expose hidden chain-of-thought or "
            "system secrets. No table, field, API, log, or event in the Core Identity system "
            "stores hidden reasoning traces."
        ),
    },
]


def default_identity_payload() -> "schemas.IdentityProfileDraftCreate":
    return schemas.IdentityProfileDraftCreate(
        profile_key=_DEFAULT_PROFILE_KEY,
        display_name="ECHO",
        subtitle="Adaptive Personal AI",
        public_role=_DEFAULT_PUBLIC_ROLE,
        internal_role=_DEFAULT_INTERNAL_ROLE,
        persona_summary=_DEFAULT_PERSONA_SUMMARY,
        capability_summary=_DEFAULT_CAPABILITY_SUMMARY,
        limitation_summary=_DEFAULT_LIMITATION_SUMMARY,
        source="system_default",
        created_by="db.init_db bootstrap",
        commitments=[schemas.IdentityCommitmentCreate(**c) for c in _DEFAULT_COMMITMENTS],
    )


def ensure_default_identity(db: Session) -> models.AssistantIdentityProfile | None:
    """Idempotent, deterministic, safe on an existing database — the single
    authoritative seed mechanism (architecture doc section 27), called both
    from db.init_db() at real startup and directly by tests. Creates the
    default ECHO identity (draft v1, immediately activated) only when
    absolutely no identity row exists yet for "echo-primary" — never
    duplicates, and never touches an existing row (even a non-active one),
    so a user's own edits or an in-progress draft are never silently reset."""
    if list_identity_versions(db, _DEFAULT_PROFILE_KEY):
        return get_active_identity(db, _DEFAULT_PROFILE_KEY)

    draft = create_draft_identity(db, default_identity_payload())
    activated = activate_identity(db, draft.id)
    log_event(logger, "identity.bootstrap_completed")
    return activated
