from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import atlas as atlas_store
from app import schemas
from app.db import get_db
from app.models import AtlasEntry

router = APIRouter(prefix="/api/atlas", tags=["atlas"])


def _get_entry_or_404(db: Session, entry_id: str) -> AtlasEntry:
    entry = db.get(AtlasEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Atlas entry not found")
    return entry


@router.get("", response_model=list[schemas.AtlasEntryOut])
def list_entries(db: Session = Depends(get_db)):
    return atlas_store.list_entries(db)


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
