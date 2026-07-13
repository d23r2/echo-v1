from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import atlas as atlas_store
from app import memory_conflicts, schemas
from app.db import get_db
from app.models import AtlasEntry, MemoryExtractionLog

router = APIRouter(prefix="/api/atlas", tags=["atlas"])


def _get_entry_or_404(db: Session, entry_id: str) -> AtlasEntry:
    entry = db.get(AtlasEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Atlas entry not found")
    return entry


@router.get("", response_model=list[schemas.AtlasEntryOut])
def list_entries(memory_type: str | None = Query(None), db: Session = Depends(get_db)):
    return atlas_store.list_entries(db, memory_type=memory_type)


@router.get("/diagnostics", response_model=list[schemas.MemoryExtractionLogOut])
def list_memory_diagnostics(limit: int = Query(50, le=200), db: Session = Depends(get_db)):
    """Recent memory-extraction outcomes — why Atlas is or isn't remembering
    things — see app/routers/chat.py's _log_memory_diagnostic()."""
    return (
        db.query(MemoryExtractionLog)
        .order_by(MemoryExtractionLog.created_at.desc())
        .limit(limit)
        .all()
    )


@router.get("/conflicts", response_model=dict[str, list[str]])
def list_conflicts(db: Session = Depends(get_db)):
    """Entry id -> conflicting entry ids, computed pairwise across the whole
    Atlas using the same local word/tag-overlap heuristic as memory-candidate
    conflict detection (see app/memory_conflicts.py)."""
    return memory_conflicts.find_all_conflicts(db)


@router.get("/search", response_model=list[schemas.AtlasSearchResult])
def search_entries(q: str = Query(..., min_length=1), top_k: int = 5, db: Session = Depends(get_db)):
    results = atlas_store.search(db, q, top_k=top_k)
    return [
        schemas.AtlasSearchResult(**schemas.AtlasEntryOut.model_validate(entry).model_dump(), distance=distance)
        for entry, distance in results
    ]


@router.post("", response_model=schemas.AtlasEntryOut)
def create_entry(payload: schemas.AtlasEntryCreate, db: Session = Depends(get_db)):
    return atlas_store.create_entry(db, payload)


@router.patch("/{entry_id}", response_model=schemas.AtlasEntryOut)
def update_entry(entry_id: str, payload: schemas.AtlasEntryUpdate, db: Session = Depends(get_db)):
    entry = _get_entry_or_404(db, entry_id)
    return atlas_store.update_entry(db, entry, payload)


@router.delete("/{entry_id}", status_code=204)
def delete_entry(entry_id: str, db: Session = Depends(get_db)):
    entry = _get_entry_or_404(db, entry_id)
    atlas_store.delete_entry(db, entry)


@router.post("/merge", response_model=schemas.AtlasEntryOut)
def merge_entries(payload: schemas.AtlasMergeRequest, db: Session = Depends(get_db)):
    if payload.keep_id == payload.remove_id:
        raise HTTPException(status_code=400, detail="Cannot merge an entry with itself")
    keep = _get_entry_or_404(db, payload.keep_id)
    remove = _get_entry_or_404(db, payload.remove_id)
    return atlas_store.merge_entries(db, keep, remove, payload.merged_content)
