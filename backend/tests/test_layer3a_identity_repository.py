"""ECHO Layer 3A Part 2A — Core Identity repository/lifecycle tests
(category C + G). Isolated db_session fixture."""

import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app import schemas
from app.services import identity_service


def _payload(**overrides):
    base = identity_service.default_identity_payload().model_dump()
    base.pop("commitments")
    base.update(overrides)
    return schemas.IdentityProfileDraftCreate(**base)


def _draft(db_session, **overrides):
    return identity_service.create_draft_identity(db_session, _payload(**overrides))


# ---- Create / retrieve ----


def test_create_draft_identity(db_session):
    profile = _draft(db_session)
    assert profile.status == "draft"
    assert profile.version_number == 1


def test_profile_key_is_normalized_for_storage_and_lookup(db_session):
    profile = _draft(db_session, profile_key="  ECHO-PRIMARY  ")
    assert profile.profile_key == "echo-primary"
    assert identity_service.get_identity_by_version(db_session, "ECHO-PRIMARY", 1).id == profile.id


def test_retrieve_by_id(db_session):
    profile = _draft(db_session)
    fetched = identity_service.get_identity_by_id(db_session, profile.id)
    assert fetched is not None
    assert fetched.id == profile.id


def test_retrieve_missing_by_id_returns_none(db_session):
    assert identity_service.get_identity_by_id(db_session, "does-not-exist") is None


def test_retrieve_by_version(db_session):
    profile = _draft(db_session)
    fetched = identity_service.get_identity_by_version(db_session, profile.profile_key, profile.version_number)
    assert fetched.id == profile.id


def test_retrieve_active_identity(db_session):
    draft = _draft(db_session)
    identity_service.activate_identity(db_session, draft.id)
    active = identity_service.get_active_identity(db_session, "echo-primary")
    assert active is not None
    assert active.id == draft.id
    assert active.status == "active"


def test_get_active_identity_returns_none_when_absent(db_session):
    assert identity_service.get_active_identity(db_session, "echo-primary") is None


def test_require_active_identity_raises_typed_error_when_absent(db_session):
    with pytest.raises(identity_service.ActiveIdentityNotFoundError):
        identity_service.require_active_identity(db_session, "echo-primary")


def test_list_versions_deterministic_order_descending(db_session):
    v1 = _draft(db_session)
    identity_service.activate_identity(db_session, v1.id)
    v2 = _draft(db_session, display_name="ECHO v2")
    identity_service.activate_identity(db_session, v2.id)
    v3 = _draft(db_session, display_name="ECHO v3")

    versions = identity_service.list_identity_versions(db_session, "echo-primary")
    assert [v.version_number for v in versions] == [3, 2, 1]
    assert versions[0].id == v3.id


def test_identity_exists(db_session):
    profile = _draft(db_session)
    assert identity_service.identity_exists(db_session, "echo-primary", profile.version_number) is True
    assert identity_service.identity_exists(db_session, "echo-primary", 999) is False


# ---- Activation lifecycle ----


def test_activate_draft(db_session):
    draft = _draft(db_session)
    activated = identity_service.activate_identity(db_session, draft.id)
    assert activated.status == "active"
    assert activated.effective_from is not None


def test_old_active_becomes_superseded(db_session):
    v1 = _draft(db_session)
    identity_service.activate_identity(db_session, v1.id)
    v2 = _draft(db_session, display_name="ECHO v2")
    identity_service.activate_identity(db_session, v2.id)

    refreshed_v1 = identity_service.get_identity_by_id(db_session, v1.id)
    assert refreshed_v1.status == "superseded"
    assert refreshed_v1.superseded_by_identity_id == v2.id
    assert refreshed_v1.effective_until is not None


def test_only_one_active_profile_remains(db_session):
    v1 = _draft(db_session)
    identity_service.activate_identity(db_session, v1.id)
    v2 = _draft(db_session, display_name="ECHO v2")
    identity_service.activate_identity(db_session, v2.id)

    assert identity_service.count_active_identities(db_session, "echo-primary") == 1


def test_activation_is_atomic_no_active_lost_on_bad_target(db_session):
    v1 = _draft(db_session)
    identity_service.activate_identity(db_session, v1.id)

    with pytest.raises(identity_service.IdentityNotFoundError):
        identity_service.activate_identity(db_session, "does-not-exist")

    # The real active identity must be untouched by the failed attempt.
    still_active = identity_service.get_active_identity(db_session, "echo-primary")
    assert still_active.id == v1.id
    assert identity_service.count_active_identities(db_session, "echo-primary") == 1


