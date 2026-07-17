"""ECHO Layer 1 — Local Embedding / Vector Index status (Phase 9).

ECHO already uses a local embedding model (sentence-transformers
all-MiniLM-L6-v2 via ChromaDB, see atlas.py) — this module doesn't add a
second index, it adds *visibility* into the one that already exists:
status/orphan-detection/rebuild/repair, all read-only or additive
operations over atlas.py's existing collection.
"""

import logging

from sqlalchemy.orm import Session

from app import atlas
from app.config import get_settings
from app.models import AtlasEntry

logger = logging.getLogger(__name__)

_EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # matches atlas.py's SentenceTransformerEmbeddingFunction


def status(db: Session) -> dict:
    settings = get_settings()
    try:
        collection = atlas._get_collection()
        chroma_count = collection.count()
        healthy = True
        error: str | None = None
    except Exception as exc:
        chroma_count = 0
        healthy = False
        error = str(exc)

    sql_count = db.query(AtlasEntry).count()
    return {
        "backend": "chromadb",
        "collection": "atlas",
        "embedding_model": _EMBEDDING_MODEL,
        "persist_dir": settings.chroma_dir,
        "healthy": healthy,
        "error": error,
        "sql_row_count": sql_count,
        "indexed_count": chroma_count,
        "in_sync": healthy and sql_count == chroma_count,
    }


def find_orphans(db: Session) -> dict:
    """Returns {"missing_from_index": [...], "orphaned_in_index": [...]} —
    SQL rows with no Chroma vector, and Chroma vectors with no SQL row,
    respectively. Never raises — an unreachable Chroma degrades to reporting
    everything as "missing" rather than crashing the caller."""
    sql_ids = {row.id for row in db.query(AtlasEntry.id).all()}
    try:
        collection = atlas._get_collection()
        chroma_ids = set(collection.get()["ids"])
    except Exception:
        logger.warning("Could not reach the vector index while checking for orphans", exc_info=True)
        return {"missing_from_index": sorted(sql_ids), "orphaned_in_index": []}

    return {
        "missing_from_index": sorted(sql_ids - chroma_ids),
        "orphaned_in_index": sorted(chroma_ids - sql_ids),
    }


def repair_index(db: Session) -> dict:
    """Re-embeds every SQL row missing from the index, and removes every
    Chroma vector with no corresponding SQL row. Idempotent — running this
    twice with no intervening change does nothing the second time."""
    orphans = find_orphans(db)
    repaired = 0
    removed = 0

    if orphans["missing_from_index"]:
        rows = db.query(AtlasEntry).filter(AtlasEntry.id.in_(orphans["missing_from_index"])).all()
        for row in rows:
            try:
                atlas._upsert_chroma(row)
                repaired += 1
            except Exception:
                logger.warning("Failed to re-index memory %s", row.id, exc_info=True)

    if orphans["orphaned_in_index"]:
        try:
            atlas._get_collection().delete(ids=orphans["orphaned_in_index"])
            removed = len(orphans["orphaned_in_index"])
        except Exception:
            logger.warning("Failed to remove orphaned index entries", exc_info=True)

    return {"repaired": repaired, "removed": removed}


def rebuild_index(db: Session) -> dict:
    """Re-embeds every active AtlasEntry row from scratch — for recovering
    from a corrupted/deleted Chroma directory, or after an embedding model
    change. Does not touch SQL data (source of truth, untouched)."""
    rows = db.query(AtlasEntry).all()
    rebuilt = 0
    failed = 0
    for row in rows:
        try:
            atlas._upsert_chroma(row)
            rebuilt += 1
        except Exception:
            logger.warning("Failed to rebuild index for memory %s", row.id, exc_info=True)
            failed += 1
    return {"rebuilt": rebuilt, "failed": failed}
