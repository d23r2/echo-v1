from fastapi import APIRouter

from app import schemas
from app.router import router as model_router
from app.services import local_model_router

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("", response_model=list[schemas.ProviderStatus])
def list_model_providers():
    return model_router.statuses()


@router.get("/local", response_model=schemas.LocalModelsOut)
def list_local_models():
    """Installed Ollama models (GET Ollama's own /api/tags) — a clean
    unavailable state when Ollama is offline, never a raw error."""
    names, error = local_model_router.list_installed_models()
    return schemas.LocalModelsOut(available=error is None, models=names, error=error)
