from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import human_persona, schemas
from app.db import get_db
from app.models import Conversation, ConversationMoodState, ConversationThreadState
from app.services import persona_service
from app.tester import get_tester_id

router = APIRouter(prefix="/api", tags=["human-persona"])


def _tester_conversation(db: Session, conversation_id: str, tester_id: str) -> Conversation:
    """404s if the conversation doesn't exist OR belongs to a different
    tester — the same response either way, so this endpoint can never be
    used to probe whether a conversation id exists for someone else."""
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.tester_id != tester_id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.get("/persona-settings", response_model=schemas.PersonaSettingsOut)
def get_persona_settings(db: Session = Depends(get_db), tester_id: str = Depends(get_tester_id)):
    return human_persona.get_or_create_persona_settings(db, tester_id)


@router.patch("/persona-settings", response_model=schemas.PersonaSettingsOut)
def update_persona_settings(
    payload: schemas.PersonaSettingsUpdate,
    db: Session = Depends(get_db),
    tester_id: str = Depends(get_tester_id),
):
    return human_persona.update_persona_settings(db, tester_id, payload)


@router.post("/persona-settings/reset", response_model=schemas.PersonaSettingsOut)
def reset_persona_settings(db: Session = Depends(get_db), tester_id: str = Depends(get_tester_id)):
    """Deletes this tester's PersonaSettings row and recreates it with fresh
    defaults — Phase 16's "Reset human persona layer" action. Does not touch
    RelationshipProfile (a separate, more durable resource) or any other
    tester's data."""
    existing = human_persona.get_or_create_persona_settings(db, tester_id)
    db.delete(existing)
    db.commit()
    persona_service.invalidate_persona_cache(tester_id, reason="settings_reset")
    return human_persona.get_or_create_persona_settings(db, tester_id)


@router.get("/relationship-profile", response_model=schemas.RelationshipProfileOut)
def get_relationship_profile(db: Session = Depends(get_db), tester_id: str = Depends(get_tester_id)):
    return human_persona.get_or_create_relationship_profile(db, tester_id)


@router.patch("/relationship-profile", response_model=schemas.RelationshipProfileOut)
def update_relationship_profile(
    payload: schemas.RelationshipProfileUpdate,
    db: Session = Depends(get_db),
    tester_id: str = Depends(get_tester_id),
):
    try:
        return human_persona.update_relationship_profile(db, tester_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/persona/runtime", response_model=schemas.PersonaRuntimeOut)
def get_persona_runtime(
    context_type: str = Query("general_chat"),
    conversation_id: str | None = Query(None),
    db: Session = Depends(get_db),
    tester_id: str = Depends(get_tester_id),
):
    """Safe resolved-style inspection. No raw memory, prompt, ids, scores,
    conflict trace, fingerprint, or hidden reasoning is returned."""
    conversation = _tester_conversation(db, conversation_id, tester_id) if conversation_id else None
    resolved = persona_service.resolve_persona(
        db,
        "",
        tester_id=tester_id,
        context_type=context_type,
        conversation=conversation,
    )
    brief = persona_service.build_persona_brief(resolved)
    return persona_service.get_safe_persona_runtime(resolved, brief)


@router.post("/persona/runtime/refresh", response_model=schemas.PersonaRuntimeOut)
def refresh_persona_runtime(
    db: Session = Depends(get_db),
    tester_id: str = Depends(get_tester_id),
):
    persona_service.invalidate_persona_cache(tester_id, reason="api_refresh")
    resolved = persona_service.resolve_persona(db, "", tester_id=tester_id)
    brief = persona_service.build_persona_brief(resolved)
    return persona_service.get_safe_persona_runtime(resolved, brief)


@router.get("/persona/health", response_model=schemas.PersonaHealthOut)
def get_persona_health():
    return persona_service.get_safe_persona_diagnostics()


@router.get("/rituals", response_model=list[schemas.PersonalRitualOut])
def list_rituals(db: Session = Depends(get_db), tester_id: str = Depends(get_tester_id)):
    return human_persona.get_or_create_rituals(db, tester_id)


@router.patch("/rituals/{ritual_type}", response_model=schemas.PersonalRitualOut)
def update_ritual(
    ritual_type: str,
    payload: schemas.PersonalRitualUpdate,
    db: Session = Depends(get_db),
    tester_id: str = Depends(get_tester_id),
):
    if ritual_type not in human_persona.ALL_RITUAL_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown ritual type '{ritual_type}'")
    human_persona.get_or_create_rituals(db, tester_id)  # ensures the row exists
    ritual = human_persona.update_ritual(db, tester_id, ritual_type, payload)
    if ritual is None:
        raise HTTPException(status_code=404, detail="Ritual not found")
    return ritual


@router.get("/conversations/{conversation_id}/mode", response_model=schemas.ConversationModeOut)
def get_conversation_mode(
    conversation_id: str, db: Session = Depends(get_db), tester_id: str = Depends(get_tester_id)
):
    conversation = _tester_conversation(db, conversation_id, tester_id)
    settings = human_persona.get_or_create_persona_settings(db, tester_id)
    return schemas.ConversationModeOut(
        conversation_id=conversation.id,
        active_operational_mode=conversation.active_operational_mode,
        default_operational_mode=settings.default_operational_mode,
        session_style_override=conversation.session_style_override or {},
    )


@router.patch("/conversations/{conversation_id}/mode", response_model=schemas.ConversationModeOut)
def set_conversation_mode(
    conversation_id: str,
    payload: schemas.ConversationModeUpdate,
    db: Session = Depends(get_db),
    tester_id: str = Depends(get_tester_id),
):
    conversation = _tester_conversation(db, conversation_id, tester_id)
    conversation.active_operational_mode = payload.mode
    db.commit()
    db.refresh(conversation)
    settings = human_persona.get_or_create_persona_settings(db, tester_id)
    return schemas.ConversationModeOut(
        conversation_id=conversation.id,
        active_operational_mode=conversation.active_operational_mode,
        default_operational_mode=settings.default_operational_mode,
        session_style_override=conversation.session_style_override or {},
    )


@router.get("/conversations/{conversation_id}/mood", response_model=schemas.ConversationMoodStateOut)
def get_conversation_mood(
    conversation_id: str, db: Session = Depends(get_db), tester_id: str = Depends(get_tester_id)
):
    _tester_conversation(db, conversation_id, tester_id)
    state = (
        db.query(ConversationMoodState)
        .filter(ConversationMoodState.conversation_id == conversation_id)
        .one_or_none()
    )
    if state is None:
        raise HTTPException(status_code=404, detail="No mood detected yet for this conversation")
    return state


@router.get("/conversations/{conversation_id}/thread-state", response_model=schemas.ConversationThreadStateOut)
def get_conversation_thread_state(
    conversation_id: str, db: Session = Depends(get_db), tester_id: str = Depends(get_tester_id)
):
    _tester_conversation(db, conversation_id, tester_id)
    state = (
        db.query(ConversationThreadState)
        .filter(ConversationThreadState.conversation_id == conversation_id)
        .one_or_none()
    )
    if state is None:
        raise HTTPException(status_code=404, detail="No thread state yet for this conversation")
    return state
