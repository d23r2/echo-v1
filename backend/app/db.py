from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    # ECHO Layer 0 — SQLite defaults foreign_keys OFF per connection; this
    # app already declares real ForeignKey columns (Message -> Conversation,
    # Attachment -> Message, ...) that were previously unenforced. Listens
    # on the generic Engine class (not just the module-level `engine`
    # instance above) so every SQLite connection this process opens gets
    # the same behavior, including tests/conftest.py's isolated per-test
    # engines — deliberately, so the full test suite actually exercises
    # this rather than only the shared app engine. Silently no-ops for a
    # non-SQLite DBAPI connection (defensive — this app is SQLite-only
    # today, but this must never break a future non-SQLite backend).
    module_name = type(dbapi_connection).__module__
    if "sqlite3" not in module_name:
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401  (ensure models are registered)

    Base.metadata.create_all(bind=engine)
    _ensure_atlas_memory_type_column()
    _ensure_column("attachments", "generated", "BOOLEAN DEFAULT 0")
    _ensure_column("messages", "fallback_note", "TEXT")
    _ensure_column("self_improvement_requests", "verification_checks", "TEXT DEFAULT '[]'")
    _ensure_column("self_improvement_requests", "verified_at", "DATETIME")
    _ensure_column("atlas_entries", "outdated", "BOOLEAN DEFAULT 0")
    _ensure_column("messages", "independence_nudge_reason", "TEXT")
    _ensure_column("attachments", "analysis_status", "TEXT DEFAULT 'stored'")
    _ensure_column("messages", "conversation_snippets", "TEXT DEFAULT '[]'")
    _ensure_column("messages", "envelope_status", "TEXT DEFAULT 'missing'")
    _ensure_column("messages", "envelope_degradation_reason", "TEXT")
    _ensure_column("messages", "sources_used", "TEXT DEFAULT '[]'")
    _ensure_column("messages", "current_info_intent", "TEXT")
    _ensure_column("messages", "search_failure_reason", "TEXT")
    _ensure_column("conversations", "tester_id", "TEXT DEFAULT 'default'")
    _ensure_column("conversations", "active_operational_mode", "TEXT")
    _ensure_column("conversations", "session_style_override", "TEXT DEFAULT '{}'")
    _ensure_column("persona_settings", "local_answer_quality_mode", "TEXT DEFAULT 'balanced'")
    _ensure_column("persona_settings", "voice_mode", "TEXT DEFAULT 'push_to_talk'")
    _ensure_column("persona_settings", "tts_enabled", "BOOLEAN DEFAULT 0")
    # ECHO Layer 2E — goal_id loose-reference columns on two pre-existing tables.
    _ensure_column("tasks", "goal_id", "TEXT")
    _ensure_column("plans", "goal_id", "TEXT")
    _ensure_column("sandbox_executions", "sandbox_type", "TEXT DEFAULT 'docker_worktree'")
    _ensure_column("sandbox_executions", "runner_image", "TEXT")
    _ensure_column("human_approvals", "target_at_approval", "TEXT DEFAULT 'local-dev'")
    _ensure_column("human_approvals", "policy_fingerprint_at_approval", "TEXT DEFAULT ''")
    _ensure_column("human_approvals", "constitution_fingerprint_at_approval", "TEXT DEFAULT ''")
    _ensure_layer1_memory_columns()
    _ensure_layer2a_cognitive_columns()
    _seed_action_reliability_core()
    _seed_cognitive_core()
    _seed_core_identity()
    _seed_self_modification_governance()
    _ensure_schema_version()


def _ensure_layer2a_cognitive_columns() -> None:
    """ECHO Layer 2A — additive columns on task_understandings/cognitive_briefs,
    same non-destructive pattern as Layer 0/1."""
    for column, ddl_type in (
        ("project_id", "TEXT"),
        ("parent_task_id", "TEXT"),
        ("normalized_request", "TEXT"),
        ("task_category", "TEXT DEFAULT 'mixed'"),
        ("urgency", "TEXT DEFAULT 'normal'"),
        ("complexity", "TEXT DEFAULT 'moderate'"),
        ("primary_goal", "TEXT"),
        ("secondary_goals_json", "TEXT DEFAULT '[]'"),
        ("user_intent", "TEXT"),
        ("expected_output", "TEXT"),
        ("inferred_constraints_json", "TEXT DEFAULT '[]'"),
        ("preferences_json", "TEXT DEFAULT '[]'"),
        ("forbidden_actions_json", "TEXT DEFAULT '[]'"),
        ("uncertainties_json", "TEXT DEFAULT '[]'"),
        ("missing_information_json", "TEXT DEFAULT '[]'"),
        ("failure_conditions_json", "TEXT DEFAULT '[]'"),
        ("acceptance_tests_json", "TEXT DEFAULT '[]'"),
        ("required_capabilities_json", "TEXT DEFAULT '[]'"),
        ("candidate_skills_json", "TEXT DEFAULT '[]'"),
        ("candidate_tools_json", "TEXT DEFAULT '[]'"),
        ("required_sources_json", "TEXT DEFAULT '[]'"),
        ("risk_level", "TEXT DEFAULT 'low'"),
        ("consequence_level", "TEXT DEFAULT 'low'"),
        ("reversibility", "TEXT DEFAULT 'reversible'"),
        ("confirmation_requirement", "BOOLEAN DEFAULT 0"),
        ("status", "TEXT DEFAULT 'ready'"),
        ("intent_hierarchy_json", "TEXT DEFAULT '{}'"),
        ("scope", "TEXT DEFAULT 'current_turn'"),
        ("clarification_questions_json", "TEXT DEFAULT '[]'"),
        ("content_fingerprint", "TEXT"),
        ("updated_at", "DATETIME"),
    ):
        _ensure_column("task_understandings", column, ddl_type)

    for column, ddl_type in (
        ("candidate_tools_json", "TEXT DEFAULT '[]'"),
        ("risk_and_confirmation_summary", "TEXT"),
        ("confidence", "TEXT DEFAULT 'medium'"),
        ("next_reasoning_stage", "TEXT"),
    ):
        _ensure_column("cognitive_briefs", column, ddl_type)


