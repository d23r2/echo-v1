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


def _ensure_atlas_memory_type_column() -> None:
    """create_all only creates missing tables, not missing columns on tables that
    already exist — add memory_type in place for databases created before this field
    existed, so existing Atlas entries survive rather than requiring a fresh DB."""
    with engine.connect() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(atlas_entries)")}
        if "memory_type" not in cols:
            conn.exec_driver_sql("ALTER TABLE atlas_entries ADD COLUMN memory_type TEXT DEFAULT 'fact'")
            conn.commit()
