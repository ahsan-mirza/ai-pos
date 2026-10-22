import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.stock_counts import StockCountCreate, StockCountEntries, StockCountOut, StockCountSummary
from app.services import stock_count_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]
CanCount = Annotated[Principal, Depends(authorize(Permission.PORTAL_ACCESS))]
CanPost = Annotated[Principal, Depends(authorize(Permission.INVENTORY_ADJUST_STOCK))]


@router.get("", response_model=list[StockCountSummary])
def list_counts(
    db: Db,
    settings: Config,
    principal: CanCount,
    store_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[StockCountSummary]:
    return stock_count_service.list_counts(db, settings, principal, store_id=store_id, limit=limit)


@router.post("", response_model=StockCountOut, status_code=201)
def create_count(payload: StockCountCreate, db: Db, settings: Config, principal: CanPost) -> StockCountOut:
    return stock_count_service.create(db, settings, principal, payload)


@router.get("/{count_id}", response_model=StockCountOut)
def get_count(count_id: uuid.UUID, db: Db, settings: Config, principal: CanCount) -> StockCountOut:
    return stock_count_service.get_count(db, settings, principal, count_id)


@router.put("/{count_id}/lines", response_model=StockCountOut)
def record_lines(
    count_id: uuid.UUID, payload: StockCountEntries, db: Db, settings: Config, principal: CanCount
) -> StockCountOut:
    return stock_count_service.record(db, settings, principal, count_id, payload)


@router.post("/{count_id}/submit", response_model=StockCountOut)
def submit_count(count_id: uuid.UUID, db: Db, settings: Config, principal: CanCount) -> StockCountOut:
    return stock_count_service.submit(db, settings, principal, count_id)


@router.post("/{count_id}/{action}", response_model=StockCountOut)
def review_count(
    count_id: uuid.UUID,
    action: Literal["post", "reopen", "cancel"],
    db: Db,
    settings: Config,
    principal: CanPost,
) -> StockCountOut:
    handler = {
        "post": stock_count_service.post,
        "reopen": stock_count_service.reopen,
        "cancel": stock_count_service.cancel,
    }[action]
    return handler(db, settings, principal, count_id)
