"""Atlas: persistent memory system with semantic search.

SQLite (via SQLAlchemy `AtlasEntry`) is the source of truth for all fields.
ChromaDB (local, persistent, sentence-transformers embeddings) mirrors just
`id -> content` for semantic recall; every write path below keeps both in
sync so a Chroma rebuild is always possible by re-embedding SQL rows.
"""

from functools import lru_cache

import chromadb
from chromadb.utils import embedding_functions
from sqlalchemy.orm import Session

from app import models, schemas
from app.config import get_settings

_COLLECTION_NAME = "atlas"


def _invalidate_persona_if_preference(*entries: models.AtlasEntry, reason: str) -> None:
    if not any(entry.category == "preference" for entry in entries):
        return
    from app.services import persona_service

    persona_service.invalidate_persona_cache(reason=reason)

# ECHO Layer 1 — maps the legacy `memory_type` taxonomy (fact|preference|mood|
# goal|fear|capability|project|relationship|event) to the new `category`
# taxonomy (profile|preference|project|task|episodic|semantic|skill|
# relationship|environment|temporary), used both for legacy-row backfill and
# for new writes that only specify the old field. Kept as a plain module-level
# dict (not a DB migration) — a compatibility adapter, per Phase 1 rule 4.
_LEGACY_TYPE_TO_CATEGORY = {
    "fact": "semantic",
    "preference": "preference",
    "mood": "episodic",
    "goal": "task",
    "fear": "episodic",
    "capability": "skill",
    "project": "project",
    "relationship": "relationship",
    "event": "episodic",
}


def legacy_type_to_category(memory_type: str | None) -> str:
    return _LEGACY_TYPE_TO_CATEGORY.get(memory_type or "fact", "semantic")


@lru_cache
def _get_collection():
    settings = get_settings()
    client = chromadb.PersistentClient(path=settings.chroma_dir)
    embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    return client.get_or_create_collection(name=_COLLECTION_NAME, embedding_function=embedding_fn)


def _upsert_chroma(entry: models.AtlasEntry) -> None:
    _get_collection().upsert(
        ids=[entry.id],
        documents=[entry.content],
        metadatas=[{"epistemic_status": entry.epistemic_status}],
    )


