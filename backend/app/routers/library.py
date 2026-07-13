import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import schemas
from app.config import get_settings
from app.db import get_db
from app.models import LibraryItem

router = APIRouter(prefix="/api/library", tags=["library"])
logger = logging.getLogger(__name__)


def _resolve_within_attachments(file_path: str) -> Path | None:
    """Resolves file_path and confirms it's inside the configured attachments
    directory — the same guard used by delete_library_item, factored out so
    the download route can't be pointed at an arbitrary filesystem path via a
    corrupted/tampered row."""
    settings = get_settings()
    try:
        attachments_root = Path(settings.attachments_dir).resolve()
        target = Path(file_path).resolve()
    except OSError:
        return None
    if not target.is_relative_to(attachments_root):
        return None
    return target


@router.get("", response_model=list[schemas.LibraryItemOut])
def list_library_items(
    q: str = Query(""),
    file_type: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Newest first. `q` matches title/description (simple substring, same
    honesty tier as conversation search — no semantic ranking claimed here)."""
    query = db.query(LibraryItem)
    if file_type:
        query = query.filter(LibraryItem.file_type == file_type)
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(or_(LibraryItem.title.ilike(like), LibraryItem.description.ilike(like)))
    return query.order_by(LibraryItem.created_at.desc()).all()


@router.get("/{item_id}", response_model=schemas.LibraryItemOut)
def get_library_item(item_id: str, db: Session = Depends(get_db)):
    item = db.get(LibraryItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Library item not found")
    return item


@router.get("/{item_id}/download")
def download_library_item(item_id: str, db: Session = Depends(get_db)):
    item = db.get(LibraryItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Library item not found")
    target = _resolve_within_attachments(item.file_path)
    if target is None or not target.exists():
        raise HTTPException(status_code=404, detail="The underlying file is no longer available.")
    return FileResponse(target, filename=target.name)


@router.delete("/{item_id}")
def delete_library_item(item_id: str, db: Session = Depends(get_db)):
    """Removes the DB row and best-effort deletes the underlying file, scoped
    to the app's own attachments directory only — never follows file_path
    outside that root, so a corrupted/tampered row can't be used to delete an
    arbitrary file on disk."""
    item = db.get(LibraryItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Library item not found")

    try:
        target = _resolve_within_attachments(item.file_path)
        if target is not None and target.exists():
            target.unlink()
    except OSError as exc:
        logger.warning("Failed to delete library item file %s: %s", item.file_path, exc)
    except Exception as exc:
        logger.warning("Unexpected error deleting library item file %s: %s", item.file_path, exc)

    db.delete(item)
    db.commit()
    return {"deleted": True}
