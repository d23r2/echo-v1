from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import persona, schemas
from app.db import get_db
from app.models import Conversation, Message
from app.providers.base import ChatMessage
from app.router import NoProviderAvailableError, ProviderUnavailableError, router as model_router

router = APIRouter(prefix="/api", tags=["chat"])

_ROLE_MAP = {"user": "user", "echo": "assistant"}


@router.post("/chat", response_model=schemas.ChatResponse)
def send_chat_message(payload: schemas.ChatRequest, db: Session = Depends(get_db)):
    if payload.conversation_id:
        conversation = db.get(Conversation, payload.conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        title = payload.message.strip()[:60] or "New conversation"
        conversation = Conversation(title=title)
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    history = [
        ChatMessage(role=_ROLE_MAP[m.role], content=m.content) for m in conversation.messages
    ]
    turn_count = len(conversation.messages)

    system_prompt, citations = persona.build_system_prompt(db, payload.message, turn_count)
    history.append(ChatMessage(role="user", content=payload.message))

    try:
        result, provider_used = model_router.chat(payload.provider, system_prompt, history)
    except (NoProviderAvailableError, ProviderUnavailableError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user_msg = Message(conversation_id=conversation.id, role="user", content=payload.message)
    echo_msg = Message(
        conversation_id=conversation.id,
        role="echo",
        content=result.text,
        reasoning=result.reasoning,
        provider=provider_used,
        atlas_citations=[c.model_dump() for c in citations],
    )
    db.add(user_msg)
    db.add(echo_msg)
    db.commit()
    db.refresh(echo_msg)

    return schemas.ChatResponse(
        conversation_id=conversation.id,
        message_id=echo_msg.id,
        content=result.text,
        reasoning=result.reasoning,
        provider_used=provider_used,
        atlas_citations=citations,
    )


@router.get("/conversations", response_model=list[schemas.ConversationOut])
def list_conversations(db: Session = Depends(get_db)):
    return db.query(Conversation).order_by(Conversation.created_at.desc()).all()


@router.get("/conversations/{conversation_id}", response_model=schemas.ConversationDetailOut)
def get_conversation(conversation_id: str, db: Session = Depends(get_db)):
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation
