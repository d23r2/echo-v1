from fastapi import APIRouter

from app import schemas
from app.config import get_settings
from app.services.local_model_router import list_installed_models

router = APIRouter(prefix="/api/local-intelligence", tags=["local-intelligence"])


@router.get("/settings", response_model=schemas.LocalIntelligenceSettingsOut)
def get_local_intelligence_settings():
    """Read-only reflection of the .env-configured Local Intelligence Engine
    flags — same convention as every other feature flag in this app
    (FREE_MODE, WEB_SEARCH_ENABLED, ...), none of which have a runtime
    toggle either. The one genuinely per-tester, runtime-adjustable setting
    (answer quality mode) lives on PersonaSettings instead — see
    GET/PATCH /api/persona-settings."""
    settings = get_settings()
    models, error = list_installed_models()
    return schemas.LocalIntelligenceSettingsOut(
        local_intelligence_engine_enabled=settings.local_intelligence_engine_enabled,
        local_model_routing_enabled=settings.local_model_routing_enabled,
        local_answer_quality_mode=settings.local_answer_quality_mode,
        local_critic_enabled=settings.local_critic_enabled,
        cloud_fallback_enabled=settings.cloud_fallback_enabled,
        cloud_fallback_require_user_confirmation=settings.cloud_fallback_require_user_confirmation,
        ollama_available=error is None,
        ollama_status_reason=error,
        installed_models=models,
    )
