from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_db
from app.services import evaluation_lab

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])


@router.get("/cases", response_model=list[schemas.EvaluationCaseOut])
def list_cases():
    return [
        schemas.EvaluationCaseOut(id=c["id"], name=c["name"], category=c["category"], user_message=c["user_message"], notes=c.get("notes"))
        for c in evaluation_lab.load_cases()
    ]


@router.post("/run", response_model=schemas.EvaluationRunOut)
def run_evaluation(db: Session = Depends(get_db)):
    return evaluation_lab.run_evaluation(db)


@router.get("/runs", response_model=list[schemas.EvaluationRunOut])
def list_runs(db: Session = Depends(get_db)):
    return evaluation_lab.list_runs(db)


@router.get("/runs/{run_id}", response_model=schemas.EvaluationRunDetailOut)
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = evaluation_lab.get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    return run
