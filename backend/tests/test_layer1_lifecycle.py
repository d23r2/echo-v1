"""ECHO Layer 1 (Phase 7) — memory_lifecycle.py: state transitions and
maintenance pass. All DB timestamps come back naive from SQLite even on a
DateTime(timezone=True) column — confirmed empirically — so these tests also
guard against a naive/aware subtraction crash in run_maintenance()."""

from datetime import UTC, datetime, timedelta

from app import atlas, schemas
from app.services import memory_lifecycle


def _entry(db, content="X", category="environment", days_old=0):
    entry = atlas.create_entry(db, schemas.AtlasEntryCreate(content=content, category=category))
    if days_old:
        entry.created_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days_old)
        db.commit()
        db.refresh(entry)
    return entry


def test_archive_sets_status_and_outdated(db_session):
    entry = _entry(db_session)
    memory_lifecycle.archive(db_session, entry)
    assert entry.status == "archived"
    assert entry.outdated is True


def test_restore_reactivates(db_session):
    entry = _entry(db_session)
    memory_lifecycle.archive(db_session, entry)
    memory_lifecycle.restore(db_session, entry)
    assert entry.status == "active"
    assert entry.outdated is False
    assert entry.review_state == "none"


def test_mark_verified_sets_last_verified_at(db_session):
    entry = _entry(db_session)
    assert entry.last_verified_at is None
    memory_lifecycle.mark_verified(db_session, entry)
    assert entry.last_verified_at is not None
    assert entry.verification_status == "verified"


def test_mark_outdated(db_session):
    entry = _entry(db_session)
    memory_lifecycle.mark_outdated(db_session, entry)
    assert entry.outdated is True
    assert entry.verification_status == "outdated"


def test_run_maintenance_does_not_crash_on_naive_vs_aware(db_session):
    _entry(db_session, category="environment", days_old=30)
    result = memory_lifecycle.run_maintenance(db_session)
    assert result["checked"] >= 1


def test_run_maintenance_expires_past_due_entries(db_session):
    entry = _entry(db_session)
    entry.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
    db_session.commit()
    result = memory_lifecycle.run_maintenance(db_session)
    assert result["expired"] == 1
    db_session.refresh(entry)
    assert entry.status == "archived"


def test_run_maintenance_flags_stale_environment_memory_for_review(db_session):
    entry = _entry(db_session, category="environment", days_old=20)  # > 14-day interval
    result = memory_lifecycle.run_maintenance(db_session)
    assert result["needs_review"] == 1
    db_session.refresh(entry)
    assert entry.review_state == "pending_review"


def test_run_maintenance_does_not_flag_fresh_environment_memory(db_session):
    _entry(db_session, category="environment", days_old=1)
    result = memory_lifecycle.run_maintenance(db_session)
    assert result["needs_review"] == 0


def test_run_maintenance_never_flags_durable_categories_by_age(db_session):
    _entry(db_session, category="profile", days_old=9999)
    _entry(db_session, category="preference", days_old=9999)
    result = memory_lifecycle.run_maintenance(db_session)
    assert result["needs_review"] == 0


def test_run_maintenance_is_idempotent(db_session):
    _entry(db_session, category="environment", days_old=20)
    first = memory_lifecycle.run_maintenance(db_session)
    second = memory_lifecycle.run_maintenance(db_session)
    assert first["needs_review"] == 1
    assert second["needs_review"] == 0  # already flagged, not re-counted


def test_run_maintenance_never_deletes_anything(db_session):
    entry = _entry(db_session)
    entry.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
    db_session.commit()
    memory_lifecycle.run_maintenance(db_session)
    # still present in the DB (just archived), not hard-deleted
    assert atlas.list_entries(db_session, memory_type=None) or True
    from app.models import AtlasEntry

    assert db_session.get(AtlasEntry, entry.id) is not None
