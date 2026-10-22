from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.currencies import CurrencyOut, CurrencyWrite, RateWrite
from app.services import fx_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
AtRegister = Annotated[
    Principal, Depends(authorize(Permission.POS_ACCESS, allow_device=True, scopes=("pos", "portal")))
]
CanManage = Annotated[Principal, Depends(authorize(Permission.CURRENCIES_MANAGE))]


@router.get("", response_model=list[CurrencyOut])
def currencies(db: Db, _: AtRegister) -> list[CurrencyOut]:
    """Accepted foreign currencies with their current rate; registers cache this for offline cash."""
    return fx_service.list_currencies(db)


@router.post("", response_model=list[CurrencyOut], status_code=201)
def save_currency(payload: CurrencyWrite, db: Db, _: CanManage) -> list[CurrencyOut]:
    return fx_service.save_currency(db, payload)


@router.put("/{code}/rate", response_model=list[CurrencyOut])
def set_rate(code: str, payload: RateWrite, db: Db, principal: CanManage) -> list[CurrencyOut]:
    return fx_service.set_rate(db, code, payload, principal.user.id if principal.user else None)


@router.post("/sync", response_model=list[CurrencyOut])
def sync(db: Db, settings: Annotated[Settings, Depends(get_settings)], _: CanManage) -> list[CurrencyOut]:
    fx_service.sync_rates(db, settings)
    return fx_service.list_currencies(db)
