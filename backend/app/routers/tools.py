from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_db
from app.services import tool_registry

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("", response_model=list[schemas.ToolDefinitionOut])
def list_tools(db: Session = Depends(get_db)):
    return tool_registry.list_tools(db)


@router.get("/runs", response_model=list[schemas.ToolRunOut])
def list_runs(db: Session = Depends(get_db)):
    return tool_registry.list_runs(db)


@router.post("/{tool_name}/run", response_model=schemas.ToolRunOut)
def run_tool(tool_name: str, payload: schemas.ToolRunRequest, db: Session = Depends(get_db)):
    try:
        return tool_registry.run_tool(db, tool_name, payload.input, confirm=payload.confirm)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
