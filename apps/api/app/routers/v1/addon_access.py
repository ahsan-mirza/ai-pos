import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.addon_access import (
    AccessEventOut,
    AddonModuleOut,
    AddonUserOut,
    AssignmentBatch,
    AssignmentOut,
)
from app.services import addon_access

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
CanView = Annotated[Principal, Depends(authorize(Permission.USERS_READ))]
CanManage = Annotated[Principal, Depends(authorize(Permission.USERS_UPDATE))]


@router.get("/modules", response_model=list[AddonModuleOut])
def modules(db: Db, _: CanView) -> list[dict]:
    return addon_access.list_modules(db)


@router.get("/users", response_model=list[AddonUserOut])
def users(
    db: Db,
    actor: CanView,
    module_key: Annotated[str, Query(min_length=1, max_length=64)],
    q: Annotated[str, Query(max_length=80)] = "",
    role_id: uuid.UUID | None = None,
    status: Literal["active", "inactive"] | None = None,
    access: Literal["grant", "role", "revoked", "none", "inactive"] | None = None,
) -> list[dict]:
    return addon_access.list_users(db, actor, module_key, query=q, role_id=role_id, status=status, access=access)


@router.put("/assignments", response_model=list[AssignmentOut])
def assign(payload: AssignmentBatch, db: Db, actor: CanManage) -> list[AssignmentOut]:
    rows = addon_access.apply_changes(db, actor, [change.model_dump() for change in payload.changes])
    return [
        AssignmentOut(
            user_id=row.user_id,
            module_key=row.module_key,
            status=row.status,
            permissions=list(row.permissions or []),
        )
        for row in rows
    ]


@router.get("/history", response_model=list[AccessEventOut])
def events(
    db: Db,
    _: CanView,
    module_key: Annotated[str | None, Query(max_length=64)] = None,
    user_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[dict]:
    return addon_access.history(db, module_key, user_id, limit)
