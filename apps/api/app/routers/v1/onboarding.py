from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.onboarding import Checklist, GoLiveRequest, GoLiveResult
from app.services import onboarding_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]


@router.get("/checklist", response_model=Checklist)
def checklist(db: Db, _: Annotated[Principal, Depends(authorize(Permission.PORTAL_ACCESS))]) -> Checklist:
    return onboarding_service.checklist(db)


@router.post("/go-live", response_model=GoLiveResult)
def go_live(
    payload: GoLiveRequest,
    db: Db,
    principal: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))],
) -> GoLiveResult:
    return onboarding_service.go_live(db, principal, payload.confirm)
