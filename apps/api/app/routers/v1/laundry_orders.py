"""Laundry order intake. Catalog prices are snapshotted. Payments stay on the existing deposit pattern."""

import base64
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.models.laundry_order import LaundryBag, LaundryGarment, LaundryOrderEvent, LaundryPhoto, LaundryTag
from app.schemas.laundry_order import (
    BagOut,
    CancelIn,
    DepositPost,
    EventOut,
    GarmentOut,
    GarmentPatch,
    OrderDetail,
    OrderIn,
    OrderOut,
    PhotoIn,
    PhotoOut,
    ProductionIn,
    QuantityChange,
    ScanIn,
    TagActionIn,
    TagOut,
)
from app.services import laundry_orders

router = APIRouter()
_POS = ("portal", "pos")
View = Annotated[Principal, Depends(authorize(Permission.LAUNDRY_ORDERS_VIEW, scopes=_POS))]
Create = Annotated[Principal, Depends(authorize(Permission.LAUNDRY_ORDERS_CREATE, scopes=_POS))]
Update = Annotated[Principal, Depends(authorize(Permission.LAUNDRY_ORDERS_UPDATE, scopes=_POS))]
Cancel = Annotated[Principal, Depends(authorize(Permission.LAUNDRY_ORDERS_CANCEL, scopes=_POS))]
Print = Annotated[Principal, Depends(authorize(Permission.LAUNDRY_TAGS_PRINT, scopes=_POS))]
Upload = Annotated[Principal, Depends(authorize(Permission.LAUNDRY_PHOTOS_UPLOAD, scopes=_POS))]
Db = Annotated[Session, Depends(get_db)]


def _detail(db: Session, order) -> OrderDetail:
    garments = list(db.scalars(select(LaundryGarment).where(LaundryGarment.order_id == order.id)))
    bags = list(db.scalars(select(LaundryBag).where(LaundryBag.order_id == order.id)))
    tags = list(db.scalars(select(LaundryTag).where(LaundryTag.order_id == order.id)))
    events = list(db.scalars(select(LaundryOrderEvent).where(LaundryOrderEvent.order_id == order.id)))
    photos = list(db.scalars(select(LaundryPhoto).where(LaundryPhoto.order_id == order.id)))
    return OrderDetail(
        **OrderOut.model_validate(order).model_dump(),
        garments=[GarmentOut.model_validate(row) for row in garments],
        bags=[BagOut.model_validate(row) for row in bags],
        tags=[TagOut.model_validate(row) for row in tags],
        events=[EventOut.model_validate(row) for row in events],
        photos=[PhotoOut.model_validate(row) for row in photos],
    )


@router.get("/orders", response_model=list[OrderOut])
def list_orders(db: Db, principal: View, q: str = "", store_id: uuid.UUID | None = None) -> list:
    if principal.store_id is not None:
        store_id = principal.store_id
    return laundry_orders.list_orders(db, q, store_id)


@router.post("/orders", response_model=OrderDetail, status_code=201)
def create_order(payload: OrderIn, db: Db, principal: Create) -> OrderDetail:
    if principal.store_id is not None and payload.intake_store_id != principal.store_id:
        from app.core.errors import ApiError

        raise ApiError(403, "wrong_branch", "This register can only take orders for its own branch.")
    order = laundry_orders.create_order(
        db,
        payload,
        actor_id=principal.user.id if principal.user is not None else None,
        discount_authorized=principal.has(Permission.POS_DISCOUNT),
    )
    db.commit()
    db.refresh(order)
    return _detail(db, order)


@router.get("/orders/{order_id}", response_model=OrderDetail)
def read_order(order_id: uuid.UUID, db: Db, principal: View) -> OrderDetail:
    order = laundry_orders.get_order(db, order_id)
    if principal.store_id is not None and order.intake_store_id != principal.store_id:
        from app.core.errors import ApiError

        raise ApiError(404, "not_found", "This laundry order does not exist.")
    return _detail(db, order)


@router.post("/orders/{order_id}/garments", response_model=OrderDetail)
def patch_garment(order_id: uuid.UUID, payload: GarmentPatch, db: Db, principal: Update) -> OrderDetail:
    order = laundry_orders.update_garment(
        db,
        order_id,
        payload,
        actor_id=principal.user.id if principal.user is not None else None,
        can_override=principal.has(Permission.LAUNDRY_PRICING_OVERRIDE),
    )
    db.commit()
    return _detail(db, order)


