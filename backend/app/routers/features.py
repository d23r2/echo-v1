from fastapi import APIRouter

from app import schemas
from app.router import router as model_router

router = APIRouter(prefix="/api", tags=["features"])

# Providers currently know the same thing vision needs (Gemini's inline_data
# wiring is the only real vision path — see providers/gemini_provider.py).
_VISION_PROVIDER = "gemini"


def _provider_status_label(available: bool, reason: str | None) -> str:
    if available:
        return "available"
    if reason and ("api_key" in reason.lower() or "not set" in reason.lower()):
        return "not_configured"
    return "unavailable"


@router.get("/features", response_model=schemas.FeatureAvailability)
def get_feature_availability():
    """Tells the frontend which features actually work right now, so it can
    disable/clearly-label things instead of letting the user hit a failure.
    No secrets in here — just availability booleans and short reasons."""
    statuses = model_router.statuses()
    by_name = {s["name"]: s for s in statuses}
    any_chat_provider = any(s["available"] for s in statuses)

    vision_status = by_name.get(_VISION_PROVIDER, {"available": False, "reason": f"{_VISION_PROVIDER} not configured"})

    return schemas.FeatureAvailability(
        chat=any_chat_provider,
        voice_input=True,  # browser-native (SpeechRecognition) — frontend checks support itself
        file_upload=True,  # attachments are always stored; analysis depth varies (see Attachment.analysis_status)
        image_generation=bool(vision_status["available"]),  # Imagen shares the Gemini API key
        vision=schemas.VisionAvailability(
            available=bool(vision_status["available"]),
            provider=_VISION_PROVIDER,
            reason=None if vision_status["available"] else vision_status.get("reason"),
        ),
        providers={
            s["name"]: _provider_status_label(s["available"], s.get("reason")) for s in statuses
        },
    )