def test_cannot_activate_already_active_identity(db_session):
    draft = _draft(db_session)
    identity_service.activate_identity(db_session, draft.id)
    with pytest.raises(identity_service.InvalidIdentityStateError):
        identity_service.activate_identity(db_session, draft.id)


def test_simultaneous_activation_attempts_leave_exactly_one_active(db_session):
    """Two independent sessions race against the same SQLite database.

    SQLite may serialize both activations (both succeed, with the second
    superseding the first) or the partial unique index/lock may reject one;
    either behavior is valid. A rejection must be the typed domain error,
    and the durable invariant must always be exactly one active profile.
    """
    v1 = _draft(db_session)
    v2 = _draft(db_session, display_name="ECHO v2")
    session_factory = sessionmaker(bind=db_session.get_bind())
    barrier = Barrier(2)

    def activate_in_session(identity_id):
        with session_factory() as session:
            barrier.wait(timeout=10)
            try:
                return ("activated", identity_service.activate_identity(session, identity_id).id)
            except identity_service.IdentityActivationConflictError:
                return ("conflict", identity_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(activate_in_session, (v1.id, v2.id)))

    db_session.expire_all()
    assert identity_service.count_active_identities(db_session, "echo-primary") == 1
    active = identity_service.get_active_identity(db_session, "echo-primary")
    assert active.id in {v1.id, v2.id}
    assert {result[0] for result in results}.issubset({"activated", "conflict"})
    assert any(result[0] == "activated" for result in results)


def test_database_activation_conflict_is_typed_and_rolls_back(db_session, monkeypatch):
    v1 = _draft(db_session)
    identity_service.activate_identity(db_session, v1.id)
    v2 = _draft(db_session, display_name="ECHO v2")

    real_commit = db_session.commit

    def fail_commit():
        raise IntegrityError("forced activation collision", {}, RuntimeError("forced"))

    monkeypatch.setattr(db_session, "commit", fail_commit)
    with pytest.raises(identity_service.IdentityActivationConflictError):
        identity_service.activate_identity(db_session, v2.id)
    monkeypatch.setattr(db_session, "commit", real_commit)

    db_session.expire_all()
    still_active = identity_service.get_active_identity(db_session, "echo-primary")
    assert still_active.id == v1.id
    assert identity_service.get_identity_by_id(db_session, v2.id).status == "draft"


# ---- Archive / delete ----


def test_archive_superseded_profile(db_session):
    v1 = _draft(db_session)
    identity_service.activate_identity(db_session, v1.id)
    v2 = _draft(db_session, display_name="ECHO v2")
    identity_service.activate_identity(db_session, v2.id)

    archived = identity_service.archive_identity(db_session, v1.id)
    assert archived.status == "archived"


def test_active_profile_cannot_be_archived(db_session):
    draft = _draft(db_session)
    identity_service.activate_identity(db_session, draft.id)
    with pytest.raises(identity_service.InvalidIdentityStateError):
        identity_service.archive_identity(db_session, draft.id)


def test_active_profile_cannot_be_hard_deleted(db_session):
    draft = _draft(db_session)
    identity_service.activate_identity(db_session, draft.id)
    with pytest.raises(identity_service.ProtectedIdentityDeletionError):
        identity_service.delete_draft_identity(db_session, draft.id)


def test_never_activated_draft_can_be_deleted(db_session):
    draft = _draft(db_session)
    identity_service.delete_draft_identity(db_session, draft.id)
    assert identity_service.get_identity_by_id(db_session, draft.id) is None


def test_draft_delete_explicitly_deletes_owned_commitments(db_session):
    draft = _draft(
        db_session,
        commitments=[
            schemas.IdentityCommitmentCreate(
                commitment_key="draft-only", title="Draft only", description="d", category="honesty"
            )
        ],
    )
    identity_service.delete_draft_identity(db_session, draft.id)
    assert identity_service.list_commitments(db_session, draft.id) == []


def test_archived_profile_cannot_be_archived_again(db_session):
    never_activated = _draft(db_session, display_name="Never activated")
    identity_service.archive_identity(db_session, never_activated.id)
    with pytest.raises(identity_service.InvalidIdentityStateError):
        identity_service.archive_identity(db_session, never_activated.id)


# ---- Version / commitment duplication ----