@router.post("/orders/{order_id}/deposits", response_model=OrderDetail)
def take_deposit(order_id: uuid.UUID, payload: DepositPost, db: Db, principal: Create) -> OrderDetail:
    if principal.store_id is not None:
        order = laundry_orders.get_order(db, order_id)
        if order.intake_store_id != principal.store_id:
            from app.core.errors import ApiError

            raise ApiError(404, "not_found", "This laundry order does not exist.")
    order = laundry_orders.post_deposit(
        db,
        order_id,
        payload,
        actor_id=principal.user.id if principal.user is not None else None,
    )
    db.commit()
    return _detail(db, order)


@router.post("/orders/{order_id}/quantity", response_model=OrderDetail)
def change_quantity(order_id: uuid.UUID, payload: QuantityChange, db: Db, principal: Update) -> OrderDetail:
    order = laundry_orders.change_quantity(
        db,
        order_id,
        payload,
        actor_id=principal.user.id if principal.user is not None else None,
        can_override=principal.has(Permission.LAUNDRY_PRICING_OVERRIDE),
    )
    db.commit()
    return _detail(db, order)


@router.post("/orders/{order_id}/production", response_model=OrderDetail)
def start_production(order_id: uuid.UUID, payload: ProductionIn, db: Db, principal: Update) -> OrderDetail:
    order = laundry_orders.start_production(
        db,
        order_id,
        actor_id=principal.user.id if principal.user is not None else None,
        reason=payload.reason,
    )
    db.commit()
    return _detail(db, order)


@router.post("/orders/{order_id}/cancel", response_model=OrderDetail)
def cancel_order(order_id: uuid.UUID, payload: CancelIn, db: Db, principal: Cancel) -> OrderDetail:
    order = laundry_orders.cancel_order(
        db,
        order_id,
        actor_id=principal.user.id if principal.user is not None else None,
        reason=payload.reason,
        version=payload.version,
    )
    db.commit()
    return _detail(db, order)


@router.post("/tags/scan", response_model=TagOut)
def scan_tag(payload: ScanIn, db: Db, _: View) -> TagOut:
    event = laundry_orders.scan_tag(
        db,
        payload.code,
        order_id=payload.order_id,
        idempotency_key=payload.idempotency_key,
        device_id=payload.device_id,
    )
    db.commit()
    tag = db.get(LaundryTag, event.tag_id)
    return TagOut.model_validate(tag)


@router.post("/tags/{tag_id}/reprint", response_model=TagOut)
def reprint_tag(tag_id: uuid.UUID, payload: TagActionIn, db: Db, _: Print) -> TagOut:
    tag = laundry_orders.reprint_tag(db, tag_id, idempotency_key=payload.idempotency_key, device_id=payload.device_id)
    db.commit()
    return TagOut.model_validate(tag)


@router.post("/tags/{tag_id}/replace", response_model=TagOut)
def replace_tag(tag_id: uuid.UUID, payload: TagActionIn, db: Db, _: Print) -> TagOut:
    tag = laundry_orders.replace_tag(db, tag_id, idempotency_key=payload.idempotency_key, device_id=payload.device_id)
    db.commit()
    return TagOut.model_validate(tag)


@router.get("/orders/{order_id}/photos/{photo_id}")
def read_photo(order_id: uuid.UUID, photo_id: uuid.UUID, db: Db, principal: View) -> Response:
    order = laundry_orders.get_order(db, order_id)
    if principal.store_id is not None and order.intake_store_id != principal.store_id:
        from app.core.errors import ApiError

        raise ApiError(404, "not_found", "This laundry order does not exist.")
    photo = db.get(LaundryPhoto, photo_id)
    if photo is None or photo.order_id != order.id:
        from app.core.errors import ApiError

        raise ApiError(404, "not_found", "That photo is not on this order.")
    return Response(content=photo.content, media_type=photo.mime)


@router.post("/orders/{order_id}/photos", response_model=PhotoOut, status_code=201)
def add_photo(order_id: uuid.UUID, payload: PhotoIn, db: Db, principal: Upload) -> PhotoOut:
    try:
        content = base64.b64decode(payload.content_base64, validate=True)
    except ValueError as exc:
        from app.core.errors import ApiError

        raise ApiError(422, "invalid_photo", "The photo was not valid base64.") from exc
    photo = laundry_orders.add_photo(
        db,
        order_id,
        payload,
        content,
        actor_id=principal.user.id if principal.user is not None else None,
    )
    db.commit()
    return PhotoOut.model_validate(photo)
