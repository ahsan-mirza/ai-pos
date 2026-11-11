import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.orders import (
    CodCollection,
    CodHandoverIn,
    DeliveryAssign,
    DeliveryOutcome,
    DeliveryProgress,
    GuestSuggestionsOut,
    ItemQuantity,
    ItemVoid,
    OrderAction,
    OrderCreate,
    OrderItemsAdd,
    OrderMerge,
    OrderMove,
    OrderOut,
    OrderUpdate,
)
from app.services import delivery_finance, guest_suggestion_service, order_service

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


@router.get("/cod-pending", response_model=list[OrderOut])
def cod_pending(db: Db, principal: CanOrder, store_id: uuid.UUID) -> list[OrderOut]:
    return delivery_finance.pending_cod(db, principal, store_id=store_id)


@router.get("/suggestions", response_model=GuestSuggestionsOut)
def suggestions(
    db: Db,
    principal: CanOrder,
    store_id: uuid.UUID,
    customer_id: uuid.UUID | None = None,
    product_id: Annotated[list[uuid.UUID] | None, Query(max_length=50)] = None,
) -> GuestSuggestionsOut:
    """Up to three dishes for this guest. Restaurant and cafe only; the caller still adds and sends the line."""
    return guest_suggestion_service.suggestions(
        db,
        principal,
        store_id=store_id,
        customer_id=customer_id,
        product_ids=product_id or [],
    )


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


@router.post("/{order_id}/hand-over", response_model=OrderOut)
def hand_over(order_id: uuid.UUID, payload: OrderAction, db: Db, principal: CanOrder) -> OrderOut:
    return order_service.hand_over(db, principal, order_id, payload)


@router.post("/{order_id}/items/{item_id}/quantity", response_model=OrderOut)
def set_item_quantity(
    order_id: uuid.UUID, item_id: uuid.UUID, payload: ItemQuantity, db: Db, principal: CanOrder
) -> OrderOut:
    return order_service.set_item_quantity(db, principal, order_id, item_id, payload)


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


@router.post("/{order_id}/delivery/assign", response_model=OrderOut)
def assign_rider(order_id: uuid.UUID, payload: DeliveryAssign, db: Db, principal: CanOrder) -> OrderOut:
    return delivery_finance.assign_rider(
        db,
        principal,
        order_id,
        revision=payload.revision,
        user_id=payload.user_id,
        rider_id=payload.rider_id,
        phone=payload.phone,
        address=payload.address,
    )


@router.post("/{order_id}/delivery/start", response_model=OrderOut)
def start_delivery(order_id: uuid.UUID, payload: OrderAction, db: Db, principal: CanOrder) -> OrderOut:
    return delivery_finance.start_delivery(db, principal, order_id, revision=payload.revision, user_id=payload.user_id)


@router.post("/{order_id}/delivery/delivered", response_model=OrderOut)
def mark_delivered(order_id: uuid.UUID, payload: DeliveryProgress, db: Db, principal: CanOrder) -> OrderOut:
    return delivery_finance.mark_delivered(
        db,
        principal,
        order_id,
        revision=payload.revision,
        user_id=payload.user_id,
        collected_cents=payload.collected_cents,
    )


@router.post("/{order_id}/delivery/collection", response_model=OrderOut)
def report_collection(order_id: uuid.UUID, payload: CodCollection, db: Db, principal: CanOrder) -> OrderOut:
    return delivery_finance.report_collection(
        db,
        principal,
        order_id,
        revision=payload.revision,
        user_id=payload.user_id,
        collected_cents=payload.collected_cents,
    )


@router.post("/{order_id}/delivery/outcome", response_model=OrderOut)
def delivery_outcome(order_id: uuid.UUID, payload: DeliveryOutcome, db: Db, principal: CanOrder) -> OrderOut:
    return delivery_finance.set_outcome(
        db,
        principal,
        order_id,
        revision=payload.revision,
        user_id=payload.user_id,
        status=payload.status,
        reason=payload.reason,
    )


@router.post("/{order_id}/delivery/handover", response_model=OrderOut)
def cod_handover(order_id: uuid.UUID, payload: CodHandoverIn, db: Db, principal: CanOrder) -> OrderOut:
    return delivery_finance.handover(
        db,
        principal,
        order_id,
        revision=payload.revision,
        user_id=payload.user_id,
        shift_id=payload.shift_id,
        received_cents=payload.received_cents,
        idempotency_key=payload.idempotency_key,
        note=payload.note,
        approved_by_id=payload.approved_by_id,
    )
