import json
import logging
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app import (
    atlas,
    conversation_search,
    library,
    memory_conflicts,
    memory_extraction,
    persona,
    preference_detection,
    schemas,
)
from app import (
    attachments as attachments_lib,
)
from app.config import get_settings
from app.db import get_db
from app.envelope_stream import EnvelopeStreamParser
from app.image_router import clean_unavailable_reason, image_router
from app.models import Attachment, Conversation, MemoryCandidate, MemoryExtractionLog, Message
from app.providers import gemini_provider
from app.providers.base import ChatMessage, ChatResult
from app.router import NoProviderAvailableError, ProviderUnavailableError
from app.router import router as model_router
from app.web_search import GatherResult

router = APIRouter(prefix="/api", tags=["chat"])
logger = logging.getLogger(__name__)

_ROLE_MAP = {"user": "user", "echo": "assistant"}


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"

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

# Keep in sync with which providers actually read ChatMessage.images (currently just
# Gemini — see gemini_provider.py). Used only to decide whether the image note in the
# prompt should invite genuine description or an honest "I can't see images" fallback;
# getting this wrong for a real routing change just costs an honesty nudge, not safety.
_VISION_CAPABLE_PROVIDERS = {"gemini"}


def _will_use_vision_capable_provider(preferred: str) -> bool:
    if preferred != "auto":
        return preferred in _VISION_CAPABLE_PROVIDERS
    for p in model_router.providers:
        available, _ = p.available()
        if available:
            return p.name in _VISION_CAPABLE_PROVIDERS
    return False


def _make_snippet(text: str, query: str, context: int = 40) -> str:
    idx = text.lower().find(query.lower())
    if idx == -1:
        return text[:100]
    start = max(0, idx - context)
    end = min(len(text), idx + len(query) + context)
    snippet = text[start:end]
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet


def _conversation_updated_at(conversation: Conversation):
    if conversation.messages:
        return max(m.created_at for m in conversation.messages)
    return conversation.created_at


def _search_metadata_kwargs(gather_result: GatherResult) -> dict:
    """Shared shape for both the persisted Message row and the API response —
    see app/web_search.py's GatherResult/SourceResult and the matching
    frontend fields on MessageOut/StreamDoneEvent (chatMetadata.ts)."""
    return {
        "sources_used": [asdict(s) for s in gather_result.sources],
        "current_info_intent": gather_result.task_type,
        "search_failure_reason": gather_result.search_failure_reason,
    }


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


def _log_memory_diagnostic(
    db: Session,
    *,
    conversation_id: str | None,
    message_id: str | None,
    explicit_request: bool,
    memory_block_present: bool,
    was_none: bool,
    json_detected: bool,
    parse_succeeded: bool,
    saved: bool,
    rejection_reason: str | None,
) -> None:
    """Records one row per chat turn's memory-extraction attempt for
    GET /api/atlas/diagnostics — best-effort only, must never break the chat
    turn itself if writing the log row fails for some reason."""
    try:
        db.add(
            MemoryExtractionLog(
                conversation_id=conversation_id,
                message_id=message_id,
                explicit_request=explicit_request,
                memory_block_present=memory_block_present,
                was_none=was_none,
                json_detected=json_detected,
                parse_succeeded=parse_succeeded,
                saved=saved,
                rejection_reason=rejection_reason,
            )
        )
        db.commit()
    except Exception:
        logger.warning("Failed to record memory-extraction diagnostic", exc_info=True)
        db.rollback()


