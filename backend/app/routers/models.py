from fastapi import APIRouter

from app import schemas
from app.router import router as model_router

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("", response_model=list[schemas.ProviderStatus])
def list_model_providers():
    return model_router.statuses()
