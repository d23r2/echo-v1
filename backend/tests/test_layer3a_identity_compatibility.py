"""ECHO Layer 3A Part 2A — Core Identity migration, compatibility, and
security/privacy shape tests (categories B, E, F). Uses the real shared app
DB via TestClient/init_db() for the compatibility checks (same established
pattern as test_layer2e_intelligence_api.py) and db_session for schema
introspection, matching the isolated-vs-shared distinction the rest of this
suite already uses."""

import inspect
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import models, schemas
from app.db import engine, init_db
from app.main import app
from app.services import identity_service

# ---- Migration (category B) ----


def test_migration_applies_to_clean_database_and_tables_exist(db_session):
    """db_session's fixture already runs Base.metadata.create_all() for a
    fresh temp DB — this test asserts the two new tables specifically
    exist with the expected columns, proving the migration (in this repo's
    create_all + _ensure_column() sense — see db.py) actually took effect."""
    inspector = sa_inspect(db_session.get_bind())
    tables = inspector.get_table_names()
    assert "assistant_identity_profiles" in tables
    assert "identity_commitments" in tables

    profile_columns = {c["name"] for c in inspector.get_columns("assistant_identity_profiles")}
    for expected in ("id", "profile_key", "display_name", "version_number", "status", "source"):
        assert expected in profile_columns

    commitment_columns = {c["name"] for c in inspector.get_columns("identity_commitments")}
    for expected in ("id", "identity_profile_id", "commitment_key", "category", "enforcement_level", "priority"):
        assert expected in commitment_columns


def test_unique_constraints_exist_and_are_enforced(db_session):
    inspector = sa_inspect(db_session.get_bind())
    profile_uniques = inspector.get_unique_constraints("assistant_identity_profiles")
    assert any(set(uc["column_names"]) == {"profile_key", "version_number"} for uc in profile_uniques)

    commitment_uniques = inspector.get_unique_constraints("identity_commitments")
    assert any(set(uc["column_names"]) == {"identity_profile_id", "commitment_key"} for uc in commitment_uniques)


def test_foreign_key_exists_and_is_enforced(db_session):
    inspector = sa_inspect(db_session.get_bind())
    fks = inspector.get_foreign_keys("identity_commitments")
    assert any(fk["referred_table"] == "assistant_identity_profiles" for fk in fks)

    # SQLite only enforces FKs when PRAGMA foreign_keys=ON — confirm the
    # existing app-wide listener (db.py's _enable_sqlite_foreign_keys) is
    # actually active for this session's connection, not just declared.
    result = db_session.execute(text("PRAGMA foreign_keys")).scalar()
    assert result == 1

    from app.models import IdentityCommitment

    orphan = IdentityCommitment(
        identity_profile_id="does-not-exist",
        commitment_key="x",
        title="x",
        description="x",
        category="honesty",
    )
    db_session.add(orphan)
    try:
        db_session.commit()
        raised = False
    except Exception:
        raised = True
        db_session.rollback()
    assert raised, "inserting a commitment with a non-existent identity_profile_id should violate the FK"


def test_indexes_exist(db_session):
    inspector = sa_inspect(db_session.get_bind())
    profile_indexes = inspector.get_indexes("assistant_identity_profiles")
    profile_index_columns = {tuple(ix["column_names"]) for ix in profile_indexes}
    assert ("profile_key",) in profile_index_columns
    assert ("status",) in profile_index_columns
    one_active = next(ix for ix in profile_indexes if ix["name"] == "uq_identity_profiles_one_active")
    assert one_active["unique"] == 1

    commitment_index_columns = {tuple(ix["column_names"]) for ix in inspector.get_indexes("identity_commitments")}
    assert ("identity_profile_id",) in commitment_index_columns
    assert ("category",) in commitment_index_columns


def test_check_constraints_exist(db_session):
    inspector = sa_inspect(db_session.get_bind())
    profile_checks = {check["name"] for check in inspector.get_check_constraints("assistant_identity_profiles")}
    assert {
        "ck_identity_profile_version_positive",
        "ck_identity_profile_key_nonempty",
        "ck_identity_profile_name_nonempty",
        "ck_identity_profile_status",
        "ck_identity_profile_source",
        "ck_identity_profile_effective_dates",
    }.issubset(profile_checks)

    commitment_checks = {check["name"] for check in inspector.get_check_constraints("identity_commitments")}
    assert {
        "ck_identity_commitment_key_nonempty",
        "ck_identity_commitment_title_nonempty",
        "ck_identity_commitment_priority",
        "ck_identity_commitment_category",
        "ck_identity_commitment_enforcement_level",
        "ck_identity_commitment_source",
        "ck_identity_commitment_effective_dates",
    }.issubset(commitment_checks)


