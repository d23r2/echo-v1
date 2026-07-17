"""ECHO Layer 1 (Phase 17) — deletion/forgetting flow: chat-level "forget
that" (archive-only, unambiguous-only), relationship deactivation on real
delete, and zombie-memory prevention (a deleted memory never reappears)."""

from app import atlas, chat_actions, schemas
from app.models import AtlasEntry, MemoryRelationship


def _entry(db, content, capture_method="explicit_user_request"):
    return atlas.create_entry(db, schemas.AtlasEntryCreate(content=content, capture_method=capture_method))


def test_forget_with_no_recent_memory_reports_not_found(db_session):
    result = chat_actions.try_handle_forget_action(db_session, "forget that")
    assert result is not None
    assert result.action_type == "forget_memory_not_found"


def test_forget_archives_single_unambiguous_recent_memory(db_session):
    entry = _entry(db_session, "User's favorite color is blue.")
    result = chat_actions.try_handle_forget_action(db_session, "forget that")
    assert result is not None
    assert result.action_type == "forget_memory"
    assert result.target_id == entry.id
    db_session.refresh(entry)
    assert entry.status == "archived"
    assert entry.outdated is True


def test_forget_is_reversible_via_restore(db_session):
    entry = _entry(db_session, "User's favorite color is blue.")
    chat_actions.try_handle_forget_action(db_session, "forget that")
    from app.services import memory_lifecycle

    memory_lifecycle.restore(db_session, entry)
    db_session.refresh(entry)
    assert entry.status == "active"


def test_forget_with_multiple_recent_candidates_is_ambiguous(db_session):
    _entry(db_session, "User's favorite color is blue.")
    _entry(db_session, "User's favorite food is pasta.")
    result = chat_actions.try_handle_forget_action(db_session, "forget that")
    assert result.action_type == "forget_memory_ambiguous"
    # neither entry was touched
    entries = atlas.list_entries(db_session)
    assert all(e.status == "active" for e in entries)


def test_forget_ignores_system_generated_candidates(db_session):
    _entry(db_session, "Auto-extracted fact.", capture_method="system_generated")
    result = chat_actions.try_handle_forget_action(db_session, "forget that")
    assert result.action_type == "forget_memory_not_found"


def test_non_forget_message_returns_none(db_session):
    _entry(db_session, "User's favorite color is blue.")
    assert chat_actions.try_handle_forget_action(db_session, "what's the weather like today") is None


def test_delete_entry_deactivates_relationships(db_session):
    a = _entry(db_session, "Backend runs on port 8001.")
    b = _entry(db_session, "Backend runs on port 8000.")
    db_session.add(
        MemoryRelationship(source_memory_id=b.id, target_memory_id=a.id, relationship_type="supersedes")
    )
    db_session.commit()

    atlas.delete_entry(db_session, a)

    rel = db_session.query(MemoryRelationship).filter(MemoryRelationship.target_memory_id == a.id).one()
    assert rel.status == "deactivated"
    assert db_session.get(AtlasEntry, a.id) is None


def test_deleted_memory_never_reappears_in_search(db_session):
    entry = _entry(db_session, "A memory that will be permanently deleted.")
    atlas.delete_entry(db_session, entry)
    results = atlas.search(db_session, "memory that will be permanently deleted", top_k=5)
    assert all(row.id != entry.id for row, _distance in results)
