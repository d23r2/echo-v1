"""Shared pytest fixtures for the backend test suite.

Test isolation: DATABASE_URL / CHROMA_DIR / ATTACHMENTS_DIR are redirected to a
fresh temp directory *before* any `app.*` module is imported below, so running
the test suite never reads or writes backend/data/ (the real running app's
persisted state). See tests/README.md for how to run these.
"""

import os
import sys
import tempfile
from pathlib import Path

# Make `app` importable regardless of whether pytest is invoked from backend/
# or the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_TEST_DATA_DIR = tempfile.mkdtemp(prefix="echo_backend_tests_")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_TEST_DATA_DIR, 'session.db').as_posix()}"
os.environ["CHROMA_DIR"] = str(Path(_TEST_DATA_DIR, "chroma"))
os.environ["ATTACHMENTS_DIR"] = str(Path(_TEST_DATA_DIR, "attachments"))

import pytest  # noqa: E402  (must come after the sys.path / env var setup above)
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app import models  # noqa: E402,F401  (registers all tables on Base.metadata)
from app.db import Base, SessionLocal  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_chroma_collections():
    """Root cause of the intermittent full-suite flake: atlas.py's and
    conversation_search.py's _get_collection() are each @lru_cache'd to a
    SINGLE Chroma collection for the whole pytest process. chromadb's
    PersistentClient persists to CHROMA_DIR on disk, so re-creating the
    Python-level client wrapper doesn't clear what's already stored there —
    every test that touches Atlas/conversation search (directly, or
    indirectly via persona.build_system_prompt(), which any chat-turn test
    exercises) shares ONE ever-growing collection for the entire run. A
    previous test's entries are never removed, and as the collection grows,
    semantic-search ranking can shift enough to intermittently fail an
    unrelated test's assertion ("my specific entry should be in the top-K
    results") — even though that test passes every time in isolation or on
    retry, because a fresh run hasn't accumulated the same noise yet.

    This wipes both collections' *contents* before every test (not just the
    client cache) — cheap (a metadata-only get() + delete-by-id, no
    re-embedding), and works regardless of which DB-isolation pattern a
    given test uses (the isolated db_session fixture below, or the real
    shared app DB some route-level test files use directly), since it
    operates on the Chroma collection object itself rather than the DB
    session. See tests/README.md for the isolation rule this establishes:
    tests must not depend on what a prior test wrote to Atlas/conversation
    search, since nothing here scopes those collections per-test-file."""
    from app import atlas as atlas_module
    from app import conversation_search as conversation_search_module

    for module in (atlas_module, conversation_search_module):
        try:
            collection = module._get_collection()
            existing_ids = collection.get()["ids"]
            if existing_ids:
                collection.delete(ids=existing_ids)
        except Exception:
            # Best-effort — e.g. no collection created yet on the very first
            # test. Must never block the actual test from running.
            pass
    yield


@pytest.fixture(autouse=True)
def _clear_provider_cooldowns():
    """Router-level route tests (test_chat_stream_endpoint.py etc.) hit the
    real app.db session-wide DATABASE_URL, not the isolated db_session
    fixture below, since they exercise POST /api/chat[/stream] end-to-end.
    A cooldown set by one test (e.g. a simulated gemini rate limit) would
    otherwise leak into every later test that also uses "gemini" as a
    provider name, silently skipping it. Clearing before each test keeps
    that shared DB's cooldown state test-order-independent."""
    session = SessionLocal()
    try:
        session.query(models.ProviderCooldown).delete()
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()
    yield


@pytest.fixture()
def db_session():
    """A fresh, isolated SQLite database for a single test. Each test gets its
    own file (not just a shared connection), so nothing persists between tests
    and nothing touches the real app's data."""
    fd, path = tempfile.mkstemp(suffix=".db", dir=_TEST_DATA_DIR)
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
        os.remove(path)
