from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import usage as usage_lib
from app.db import get_db
from app.schemas import ProviderUsageOut

router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("", response_model=dict[str, ProviderUsageOut])
def get_usage(db: Session = Depends(get_db)):
    return usage_lib.get_usage_summary(db)
