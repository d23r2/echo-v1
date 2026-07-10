import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import atlas, memory_extraction, persona, schemas
from app.db import get_db
from app.models import Conversation, Message
from app.providers.base import ChatMessage, ChatResult
from app.router import NoProviderAvailableError, ProviderUnavailableError, router as model_router

router = APIRouter(prefix="/api", tags=["chat"])
logger = logging.getLogger(__name__)

_ROLE_MAP = {"user": "user", "echo": "assistant"}


def _save_memory(db: Session, *, content: str, explicit: bool, epistemic_status: str, confidence: float, tags: list[str], source: str) -> schemas.MemoryUpdate:
    try:
        entry = atlas.create_entry(
            db,
            schemas.AtlasEntryCreate(
                content=content,
                epistemic_status=epistemic_status,
                confidence=confidence,
                tags=tags,
                source=source,
            ),
        )
        return schemas.MemoryUpdate(saved=True, explicit=explicit, content=entry.content)
    except Exception as exc:
        logger.warning("Atlas memory save failed (explicit=%s): %s", explicit, exc)
        return schemas.MemoryUpdate(saved=False, explicit=explicit, content=content, error=str(exc))


def _extract_memory(db: Session, payload_message: str, result: ChatResult) -> schemas.MemoryUpdate | None:
    if memory_extraction.is_explicit_remember_request(payload_message):
        content = memory_extraction.extract_explicit_memory(payload_message)
        # Bypasses the model's own MEMORY: judgment entirely — an explicit ask is
        # saved directly from the user's words, so it can't be silently dropped by a
        # flaky extraction call or rate limiting.
        return _save_memory(
            db,
            content=content,
            explicit=True,
            epistemic_status="Verified",
            confidence=0.95,
            tags=["user-stated"],
            source="explicit user request",
        )

    parsed = memory_extraction.parse_memory_json(result.memory_json)
    if parsed is None:
        return None
    return _save_memory(
        db,
        content=parsed["content"],
        explicit=False,
        epistemic_status=parsed["epistemic_status"],
        confidence=parsed["confidence"],
        tags=[*parsed["tags"], "auto-extracted"],
        source="auto-extracted from conversation",
    )


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

    explicit_remember = memory_extraction.is_explicit_remember_request(payload.message)
    system_prompt, citations = persona.build_system_prompt(
        db, payload.message, turn_count, explicit_remember_request=explicit_remember
    )
    history.append(ChatMessage(role="user", content=payload.message))

    try:
        result, provider_used = model_router.chat(payload.provider, system_prompt, history)
    except (NoProviderAvailableError, ProviderUnavailableError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    memory_update = _extract_memory(db, payload.message, result)

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
        memory_update=memory_update,
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