def create_entry(db: Session, data: schemas.AtlasEntryCreate) -> models.AtlasEntry:
    entry = models.AtlasEntry(
        content=data.content,
        epistemic_status=data.epistemic_status,
        memory_type=data.memory_type,
        tags=data.tags,
        confidence=data.confidence,
        source=data.source,
        valid_until=data.valid_until,
        # ECHO Layer 1 — category defaults from the legacy memory_type when the
        # caller doesn't specify one, so every existing create_entry() call
        # site (none of which know about `category` yet) still gets a sane
        # value instead of the raw column default.
        category=data.category or legacy_type_to_category(data.memory_type),
        importance=data.importance or "medium",
        stability=data.stability or "semi_stable",
        retention_policy=data.retention_policy or "periodic_review",
        capture_method=data.capture_method or "manual_entry",
        project_id=data.project_id,
        task_id=data.task_id,
        source_type=data.source_type,
        source_reference=data.source_reference,
        expires_at=data.expires_at,
        verification_status="verified" if data.epistemic_status == "Verified" else "unverified",
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    try:
        _upsert_chroma(entry)
    except Exception:
        # Keep SQL and Chroma in sync: don't leave a SQL-only row that can never
        # be found by semantic search if embedding the memory fails.
        db.delete(entry)
        db.commit()
        raise
    _invalidate_persona_if_preference(entry, reason="preference_created")
    return entry


def update_entry(db: Session, entry: models.AtlasEntry, data: schemas.AtlasEntryUpdate) -> models.AtlasEntry:
    was_preference = entry.category == "preference"
    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(entry, field, value)
    db.commit()
    db.refresh(entry)
    if "content" in updates or "epistemic_status" in updates:
        _upsert_chroma(entry)
    if was_preference or entry.category == "preference":
        _invalidate_persona_if_preference(entry, reason="preference_updated")
    return entry


def merge_entries(
    db: Session, keep: models.AtlasEntry, remove: models.AtlasEntry, merged_content: str | None = None
) -> models.AtlasEntry:
    """Fold `remove` into `keep`: keep the higher confidence of the two, optionally
    take an edited combined content string, then delete `remove`. Deliberately
    simple — no attempt at automatic content merging beyond what the caller supplies."""
    if merged_content:
        keep.content = merged_content
    keep.confidence = max(keep.confidence, remove.confidence)
    db.commit()
    db.refresh(keep)
    _upsert_chroma(keep)
    delete_entry(db, remove)
    _invalidate_persona_if_preference(keep, remove, reason="preference_merged")
    return keep


def delete_entry(db: Session, entry: models.AtlasEntry) -> None:
    entry_id = entry.id
    was_preference = entry.category == "preference"
    # ECHO Layer 1 (Phase 17, rule 18) — deleting a memory must safely
    # deactivate its relationships, not leave dangling MemoryRelationship
    # rows pointing at an id that no longer exists. Deactivate (not delete)
    # the edges themselves, matching this table's own audit-friendly design.
    db.query(models.MemoryRelationship).filter(
        (models.MemoryRelationship.source_memory_id == entry_id)
        | (models.MemoryRelationship.target_memory_id == entry_id)
    ).update({"status": "deactivated"}, synchronize_session=False)
    db.delete(entry)
    db.commit()
    try:
        _get_collection().delete(ids=[entry_id])
    except Exception:
        pass
    if was_preference:
        from app.services import persona_service

        persona_service.invalidate_persona_cache(reason="preference_deleted")


def list_entries(
    db: Session, limit: int = 200, memory_type: str | None = None
) -> list[models.AtlasEntry]:
    query = db.query(models.AtlasEntry)
    if memory_type:
        query = query.filter(models.AtlasEntry.memory_type == memory_type)
    return query.order_by(models.AtlasEntry.created_at.desc()).limit(limit).all()


def search(
    db: Session, query: str, top_k: int = 5, include_outdated: bool = False
) -> list[tuple[models.AtlasEntry, float]]:
    """Semantic search over Atlas. Outdated entries (AtlasEntry.outdated=True)
    are excluded by default — an entry marked outdated is a deliberate "don't
    treat this as current" signal (see routers/atlas.py's update endpoint),
    and normal search/persona prompt-injection/conflict-detection should
    honor that rather than still surfacing it as relevant. It stays fully
    visible via list_entries() (the Atlas UI list) regardless of this flag —
    only *retrieval as a relevant/current memory* is affected. Pass
    include_outdated=True for the rare case that genuinely wants it back
    (e.g. an audit view).

    Outdated rows are filtered out after Chroma's nearest-neighbor query, so
    this over-fetches (same 3x pattern conversation_search.py's semantic_search
    already uses for its own post-query distance filtering) to make it
    unlikely that filtering leaves fewer than top_k real results just because
    a few of the nearest matches happened to be outdated."""
    collection = _get_collection()
    if collection.count() == 0:
        return []
    fetch_n = min(top_k * 3, collection.count()) if not include_outdated else min(top_k, collection.count())
    result = collection.query(query_texts=[query], n_results=fetch_n)
    ids = result.get("ids", [[]])[0]
    distances = result.get("distances", [[]])[0]

    rows_by_id = {
        row.id: row
        for row in db.query(models.AtlasEntry).filter(models.AtlasEntry.id.in_(ids)).all()
    }

    hydrated: list[tuple[models.AtlasEntry, float]] = []
    for entry_id, distance in zip(ids, distances, strict=True):
        row = rows_by_id.get(entry_id)
        if row is None:
            continue
        if row.outdated and not include_outdated:
            continue
        hydrated.append((row, distance))
        if len(hydrated) >= top_k:
            break
    return hydrated
