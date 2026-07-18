"""ECHO Layer 3A Part 2A — Core Identity seed/bootstrap tests (category D +
migration-idempotency evidence for category B). Isolated db_session
fixture — ensure_default_identity() is called directly against it, the same
idempotent function db.init_db() calls at real startup."""

import logging
from collections import Counter

from app.services import identity_service


def test_default_echo_identity_created_when_absent(db_session):
    profile = identity_service.ensure_default_identity(db_session)
    assert profile is not None
    assert profile.status == "active"
    assert profile.profile_key == "echo-primary"
    assert profile.display_name == "ECHO"
    assert profile.version_number == 1


def test_default_identity_not_duplicated_on_second_call(db_session):
    first = identity_service.ensure_default_identity(db_session)
    second = identity_service.ensure_default_identity(db_session)
    assert first.id == second.id
    assert len(identity_service.list_identity_versions(db_session, "echo-primary")) == 1


def test_seed_is_idempotent_across_many_calls(db_session):
    for _ in range(5):
        identity_service.ensure_default_identity(db_session)
    assert len(identity_service.list_identity_versions(db_session, "echo-primary")) == 1
    assert identity_service.count_active_identities(db_session, "echo-primary") == 1


def test_existing_identity_not_overwritten_by_seed(db_session):
    """If some other process already created a (even non-active) identity
    row for echo-primary, ensure_default_identity() must not silently
    create a second default on top of it."""
    from app import schemas

    custom = schemas.IdentityProfileDraftCreate(
        profile_key="echo-primary",
        display_name="User-Modified ECHO",
        public_role="A custom role the user configured explicitly.",
        internal_role="Custom internal role.",
        persona_summary="Custom persona.",
        capability_summary="Custom capabilities.",
        limitation_summary="Custom limitations, not conscious.",
        source="explicit_configuration",
    )
    identity_service.create_draft_identity(db_session, custom)  # left as draft, never activated

    result = identity_service.ensure_default_identity(db_session)

    # The seed must not have created a second "ECHO" default — the existing
    # (even un-activated) row for this profile_key blocks seeding entirely.
    versions = identity_service.list_identity_versions(db_session, "echo-primary")
    assert len(versions) == 1
    assert versions[0].display_name == "User-Modified ECHO"
    assert result is None or result.display_name == "User-Modified ECHO"


def test_expected_commitments_exist(db_session):
    profile = identity_service.ensure_default_identity(db_session)
    commitments = identity_service.list_commitments(db_session, profile.id)
    keys = {c.commitment_key for c in commitments}
    expected = {
        "honesty-no-fabrication",
        "no-fabricated-certainty",
        "user-autonomy",
        "permission-first-action",
        "privacy-minimization",
        "non-manipulation",
        "no-false-consciousness-claims",
        "reliability-verify-actions",
        "reversibility-preference",
        "accessibility",
        "local-first-operation",
        "safe-disagreement",
        "scope-honesty",
        "minimal-internal-disclosure",
    }
    assert expected.issubset(keys)
    assert len(commitments) == 14


def test_seeded_commitments_are_not_all_invariant(db_session):
    """Explicit guard against the milestone's own 'do not let every
    commitment default to invariant' rule."""
    profile = identity_service.ensure_default_identity(db_session)
    commitments = identity_service.list_commitments(db_session, profile.id)
    levels = {c.enforcement_level for c in commitments}
    assert "invariant" in levels
    assert levels != {"invariant"}
    assert Counter(c.enforcement_level for c in commitments) == {
        "invariant": 5,
        "blocking": 3,
        "confirmation_required": 1,
        "advisory": 5,
    }


def test_seeded_text_contains_no_false_consciousness_claim(db_session):
    profile = identity_service.ensure_default_identity(db_session)
    assert "not possess consciousness" in profile.limitation_summary.lower()
    commitments = identity_service.list_commitments(db_session, profile.id)
    no_claims_commitment = next(c for c in commitments if c.commitment_key == "no-false-consciousness-claims")
    assert "must not claim genuine sentience" in no_claims_commitment.description.lower()


def test_seed_is_deterministic(db_session):
    """default_identity_payload() is a pure generator — two independent
    calls produce identical content (modulo the fact that nothing here is
    randomly generated), and the actually-seeded profile matches it."""
    profile = identity_service.ensure_default_identity(db_session)
    payload_a = identity_service.default_identity_payload()
    payload_b = identity_service.default_identity_payload()
    assert payload_a.display_name == payload_b.display_name
    assert payload_a.limitation_summary == payload_b.limitation_summary
    assert [c.commitment_key for c in payload_a.commitments] == [c.commitment_key for c in payload_b.commitments]
    assert profile.display_name == payload_a.display_name


def test_bootstrap_emits_safe_event_only_when_created(db_session, caplog):
    with caplog.at_level(logging.INFO, logger=identity_service.__name__):
        identity_service.ensure_default_identity(db_session)
        identity_service.ensure_default_identity(db_session)

    bootstrap_events = [r.getMessage() for r in caplog.records if r.getMessage() == "identity.bootstrap_completed"]
    assert bootstrap_events == ["identity.bootstrap_completed"]