def _ensure_layer1_memory_columns() -> None:
    """ECHO Layer 1 — additive columns on tables that already existed before
    this milestone (atlas_entries, memory_candidates, projects,
    conversation_summaries). Every legacy row gets the field's declared
    default via SQLite's ADD COLUMN ... DEFAULT, so nothing pre-Layer-1 ever
    reads an unset value."""
    for column, ddl_type in (
        ("category", "TEXT DEFAULT 'semantic'"),
        ("verification_status", "TEXT DEFAULT 'unverified'"),
        ("importance", "TEXT DEFAULT 'medium'"),
        ("stability", "TEXT DEFAULT 'semi_stable'"),
        ("retention_policy", "TEXT DEFAULT 'periodic_review'"),
        ("expires_at", "DATETIME"),
        ("last_verified_at", "DATETIME"),
        ("last_accessed_at", "DATETIME"),
        ("access_count", "INTEGER DEFAULT 0"),
        ("capture_method", "TEXT DEFAULT 'migration'"),
        ("project_id", "TEXT"),
        ("task_id", "TEXT"),
        ("source_type", "TEXT"),
        ("source_reference", "TEXT"),
        ("parent_memory_id", "TEXT"),
        ("supersedes_memory_id", "TEXT"),
        ("contradiction_group_id", "TEXT"),
        ("duplicate_group_id", "TEXT"),
        ("review_state", "TEXT DEFAULT 'none'"),
        ("status", "TEXT DEFAULT 'active'"),
    ):
        _ensure_column("atlas_entries", column, ddl_type)

    for column, ddl_type in (
        ("category", "TEXT"),
        ("sensitivity_level", "TEXT DEFAULT 'ordinary_personal'"),
        ("recommendation", "TEXT"),
        ("capture_reason", "TEXT"),
        ("duplicate_memory_id", "TEXT"),
        ("importance", "TEXT DEFAULT 'medium'"),
        ("stability", "TEXT DEFAULT 'semi_stable'"),
    ):
        _ensure_column("memory_candidates", column, ddl_type)

    _ensure_column("projects", "objective", "TEXT")
    _ensure_column("projects", "constraints_json", "TEXT DEFAULT '[]'")
    _ensure_column("projects", "decisions_json", "TEXT DEFAULT '[]'")
    _ensure_column("projects", "blockers_json", "TEXT DEFAULT '[]'")
    _ensure_column("projects", "last_reviewed_at", "DATETIME")

    _ensure_column("conversation_summaries", "summary_type", "TEXT DEFAULT 'final'")
    _ensure_column("conversation_summaries", "candidate_memory_ids_json", "TEXT DEFAULT '[]'")


