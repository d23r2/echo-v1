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
    return entry


def update_entry(db: Session, entry: models.AtlasEntry, data: schemas.AtlasEntryUpdate) -> models.AtlasEntry:
    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(entry, field, value)
    db.commit()
    db.refresh(entry)
    if "content" in updates or "epistemic_status" in updates:
        _upsert_chroma(entry)
    return entry


def delete_entry(db: Session, entry: models.AtlasEntry) -> None:
    entry_id = entry.id
    db.delete(entry)
    db.commit()
    try:
        _get_collection().delete(ids=[entry_id])
    except Exception:
        pass


def list_entries(
    db: Session, limit: int = 200, memory_type: str | None = None
) -> list[models.AtlasEntry]:
    query = db.query(models.AtlasEntry)
    if memory_type:
        query = query.filter(models.AtlasEntry.memory_type == memory_type)
    return query.order_by(models.AtlasEntry.created_at.desc()).limit(limit).all()


def search(db: Session, query: str, top_k: int = 5) -> list[tuple[models.AtlasEntry, float]]:
    collection = _get_collection()
    if collection.count() == 0:
        return []
    result = collection.query(query_texts=[query], n_results=min(top_k, collection.count()))
    ids = result.get("ids", [[]])[0]
    distances = result.get("distances", [[]])[0]

    rows_by_id = {
        row.id: row
        for row in db.query(models.AtlasEntry).filter(models.AtlasEntry.id.in_(ids)).all()
    }

    hydrated: list[tuple[models.AtlasEntry, float]] = []
    for entry_id, distance in zip(ids, distances):
        row = rows_by_id.get(entry_id)
        if row is not None:
            hydrated.append((row, distance))
    return hydrated
