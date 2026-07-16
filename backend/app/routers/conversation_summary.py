from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_db
from app.services import conversation_summary

router = APIRouter(prefix="/api/conversations", tags=["conversation-summary"])


@router.post("/{conversation_id}/summarize", response_model=schemas.ConversationSummaryOut)
def summarize(conversation_id: str, payload: schemas.ConversationSummarizeRequest, db: Session = Depends(get_db)):
    summary = conversation_summary.summarize_conversation(db, conversation_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Conversation not found or has no messages yet")
    if payload.save_to_knowledge_vault:
        conversation_summary.summary_to_knowledge_item(db, summary)
    return summary


@router.get("/{conversation_id}/summary", response_model=schemas.ConversationSummaryOut)
def get_summary(conversation_id: str, db: Session = Depends(get_db)):
    summary = conversation_summary.get_summary(db, conversation_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="No summary saved for this conversation yet")
    return summary
