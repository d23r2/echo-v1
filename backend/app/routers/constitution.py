from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import council, schemas
from app.db import get_db

router = APIRouter(prefix="/api/constitution", tags=["constitution"])


@router.get("", response_model=schemas.ConstitutionOut)
def get_constitution(db: Session = Depends(get_db)):
    return council.build_constitution_view(db)


@router.get("/history", response_model=list[schemas.AmendmentLogEntryOut])
def get_amendment_history(db: Session = Depends(get_db)):
    return council.build_constitution_view(db)["amendment_log"]
