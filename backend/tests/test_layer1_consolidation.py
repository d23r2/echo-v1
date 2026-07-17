"""ECHO Layer 1 (Phase 5) — memory_consolidation.py: duplicate detection and
consolidation actions."""

from app import atlas, schemas
from app.models import MemoryConsolidationEvent, MemoryRelationship, MemoryRevision
from app.services import memory_consolidation


def _make_entry(db, content, memory_type="fact", confidence=0.6):
    return atlas.create_entry(
        db, schemas.AtlasEntryCreate(content=content, memory_type=memory_type, confidence=confidence)
    )


def test_classify_exact_duplicate():
    assert memory_consolidation.classify_action("User likes tea.", "User likes tea.") == "reject_duplicate"
    assert memory_consolidation.classify_action("User likes tea.", "  user likes tea. ") == "reject_duplicate"


def test_classify_unrelated_is_keep_both():
    assert memory_consolidation.classify_action("User likes tea.", "The sky is blue today.") == "keep_both"


def test_classify_correction_is_supersede():
    action = memory_consolidation.classify_action(
        "Backend runs on port 8001.", "Backend must run on port 8000; 8001 was temporary."
    )
    assert action == "supersede_existing"


def test_classify_more_specific_is_update_existing():
    action = memory_consolidation.classify_action(
        "User prefers detailed explanations.",
        "User prefers detailed explanations that start with a practical worked example walkthrough.",
    )
    assert action == "update_existing"


def test_find_duplicates_empty_when_nothing_similar(db_session):
    _make_entry(db_session, "User likes tea.")
    duplicates = memory_consolidation.find_duplicates(db_session, content="The weather is nice.", memory_type="fact")
    assert duplicates == []


def test_find_duplicates_excludes_archived_status(db_session):
    entry = _make_entry(db_session, "Backend runs on port 8001.")
    entry.status = "superseded"
    db_session.commit()
    duplicates = memory_consolidation.find_duplicates(
        db_session, content="Backend runs on port 8001 for local dev.", memory_type="fact"
    )
    assert duplicates == []


def test_consolidate_new_memory_reject_exact_duplicate(db_session):
    _make_entry(db_session, "User likes tea.")
    event = memory_consolidation.consolidate_new_memory(
        db_session, content="User likes tea.", memory_type="fact", tags=[], confidence=0.6, source="test",
    )
    assert event is not None
    assert event.action == "reject_duplicate"
    assert len(atlas.list_entries(db_session)) == 1  # no new row created


def test_consolidate_new_memory_supersedes_and_preserves_history(db_session):
    old = _make_entry(db_session, "Backend runs on port 8001.")
    event = memory_consolidation.consolidate_new_memory(
        db_session,
        content="Backend must run on port 8000; 8001 was temporary.",
        memory_type="fact",
        tags=[],
        confidence=0.9,
        source="test",
    )
    assert event.action == "supersede_existing"
    db_session.refresh(old)
    assert old.status == "superseded"
    assert old.outdated is True

    new_entry_id = event.result_memory_id
    assert new_entry_id != old.id
    link = (
        db_session.query(MemoryRelationship)
        .filter(MemoryRelationship.source_memory_id == new_entry_id, MemoryRelationship.target_memory_id == old.id)
        .one()
    )
    assert link.relationship_type == "supersedes"

    # old memory still exists (history preserved), just excluded from active retrieval
    entries = atlas.list_entries(db_session)
    assert any(e.id == old.id for e in entries)
    assert any(e.id == new_entry_id for e in entries)


def test_consolidate_new_memory_updates_existing_for_more_specific(db_session):
    old = _make_entry(db_session, "User prefers detailed explanations.")
    event = memory_consolidation.consolidate_new_memory(
        db_session,
        content="User prefers detailed explanations that start with a practical worked example walkthrough.",
        memory_type="fact",
        tags=[],
        confidence=0.8,
        source="test",
    )
    assert event.action == "update_existing"
    assert event.result_memory_id == old.id
    db_session.refresh(old)
    assert "worked example" in old.content

    revision = db_session.query(MemoryRevision).filter(MemoryRevision.memory_id == old.id).one()
    assert revision.previous_content == "User prefers detailed explanations."
    assert revision.change_type == "edited"


def test_consolidate_new_memory_returns_none_when_no_duplicate(db_session):
    _make_entry(db_session, "User likes tea.")
    event = memory_consolidation.consolidate_new_memory(
        db_session, content="Completely unrelated statement about weather.", memory_type="fact",
        tags=[], confidence=0.6, source="test",
    )
    assert event is None


def test_consolidation_event_recorded_for_audit(db_session):
    _make_entry(db_session, "User likes tea.")
    memory_consolidation.consolidate_new_memory(
        db_session, content="User likes tea.", memory_type="fact", tags=[], confidence=0.6, source="test",
    )
    assert db_session.query(MemoryConsolidationEvent).count() == 1
