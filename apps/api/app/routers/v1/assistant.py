from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.assistant import AssistantAsk, AssistantInfo, AssistantReply
from app.services import assistant_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]
CanAsk = Annotated[Principal, Depends(authorize(Permission.PORTAL_REPORTS_READ))]


@router.get("", response_model=AssistantInfo)
def info(principal: CanAsk, settings: Config) -> AssistantInfo:
    return assistant_service.info(principal, settings)


@router.post("/ask", response_model=AssistantReply)
def ask(payload: AssistantAsk, db: Db, principal: CanAsk, settings: Config) -> AssistantReply:
    return assistant_service.ask(db, principal, settings, payload)
