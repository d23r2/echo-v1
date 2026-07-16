from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_db
from app.services import knowledge_vault

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("", response_model=list[schemas.KnowledgeItemOut])
def list_knowledge(item_type: str | None = Query(None), db: Session = Depends(get_db)):
    return knowledge_vault.list_items(db, item_type=item_type)


@router.get("/search", response_model=list[schemas.KnowledgeItemOut])
def search_knowledge(q: str = Query(...), db: Session = Depends(get_db)):
    return knowledge_vault.search_items(db, q)


@router.post("", response_model=schemas.KnowledgeItemOut)
def create_knowledge(payload: schemas.KnowledgeItemCreate, db: Session = Depends(get_db)):
    try:
        return knowledge_vault.create_item(db, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.get("/{item_id}", response_model=schemas.KnowledgeItemOut)
def get_knowledge(item_id: str, db: Session = Depends(get_db)):
    item = knowledge_vault.get_item(db, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Knowledge item not found")
    return item


@router.patch("/{item_id}", response_model=schemas.KnowledgeItemOut)
def update_knowledge(item_id: str, payload: schemas.KnowledgeItemUpdate, db: Session = Depends(get_db)):
    try:
        return knowledge_vault.update_item(db, item_id, payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.delete("/{item_id}", response_model=schemas.KnowledgeItemOut)
def archive_knowledge(item_id: str, db: Session = Depends(get_db)):
    try:
        return knowledge_vault.archive_item(db, item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
