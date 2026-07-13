from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


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
