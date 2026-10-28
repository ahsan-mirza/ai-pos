from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.onboarding import Checklist, GoLiveRequest, GoLiveResult, OnboardingSkip
from app.services import onboarding_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]


@router.get("/checklist", response_model=Checklist)
def checklist(
    db: Db,
    settings: Config,
    _: Annotated[Principal, Depends(authorize(Permission.PORTAL_ACCESS))],
) -> Checklist:
    return onboarding_service.checklist(db, settings)


@router.post("/explore", response_model=Checklist)
def explore(
    db: Db,
    settings: Config,
    _: Annotated[Principal, Depends(authorize(Permission.PORTAL_ACCESS))],
) -> Checklist:
    return onboarding_service.mark_explored(db, settings)


@router.post("/skip", response_model=Checklist)
def skip(
    payload: OnboardingSkip,
    db: Db,
    settings: Config,
    _: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))],
) -> Checklist:
    return onboarding_service.skip_optional(db, payload.key, settings)


@router.post("/go-live", response_model=GoLiveResult)
def go_live(
    payload: GoLiveRequest,
    db: Db,
    settings: Config,
    principal: Annotated[Principal, Depends(authorize(Permission.SETTINGS_MANAGE))],
) -> GoLiveResult:
    return onboarding_service.go_live(db, principal, payload, settings=settings)
