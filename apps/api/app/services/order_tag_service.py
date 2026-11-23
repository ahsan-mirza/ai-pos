"""Cashier-facing order tags for takeaway and delivery.

The daily open-order number stays the kitchen number. This sequence is the token printed
for the guest (`TW001`, `DL001`). It is one row per order id, incremented under a row lock
when the database supports it, and it is not replaced after it has been issued.

A register that was offline may present a tag it already showed (`TW-AB12-001`). That tag is
stored as-is when it is unique. A register may not choose the next server number itself.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.restaurant import OrderTag, OrderTagCounter
from app.models.store import Store
from app.services import audit

TAG_TYPES = ("TAKEAWAY", "DELIVERY")
PREFIX = {"TAKEAWAY": "TW", "DELIVERY": "DL"}
SERVER_TAG = re.compile(r"^(TW|DL)[0-9]{3,6}$")
OFFLINE_TAG = re.compile(r"^(TW|DL)-[A-Z0-9]{2,8}-[0-9]{3,6}$")


def tags_for(db: Session, order_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not order_ids:
        return {}
    rows = db.scalars(select(OrderTag).where(OrderTag.id.in_(order_ids))).all()
    return {row.id: row.tag for row in rows}


def bind(db: Session, order, presented: str | None, *, actor_id: uuid.UUID | None) -> str | None:
    """Attach the tag for this order. A second call returns the tag already stored."""
    service = order.service_type
    if service not in TAG_TYPES:
        if (presented or "").strip():
            raise ApiError(422, "tag_rejected", "Dine-in orders keep the table name.")
        return None
    return assign(
        db,
        order_id=order.id,
        store_id=order.store_id,
        service_type=service,
        presented=presented,
        actor_id=actor_id,
    )


def assign(
    db: Session,
    *,
    order_id: uuid.UUID,
    store_id: uuid.UUID,
    service_type: str,
    presented: str | None,
    actor_id: uuid.UUID | None,
) -> str:
    if service_type not in TAG_TYPES:
        raise ApiError(422, "tag_rejected", "This order type keeps the table name.")
    if db.get(Store, store_id) is None:
        raise ApiError(404, "not_found", "Store was not found.")
    existing = db.get(OrderTag, order_id)
    if existing is not None:
        if existing.store_id != store_id or existing.service_type != service_type:
            raise ApiError(409, "tag_scope", "This order already has a tag for another branch or order type.")
        wanted = (presented or "").strip().upper()
        if wanted and wanted != existing.tag:
            raise ApiError(422, "tag_locked", "The order tag cannot be changed.")
        return existing.tag
    wanted = (presented or "").strip().upper()
    if wanted:
        if SERVER_TAG.fullmatch(wanted):
            raise ApiError(422, "tag_rejected", "Order tags are assigned by the register. A typed tag is not accepted.")
        if not OFFLINE_TAG.fullmatch(wanted):
            raise ApiError(422, "tag_rejected", "Order tags are assigned by the register. A typed tag is not accepted.")
        if not wanted.startswith(PREFIX[service_type]):
            raise ApiError(422, "tag_rejected", "That tag belongs to a different order type.")
        return _insert(db, order_id, store_id, service_type, wanted, "register", actor_id)
    tag = f"{PREFIX[service_type]}{_next_value(db, store_id, service_type):03d}"
    return _insert(db, order_id, store_id, service_type, tag, "server", actor_id)


def _next_value(db: Session, store_id: uuid.UUID, service_type: str) -> int:
    row = _locked_counter(db, store_id, service_type)
    if row is None:
        fresh = OrderTagCounter(store_id=store_id, service_type=service_type, last_value=0)
        try:
            with db.begin_nested():
                db.add(fresh)
                db.flush()
        except IntegrityError:
            fresh = None
        row = fresh or _locked_counter(db, store_id, service_type)
    if row is None:
        raise ApiError(409, "tag_busy", "The order tag sequence is busy. Try again.")
    row.last_value += 1
    db.flush()
    return int(row.last_value)


def _locked_counter(db: Session, store_id: uuid.UUID, service_type: str) -> OrderTagCounter | None:
    statement = select(OrderTagCounter).where(
        OrderTagCounter.store_id == store_id,
        OrderTagCounter.service_type == service_type,
    )
    if db.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update()
    return db.scalar(statement)


def _insert(
    db: Session,
    order_id: uuid.UUID,
    store_id: uuid.UUID,
    service_type: str,
    tag: str,
    source: str,
    actor_id: uuid.UUID | None,
) -> str:
    row = OrderTag(
        id=order_id,
        store_id=store_id,
        service_type=service_type,
        tag=tag,
        source=source,
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError as exc:
        detail = str(getattr(exc, "orig", exc)).lower()
        if "foreign key" in detail:
            raise ApiError(404, "not_found", "Store was not found.") from exc
        raise ApiError(409, "tag_taken", "That order tag is already used.") from exc
    audit.record(
        db,
        action_type="CREATE",
        action="order.tag_issued",
        target_entity="OrderTag",
        target_entity_id=order_id,
        store_id=store_id,
        user_id=actor_id,
        client_device="desktop",
        new_values={"tag": tag, "service_type": service_type, "source": source},
        details={"outcome": "issued"},
    )
    return tag
