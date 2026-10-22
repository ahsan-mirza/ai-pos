import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.orders import (
    ItemVoid,
    OrderAction,
    OrderCreate,
    OrderItemsAdd,
    OrderMerge,
    OrderMove,
    OrderOut,
    OrderUpdate,
)
from app.services import order_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
# Registers call these as the device on behalf of the signed-in cashier (user_id in the body).
CanOrder = Annotated[Principal, Depends(authorize(Permission.POS_ORDERS, allow_device=True, scopes=("portal", "pos")))]


@router.get("", response_model=list[OrderOut])
def list_orders(
    db: Db,
    principal: CanOrder,
    store_id: uuid.UUID,
    status: Literal["OPEN", "SETTLED", "VOID"] | None = None,
    since: Annotated[datetime | None, Query()] = None,
) -> list[OrderOut]:
    return order_service.list_orders(db, principal, store_id=store_id, status=status, since=since)


@router.post("", response_model=OrderOut, status_code=201)
def create_order(payload: OrderCreate, db: Db, principal: CanOrder) -> OrderOut:
    return order_service.create_order(db, principal, payload)


@router.get("/{order_id}", response_model=OrderOut)
def get_order(order_id: uuid.UUID, db: Db, principal: CanOrder) -> OrderOut:
    return order_service.get_order(db, principal, order_id)


@router.patch("/{order_id}", response_model=OrderOut)
def update_order(order_id: uuid.UUID, payload: OrderUpdate, db: Db, principal: CanOrder) -> OrderOut:
    return order_service.update_order(db, principal, order_id, payload)


@router.post("/{order_id}/items", response_model=OrderOut)
def add_items(order_id: uuid.UUID, payload: OrderItemsAdd, db: Db, principal: CanOrder) -> OrderOut:
    return order_service.add_items(db, principal, order_id, payload)


@router.post("/{order_id}/send", response_model=OrderOut)
def send_order(order_id: uuid.UUID, payload: OrderAction, db: Db, principal: CanOrder) -> OrderOut:
    return order_service.send_order(db, principal, order_id, payload)


@router.post("/{order_id}/items/{item_id}/void", response_model=OrderOut)
def void_item(order_id: uuid.UUID, item_id: uuid.UUID, payload: ItemVoid, db: Db, principal: CanOrder) -> OrderOut:
    return order_service.void_item(db, principal, order_id, item_id, payload)


@router.post("/{order_id}/bill", response_model=OrderOut)
def request_bill(order_id: uuid.UUID, payload: OrderAction, db: Db, principal: CanOrder) -> OrderOut:
    return order_service.request_bill(db, principal, order_id, payload)


@router.post("/{order_id}/void", response_model=OrderOut)
def void_order(order_id: uuid.UUID, payload: ItemVoid, db: Db, principal: CanOrder) -> OrderOut:
    return order_service.void_order(db, principal, order_id, payload)


@router.post("/{order_id}/move", response_model=OrderOut)
def move_order(order_id: uuid.UUID, payload: OrderMove, db: Db, principal: CanOrder) -> OrderOut:
    return order_service.move_order(db, principal, order_id, payload)


@router.post("/{order_id}/merge", response_model=OrderOut)
def merge_order(order_id: uuid.UUID, payload: OrderMerge, db: Db, principal: CanOrder) -> OrderOut:
    return order_service.merge_order(db, principal, order_id, payload)
