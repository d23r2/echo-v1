from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_db
from app.services import permission_center

router = APIRouter(prefix="/api/permissions", tags=["permissions"])


@router.get("", response_model=list[schemas.PermissionSettingOut])
def list_permissions(db: Session = Depends(get_db)):
    return permission_center.list_permissions(db)


@router.patch("/{permission_key}", response_model=schemas.PermissionSettingOut)
def update_permission(permission_key: str, payload: schemas.PermissionSettingUpdate, db: Session = Depends(get_db)):
    try:
        return permission_center.set_permission_level(db, permission_key, payload.level)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.post("/reset-defaults", response_model=list[schemas.PermissionSettingOut])
def reset_defaults(db: Session = Depends(get_db)):
    """Resets every permission to its safe v1 default (see
    permission_center.DEFAULT_PERMISSIONS) — never widens beyond the
    original safe defaults, only ever restores them."""
    for perm in permission_center.DEFAULT_PERMISSIONS:
        permission_center.set_permission_level(db, perm["key"], perm["level"])
    return permission_center.list_permissions(db)