def _extract_memory(
    db: Session,
    payload_message: str,
    result: ChatResult,
    *,
    conversation_id: str | None = None,
    message_id: str | None = None,
) -> schemas.MemoryUpdate | None:
    if memory_extraction.is_explicit_remember_request(payload_message):
        content = memory_extraction.extract_explicit_memory(payload_message)
        # Bypasses the model's own MEMORY: judgment entirely — an explicit ask is
        # saved directly from the user's words, so it can't be silently dropped by a
        # flaky extraction call or rate limiting. Also bypasses the memory-candidate
        # review queue below: the user already deliberately asked, there's nothing
        # to review.
        update = _save_memory(
            db,
            content=content,
            explicit=True,
            epistemic_status="Verified",
            confidence=0.95,
            tags=["user-stated"],
            source="explicit user request",
        )
        _log_memory_diagnostic(
            db,
            conversation_id=conversation_id,
            message_id=message_id,
            explicit_request=True,
            memory_block_present=True,
            was_none=False,
            json_detected=False,
            parse_succeeded=True,
            saved=update.saved,
            rejection_reason=None if update.saved else update.error,
        )
        return update

    preference = preference_detection.detect_preference_statement(payload_message)
    if preference is not None:
        # A durable preference/learning-style statement, detected from the
        # user's own words — not "remember that" (handled above), but still
        # deterministic, not dependent on the model choosing to emit a
        # MEMORY: block. Queued for review like any other candidate rather
        # than saved directly: this is an inference about durability from
        # phrasing, not something the user explicitly asked to be remembered.
        conflicts = memory_conflicts.find_conflicts(
            db, content=preference.content, memory_type="preference", tags=preference.tags
        )
        candidate = MemoryCandidate(
            content=preference.content,
            epistemic_status="Verified",
            memory_type="preference",
            tags=preference.tags,
            confidence=0.9,
            source=preference.source,
            conversation_id=conversation_id,
            conflict_with=[c.id for c in conflicts],
        )
        db.add(candidate)
        db.commit()
        _log_memory_diagnostic(
            db,
            conversation_id=conversation_id,
            message_id=message_id,
            explicit_request=False,
            memory_block_present=False,
            was_none=False,
            json_detected=False,
            parse_succeeded=True,
            saved=False,
            rejection_reason=(
                f"Queued as a pending preference candidate ({preference.source}, "
                f"{len(conflicts)} possible conflict(s))"
                if conflicts
                else f"Queued as a pending preference candidate ({preference.source})"
            ),
        )
        return schemas.MemoryUpdate(
            saved=False, explicit=False, pending_review=True, content=preference.content
        )

    parsed, diag = memory_extraction.parse_memory_json_with_diagnostics(result.memory_json)
    if parsed is None:
        _log_memory_diagnostic(
            db,
            conversation_id=conversation_id,
            message_id=message_id,
            explicit_request=False,
            memory_block_present=diag.memory_block_present,
            was_none=diag.was_none,
            json_detected=diag.json_detected,
            parse_succeeded=False,
            saved=False,
            rejection_reason=diag.rejection_reason,
        )
        return None

    # A valid opportunistic candidate is NOT saved straight to Atlas — it's queued
    # for human review (with any plausible conflicts flagged) rather than trusted
    # outright, per the memory-candidate workflow. Explicit requests above are the
    # only path that still saves directly.
    conflicts = memory_conflicts.find_conflicts(
        db, content=parsed["content"], memory_type="fact", tags=parsed["tags"]
    )
    candidate = MemoryCandidate(
        content=parsed["content"],
        epistemic_status=parsed["epistemic_status"],
        memory_type="fact",
        tags=[*parsed["tags"], "auto-extracted"],
        confidence=parsed["confidence"],
        source="auto-extracted from conversation",
        conversation_id=conversation_id,
        conflict_with=[c.id for c in conflicts],
    )
    db.add(candidate)
    db.commit()

    _log_memory_diagnostic(
        db,
        conversation_id=conversation_id,
        message_id=message_id,
        explicit_request=False,
        memory_block_present=True,
        was_none=False,
        json_detected=True,
        parse_succeeded=True,
        saved=False,
        rejection_reason=(
            f"Queued as a pending memory candidate for review ({len(conflicts)} possible conflict(s))"
            if conflicts
            else "Queued as a pending memory candidate for review"
        ),
    )
    return schemas.MemoryUpdate(saved=False, explicit=False, pending_review=True, content=parsed["content"])


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
    prior_user_messages = [m.content for m in conversation.messages if m.role == "user"]

    explicit_remember = memory_extraction.is_explicit_remember_request(payload.message)
    system_prompt, citations, nudge_reason, conversation_snippets, gather_result = persona.build_system_prompt(
        db,
        payload.message,
        turn_count,
        explicit_remember_request=explicit_remember,
        prior_user_messages=prior_user_messages,
        conversation_id=conversation.id,
    )
    history.append(ChatMessage(role="user", content=payload.message))

    try:
        result, provider_used, fallback_note = model_router.chat(
            payload.provider, system_prompt, history, db=db
        )
    except (NoProviderAvailableError, ProviderUnavailableError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    memory_update = _extract_memory(db, payload.message, result, conversation_id=conversation.id)
    snippets_out = [schemas.ConversationSnippetOut.model_validate(s) for s in conversation_snippets]
    search_meta = _search_metadata_kwargs(gather_result)

    user_msg = Message(conversation_id=conversation.id, role="user", content=payload.message)
    echo_msg = Message(
        conversation_id=conversation.id,
        role="echo",
        content=result.text,
        reasoning=result.reasoning,
        provider=provider_used,
        atlas_citations=[c.model_dump() for c in citations],
        fallback_note=fallback_note,
        independence_nudge_reason=nudge_reason,
        conversation_snippets=[s.model_dump(mode="json") for s in snippets_out],
        envelope_status=result.envelope_status,
        envelope_degradation_reason=result.envelope_degradation_reason,
        **search_meta,
    )
    db.add(user_msg)
    db.add(echo_msg)
    db.commit()
    db.refresh(echo_msg)
    conversation_search.index_message(user_msg)
    conversation_search.index_message(echo_msg)

    return schemas.ChatResponse(
        conversation_id=conversation.id,
        message_id=echo_msg.id,
        content=result.text,
        reasoning=result.reasoning,
        provider_used=provider_used,
        atlas_citations=citations,
        memory_update=memory_update,
        fallback_note=fallback_note,
        independence_nudge_reason=nudge_reason,
        conversation_snippets=snippets_out,
        envelope_status=result.envelope_status,
        envelope_degradation_reason=result.envelope_degradation_reason,
        **search_meta,
    )


@router.post("/chat/stream")
def send_chat_message_stream(payload: schemas.ChatRequest, db: Session = Depends(get_db)):
    """Server-Sent Events counterpart to POST /api/chat. Streams only the
    user-facing ANSWER text as `token` events while REASONING/MEMORY stay
    buffered server-side (see app/envelope_stream.py) — never exposed to the
    client, malformed or not. Once the provider's reply is complete, parses the
    full envelope exactly like the non-streaming endpoint, saves the same
    Message rows, and emits one final `done` event carrying everything the
    non-streaming response would have returned. Text-only — attachments still
    go through POST /api/chat/send-with-files."""
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
    prior_user_messages = [m.content for m in conversation.messages if m.role == "user"]

    explicit_remember = memory_extraction.is_explicit_remember_request(payload.message)
    system_prompt, citations, nudge_reason, conversation_snippets, gather_result = persona.build_system_prompt(
        db,
        payload.message,
        turn_count,
        explicit_remember_request=explicit_remember,
        prior_user_messages=prior_user_messages,
        conversation_id=conversation.id,
    )
    history.append(ChatMessage(role="user", content=payload.message))

    conversation_id = conversation.id
    user_message = payload.message
    snippets_out = [schemas.ConversationSnippetOut.model_validate(s) for s in conversation_snippets]
    search_meta = _search_metadata_kwargs(gather_result)

    def event_stream():
        parser = EnvelopeStreamParser()
        provider_used: str | None = None
        fallback_note: str | None = None

        try:
            for raw_chunk, provider, fb_note in model_router.stream_chat(
                payload.provider, system_prompt, history, db=db
            ):
                if provider_used is None:
                    provider_used = provider.name
                    fallback_note = fb_note
                answer_piece = parser.feed(raw_chunk)
                if answer_piece:
                    yield _sse("token", {"text": answer_piece})
        except (NoProviderAvailableError, ProviderUnavailableError, ValueError) as exc:
            yield _sse("error", {"detail": str(exc)})
            return
        except Exception:
            # Full technical detail stays server-side only — see this module's
            # other error branches (e.g. the non-streaming /api/chat's
            # NoProviderAvailableError handling) for the same policy.
            logger.exception("Streaming chat turn failed mid-stream")
            yield _sse("error", {"detail": "Streaming failed. Please try again."})
            return

        try:
            result = parser.result()
            memory_update = _extract_memory(db, user_message, result, conversation_id=conversation_id)

            user_msg = Message(conversation_id=conversation_id, role="user", content=user_message)
            echo_msg = Message(
                conversation_id=conversation_id,
                role="echo",
                content=result.text,
                reasoning=result.reasoning,
                provider=provider_used,
                atlas_citations=[c.model_dump() for c in citations],
                fallback_note=fallback_note,
                independence_nudge_reason=nudge_reason,
                conversation_snippets=[s.model_dump(mode="json") for s in snippets_out],
                envelope_status=result.envelope_status,
                envelope_degradation_reason=result.envelope_degradation_reason,
                **search_meta,
            )
            db.add(user_msg)
            db.add(echo_msg)
            db.commit()
            db.refresh(echo_msg)
            conversation_search.index_message(user_msg)
            conversation_search.index_message(echo_msg)
        except Exception:
            logger.exception("Failed to save streamed chat turn")
            db.rollback()
            yield _sse("error", {"detail": "The completed reply could not be saved. Please try again."})
            return

        yield _sse(
            "done",
            {
                "conversation_id": conversation_id,
                "message_id": echo_msg.id,
                "content": result.text,
                "reasoning": result.reasoning,
                "provider_used": provider_used,
                "atlas_citations": [c.model_dump() for c in citations],
                "memory_update": memory_update.model_dump() if memory_update else None,
                "conversation_snippets": [s.model_dump(mode="json") for s in snippets_out],
                "fallback_note": fallback_note,
                "independence_nudge_reason": nudge_reason,
                "envelope_status": result.envelope_status,
                "envelope_degradation_reason": result.envelope_degradation_reason,
                **search_meta,
            },
        )

    return StreamingResponse(event_stream(), media_type="text/event-stream")


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
    prior_user_messages = [m.content for m in conversation.messages if m.role == "user"]

    explicit_remember = memory_extraction.is_explicit_remember_request(message)
    system_prompt, citations, nudge_reason, conversation_snippets, gather_result = persona.build_system_prompt(
        db,
        message,
        turn_count,
        explicit_remember_request=explicit_remember,
        prior_user_messages=prior_user_messages,
        conversation_id=conversation.id,
    )

    if uploads:
        # Deterministic, rather than hoping the model happens to mention this on its
        # own — the reasoning trace should always state how many files were attached
        # and name any that couldn't be natively read.
        system_prompt += (
            f"\n\nATTACHMENT INSTRUCTIONS: This turn has {len(uploads)} file(s) attached. Your "
            "REASONING section MUST begin by stating this count in the form 'N file(s) attached' "
            "and, if any could not be natively read (see the per-file notes below), name them "
            "explicitly there."
        )

    # If the user attached an image and left the provider on auto, route this turn
    # to Gemini (the only vision-capable provider) when it's actually available,
    # rather than letting auto-mode's normal priority order land on a text-only
    # provider that would have to guess at the image. An explicit pin to a
    # different provider is left alone — that's a deliberate choice, not something
    # to silently override (same "pinned means pinned" rule as the router itself).
    image_mimes = [attachments_lib.guess_mime_type(u.filename or "file", u.content_type) for u, _ in uploads]
    has_image_upload = any(m.startswith("image/") for m in image_mimes)
    effective_provider = provider
    if provider == "auto" and has_image_upload:
        gemini = next((p for p in model_router.providers if p.name == "gemini"), None)
        if gemini is not None:
            available, _ = gemini.available()
            if available:
                effective_provider = "gemini"

    # Fold attachment content into what the model actually sees: real extracted text
    # for files we can read (text/code/PDF), the actual image bytes for images (only
    # Gemini currently has real vision wiring — see gemini_provider.py — other
    # providers just get the text note and will honestly say they can't see it), and
    # an explicit "unsupported" note for anything else, so the model never silently
    # pretends to have read something it didn't.
    prompt_parts = [message] if message.strip() else []
    attachment_records: list[Attachment] = []
    image_payloads: list[tuple[str, bytes]] = []
    device_note = f" (from {device_label})" if device_label else ""
    vision_capable = _will_use_vision_capable_provider(effective_provider)
    for upload, content in uploads:
        filename = upload.filename or "file"
        mime_type = attachments_lib.guess_mime_type(filename, upload.content_type)
        understood = attachments_lib.classify(filename, mime_type)
        extracted = attachments_lib.extract_text_for_prompt(filename, mime_type, content)
        analysis_status = attachments_lib.determine_analysis_status(
            mime_type=mime_type, understood=understood, extracted=extracted, vision_capable=vision_capable
        )
        if mime_type.startswith("image/"):
            image_payloads.append((mime_type, content))
            if vision_capable:
                # Don't hand the model an "I can't see it" excuse when it genuinely can —
                # a prior version of this note included that framing unconditionally, and
                # the model reflexively took the honest-sounding opt-out even though the
                # actual image bytes were right there in the request.
                prompt_parts.append(
                    f"\n[Attached file: {filename} ({mime_type}) — an image, attached below for "
                    "you to look at directly.]"
                )
            else:
                prompt_parts.append(
                    f"\n[Attached file: {filename} ({mime_type}) — an image. You do not have "
                    "image-viewing capability in this context; say so honestly rather than "
                    "guessing at its contents.]"
                )
        elif extracted:
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
                analysis_status=analysis_status,
            )
        )

    combined_message = "\n".join(prompt_parts) if prompt_parts else "(no message text, files attached)"
    history.append(
        ChatMessage(
            role="user",
            content=combined_message + device_note,
            images=image_payloads or None,
        )
    )

    try:
        result, provider_used, fallback_note = model_router.chat(
            effective_provider, system_prompt, history, db=db
        )
    except (NoProviderAvailableError, ProviderUnavailableError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _extract_memory(db, message, result, conversation_id=conversation.id)
    snippets_out = [schemas.ConversationSnippetOut.model_validate(s) for s in conversation_snippets]
    search_meta = _search_metadata_kwargs(gather_result)

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
        fallback_note=fallback_note,
        independence_nudge_reason=nudge_reason,
        conversation_snippets=[s.model_dump(mode="json") for s in snippets_out],
        envelope_status=result.envelope_status,
        envelope_degradation_reason=result.envelope_degradation_reason,
        **search_meta,
    )
    db.add(user_msg)
    db.add(echo_msg)
    db.commit()
    db.refresh(echo_msg)
    conversation_search.index_message(user_msg)
    conversation_search.index_message(echo_msg)

    # The response's `message` is Echo's reply (for the frontend to append/render),
    # but the attachments themselves live on the *user's* message (they uploaded the
    # files, not Echo) — echo_msg.attachments is genuinely empty. Overlay the just-
    # uploaded file list onto the response payload so `message.attachments` matches
    # the documented contract instead of always coming back empty.
    message_out = schemas.MessageOut.model_validate(echo_msg)
    message_out.attachments = [schemas.AttachmentOut.model_validate(a) for a in attachment_records]

    return schemas.SendWithFilesResponse(
        conversation_id=conversation.id,
        message=message_out,
    )