def test_duplicate_version_number_rejected_at_repository_level(db_session):
    """create_draft_identity always computes the next free version number,
    so this proves the underlying unique constraint by inserting directly."""
    from app.models import AssistantIdentityProfile

    _draft(db_session)  # version 1
    duplicate = AssistantIdentityProfile(
        profile_key="echo-primary",
        version_number=1,
        display_name="Conflicting",
        public_role="x",
        internal_role="x",
        persona_summary="x",
        capability_summary="x",
        limitation_summary="x",
    )
    db_session.add(duplicate)
    with pytest.raises(Exception):  # noqa: B017 — raw IntegrityError from the unique constraint
        db_session.commit()
    db_session.rollback()


def test_duplicate_commitment_key_rejected_via_repository(db_session):
    profile = _draft(
        db_session,
        commitments=[
            schemas.IdentityCommitmentCreate(
                commitment_key="honesty", title="Honesty", description="d", category="honesty"
            )
        ],
    )
    from app.models import IdentityCommitment

    dupe = IdentityCommitment(
        identity_profile_id=profile.id,
        commitment_key="honesty",
        title="Honesty dup",
        description="d2",
        category="honesty",
    )
    db_session.add(dupe)
    with pytest.raises(Exception):  # noqa: B017 — raw IntegrityError from the unique constraint
        db_session.commit()
    db_session.rollback()


# ---- Commitments retrieval ----


def test_commitments_retrieved_by_category(db_session):
    profile = _draft(
        db_session,
        commitments=[
            schemas.IdentityCommitmentCreate(
                commitment_key="honesty", title="Honesty", description="d", category="honesty"
            ),
            schemas.IdentityCommitmentCreate(
                commitment_key="privacy", title="Privacy", description="d", category="privacy"
            ),
        ],
    )
    honesty_only = identity_service.list_commitments_by_category(db_session, profile.id, "honesty")
    assert len(honesty_only) == 1
    assert honesty_only[0].commitment_key == "honesty"


def test_get_commitment_by_key(db_session):
    profile = _draft(
        db_session,
        commitments=[
            schemas.IdentityCommitmentCreate(
                commitment_key="Honesty", title="Honesty", description="d", category="honesty"
            )
        ],
    )
    found = identity_service.get_commitment(db_session, profile.id, "honesty")
    assert found is not None
    assert found.title == "Honesty"


def test_commitments_ordered_by_priority_then_category_then_key(db_session):
    profile = _draft(
        db_session,
        commitments=[
            schemas.IdentityCommitmentCreate(
                commitment_key="low", title="Low", description="d", category="honesty",
                priority=200, enforcement_level="informational",
            ),
            schemas.IdentityCommitmentCreate(
                commitment_key="invariant", title="Invariant", description="d", category="honesty",
                priority=1000, enforcement_level="invariant",
            ),
        ],
    )
    ordered = identity_service.list_commitments(db_session, profile.id)
    assert [c.commitment_key for c in ordered] == ["invariant", "low"]


# ---- Missing identity raises typed error ----


def test_activate_missing_identity_raises_typed_error(db_session):
    with pytest.raises(identity_service.IdentityNotFoundError):
        identity_service.activate_identity(db_session, "does-not-exist")


def test_archive_missing_identity_raises_typed_error(db_session):
    with pytest.raises(identity_service.IdentityNotFoundError):
        identity_service.archive_identity(db_session, "does-not-exist")


def test_delete_missing_identity_raises_typed_error(db_session):
    with pytest.raises(identity_service.IdentityNotFoundError):
        identity_service.delete_draft_identity(db_session, "does-not-exist")


# ---- create_new_identity_version convenience wrapper ----


def test_create_new_identity_version_with_activate_true(db_session):
    result = identity_service.create_new_identity_version(db_session, _payload(), activate=True)
    assert result.status == "active"


def test_create_new_identity_version_without_activate_stays_draft(db_session):
    result = identity_service.create_new_identity_version(db_session, _payload(), activate=False)
    assert result.status == "draft"


def test_identity_lifecycle_emits_safe_structured_events(db_session, caplog):
    with caplog.at_level(logging.INFO, logger=identity_service.__name__):
        v1 = _draft(db_session)
        identity_service.activate_identity(db_session, v1.id)
        v2 = _draft(db_session, display_name="ECHO v2")
        identity_service.activate_identity(db_session, v2.id)
        identity_service.archive_identity(db_session, v1.id)

    messages = [record.getMessage() for record in caplog.records]
    assert "identity.profile_created" in messages
    assert "identity.profile_activated" in messages
    assert "identity.profile_superseded" in messages
    assert "identity.profile_archived" in messages
    assert all(v1.public_role not in message for message in messages)
