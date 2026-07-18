"""ECHO Layer 1 — Memory Lifecycle and Aging (Phase 7).

Deterministic, idempotent state transitions for AtlasEntry — no model call.
`run_maintenance()` is the one function meant to be called periodically (via
POST /api/memory/maintenance/run, developer/founder only); everything else
is a plain, directly-callable transition used by the Memory Center UI and
the deletion/forgetting flow (Phase 17).

Review intervals are deliberately category-specific per the milestone's own
guidance: environment/project facts need frequent revalidation, durable
profile/preference facts don't get auto-flagged by time alone (a contradictory
new statement is what should trigger their review — see memory_conflicts.py —
not a calendar).
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import AtlasEntry

# None = never auto-flagged for review by age alone (reviewed on
# contradiction/conflict instead, or not at all for narrow, low-stakes types).
_REVIEW_INTERVAL_DAYS: dict[str, int | None] = {
    "profile": None,
    "preference": None,
    "project": 30,
    "task": 30,
    "episodic": None,
    "semantic": None,
    "skill": None,
    "relationship": None,
    "environment": 14,
    "temporary": 1,
}


def activate(db: Session, entry: AtlasEntry) -> AtlasEntry:
    entry.status = "active"
    entry.outdated = False
    db.commit()
    db.refresh(entry)
    _invalidate_persona_if_preference(entry, "preference_activated")
    return entry


def mark_needs_review(db: Session, entry: AtlasEntry) -> AtlasEntry:
    entry.review_state = "pending_review"
    db.commit()
    db.refresh(entry)
    return entry


def mark_verified(db: Session, entry: AtlasEntry) -> AtlasEntry:
    entry.verification_status = "verified"
    entry.last_verified_at = datetime.now(UTC)
    entry.review_state = "reviewed"
    db.commit()
    db.refresh(entry)
    _invalidate_persona_if_preference(entry, "preference_verified")
    return entry


def mark_outdated(db: Session, entry: AtlasEntry) -> AtlasEntry:
    entry.outdated = True
    entry.verification_status = "outdated"
    db.commit()
    db.refresh(entry)
    _invalidate_persona_if_preference(entry, "preference_outdated")
    return entry


def archive(db: Session, entry: AtlasEntry) -> AtlasEntry:
    """Excludes the memory from active retrieval (search() already filters
    outdated=True; status="archived" is the richer Layer 1 signal) without
    deleting it — still auditable, still restorable. See Phase 17's
    deletion/forgetting flow for the separate, real-delete path."""
    entry.status = "archived"
    entry.outdated = True
    db.commit()
    db.refresh(entry)
    _invalidate_persona_if_preference(entry, "preference_archived")
    return entry


def restore(db: Session, entry: AtlasEntry) -> AtlasEntry:
    entry.status = "active"
    entry.outdated = False
    entry.review_state = "none"
    db.commit()
    db.refresh(entry)
    _invalidate_persona_if_preference(entry, "preference_restored")
    return entry


def supersede(db: Session, old: AtlasEntry, new: AtlasEntry) -> None:
    old.status = "superseded"
    old.outdated = True
    new.supersedes_memory_id = old.id
    db.commit()
    _invalidate_persona_if_preference(old, "preference_superseded")


def _invalidate_persona_if_preference(entry: AtlasEntry, reason: str) -> None:
    if entry.category != "preference":
        return
    from app.services import persona_service

    persona_service.invalidate_persona_cache(reason=reason)


def run_maintenance(db: Session) -> dict:
    """Idempotent — running this twice in a row produces no further change
    beyond the first run (an already-archived entry is skipped by the
    status="active" filter; an already-pending-review entry isn't re-flagged
    or double-counted). Never deletes anything."""
    now = datetime.now(UTC)
    # SQLite drops tzinfo on DateTime(timezone=True) read-back (confirmed
    # empirically — every AtlasEntry timestamp comes back naive regardless of
    # the column type), so comparisons below use a naive "now" rather than
    # attaching tzinfo to every row; both sides are naive-UTC consistently.
    now_naive = now.replace(tzinfo=None)
    checked = 0
    expired = 0
    needs_review = 0
    expired_preference = False

    entries = db.query(AtlasEntry).filter(AtlasEntry.status == "active").all()
    for entry in entries:
        checked += 1

        if entry.expires_at is not None and entry.expires_at <= now_naive:
            entry.status = "archived"
            entry.outdated = True
            expired += 1
            expired_preference = expired_preference or entry.category == "preference"
            continue

        interval_days = _REVIEW_INTERVAL_DAYS.get(entry.category)
        if interval_days is None:
            continue
        reference = entry.last_verified_at or entry.created_at
        if reference is None:
            continue
        age_days = (now_naive - reference).days
        if age_days >= interval_days and entry.review_state == "none":
            entry.review_state = "pending_review"
            needs_review += 1

    db.commit()
    if expired_preference:
        from app.services import persona_service

        persona_service.invalidate_persona_cache(reason="preference_expired")
    return {"checked": checked, "expired": expired, "needs_review": needs_review, "run_at": now.isoformat()}