@router.post("/chat/generate-image", response_model=schemas.SendWithFilesResponse)
async def generate_image(
    prompt: str = Form(...),
    conversation_id: str | None = Form(None),
    device_label: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """Deliberately separate from send_chat_message / send_chat_message_with_files —
    this calls a PAID model (Imagen, via gemini_provider.generate_image) and must only
    ever run from an explicit user action, never as a side effect of normal chat."""
    if not prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt is required")

    active_provider, unavailable_reason = image_router.select_provider()
    if active_provider is None:
        # unavailable_reason is internal/log detail — may name a config field
        # like GEMINI_API_KEY or COMFYUI_BASE_URL (see image_router.py) — so
        # it's logged here, never put directly into the HTTP response the
        # frontend renders.
        logger.info("Image generation unavailable: %s", unavailable_reason)
        raise HTTPException(
            status_code=502,
            detail=f"Image generation is unavailable — {clean_unavailable_reason(unavailable_reason)}",
        )
    if active_provider != "gemini":
        # Only Gemini has a real generate() implementation wired up in this
        # build — see app/image_router.py's module docstring for why
        # comfyui/ollama never reach this branch.
        raise HTTPException(
            status_code=502,
            detail=f"Image generation via {active_provider} isn't implemented in this build yet.",
        )

    if conversation_id:
        conversation = db.get(Conversation, conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        conversation = Conversation(title=f"Image: {prompt.strip()[:50]}")
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    try:
        image_bytes = gemini_provider.generate_image(prompt)
    except Exception as exc:
        # Full technical detail (including any raw Imagen API response text) stays
        # server-side only — the chat UI never shows raw provider/API error text.
        logger.warning("Image generation failed: %s", exc)
        clean_detail = (
            "Image generation is unavailable — Gemini isn't configured."
            if "not set" in str(exc).lower()
            else "Image generation is unavailable right now."
        )
        raise HTTPException(status_code=502, detail=clean_detail) from exc

    filename = f"generated-{uuid4().hex[:8]}.png"
    storage_path = attachments_lib.save_to_disk(filename, image_bytes)
    device_note = f" (from {device_label})" if device_label else ""

    user_msg = Message(
        conversation_id=conversation.id,
        role="user",
        content=f"Generate image: {prompt}{device_note}",
    )
    attachment = Attachment(
        filename=filename,
        mime_type="image/png",
        size_bytes=len(image_bytes),
        storage_path=storage_path,
        understood=True,
        generated=True,
    )
    echo_msg = Message(
        conversation_id=conversation.id,
        role="echo",
        content=f'Here\'s the generated image for: "{prompt}"',
        provider="gemini-image",
        attachments=[attachment],
    )
    db.add(user_msg)
    db.add(echo_msg)
    db.commit()
    db.refresh(echo_msg)

    library.register_item(
        db,
        title=f"Generated image: {prompt.strip()[:60]}",
        file_path=storage_path,
        file_type="image",
        source="image_generation",
        conversation_id=conversation.id,
        message_id=echo_msg.id,
        tags=["generated", "gemini"],
        description=prompt.strip(),
    )

    return schemas.SendWithFilesResponse(
        conversation_id=conversation.id,
        message=schemas.MessageOut.model_validate(echo_msg),
    )


@router.get("/chat/search", response_model=list[schemas.ConversationSearchResult])
def search_conversations(q: str = Query(""), db: Session = Depends(get_db)):
    """Plain substring search over conversation titles and message content — distinct
    from Atlas's semantic search, which queries persistent memory, not chat history."""
    query = q.strip()
    if len(query) < 2:
        return []
    query_lower = query.lower()

    results: list[schemas.ConversationSearchResult] = []
    conversations = db.query(Conversation).order_by(Conversation.created_at.desc()).all()
    for conversation in conversations:
        if query_lower in conversation.title.lower():
            results.append(
                schemas.ConversationSearchResult(
                    conversation_id=conversation.id,
                    title=conversation.title,
                    snippet=_make_snippet(conversation.title, query),
                    matched_role="title",
                    updated_at=_conversation_updated_at(conversation),
                )
            )
            continue

        matched_message = next(
            (m for m in conversation.messages if query_lower in m.content.lower()), None
        )
        if matched_message:
            results.append(
                schemas.ConversationSearchResult(
                    conversation_id=conversation.id,
                    title=conversation.title,
                    snippet=_make_snippet(matched_message.content, query),
                    matched_role=matched_message.role,
                    updated_at=_conversation_updated_at(conversation),
                )
            )

    results.sort(key=lambda r: r.updated_at, reverse=True)
    return results


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
        result, _provider_used, _fallback_note = model_router.chat(
            "auto", system_prompt, [ChatMessage(role="user", content="Greet me.")], db=db
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
