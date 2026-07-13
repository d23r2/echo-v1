"""Outdated Atlas entries (AtlasEntry.outdated=True) must stay visible in the
Atlas list/history UI, but must NOT be surfaced as "relevant" by normal
semantic search, persona prompt injection, or conflict detection — marking
something outdated is a deliberate "don't treat this as current" signal (see
routers/atlas.py's PATCH endpoint) that those code paths should honor.

Real Chroma + sentence-transformers embeddings are used throughout (same as
the rest of the Atlas test suite) — no real external API calls, no mocking
of the embedding model itself. Content/query strings are kept distinctive
enough to rank reliably despite the shared, never-reset Chroma "atlas"
collection accumulating entries from every other Atlas test in the run.
"""

import uuid

from app import atlas, memory_conflicts, persona, schemas

_TOKEN = lambda: uuid.uuid4().hex[:8]  # noqa: E731


def _entry(db, content: str, **kwargs) -> "atlas.models.AtlasEntry":
    return atlas.create_entry(
        db, schemas.AtlasEntryCreate(content=content, memory_type=kwargs.pop("memory_type", "fact"), **kwargs)
    )


# ---- list_entries(): outdated stays visible ----


def test_list_entries_includes_outdated(db_session):
    token = _TOKEN()
    entry = _entry(db_session, f"Distinctive outdated fact {token}.")
    entry.outdated = True
    db_session.commit()

    listed = atlas.list_entries(db_session)
    assert any(e.id == entry.id for e in listed)


# ---- atlas.search(): outdated excluded by default ----


def test_search_excludes_outdated_entry(db_session):
    token = _TOKEN()
    content = f"Zylthorqu marker {token} prefers midnight coding sessions."
    entry = _entry(db_session, content)
    entry.outdated = True
    db_session.commit()

    results = atlas.search(db_session, content, top_k=5)
    assert entry.id not in [e.id for e, _ in results]


def test_search_includes_non_outdated_entry(db_session):
    token = _TOKEN()
    content = f"Zylthorqu marker {token} prefers early morning coding sessions."
    entry = _entry(db_session, content)

    results = atlas.search(db_session, content, top_k=5)
    assert entry.id in [e.id for e, _ in results]


def test_search_include_outdated_true_returns_it(db_session):
    token = _TOKEN()
    content = f"Zylthorqu marker {token} prefers late-afternoon coding sessions."
    entry = _entry(db_session, content)
    entry.outdated = True
    db_session.commit()

    results = atlas.search(db_session, content, top_k=5, include_outdated=True)
    assert entry.id in [e.id for e, _ in results]


# ---- persona.build_system_prompt(): outdated not injected as a citation ----


def test_outdated_entry_not_injected_into_persona_prompt(db_session):
    token = _TOKEN()
    content = f"Zylthorqu marker {token}'s favorite programming language is Rust."
    entry = _entry(db_session, content)
    entry.outdated = True
    db_session.commit()

    prompt, citations, _nudge, _snippets = persona.build_system_prompt(
        db_session, f"What is Zylthorqu marker {token}'s favorite programming language?", turn_count=0
    )
    assert entry.id not in [c.id for c in citations]
    assert content not in prompt


def test_non_outdated_entry_still_injected_into_persona_prompt(db_session):
    token = _TOKEN()
    content = f"Zylthorqu marker {token}'s favorite programming language is Go."
    entry = _entry(db_session, content)

    prompt, citations, _nudge, _snippets = persona.build_system_prompt(
        db_session, f"What is Zylthorqu marker {token}'s favorite programming language?", turn_count=0
    )
    assert entry.id in [c.id for c in citations]
    assert content in prompt


# ---- memory_conflicts: outdated excluded from normal conflict detection ----


def test_find_conflicts_ignores_outdated_entry_by_default(db_session):
    token = _TOKEN()
    entry = _entry(db_session, f"User {token} prefers coffee.", tags=["drink"])
    entry.outdated = True
    db_session.commit()

    conflicts = memory_conflicts.find_conflicts(
        db_session, content=f"User {token} now prefers tea.", memory_type="fact", tags=["drink"]
    )
    assert entry.id not in [e.id for e in conflicts]


def test_find_conflicts_includes_outdated_when_requested(db_session):
    token = _TOKEN()
    entry = _entry(db_session, f"User {token} prefers coffee.", tags=["drink"])
    entry.outdated = True
    db_session.commit()

    conflicts = memory_conflicts.find_conflicts(
        db_session,
        content=f"User {token} now prefers tea.",
        memory_type="fact",
        tags=["drink"],
        include_outdated=True,
    )
    assert entry.id in [e.id for e in conflicts]


def test_find_conflicts_still_flags_non_outdated_entry(db_session):
    token = _TOKEN()
    entry = _entry(db_session, f"User {token} prefers coffee.", tags=["drink"])

    conflicts = memory_conflicts.find_conflicts(
        db_session, content=f"User {token} now prefers tea.", memory_type="fact", tags=["drink"]
    )
    assert entry.id in [e.id for e in conflicts]


def test_find_all_conflicts_ignores_outdated_pair_by_default(db_session):
    token = _TOKEN()
    a = _entry(db_session, f"User {token} prefers coffee.", tags=["drink"])
    b = _entry(db_session, f"User {token} prefers tea.", tags=["drink"])
    a.outdated = True
    db_session.commit()

    conflicts = memory_conflicts.find_all_conflicts(db_session)
    assert a.id not in conflicts
    assert b.id not in conflicts.get(a.id, [])


def test_find_all_conflicts_includes_outdated_when_requested(db_session):
    token = _TOKEN()
    a = _entry(db_session, f"User {token} prefers coffee.", tags=["drink"])
    b = _entry(db_session, f"User {token} prefers tea.", tags=["drink"])
    a.outdated = True
    db_session.commit()

    conflicts = memory_conflicts.find_all_conflicts(db_session, include_outdated=True)
    assert b.id in conflicts.get(a.id, [])
