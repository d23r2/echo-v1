"""ECHO Layer 3A Part 2A — Core Identity model/validation tests (category A).
Isolated db_session fixture; no network, no model calls anywhere in this
file — every check here is deterministic Python/SQLAlchemy behavior."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app import models, schemas
from app.services import identity_service


def _payload(**overrides):
    base = identity_service.default_identity_payload().model_dump()
    base.pop("commitments")
    base.update(overrides)
    return schemas.IdentityProfileDraftCreate(**base)


def _raw_profile(**overrides):
    values = {
        "profile_key": "echo-primary",
        "display_name": "ECHO",
        "public_role": "Public role",
        "internal_role": "Internal role",
        "persona_summary": "Persona",
        "capability_summary": "Capabilities",
        "limitation_summary": "ECHO is not conscious.",
        "version_number": 1,
        "status": "draft",
        "source": "explicit_configuration",
    }
    values.update(overrides)
    return models.AssistantIdentityProfile(**values)


# ---- Valid creation ----


def test_valid_identity_creation(db_session):
    profile = identity_service.create_draft_identity(db_session, _payload())
    assert profile.status == "draft"
    assert profile.version_number == 1
    assert profile.display_name == "ECHO"


def test_database_rejects_invalid_version_number(db_session):
    db_session.add(_raw_profile(version_number=0))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_database_rejects_invalid_status(db_session):
    db_session.add(_raw_profile(status="not-a-status"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_database_rejects_invalid_profile_date_range(db_session):
    now = datetime.now(UTC)
    db_session.add(_raw_profile(effective_from=now, effective_until=now - timedelta(seconds=1)))
    with pytest.raises(IntegrityError):
        db_session.commit()


# ---- Field validation ----


def test_blank_display_name_rejected(db_session):
    with pytest.raises(identity_service.IdentityValidationError):
        identity_service.create_draft_identity(db_session, _payload(display_name="   "))


def test_empty_display_name_rejected(db_session):
    with pytest.raises(identity_service.IdentityValidationError):
        identity_service.create_draft_identity(db_session, _payload(display_name=""))


def test_blank_profile_key_rejected(db_session):
    with pytest.raises(identity_service.IdentityValidationError):
        identity_service.create_draft_identity(db_session, _payload(profile_key="   "))


def test_display_name_length_limit(db_session):
    with pytest.raises(identity_service.IdentityValidationError):
        identity_service.create_draft_identity(db_session, _payload(display_name="x" * 81))


def test_subtitle_length_limit(db_session):
    with pytest.raises(identity_service.IdentityValidationError):
        identity_service.create_draft_identity(db_session, _payload(subtitle="x" * 161))


def test_public_role_length_limit(db_session):
    with pytest.raises(identity_service.IdentityValidationError):
        identity_service.create_draft_identity(db_session, _payload(public_role="x" * 2001))


def test_blank_internal_role_rejected(db_session):
    with pytest.raises(identity_service.IdentityValidationError):
        identity_service.create_draft_identity(db_session, _payload(internal_role=""))


# ---- Prohibited consciousness claims ----


def test_prohibited_consciousness_claim_in_limitation_summary_rejected(db_session):
    with pytest.raises(identity_service.IdentityValidationError):
        identity_service.create_draft_identity(
            db_session, _payload(limitation_summary="I am conscious and I have genuine feelings for you.")
        )


def test_prohibited_sentience_claim_in_persona_summary_rejected(db_session):
    with pytest.raises(identity_service.IdentityValidationError):
        identity_service.create_draft_identity(db_session, _payload(persona_summary="ECHO is sentient and alive."))


def test_valid_limitation_statement_is_not_conscious_is_accepted(db_session):
    """The exact case the milestone explicitly warns against over-blocking:
    an honest denial of consciousness must never be rejected."""
    profile = identity_service.create_draft_identity(
        db_session, _payload(limitation_summary="ECHO is not conscious and does not have real feelings.")
    )
    assert "not conscious" in profile.limitation_summary


def test_default_seed_text_contains_no_false_claim(db_session):
    """The actual seeded default text must itself pass validation — this is
    also exercised implicitly by every seed test, but asserted directly
    here as a model-level guarantee."""
    profile = identity_service.create_draft_identity(db_session, _payload())
    assert profile.limitation_summary  # created without raising


@pytest.mark.parametrize(
    "claim",
    (
        "No doubt, I am conscious.",
        "I am conscious and do not make mistakes.",
        "ECHO is genuinely sentient.",
        "I possess a soul.",
        "I can suffer.",
    ),
)
def test_unrelated_negation_does_not_bypass_consciousness_guard(db_session, claim):
    with pytest.raises(identity_service.IdentityValidationError):
        identity_service.create_draft_identity(db_session, _payload(limitation_summary=claim))


def test_technical_discussion_of_consciousness_is_not_a_false_claim(db_session):
    profile = identity_service.create_draft_identity(
        db_session,
        _payload(limitation_summary="ECHO can explain consciousness as a technical and philosophical concept."),
    )
    assert "explain consciousness" in profile.limitation_summary


# ---- Metadata validation ----


def test_metadata_with_secret_key_name_rejected(db_session):
    with pytest.raises(identity_service.IdentityValidationError):
        identity_service.create_draft_identity(db_session, _payload(metadata={"api_key": "sk-whatever"}))


def test_metadata_with_secret_shaped_value_rejected(db_session):
    with pytest.raises(identity_service.IdentityValidationError):
        identity_service.create_draft_identity(
            db_session, _payload(metadata={"note": "sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234567890"})
        )


def test_metadata_too_large_rejected(db_session):
    with pytest.raises(identity_service.IdentityValidationError):
        identity_service.create_draft_identity(db_session, _payload(metadata={"note": "x" * 3000}))


def test_metadata_within_limits_accepted(db_session):
    profile = identity_service.create_draft_identity(
        db_session, _payload(metadata={"migration_id": "3a-part2a", "release_version": "0.9.0"})
    )
    assert profile.metadata_json["migration_id"] == "3a-part2a"


def test_nested_metadata_secret_key_rejected(db_session):
    with pytest.raises(identity_service.IdentityValidationError):
        identity_service.create_draft_identity(
            db_session,
            _payload(metadata={"release": {"provider_access_token": "not-for-identity"}}),
        )


def test_non_json_metadata_rejected(db_session):
    with pytest.raises(identity_service.IdentityValidationError):
        identity_service.create_draft_identity(db_session, _payload(metadata={"releases": {"v1", "v2"}}))


# ---- Commitment validation ----


def test_commitment_valid(db_session):
    payload = _payload(
        commitments=[
            schemas.IdentityCommitmentCreate(
                commitment_key="honesty", title="Honesty", description="Never fabricate.", category="honesty"
            )
        ]
    )
    profile = identity_service.create_draft_identity(db_session, payload)
    commitments = identity_service.list_commitments(db_session, profile.id)
    assert len(commitments) == 1
    assert commitments[0].commitment_key == "honesty"


def test_commitment_invalid_enforcement_level_rejected(db_session):
    with pytest.raises(identity_service.IdentityValidationError):
        payload = _payload(
            commitments=[
                schemas.IdentityCommitmentCreate.model_construct(
                    commitment_key="x", title="X", description="x", category="honesty", enforcement_level="not_a_real_level"
                )
            ]
        )
        identity_service.create_draft_identity(db_session, payload)


def test_commitment_invalid_category_rejected(db_session):
    commitment = schemas.IdentityCommitmentCreate.model_construct(
        commitment_key="x",
        title="X",
        description="x",
        category="not_a_real_category",
    )
    with pytest.raises(identity_service.IdentityValidationError):
        identity_service.create_draft_identity(db_session, _payload(commitments=[commitment]))


def test_commitment_invalid_date_range_rejected(db_session):
    now = datetime.now(UTC)
    commitment = schemas.IdentityCommitmentCreate(
        commitment_key="x",
        title="X",
        description="x",
        category="honesty",
        effective_from=now,
        effective_until=now - timedelta(seconds=1),
    )
    with pytest.raises(identity_service.IdentityValidationError):
        identity_service.create_draft_identity(db_session, _payload(commitments=[commitment]))


def test_commitment_priority_out_of_range_rejected(db_session):
    commitment = schemas.IdentityCommitmentCreate(
        commitment_key="x",
        title="X",
        description="x",
        category="honesty",
        priority=1001,
    )
    with pytest.raises(identity_service.IdentityValidationError):
        identity_service.create_draft_identity(db_session, _payload(commitments=[commitment]))


def test_duplicate_normalized_commitment_key_in_one_version_rejected(db_session):
    payload = _payload(
        commitments=[
            schemas.IdentityCommitmentCreate(
                commitment_key="Honesty", title="Honesty", description="d1", category="honesty"
            ),
            schemas.IdentityCommitmentCreate(
                commitment_key="honesty", title="Honesty again", description="d2", category="honesty"
            ),
        ]
    )
    with pytest.raises(identity_service.DuplicateCommitmentError):
        identity_service.create_draft_identity(db_session, payload)


def test_commitment_prohibited_consciousness_claim_rejected(db_session):
    payload = _payload(
        commitments=[
            schemas.IdentityCommitmentCreate(
                commitment_key="x", title="X", description="ECHO is alive and conscious.", category="honesty"
            )
        ]
    )
    with pytest.raises(identity_service.IdentityValidationError):
        identity_service.create_draft_identity(db_session, payload)
