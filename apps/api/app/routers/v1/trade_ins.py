import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.trade_ins import TradeInCheck, TradeInCheckOut, TradeInCreate, TradeInList, TradeInOut
from app.services import trade_in_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]
AtRegister = Annotated[
    Principal, Depends(authorize(Permission.POS_ACCESS, allow_device=True, scopes=("pos", "portal")))
]
CanRead = Annotated[Principal, Depends(authorize(Permission.PORTAL_REPORTS_READ))]


@router.get("", response_model=TradeInList)
def list_trade_ins(
    db: Db,
    settings: Config,
    principal: CanRead,
    start: Annotated[date, Query(alias="from")],
    end: Annotated[date, Query(alias="to")],
) -> TradeInList:
    return trade_in_service.list_trade_ins(db, settings, start=start, end=end, store_scope=principal.store_id)


@router.post("/check", response_model=TradeInCheckOut)
def check(payload: TradeInCheck, db: Db, _: AtRegister) -> TradeInCheckOut:
    return trade_in_service.check(db, payload)


@router.post("", response_model=TradeInOut, status_code=201)
def create(payload: TradeInCreate, db: Db, settings: Config, principal: AtRegister) -> TradeInOut:
    return trade_in_service.create(db, settings, principal, payload)


@router.post("/{trade_in_id}/cancel", response_model=TradeInOut)
def cancel(trade_in_id: uuid.UUID, db: Db, settings: Config, principal: AtRegister) -> TradeInOut:
    return trade_in_service.cancel(db, settings, principal, trade_in_id)