# ECHO Layer 0 — bump this by hand whenever a schema change genuinely
# warrants marking the database as having moved forward (not on every new
# table — this is a coarse marker, not a migration counter). See
# models.SchemaVersion's own docstring for why this app doesn't use Alembic
# in v1.
# v2 (ECHO Layer 1): Memory Foundation columns/tables — see
# _ensure_layer1_memory_columns() above and ECHO_LAYER_1_MEMORY_FOUNDATION.md.
# v3 (ECHO Layer 2A): Cognitive Core v2 / Task Understanding columns — see
# _ensure_layer2a_cognitive_columns() above.
# v4 (ECHO Layer 2B): Systems Thinking and Simulation Engine — new tables only
# (system_models, system_model_nodes, simulations, simulation_scenarios),
# created by Base.metadata.create_all() above with no _ensure_column() calls
# needed since nothing existing gained a column.
# v5 (ECHO Layer 2C): Decision Engine and Planning Engine — new tables only
# (decision_cases, decision_options, decision_criteria, plans, plan_steps,
# plan_milestones, plan_dependencies, plan_resource_requirements, plan_risks,
# plan_revisions), created by Base.metadata.create_all() above with no
# _ensure_column() calls needed since nothing existing gained a column.
# v6 (ECHO Layer 2D): Multi-Model Orchestrator and Tool Strategy Engine — new
# tables only (orchestration_policies, orchestration_runs), created by
# Base.metadata.create_all() above with no _ensure_column() calls needed
# since nothing existing gained a column.
# v7 (ECHO Layer 2E): Goal Manager, Context Selection v2, and Intelligence
# Center — new tables (goals, goal_reviews, context_selection_metrics)
# created by Base.metadata.create_all() above, plus two additive columns on
# pre-existing tables (tasks.goal_id, plans.goal_id) via _ensure_column().
# v8 (ECHO Layer 3A Part 2A): Core Identity data foundation — new tables
# only (assistant_identity_profiles, identity_commitments), created by
# Base.metadata.create_all() above with no _ensure_column() calls needed
# since nothing existing gained a column. See
# ECHO_LAYER_3A_CORE_IDENTITY_MORAL_COMPASS_ARCHITECTURE.md section 11.
# v9 (ECHO Layer 3A Part 2D): Supervised Self-Modification — new tables
# (code_modification_proposals, code_modification_revisions,
# modification_impact_assessments, constitutional_compliance_checks,
# sandbox_executions, verification_runs, human_approvals,
# deployment_attempts, rollback_events, self_modification_audit_events,
# self_modification_kill_switch), created by Base.metadata.create_all()
# v10 hardens approval invalidation and records the actual sandbox boundary;
# additive columns are installed above for databases that saw the partial v9.
CURRENT_SCHEMA_VERSION = 10


def _ensure_schema_version() -> None:
    """Idempotent, never destructive — creates the singleton row on first
    run, bumps `version` in place if the stored value is behind
    CURRENT_SCHEMA_VERSION, never touches any other table."""
    from app.models import SchemaVersion

    with SessionLocal() as db:
        row = db.get(SchemaVersion, "singleton")
        if row is None:
            db.add(SchemaVersion(id="singleton", version=CURRENT_SCHEMA_VERSION))
            db.commit()
        elif row.version < CURRENT_SCHEMA_VERSION:
            row.version = CURRENT_SCHEMA_VERSION
            db.commit()


def _seed_action_reliability_core() -> None:
    """Delegates to each service's own ensure_registered()/ensure_defaults()
    — the same idempotent functions tests call directly against the
    isolated db_session fixture, so there's exactly one seeding
    implementation per system rather than one for real startup and a
    second duplicated one for tests. Imports are local to avoid a circular
    import (these services import from app.models)."""
    from app.services import action_system, permission_center, tool_registry

    with SessionLocal() as db:
        action_system.ensure_registered(db)
        permission_center.ensure_defaults(db)
        tool_registry.ensure_registered(db)


def _seed_cognitive_core() -> None:
    """Same delegation pattern as _seed_action_reliability_core() — one
    idempotent seeding implementation, called both here (real startup) and
    directly by tests using the isolated db_session fixture."""
    from app.services import cognitive_core

    with SessionLocal() as db:
        cognitive_core.seed_world_model(db)


def _seed_core_identity() -> None:
    """ECHO Layer 3A Part 2A — same delegation pattern as
    _seed_action_reliability_core()/_seed_cognitive_core(): one idempotent
    seeding implementation, called both here (real startup) and directly by
    tests using the isolated db_session fixture. Creates the default
    "echo-primary" identity profile (active, version 1) only if no identity
    profile exists yet for that key — never duplicates, never overwrites an
    already-seeded or user-modified identity. Gated behind
    core_identity_v1_enabled (default True — see config.py's comment)."""
    if not settings.core_identity_v1_enabled:
        return
    from app.services import identity_service

    with SessionLocal() as db:
        identity_service.ensure_default_identity(db)


def _seed_self_modification_governance() -> None:
    """ECHO Layer 3A Part 2D — same delegation pattern as
    _seed_action_reliability_core(): idempotent, seeds new
    self_modification_* permission_center keys plus the kill-switch
    singleton row. Runs unconditionally (unlike _seed_core_identity) since
    seeding inert rows is safe even when the subsystem's feature flags are
    off — nothing reads them until a flag is explicitly enabled."""
    from app.services import self_modification_governance

    with SessionLocal() as db:
        self_modification_governance.ensure_defaults(db)


def _ensure_atlas_memory_type_column() -> None:
    """create_all only creates missing tables, not missing columns on tables that
    already exist — add memory_type in place for databases created before this field
    existed, so existing Atlas entries survive rather than requiring a fresh DB."""
    with engine.connect() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(atlas_entries)")}
        if "memory_type" not in cols:
            conn.exec_driver_sql("ALTER TABLE atlas_entries ADD COLUMN memory_type TEXT DEFAULT 'fact'")
            conn.commit()


def _ensure_column(table: str, column: str, ddl_type: str) -> None:
    """Same rationale as _ensure_atlas_memory_type_column, generalized: create_all
    never adds columns to a table that already exists, so new nullable/defaulted
    columns need an in-place ALTER for databases created before this field existed."""
    with engine.connect() as conn:
        cols = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
        if column not in cols:
            conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")
            conn.commit()
