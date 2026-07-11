import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app import atlas, attachments as attachments_lib, memory_extraction, persona, schemas
from app.config import get_settings
from app.db import get_db
from app.models import Attachment, Conversation, Message
from app.providers.base import ChatMessage, ChatResult
from app.router import NoProviderAvailableError, ProviderUnavailableError, router as model_router

router = APIRouter(prefix="/api", tags=["chat"])
logger = logging.getLogger(__name__)

_ROLE_MAP = {"user": "user", "echo": "assistant"}

_WELCOME_PROMPT_WITH_MEMORIES = """You are Echo, a warm, precise AI with persistent memory. The \
user just reopened the app after being away. Below are a few things you remember about them \
from Atlas. Write ONE short, natural sentence welcoming them back — you may reference one or \
two of these naturally if it fits, but don't just list facts robotically, and never state \
anything as fact that isn't listed below. Output only that one sentence: no quotes, no preamble.

Remembered:
{memories}"""

_WELCOME_PROMPT_EMPTY = """You are Echo, a warm, precise AI. The user just opened the app with \
no memories on file yet. Write ONE short, natural, inviting sentence welcoming them and \
inviting them to start talking — don't reference any specific facts since none exist yet. \
Output only that one sentence: no quotes, no preamble."""


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


@router.post("/chat/send-with-files", response_model=schemas.SendWithFilesResponse)
async def send_chat_message_with_files(
    message: str = Form(""),
    conversation_id: str | None = Form(None),
    device_label: str | None = Form(None),
    provider: str = Form("auto"),
    files: list[UploadFile] = File(default_factory=list),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    uploads: list[tuple[UploadFile, bytes]] = []
    total_size = 0
    for f in files:
        content = await f.read()
        total_size += len(content)
        uploads.append((f, content))

    if total_size > settings.max_attachment_bytes:
        limit_mb = settings.max_attachment_bytes // (1024 * 1024)
        raise HTTPException(status_code=413, detail=f"Attachments exceed the {limit_mb}MB limit")

    if not message.strip() and not uploads:
        raise HTTPException(status_code=400, detail="Message text or at least one file is required")

    if conversation_id:
        conversation = db.get(Conversation, conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        title = message.strip()[:60] or (uploads[0][0].filename if uploads else "New conversation")
        conversation = Conversation(title=title[:60])
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    history = [
        ChatMessage(role=_ROLE_MAP[m.role], content=m.content) for m in conversation.messages
    ]
    turn_count = len(conversation.messages)

    explicit_remember = memory_extraction.is_explicit_remember_request(message)
    system_prompt, citations = persona.build_system_prompt(
        db, message, turn_count, explicit_remember_request=explicit_remember
    )

    # Fold attachment content into what the model actually sees: real extracted text
    # for files we can read (text/code/PDF), an explicit "not yet readable" note for
    # types we don't extract from today (see attachments.py docstring), so the model
    # never silently pretends to have seen something it didn't.
    prompt_parts = [message] if message.strip() else []
    attachment_records: list[Attachment] = []
    device_note = f" (from {device_label})" if device_label else ""
    for upload, content in uploads:
        filename = upload.filename or "file"
        mime_type = attachments_lib.guess_mime_type(filename, upload.content_type)
        understood = attachments_lib.classify(filename, mime_type)
        extracted = attachments_lib.extract_text_for_prompt(filename, mime_type, content)
        if extracted:
            prompt_parts.append(f"\n--- Attached file: {filename} ---\n{extracted}")
        elif understood:
            prompt_parts.append(
                f"\n[Attached file: {filename} ({mime_type}) — not yet readable by Echo; "
                "content was not analyzed.]"
            )
        else:
            prompt_parts.append(f"\n[Attached file: {filename} ({mime_type}) — unsupported format.]")
        storage_path = attachments_lib.save_to_disk(filename, content)
        attachment_records.append(
            Attachment(
                filename=filename,
                mime_type=mime_type,
                size_bytes=len(content),
                storage_path=storage_path,
                understood=understood,
            )
        )

    combined_message = "\n".join(prompt_parts) if prompt_parts else "(no message text, files attached)"
    history.append(ChatMessage(role="user", content=combined_message + device_note))

    try:
        result, provider_used = model_router.chat(provider, system_prompt, history)
    except (NoProviderAvailableError, ProviderUnavailableError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _extract_memory(db, message, result)

    user_msg = Message(
        conversation_id=conversation.id,
        role="user",
        content=message if message.strip() else "(files attached)",
        attachments=attachment_records,
    )
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

    return schemas.SendWithFilesResponse(
        conversation_id=conversation.id,
        message=schemas.MessageOut.model_validate(echo_msg),
    )


@router.get("/chat/welcome", response_model=schemas.WelcomeResponse)
def get_welcome_greeting(db: Session = Depends(get_db)):
    memories = atlas.list_entries(db, limit=3)
    # No separate "title" field on Atlas entries — truncate content as a stand-in,
    # matching the same truncation convention used for conversation titles above.
    referenced = [m.content[:60] + ("…" if len(m.content) > 60 else "") for m in memories]

    if memories:
        memory_lines = "\n".join(f"- {m.content}" for m in memories)
        system_prompt = _WELCOME_PROMPT_WITH_MEMORIES.format(memories=memory_lines)
    else:
        system_prompt = _WELCOME_PROMPT_EMPTY

    try:
        result, _provider_used = model_router.chat(
            "auto", system_prompt, [ChatMessage(role="user", content="Greet me.")]
        )
    except (NoProviderAvailableError, ProviderUnavailableError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return schemas.WelcomeResponse(
        greeting=result.text,
        referenced_memories=referenced if memories else [],
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


@router.delete("/conversations/{conversation_id}", response_model=schemas.DeleteConversationResponse)
def delete_conversation(conversation_id: str, db: Session = Depends(get_db)):
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    storage_paths = [a.storage_path for m in conversation.messages for a in m.attachments]
    # Cascades to this conversation's Messages and their Attachments only (see the
    # relationship definitions in models.py) — AtlasEntry has no foreign key to
    # Conversation/Message at all, so Atlas memories are never touched by this.
    db.delete(conversation)
    db.commit()
    for path in storage_paths:
        Path(path).unlink(missing_ok=True)
    return schemas.DeleteConversationResponse(ok=True, deleted_id=conversation_id)
