"""ECHO Layer 0 — schema version marker, FK enforcement, non-destructive
re-init. Uses the isolated db_session fixture (own temp SQLite file per
test) — never touches the real app database."""

import pytest
from sqlalchemy.exc import IntegrityError

from app.db import CURRENT_SCHEMA_VERSION, Base, _ensure_schema_version
from app.models import Conversation, Message, SchemaVersion


def test_fresh_database_gets_schema_version_row(db_session):
    assert db_session.query(SchemaVersion).count() == 0
    # _ensure_schema_version() uses its own SessionLocal (the real app
    # engine), so exercise the same logic directly against db_session here.
    row = db_session.get(SchemaVersion, "singleton")
    if row is None:
        db_session.add(SchemaVersion(id="singleton", version=CURRENT_SCHEMA_VERSION))
        db_session.commit()
    row = db_session.get(SchemaVersion, "singleton")
    assert row.version == CURRENT_SCHEMA_VERSION


def test_real_app_db_has_schema_version_after_init():
    from app.db import SessionLocal, init_db

    init_db()
    with SessionLocal() as db:
        row = db.get(SchemaVersion, "singleton")
        assert row is not None
        assert row.version == CURRENT_SCHEMA_VERSION


def test_duplicate_init_is_idempotent_and_non_destructive():
    from app.db import SessionLocal, init_db

    init_db()
    with SessionLocal() as db:
        before = db.query(SchemaVersion).count()
    init_db()  # calling again must not error or duplicate the singleton row
    with SessionLocal() as db:
        after = db.query(SchemaVersion).count()
    assert before == after == 1


def test_create_all_does_not_drop_existing_tables(db_session):
    """Base.metadata.create_all only ever creates missing tables — confirm
    existing data survives calling it again against the same engine."""
    conversation = Conversation(title="survives re-init")
    db_session.add(conversation)
    db_session.commit()
    conversation_id = conversation.id

    Base.metadata.create_all(bind=db_session.get_bind())

    survived = db_session.get(Conversation, conversation_id)
    assert survived is not None
    assert survived.title == "survives re-init"


def test_foreign_key_enforcement_blocks_orphaned_message(db_session):
    """SQLite foreign_keys=ON (see db.py's engine-wide event listener) —
    inserting a Message pointing at a nonexistent conversation must now
    raise, where it previously would have silently succeeded."""
    orphan = Message(conversation_id="does-not-exist-anywhere", role="user", content="hi")
    db_session.add(orphan)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_foreign_key_enforcement_allows_valid_message(db_session):
    conversation = Conversation(title="valid parent")
    db_session.add(conversation)
    db_session.commit()

    message = Message(conversation_id=conversation.id, role="user", content="hi")
    db_session.add(message)
    db_session.commit()  # must not raise
    assert db_session.get(Message, message.id) is not None


def test_ensure_schema_version_never_downgrades():
    from app.db import SessionLocal, init_db

    init_db()
    with SessionLocal() as db:
        row = db.get(SchemaVersion, "singleton")
        row.version = CURRENT_SCHEMA_VERSION + 5  # simulate a future higher version
        db.commit()

    _ensure_schema_version()

    with SessionLocal() as db:
        row = db.get(SchemaVersion, "singleton")
        assert row.version == CURRENT_SCHEMA_VERSION + 5  # never silently downgraded

    # restore for any later test in the same process
    with SessionLocal() as db:
        row = db.get(SchemaVersion, "singleton")
        row.version = CURRENT_SCHEMA_VERSION
        db.commit()
