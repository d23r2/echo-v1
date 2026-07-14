from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import schemas, usage
from app.config import get_settings
from app.db import get_db
from app.image_router import clean_unavailable_reason, image_router
from app.router import router as model_router

router = APIRouter(prefix="/api", tags=["features"])

# Providers currently know the same thing vision needs (Gemini's inline_data
# wiring is the only real vision path — see providers/gemini_provider.py).
_VISION_PROVIDER = "gemini"

# Cooldown categories that map onto their own exact status label — the
# frontend can show "quota_exceeded" instead of a generic "unavailable" so the
# user knows this is transient and roughly why. auth_failed/invalid_request
# are deliberately NOT cooldown categories (app/provider_errors.py) — they're
# persistent config problems a cooldown wouldn't help with, so there's no
# stored state to report them from here; they'd surface as a normal chat
# failure instead. Any cooldown category outside this set (future additions)
# falls back to the generic "cooldown_active".
_COOLDOWN_LABELS = {"rate_limited", "quota_exceeded", "credit_exhausted", "billing_required"}


def _provider_status_label(db: Session, provider_name: str, available: bool, reason: str | None) -> str:
    if not available:
        if reason and ("api_key" in reason.lower() or "not set" in reason.lower()):
            return "not_configured"
        return "unavailable"
    cooldown = usage.get_active_cooldown(db, provider_name)
    if cooldown is not None:
        return cooldown.category if cooldown.category in _COOLDOWN_LABELS else "cooldown_active"
    if provider_name == "azure":
        limit = get_settings().azure_daily_request_limit
        if limit is not None and usage.get_daily_request_count(db, "azure") >= limit:
            return "daily_limit_reached"
    if provider_name == "ollama":
        return "available_local"  # local/self-hosted — no quota concept
    return "available"


@router.get("/features", response_model=schemas.FeatureAvailability)
def get_feature_availability(db: Session = Depends(get_db)):
    """Tells the frontend which features actually work right now, so it can
    disable/clearly-label things instead of letting the user hit a failure.
    No secrets in here — just availability booleans and short reasons."""
    statuses = model_router.statuses()
    by_name = {s["name"]: s for s in statuses}
    provider_labels = {
        s["name"]: _provider_status_label(db, s["name"], s["available"], s.get("reason")) for s in statuses
    }
    any_chat_provider = any(label in ("available", "available_local") for label in provider_labels.values())

    vision_status = by_name.get(_VISION_PROVIDER, {"available": False, "reason": f"{_VISION_PROVIDER} not configured"})
    vision_cooldown = usage.get_active_cooldown(db, _VISION_PROVIDER)
    vision_available = bool(vision_status["available"]) and vision_cooldown is None

    image_gen_active, image_gen_reason = image_router.select_provider()
    image_gen_statuses = image_router.statuses()

    return schemas.FeatureAvailability(
        chat=any_chat_provider,
        voice_input=True,  # browser-native (SpeechRecognition) — frontend checks support itself
        file_upload=True,  # attachments are always stored; analysis depth varies (see Attachment.analysis_status)
        image_generation=image_gen_active is not None,
        vision=schemas.VisionAvailability(
            available=vision_available,
            provider=_VISION_PROVIDER,
            reason=None
            if vision_available
            else (f"recent {vision_cooldown.category.replace('_', ' ')} error" if vision_cooldown else vision_status.get("reason")),
        ),
        image_generation_detail=schemas.ImageGenerationAvailability(
            available=image_gen_active is not None,
            active_provider=image_gen_active,
            # Cleaned for the UI (see image_router.clean_unavailable_reason) —
            # the raw reason may name a config field like GEMINI_API_KEY,
            # which is fine server-side/in logs but never in a response the
            # frontend renders. `providers` below stays raw/detailed: it's API
            # data the frontend never displays directly (see ChatView.tsx),
            # not the reason string shown in the "+" menu's unavailable state.
            reason=clean_unavailable_reason(image_gen_reason) if image_gen_active is None else None,
            providers={name: ("available" if s.available else (s.reason or "unavailable")) for name, s in image_gen_statuses.items()},
        ),
        providers=provider_labels,
    )
