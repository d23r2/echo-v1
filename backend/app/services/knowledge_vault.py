"""ECHO Action + Reliability Core v1 — Personal Knowledge Vault.

User-visible, user-editable knowledge (notes, decisions, prompts, release
notes, ...) — distinct from Atlas, which is internal/adaptive memory the
user never directly edits. Nothing here is written silently from chat;
every item is either a deliberate user action or an explicit action/tool
call (create_knowledge_note, save-summary-to-vault) that the user asked for.
"""

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import KnowledgeItem, _now


def create_item(
    db: Session,
    *,
    title: str,
    body: str = "",
    item_type: str = "note",
    source_type: str | None = None,
    source_id: str | None = None,
    project_id: str | None = None,
    task_id: str | None = None,
    tags: list[str] | None = None,
    confidence: str = "medium",
) -> KnowledgeItem:
    if not title.strip():
        raise ValueError("A title is required.")
    item = KnowledgeItem(
        title=title.strip(),
        body=body,
        item_type=item_type,
        source_type=source_type,
        source_id=source_id,
        project_id=project_id,
        task_id=task_id,
        tags=tags or [],
        confidence=confidence,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def list_items(db: Session, item_type: str | None = None, include_archived: bool = False) -> list[KnowledgeItem]:
    query = db.query(KnowledgeItem)
    if not include_archived:
        query = query.filter(KnowledgeItem.archived_at.is_(None))
    if item_type:
        query = query.filter(KnowledgeItem.item_type == item_type)
    return query.order_by(KnowledgeItem.updated_at.desc()).all()


def get_item(db: Session, item_id: str) -> KnowledgeItem | None:
    return db.get(KnowledgeItem, item_id)


def update_item(db: Session, item_id: str, updates: dict) -> KnowledgeItem:
    item = db.get(KnowledgeItem, item_id)
    if item is None:
        raise ValueError("That knowledge item doesn't exist.")
    for field, value in updates.items():
        if value is not None:
            setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return item


def archive_item(db: Session, item_id: str) -> KnowledgeItem:
    item = db.get(KnowledgeItem, item_id)
    if item is None:
        raise ValueError("That knowledge item doesn't exist.")
    item.archived_at = _now()
    db.commit()
    db.refresh(item)
    return item


def search_items(db: Session, query: str, include_archived: bool = False) -> list[KnowledgeItem]:
    q = db.query(KnowledgeItem)
    if not include_archived:
        q = q.filter(KnowledgeItem.archived_at.is_(None))
    like = f"%{query.strip()}%"
    return q.filter(or_(KnowledgeItem.title.ilike(like), KnowledgeItem.body.ilike(like))).order_by(KnowledgeItem.updated_at.desc()).all()