def test_partial_unique_index_enforces_one_active_profile(db_session):
    values = {
        "display_name": "ECHO",
        "public_role": "Public role",
        "internal_role": "Internal role",
        "persona_summary": "Persona",
        "capability_summary": "Capabilities",
        "limitation_summary": "ECHO is not conscious.",
        "status": "active",
        "source": "explicit_configuration",
        "effective_from": datetime.now(UTC),
    }
    first = models.AssistantIdentityProfile(profile_key="echo-primary", version_number=1, **values)
    db_session.add(first)
    db_session.commit()

    second = models.AssistantIdentityProfile(profile_key="echo-primary", version_number=2, **values)
    db_session.add(second)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    assert identity_service.count_active_identities(db_session, "echo-primary") == 1


def test_migration_preserves_existing_tables(db_session):
    """The new tables must be purely additive — every pre-existing Layer
    0-2E table must still exist after the same create_all() pass that
    creates the identity tables."""
    inspector = sa_inspect(db_session.get_bind())
    tables = inspector.get_table_names()
    for pre_existing in ("conversations", "messages", "atlas_entries", "goals", "plans", "decision_cases"):
        assert pre_existing in tables


def test_downgrade_not_applicable_documented():
    """This repo has no migration framework (no Alembic — see db.py's own
    docstring and ECHO_LAYER_3A_CORE_IDENTITY_MORAL_COMPASS_ARCHITECTURE.md
    section 1.3): schema changes are additive create_all()/_ensure_column()
    calls with no scripted downgrade path anywhere in the codebase. A
    "downgrade" for this milestone is: drop the two new tables (they
    reference nothing outside themselves) — documented here rather than
    implemented as a script, matching every prior layer's own migration
    plan (see e.g. ECHO_LAYER_2E_GOALS_CONTEXT_INTELLIGENCE_CENTER_ARCHITECTURE.md
    section 11's identical "Downgrade: drop the ... tables" pattern)."""
    assert True


def test_real_engine_boots_with_identity_tables():
    """init_db() against the real configured engine (redirected to a temp
    DB by conftest.py before any app import, per this repo's established
    test-isolation convention) must succeed and be idempotent when called
    twice in a row."""
    init_db()
    init_db()
    inspector = sa_inspect(engine)
    assert "assistant_identity_profiles" in inspector.get_table_names()


# ---- Compatibility (category E) ----


def test_application_startup_still_works():
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200


def test_existing_chat_action_endpoints_still_reachable():
    """Not a full chat round-trip (which requires a real/fake provider) —
    proves the router/app wiring around the new models.py/schemas.py/db.py
    edits didn't break FastAPI's route registration for an unrelated,
    pre-existing endpoint."""
    with TestClient(app) as client:
        response = client.get("/api/system/version")
        assert response.status_code == 200
        assert response.json()["schema_version"] == 8


def test_existing_goals_endpoint_still_works():
    with TestClient(app) as client:
        response = client.get("/api/goals")
        assert response.status_code == 200


def test_existing_permissions_endpoint_still_works():
    with TestClient(app) as client:
        response = client.get("/api/permissions")
        assert response.status_code == 200


# ---- Security / privacy shape (category F) ----


def test_no_hidden_reasoning_field_on_identity_models():
    from app.models import AssistantIdentityProfile, IdentityCommitment

    forbidden_substrings = ("reasoning", "chain_of_thought", "chain-of-thought", "hidden_trace")
    for model in (AssistantIdentityProfile, IdentityCommitment):
        column_names = {c.name for c in model.__table__.columns}
        for column in column_names:
            assert not any(f in column.lower() for f in forbidden_substrings), f"{model.__name__}.{column}"


def test_read_schemas_omit_internal_metadata():
    """IdentityProfileRead/IdentityCommitmentRead deliberately do not expose
    metadata_json — asserted directly against the Pydantic field set rather
    than a live response, so this fails loudly if a future edit accidentally
    re-adds it."""
    assert "metadata_json" not in schemas.IdentityProfileRead.model_fields
    assert "metadata" not in schemas.IdentityProfileRead.model_fields
    assert "metadata_json" not in schemas.IdentityCommitmentRead.model_fields
    assert "metadata" not in schemas.IdentityCommitmentRead.model_fields


def test_identity_service_module_makes_no_network_or_model_calls():
    """A cheap static guard: identity_service.py must not import anything
    from app.providers/app.router (the model-call layer) — Part 2A is
    explicitly database-only, no prompt/model integration yet."""
    source = inspect.getsource(identity_service)
    assert "app.providers" not in source
    assert "app.router" not in source
    assert "model_router" not in source
