"""Registers files Echo produces or receives into the Library (Phase 5) so
they can be listed/searched/filtered in one place instead of scattered across
conversations and the filesystem. Called by whatever code path actually
produces a file (image generation, self-improvement reports, health reports,
conversation exports) — never inferred after the fact by scanning disk.
"""

from sqlalchemy.orm import Session

from app.models import LibraryItem


def register_item(
    db: Session,
    *,
    title: str,
    file_path: str,
    file_type: str,
    source: str,
    conversation_id: str | None = None,
    message_id: str | None = None,
    tags: list[str] | None = None,
    description: str | None = None,
    metadata: dict | None = None,
) -> LibraryItem:
    item = LibraryItem(
        title=title,
        file_path=file_path,
        file_type=file_type,
        source=source,
        conversation_id=conversation_id,
        message_id=message_id,
        tags=tags or [],
        description=description,
        metadata_json=metadata or {},
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item
