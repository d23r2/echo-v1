"""ECHO Layer 1 (Phase 6) — typed/severity-scored conflict system built on
top of the existing memory_conflicts.find_conflicts() heuristic."""

from app import atlas, memory_conflicts, schemas
from app.models import MemoryConflict


def _entry(db, content, memory_type="fact", category=None, confidence=0.6, tags=None):
    data = schemas.AtlasEntryCreate(content=content, memory_type=memory_type, confidence=confidence, tags=tags or [])
    if category:
        data.category = category
    return atlas.create_entry(db, data)


def test_environment_category_is_environment_drift(db_session):
    a = _entry(db_session, "Backend runs on port 8000.", category="environment")
    b = _entry(db_session, "Backend runs on port 8001.", category="environment")
    assert memory_conflicts.classify_conflict_type(a, b) == "environment_drift"


def test_project_category_is_project_version_conflict(db_session):
    a = _entry(db_session, "Release is on v1.", category="project")
    b = _entry(db_session, "Release is on v2.", category="project")
    assert memory_conflicts.classify_conflict_type(a, b) == "project_version_conflict"


def test_preference_with_negation_is_preference_change(db_session):
    a = _entry(db_session, "User likes short answers.", category="preference")
    b = _entry(db_session, "User no longer wants short answers.", category="preference")
    assert memory_conflicts.classify_conflict_type(a, b) == "user_preference_change"


def test_preference_without_negation_is_scope_conflict(db_session):
    a = _entry(db_session, "User likes short answers.", category="preference")
    b = _entry(db_session, "User wants detailed technical answers.", category="preference")
    assert memory_conflicts.classify_conflict_type(a, b) == "scope_conflict"


def test_severity_high_when_both_high_confidence(db_session):
    a = _entry(db_session, "X", confidence=0.9)
    b = _entry(db_session, "Y", confidence=0.8)
    assert memory_conflicts.classify_severity(a, b) == "high"


def test_severity_low_when_one_low_confidence(db_session):
    a = _entry(db_session, "X", confidence=0.9)
    b = _entry(db_session, "Y", confidence=0.2)
    assert memory_conflicts.classify_severity(a, b) == "low"


def test_severity_never_critical_automatically(db_session):
    for conf_a in (0.1, 0.5, 0.9, 1.0):
        for conf_b in (0.1, 0.5, 0.9, 1.0):
            a = _entry(db_session, "X", confidence=conf_a)
            b = _entry(db_session, "Y", confidence=conf_b)
            assert memory_conflicts.classify_severity(a, b) != "critical"


def test_detect_and_record_conflicts_creates_row(db_session):
    existing = _entry(db_session, "User's favorite drink is coffee.", tags=["drink"])
    new = _entry(db_session, "User's favorite drink is tea now.", tags=["drink"])
    created = memory_conflicts.detect_and_record_conflicts(db_session, new)
    assert len(created) == 1
    assert set(created[0].memory_ids_json) == {existing.id, new.id}
    assert created[0].status in ("open", "user_review_required")


def test_detect_and_record_conflicts_does_not_duplicate(db_session):
    existing = _entry(db_session, "User's favorite drink is coffee.", tags=["drink"])
    new = _entry(db_session, "User's favorite drink is tea now.", tags=["drink"])
    memory_conflicts.detect_and_record_conflicts(db_session, new)
    second_pass = memory_conflicts.detect_and_record_conflicts(db_session, new)
    assert second_pass == []
    assert db_session.query(MemoryConflict).count() == 1
    assert existing.id  # keep referenced, silence unused-var lint


def test_resolve_conflict_choose_newer_supersedes_older(db_session):
    older = _entry(db_session, "Backend runs on port 8001.", category="environment", confidence=0.6)
    newer = _entry(db_session, "Backend runs on port 8000.", category="environment", confidence=0.6)
    created = memory_conflicts.detect_and_record_conflicts(db_session, newer)
    assert len(created) == 1
    resolved = memory_conflicts.resolve_conflict(db_session, created[0], resolution="choose_newer")
    assert resolved.status == "resolved"
    assert resolved.resolution == "choose_newer"
    db_session.refresh(older)
    db_session.refresh(newer)
    assert older.status == "superseded"
    assert older.outdated is True
    assert newer.status == "active"


def test_resolve_conflict_retain_both_changes_nothing(db_session):
    a = _entry(db_session, "User likes short answers.", category="preference")
    b = _entry(db_session, "User wants detailed technical answers.", category="preference", tags=a.tags)
    created = memory_conflicts.detect_and_record_conflicts(db_session, b)
    if created:
        resolved = memory_conflicts.resolve_conflict(db_session, created[0], resolution="retain_both_with_scope")
        assert resolved.status == "resolved"
        db_session.refresh(a)
        db_session.refresh(b)
        assert a.status == "active"
        assert b.status == "active"
