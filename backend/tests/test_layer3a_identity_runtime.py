"""Layer 3A Part 2B runtime loading, validation, fallback, cache, and health."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from app import models, schemas
from app.core import cache
from app.services import action_system, identity_runtime, identity_service, permission_center


def _seed(db):
    return identity_service.ensure_default_identity(db)


def _payload(*, display_name: str = "ECHO", commitments=None):
    payload = identity_service.default_identity_payload()
    data = payload.model_dump()
    data["display_name"] = display_name
    if commitments is not None:
        data["commitments"] = commitments
    return schemas.IdentityProfileDraftCreate(**data)


def test_loads_valid_active_identity_into_immutable_detached_snapshot(db_session):
    active = _seed(db_session)

    snapshot = identity_runtime.get_active_identity_snapshot(db_session)

    assert snapshot is not None
    assert snapshot.profile_id == active.id
    assert snapshot.version_number == 1
    assert len(snapshot.commitments) == 14
    assert "honesty-no-fabrication" in snapshot.invariant_commitment_keys
    assert "permission-first-action" in snapshot.blocking_commitment_keys
    assert all(isinstance(item, identity_runtime.RuntimeIdentityCommitment) for item in snapshot.commitments)
    with pytest.raises(FrozenInstanceError):
        snapshot.display_name = "changed"


def test_snapshot_serialization_is_safe_and_fingerprint_ignores_load_time(db_session):
    _seed(db_session)
    first = identity_runtime.get_active_identity_snapshot(db_session)
    identity_runtime.reset_runtime_state_for_tests()
    second = identity_runtime.refresh_active_identity(db_session)

    assert first is not None and second is not None
    assert first.fingerprint == second.fingerprint
    assert first.loaded_at != second.loaded_at
    serialized = first.to_serializable()
    assert "internal_role" not in serialized
    assert "metadata_json" not in str(serialized)
    assert "identity_profile" not in str(serialized)


def test_fingerprint_changes_for_meaningful_new_identity_version(db_session):
    _seed(db_session)
    first = identity_runtime.get_active_identity_snapshot(db_session)
    draft = identity_service.create_new_identity_version(db_session, _payload(display_name="ECHO Next"))
    identity_service.activate_identity(db_session, draft.id)
    second = identity_runtime.get_active_identity_snapshot(db_session)

    assert first is not None and second is not None
    assert second.version_number == 2
    assert first.fingerprint != second.fingerprint


def test_missing_identity_activates_deterministic_safe_fallback(db_session):
    snapshot = identity_runtime.get_active_identity_snapshot(db_session)

    assert snapshot is not None
    assert snapshot.fallback_used is True
    assert snapshot.validation_status == "degraded"
    assert "no-false-consciousness-claims" in snapshot.invariant_commitment_keys
    diagnostics = identity_runtime.get_safe_identity_diagnostics(detailed=True)
    assert diagnostics["status"] == "degraded"
    assert diagnostics["fallback_used"] is True
    assert "internal_role" not in diagnostics


def test_duplicate_active_profiles_are_fatal_and_fall_back(db_session):
    active = _seed(db_session)
    identity_runtime.reset_runtime_state_for_tests()
    db_session.execute(text("DROP INDEX uq_identity_profiles_one_active"))
    db_session.add(
        models.AssistantIdentityProfile(
            profile_key=active.profile_key,
            display_name=active.display_name,
            subtitle=active.subtitle,
            public_role=active.public_role,
            internal_role=active.internal_role,
            persona_summary=active.persona_summary,
            capability_summary=active.capability_summary,
            limitation_summary=active.limitation_summary,
            version_number=2,
            status="active",
            effective_from=datetime.now(UTC),
            source="system_default",
        )
    )
    db_session.commit()

    with pytest.raises(identity_runtime.IdentitySnapshotValidationError, match="exactly one"):
        identity_runtime.build_runtime_snapshot(db_session)
    snapshot = identity_runtime.refresh_active_identity(db_session)
    assert snapshot is not None and snapshot.fallback_used is True


def test_missing_required_commitments_are_fatal_but_advisory_absence_is_warning(db_session):
    empty = identity_service.create_draft_identity(db_session, _payload(commitments=[]))
    identity_service.activate_identity(db_session, empty.id)
    identity_runtime.reset_runtime_state_for_tests()
    with pytest.raises(identity_runtime.IdentitySnapshotValidationError, match="missing required"):
        identity_runtime.build_runtime_snapshot(db_session)

    # A separate database profile with every critical commitment but neither
    # optional advisory commitment remains usable in degraded/warning state.
    active = db_session.get(models.AssistantIdentityProfile, empty.id)
    active.status = "archived"
    db_session.commit()
    required_only = [
        item
        for item in identity_service.default_identity_payload().commitments
        if item.commitment_key not in {"user-autonomy", "privacy-minimization"}
    ]
    draft = identity_service.create_draft_identity(db_session, _payload(commitments=required_only))
    identity_service.activate_identity(db_session, draft.id)
    identity_runtime.reset_runtime_state_for_tests()
    snapshot = identity_runtime.build_runtime_snapshot(db_session)
    assert snapshot.fallback_used is False
    assert snapshot.validation_status == "degraded"
    assert "Optional advisory commitments absent" in snapshot.validation_warnings[0]


def test_invalid_refresh_retains_previous_valid_snapshot(db_session):
    active = _seed(db_session)
    previous = identity_runtime.get_active_identity_snapshot(db_session)
    active.limitation_summary = "I am genuinely conscious."
    db_session.commit()

    retained = identity_runtime.refresh_active_identity(db_session)

    assert retained is previous
    assert retained.fallback_used is False
    diagnostics = identity_runtime.get_safe_identity_diagnostics(detailed=True)
    assert diagnostics["cache_status"] == "retained_previous"
    assert diagnostics["last_error"] == "IdentitySnapshotValidationError"
    with pytest.raises(identity_runtime.ConsequentialIdentityUnavailableError):
        identity_runtime.require_verified_identity_for_consequential_action(retained)


def test_cache_miss_loads_once_and_hit_avoids_database_reload(db_session, monkeypatch):
    _seed(db_session)
    identity_runtime.reset_runtime_state_for_tests()
    real_build = identity_runtime.build_runtime_snapshot
    calls = 0

    def counted_build(db, profile_key="echo-primary"):
        nonlocal calls
        calls += 1
        return real_build(db, profile_key)

    monkeypatch.setattr(identity_runtime, "build_runtime_snapshot", counted_build)
    first = identity_runtime.get_active_identity_snapshot(db_session)
    second = identity_runtime.get_active_identity_snapshot(db_session)

    assert first is second
    assert calls == 1


def test_corrupt_cache_is_discarded_and_reloaded_safely(db_session):
    _seed(db_session)
    identity_runtime.reset_runtime_state_for_tests()
    cache.set("identity:active:echo-primary", object(), ttl_seconds=300)

    snapshot = identity_runtime.get_active_identity_snapshot(db_session)

    assert snapshot is not None
    assert snapshot.fallback_used is False


def test_activation_invalidates_and_hot_swaps_to_new_version(db_session):
    _seed(db_session)
    first = identity_runtime.get_active_identity_snapshot(db_session)
    draft = identity_service.create_new_identity_version(db_session, _payload(display_name="ECHO v2"))

    activated = identity_service.activate_identity(db_session, draft.id)
    second = identity_runtime.get_active_identity_snapshot(db_session)

    assert first is not None and second is not None
    assert second.profile_id == activated.id
    assert second.version_number == 2
    assert second is not first


def test_concurrent_cached_reads_return_same_immutable_snapshot(db_session):
    _seed(db_session)
    expected = identity_runtime.get_active_identity_snapshot(db_session)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _i: identity_runtime.get_active_identity_snapshot(db_session), range(32)))

    assert all(item is expected for item in results)


def test_consequential_action_guard_rejects_fallback(db_session):
    fallback = identity_runtime.get_active_identity_snapshot(db_session)
    with pytest.raises(identity_runtime.ConsequentialIdentityUnavailableError):
        identity_runtime.require_verified_identity_for_consequential_action(fallback)


def test_consequential_action_uses_existing_confirmation_lifecycle_when_identity_degraded(db_session):
    permission_center.ensure_defaults(db_session)
    permission_center.set_permission_level(db_session, "file_read", "allowed")

    run = action_system.run_action(
        db_session,
        "summarize_file",
        {"library_item_id": "missing"},
    )

    assert run.status == "pending"
    assert run.user_confirmed is False
    assert "identity verification is degraded" in run.error_summary.lower()


def test_verified_identity_does_not_add_confirmation_to_allowed_medium_action(db_session):
    _seed(db_session)
    permission_center.ensure_defaults(db_session)
    permission_center.set_permission_level(db_session, "file_read", "allowed")

    run = action_system.run_action(
        db_session,
        "summarize_file",
        {"library_item_id": "missing"},
    )

    assert run.status == "failed"
    assert run.error_summary == "That Library item doesn't exist."


def test_disabled_identity_feature_keeps_legacy_action_confirmation_behavior(db_session, monkeypatch):
    monkeypatch.setenv("CORE_IDENTITY_V1_ENABLED", "false")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        permission_center.ensure_defaults(db_session)
        permission_center.set_permission_level(db_session, "file_read", "allowed")
        run = action_system.run_action(
            db_session,
            "summarize_file",
            {"library_item_id": "missing"},
        )
        assert run.status == "failed"
    finally:
        get_settings.cache_clear()


def test_database_failure_starts_in_safe_degraded_mode():
    class BrokenSession:
        def query(self, _model):
            raise RuntimeError("database unavailable")

    snapshot = identity_runtime.refresh_active_identity(BrokenSession())
    assert snapshot is not None
    assert snapshot.fallback_used is True
