"""Portal routes for Delivery Integrations. Tenant id comes from the request, never the body."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.errors import ApiError
from app.core.permissions import Permission
from delivery import service
from delivery.schemas import ConnectionOut, ConnectionWrite, HealthOut, OrderOut, ProviderOut

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]
CanView = Annotated[Principal, Depends(authorize(Permission.DELIVERY_VIEW))]
CanManage = Annotated[Principal, Depends(authorize(Permission.DELIVERY_MANAGE))]


def _user(principal: Principal):
    if principal.user is None:
        raise ApiError(403, "forbidden", "This action requires a signed-in user.")
    return principal.user


@router.get("/providers", response_model=list[ProviderOut])
def provider_list(db: Db, _: CanView) -> list:
    service.guard(db)
    return service.providers()


@router.get("/health", response_model=HealthOut)
def health(db: Db, principal: CanView) -> dict:
    return service.health(db, principal.store_id)


@router.get("/connections", response_model=list[ConnectionOut])
def connection_list(db: Db, principal: CanView) -> list:
    return service.list_connections(db, principal.store_id)


@router.post("/connections", response_model=ConnectionOut, status_code=201)
def connection_create(payload: ConnectionWrite, db: Db, principal: CanManage) -> dict:
    return service.create_connection(db, _user(principal), payload.model_dump(), principal.store_id)


@router.post("/connections/{connection_id}/test", response_model=ConnectionOut)
def connection_test(connection_id: UUID, db: Db, principal: CanManage) -> dict:
    return service.test_connection(db, connection_id, principal.store_id)


@router.post("/connections/{connection_id}/activate", response_model=ConnectionOut)
def connection_activate(connection_id: UUID, db: Db, settings: Config, principal: CanManage) -> dict:
    return service.activate(db, settings, _user(principal), connection_id, principal.store_id)


@router.post("/connections/{connection_id}/pause", response_model=ConnectionOut)
def connection_pause(connection_id: UUID, db: Db, principal: CanManage) -> dict:
    return service.pause(db, _user(principal), connection_id, principal.store_id)


@router.get("/orders", response_model=list[OrderOut])
def order_list(db: Db, principal: CanView) -> list:
    return service.orders(db, principal.store_id)
