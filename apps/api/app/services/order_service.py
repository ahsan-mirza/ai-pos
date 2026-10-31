"""Open orders (tabs) and the dining-room floor. Orders live on the server so every register in a store shares them;
each write carries the revision it read, and a stale revision gets a 409 so the register refreshes and retries.
Registers that open or add to an order while offline sync it as an `open_order` event (lines merge by id).

An order is paid by one or more ordinary sales carrying `order_id`; it closes when every live line is paid."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.capabilities import Capability, has_capability
from app.core.config import Settings
from app.core.deps import Principal
from app.core.errors import ApiError, SyncRejected
from app.core.permissions import Permission
from app.models.kitchen import KitchenTicket
from app.models.product import Product
from app.models.restaurant import DiningArea, DiningTable, OpenOrder, OpenOrderItem
from app.models.store import Store
from app.models.user import User
from app.schemas.orders import (
    DiningAreaIn,
    DiningAreaOut,
    DiningTableIn,
    DiningTableOut,
    FloorOut,
    ItemQuantity,
    ItemVoid,
    OrderAction,
    OrderCreate,
    OrderItemIn,
    OrderItemOut,
    OrderItemsAdd,
    OrderMerge,
    OrderMove,
    OrderOut,
    OrderSyncPayload,
    OrderUpdate,
)
from app.schemas.payloads import SalePayload
from app.services import audit, combo_service
from app.services.sync_service import SyncContext, register_handler
from app.services.sync_validation import parse_payload, require_store

# Hooks other modules attach to (kitchen tickets when lines are sent, channel status when settled).
ON_SEND: list[Callable[[Session, OpenOrder, list[OpenOrderItem]], None]] = []
ON_VOID: list[Callable[[Session, OpenOrder, list[OpenOrderItem]], None]] = []
KITCHEN_STATUS: list[Callable[[Session, list[uuid.UUID]], dict[uuid.UUID, str]]] = []
CHANNEL_NAMES: list[Callable[[Session, set[uuid.UUID]], dict[uuid.UUID, str]]] = []


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    return value if value is None or value.tzinfo is not None else value.replace(tzinfo=UTC)


# --- Reading ----------------------------------------------------------------------------------------------


def live_items(order: OpenOrder) -> list[OpenOrderItem]:
    return [item for item in order.items if item.voided_at is None]


def open_cents(order: OpenOrder) -> int:
    return sum(item.unit_price_cents * item.quantity for item in live_items(order) if item.paid_sale_id is None)


def orders_out(db: Session, orders: list[OpenOrder]) -> list[OrderOut]:
    product_ids = {item.product_id for order in orders for item in order.items}
    names = (
        dict(db.execute(select(Product.id, Product.name).where(Product.id.in_(product_ids))).all())
        if product_ids
        else {}
    )
    user_ids = {order.opened_by_id for order in orders}
    users = dict(db.execute(select(User.id, User.full_name).where(User.id.in_(user_ids))).all()) if user_ids else {}
    table_ids = {order.table_id for order in orders if order.table_id is not None}
    tables = (
        dict(db.execute(select(DiningTable.id, DiningTable.label).where(DiningTable.id.in_(table_ids))).all())
        if table_ids
        else {}
    )
    kitchen: dict[uuid.UUID, str] = {}
    item_ids = [item.id for order in orders for item in order.items]
    for hook in KITCHEN_STATUS:
        kitchen.update(hook(db, item_ids))
    channels: dict[uuid.UUID, str] = {}
    channel_ids = {order.channel_id for order in orders if order.channel_id is not None}
    for hook in CHANNEL_NAMES:
        channels.update(hook(db, channel_ids))
    return [
        OrderOut(
            id=order.id,
            store_id=order.store_id,
            number=order.number,
            service_type=order.service_type,  # type: ignore[arg-type]
            status=order.status,  # type: ignore[arg-type]
            table_id=order.table_id,
            table_label=tables.get(order.table_id) if order.table_id else None,
            covers=order.covers,
            name=order.name,
            note=order.note,
            customer_id=order.customer_id,
            opened_by_id=order.opened_by_id,
            opened_by_name=users.get(order.opened_by_id),
            revision=order.revision,
            bill_requested_at=order.bill_requested_at,
            opened_at=order.opened_at,
            closed_at=order.closed_at,
            updated_at=order.updated_at,
            channel_id=order.channel_id,
            channel_name=channels.get(order.channel_id) if order.channel_id else None,
            external_ref=order.external_ref,
            channel_status=order.channel_status,
            prep_minutes=order.prep_minutes,
            items=[
                OrderItemOut(
                    id=item.id,
                    product_id=item.product_id,
                    product_name=names.get(item.product_id, "Item"),
                    quantity=item.quantity,
                    unit_price_cents=item.unit_price_cents,
                    modifiers=item.modifiers or [],
                    components=item.components or [],
                    seat=item.seat,
                    note=item.note,
                    sent_at=item.sent_at,
                    voided_at=item.voided_at,
                    void_reason=item.void_reason,
                    paid_sale_id=item.paid_sale_id,
                    kitchen_status=kitchen.get(item.id),
                )
                for item in order.items
            ],
            open_cents=open_cents(order),
        )
        for order in orders
    ]


def _scope(principal: Principal, store_id: uuid.UUID) -> None:
    if principal.store_id is not None and principal.store_id != store_id:
        raise ApiError(403, "store_scope", "You can only work with your own store's orders.")


def list_orders(
    db: Session, principal: Principal, *, store_id: uuid.UUID, status: str | None, since: datetime | None
) -> list[OrderOut]:
    _scope(principal, store_id)
    statement = select(OpenOrder).where(OpenOrder.store_id == store_id).order_by(OpenOrder.opened_at)
    if status is not None:
        statement = statement.where(OpenOrder.status == status)
    if since is not None:
        statement = statement.where(OpenOrder.updated_at > since)
    elif status is None:
        statement = statement.where(OpenOrder.opened_at >= _now() - timedelta(days=1))
    return orders_out(db, list(db.scalars(statement).all()))


def get_order(db: Session, principal: Principal, order_id: uuid.UUID) -> OrderOut:
    order = _order(db, principal, order_id)
    return orders_out(db, [order])[0]


# --- Writing ----------------------------------------------------------------------------------------------


def _order(db: Session, principal: Principal, order_id: uuid.UUID, *, lock: bool = False) -> OpenOrder:
    statement = select(OpenOrder).where(OpenOrder.id == order_id)
    if lock and db.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update()
    order = db.scalar(statement)
    if order is None:
        raise ApiError(404, "not_found", "Order was not found.")
    _scope(principal, order.store_id)
    return order


def _writable(db: Session, principal: Principal, order_id: uuid.UUID, revision: int) -> OpenOrder:
    order = _order(db, principal, order_id, lock=True)
    if order.status != "OPEN":
        raise ApiError(409, "order_closed", f"Order {order.number} is already {order.status.lower()}.")
    if revision != order.revision:
        raise ApiError(409, "stale_order", f"Order {order.number} changed on another register. Refresh and try again.")
    return order


def _actor(db: Session, principal: Principal, user_id: uuid.UUID | None, store_id: uuid.UUID) -> User:
    if principal.user is not None:
        return principal.user
    if user_id is None:
        raise ApiError(422, "invalid_request", "Name the cashier working this order.")
    user = db.get(User, user_id)
    if user is None or Permission.POS_ORDERS.value not in user.permissions:
        raise ApiError(403, "forbidden", "That cashier cannot work restaurant orders.")
    if user.store_id is not None and user.store_id != store_id:
        raise ApiError(403, "store_scope", "That cashier is not assigned to this store.")
    return user


def _touch(order: OpenOrder) -> None:
    order.revision += 1
    order.updated_at = _now()


def _next_number(db: Session, store_id: uuid.UUID) -> int:
    start = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    highest = db.scalar(
        select(func.max(OpenOrder.number)).where(OpenOrder.store_id == store_id, OpenOrder.opened_at >= start)
    )
    return int(highest or 0) + 1


def _table(db: Session, table_id: uuid.UUID | None, store_id: uuid.UUID) -> DiningTable | None:
    if table_id is None:
        return None
    statement = select(DiningTable).where(DiningTable.id == table_id)
    if db.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update()
    table = db.scalar(statement)
    area = db.get(DiningArea, table.area_id) if table is not None else None
    if table is None or area is None or area.store_id != store_id:
        raise ApiError(422, "invalid_request", "That table is not in this store.")
    return table


def _open_dine_in(db: Session, table_id: uuid.UUID) -> OpenOrder | None:
    """The single open dine-in tab on this table, locked on Postgres so two registers cannot both seat it."""
    statement = select(OpenOrder).where(
        OpenOrder.table_id == table_id,
        OpenOrder.status == "OPEN",
        OpenOrder.service_type == "DINE_IN",
    )
    if db.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update()
    return db.scalar(statement)


def _reject_second_table_order(
    db: Session, table_id: uuid.UUID | None, service_type: str, *, ignore_id: uuid.UUID | None = None
) -> None:
    if table_id is None or service_type != "DINE_IN":
        return
    existing = _open_dine_in(db, table_id)
    if existing is None or existing.id == ignore_id:
        return
    raise ApiError(
        409,
        "table_occupied",
        "That table already has an open order.",
        details={"order_id": str(existing.id)},
    )


def _item(order: OpenOrder, data: OrderItemIn, position: int, user_id: uuid.UUID | None) -> OpenOrderItem:
    return OpenOrderItem(
        id=data.id,
        order_id=order.id,
        product_id=data.product_id,
        quantity=data.quantity,
        unit_price_cents=data.unit_price_cents,
        modifiers=[choice.model_dump(mode="json") for choice in data.modifiers] or None,
        components=[choice.model_dump(mode="json") for choice in data.components] or None,
        seat=data.seat,
        note=(data.note or "").strip() or None,
        position=position,
        added_by_id=user_id,
    )


def _check_products(db: Session, items: list[OrderItemIn]) -> None:
    ids = {item.product_id for item in items}
    found = {row.id: row for row in db.scalars(select(Product).where(Product.id.in_(ids))).all()} if ids else {}
    for item in items:
        product = found.get(item.product_id)
        if product is None:
            raise ApiError(422, "invalid_request", "An ordered product does not exist.")
        if product.is_serialized or product.sold_by_weight:
            raise ApiError(422, "invalid_request", f"{product.name} cannot go on a tab; sell it at checkout.")
        # The kitchen fires a meal's parts as soon as it is sent, so its picks are checked now, not at settlement.
        try:
            combo_service.price_components(db, product, item.components)
        except SyncRejected as exc:
            raise ApiError(422, "invalid_meal", exc.message) from exc


def create_order(db: Session, principal: Principal, data: OrderCreate, *, commit: bool = True) -> OrderOut:
    _scope(principal, data.store_id)
    existing = db.get(OpenOrder, data.id)
    if existing is not None:
        return orders_out(db, [existing])[0]
    store = db.get(Store, data.store_id)
    if store is None:
        raise ApiError(404, "not_found", "Store was not found.")
    actor = _actor(db, principal, data.user_id, data.store_id)
    _table(db, data.table_id, data.store_id)
    _reject_second_table_order(db, data.table_id, data.service_type)
    _check_products(db, data.items)
    order = OpenOrder(
        id=data.id,
        store_id=data.store_id,
        number=_next_number(db, data.store_id),
        service_type=data.service_type,
        table_id=data.table_id,
        covers=data.covers,
        name=(data.name or "").strip() or None,
        note=(data.note or "").strip() or None,
        customer_id=data.customer_id,
        opened_by_id=actor.id,
        revision=1,
        opened_at=_now(),
        updated_at=_now(),
    )
    db.add(order)
    db.flush()
    for position, item in enumerate(data.items):
        db.add(_item(order, item, position, actor.id))
    from app.services.reservation_service import attach_order, observe_order

    attach_order(db, order, data.customer_id)
    if order.table_id is not None:
        observe_order(db, order, "order_created", f"Order {order.number} created.", actor.id)
    if not commit:
        db.flush()
        return orders_out(db, [order])[0]
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        taken = _open_dine_in(db, data.table_id) if data.table_id is not None else None
        if taken is not None:
            raise ApiError(
                409,
                "table_occupied",
                "That table already has an open order.",
                details={"order_id": str(taken.id)},
            ) from exc
        raise
    db.refresh(order)
    return orders_out(db, [order])[0]


def _reject_service_change(order: OpenOrder, db: Session) -> None:
    """Kitchen-fired and dispatched orders keep the type they were sent with."""
    if order.channel_status in {"ACCEPTED", "COMPLETED", "REJECTED"}:
        raise ApiError(409, "order_dispatched", "This order has already been dispatched. It cannot change type.")
    if any(item.sent_at is not None for item in live_items(order)):
        raise ApiError(409, "order_in_kitchen", "This order is already in the kitchen. It cannot change type.")
    cooking = db.scalar(
        select(KitchenTicket.id).where(
            KitchenTicket.order_id == order.id,
            KitchenTicket.status.in_(("PREPARING", "READY", "BUMPED")),
        )
    )
    if cooking is not None:
        raise ApiError(409, "order_in_kitchen", "This order is already in the kitchen. It cannot change type.")


def _convert_service(
    db: Session,
    order: OpenOrder,
    actor: User,
    *,
    target: str,
    table_id: uuid.UUID | None,
    reason: str | None,
) -> None:
    """Move an open, unsent order to another service type. The table is released or claimed here."""
    if target == order.service_type:
        return
    _reject_service_change(order, db)
    previous = order.service_type
    if target == "DINE_IN":
        if table_id is None:
            raise ApiError(422, "table_required", "Choose a free table before seating this order.")
        _table(db, table_id, order.store_id)
        taken = db.scalar(
            select(OpenOrder.id).where(
                OpenOrder.table_id == table_id,
                OpenOrder.status == "OPEN",
                OpenOrder.id != order.id,
            )
        )
        if taken is not None:
            raise ApiError(409, "table_occupied", "That table already has an open order.")
        order.table_id = table_id
    else:
        order.table_id = None
    if target == "DELIVERY" and order.customer_id is None and not (order.name or "").strip():
        raise ApiError(422, "delivery_required", "Add the customer before changing to delivery.")
    if target == "DELIVERY" and not (order.note or "").strip():
        raise ApiError(422, "delivery_required", "Add the delivery address before changing to delivery.")
    order.service_type = target
    audit.record(
        db,
        action_type="UPDATE",
        action="order.service_change",
        target_entity="OpenOrder",
        target_entity_id=order.id,
        store_id=order.store_id,
        user_id=actor.id,
        reason_notes=(reason or "").strip() or "Order type changed",
        details={"from": previous, "to": target, "table_id": str(order.table_id) if order.table_id else None},
    )


def _announce_service_change(order: OpenOrder, previous_table: uuid.UUID | None, result: OrderOut) -> None:
    from app.websockets.table_sync import publish, publish_order_status

    if previous_table is not None and order.table_id != previous_table:
        publish(
            order.store_id,
            {
                "type": "TABLE_SESSION_CLOSED",
                "store_id": str(order.store_id),
                "table_id": str(previous_table),
                "table_label": None,
                "order_id": str(order.id),
            },
        )
    label = {"DINE_IN": "Dine-in", "TAKEAWAY": "Takeaway", "DELIVERY": "Delivery"}.get(
        result.service_type, result.service_type
    )
    publish_order_status(
        order.store_id,
        order_id=order.id,
        table_id=order.table_id,
        table_label=result.table_label,
        ticket_id=None,
        status="preparing",
        kitchen_status="none",
        item_ids=[],
        message=f"Order #{order.number} changed to {label}.",
    )


def update_order(db: Session, principal: Principal, order_id: uuid.UUID, data: OrderUpdate) -> OrderOut:
    order = _writable(db, principal, order_id, data.revision)
    actor = _actor(db, principal, data.user_id, order.store_id)
    fields = data.model_fields_set
    previous_type = order.service_type
    previous_table = order.table_id
    if data.covers is not None:
        order.covers = data.covers
    if "name" in fields:
        order.name = (data.name or "").strip() or None
    if "note" in fields:
        order.note = (data.note or "").strip() or None
    if "customer_id" in fields:
        order.customer_id = data.customer_id
    if data.service_type is not None and data.service_type != previous_type:
        _convert_service(
            db,
            order,
            actor,
            target=data.service_type,
            table_id=data.table_id,
            reason=data.reason,
        )
    _touch(order)
    db.commit()
    result = orders_out(db, [order])[0]
    if result.service_type != previous_type:
        _announce_service_change(order, previous_table, result)
    return result


def add_items(db: Session, principal: Principal, order_id: uuid.UUID, data: OrderItemsAdd) -> OrderOut:
    order = _writable(db, principal, order_id, data.revision)
    actor = _actor(db, principal, data.user_id, order.store_id)
    _check_products(db, data.items)
    known = {item.id for item in order.items}
    position = max((item.position for item in order.items), default=-1) + 1
    added = 0
    for item in data.items:
        if item.id in known:
            continue
        order.items.append(_item(order, item, position, actor.id))
        position += 1
        added += 1
    if added and order.table_id is not None:
        from app.services.reservation_service import observe_order

        observe_order(db, order, "items_added", f"{added} item(s) added.", actor.id)
    order.bill_requested_at = None
    _touch(order)
    db.commit()
    db.refresh(order)
    return orders_out(db, [order])[0]


def set_item_quantity(
    db: Session, principal: Principal, order_id: uuid.UUID, item_id: uuid.UUID, data: ItemQuantity
) -> OrderOut:
    """Change the quantity of a line that has not been sent. Kitchen lines keep their quantity until a void."""
    order = _writable(db, principal, order_id, data.revision)
    actor = _actor(db, principal, data.user_id, order.store_id)
    item = next((line for line in order.items if line.id == item_id), None)
    if item is None or item.voided_at is not None:
        raise ApiError(404, "not_found", "That line is not on this order.")
    if item.paid_sale_id is not None:
        raise ApiError(409, "already_paid", "That line is already paid; refund it from Returns.")
    if item.sent_at is not None:
        raise ApiError(
            409,
            "already_sent",
            "This item is already in the kitchen. Void it with a reason instead of changing the quantity.",
        )
    previous = item.quantity
    if previous == data.quantity:
        return orders_out(db, [order])[0]
    item.quantity = data.quantity
    audit.record(
        db,
        action_type="UPDATE",
        action="order.item_quantity",
        target_entity="OpenOrder",
        target_entity_id=order.id,
        store_id=order.store_id,
        user_id=actor.id,
        details={"item_id": str(item.id), "product_id": str(item.product_id), "from": previous, "to": data.quantity},
    )
    _touch(order)
    db.commit()
    db.refresh(order)
    return orders_out(db, [order])[0]


def send_order(db: Session, principal: Principal, order_id: uuid.UUID, data: OrderAction) -> OrderOut:
    """Fires every unsent line to the kitchen."""
    order = _writable(db, principal, order_id, data.revision)
    actor = _actor(db, principal, data.user_id, order.store_id)
    fired = [item for item in live_items(order) if item.sent_at is None]
    if not fired:
        raise ApiError(422, "nothing_to_send", "Every line is already in the kitchen.")
    now = _now()
    for item in fired:
        item.sent_at = now
    for hook in ON_SEND:
        hook(db, order, fired)
    if order.table_id is not None:
        from app.services.reservation_service import observe_order

        observe_order(db, order, "items_sent", f"Order sent to the kitchen ({len(fired)} item(s)).", actor.id)
    _touch(order)
    fired_ids = {item.id for item in fired}
    db.commit()
    db.refresh(order)
    result = orders_out(db, [order])[0]
    from app.websockets.table_sync import publish, publish_order_status

    publish(
        order.store_id,
        {
            "type": "TABLE_ITEMS_ADDED",
            "store_id": str(order.store_id),
            "table_id": str(order.table_id) if order.table_id is not None else None,
            "table_label": result.table_label,
            "order_id": str(order.id),
            "open_cents": result.open_cents,
            "items": [
                {"id": str(item.id), "name": item.product_name, "quantity": item.quantity}
                for item in result.items
                if item.id in fired_ids
            ],
        },
    )
    label = result.table_label or result.name or f"#{result.number}"
    publish_order_status(
        order.store_id,
        order_id=order.id,
        table_id=order.table_id,
        table_label=result.table_label,
        ticket_id=None,
        status="preparing",
        kitchen_status="new",
        item_ids=[str(item_id) for item_id in fired_ids],
        message=f"{label} — Preparing",
    )
    return result


_HANDOFF = {"DINE_IN": "Served", "TAKEAWAY": "Picked up", "DELIVERY": "Dispatched"}


def hand_over(db: Session, principal: Principal, order_id: uuid.UUID, data: OrderAction) -> OrderOut:
    """Waiter or cashier confirms food that is already ready. Cooking tickets are not touched."""
    order = _writable(db, principal, order_id, data.revision)
    actor = _actor(db, principal, data.user_id, order.store_id)
    from app.services import kitchen_service

    tickets = kitchen_service.bump_ready(db, principal, order)
    if not tickets:
        raise ApiError(422, "nothing_ready", "Nothing is ready to hand over yet.")
    phrase = _HANDOFF.get(order.service_type, "Served")
    audit.record(
        db,
        action_type="UPDATE",
        action="order.hand_over",
        target_entity="OpenOrder",
        target_entity_id=order.id,
        store_id=order.store_id,
        user_id=actor.id,
        details={"service_type": order.service_type, "tickets": len(tickets), "phrase": phrase},
    )
    _touch(order)
    db.commit()
    db.refresh(order)
    result = orders_out(db, [order])[0]
    from app.websockets.table_sync import publish_order_status

    label = result.table_label or result.name or f"#{result.number}"
    for ticket in tickets:
        publish_order_status(
            order.store_id,
            order_id=order.id,
            table_id=order.table_id,
            table_label=result.table_label,
            ticket_id=ticket.id,
            status="completed",
            kitchen_status="bumped",
            item_ids=[
                str(item.order_item_id)
                for item in ticket.items
                if item.order_item_id is not None and item.voided_at is None
            ],
            message=f"{label} — {phrase}",
        )
    return result


def _void_approver(db: Session, approved_by_id: uuid.UUID | None, store_id: uuid.UUID) -> User:
    if approved_by_id is None:
        raise ApiError(403, "approval_required", "A manager must approve voiding an item already sent to the kitchen.")
    approver = db.get(User, approved_by_id)
    if approver is None or Permission.POS_VOID_SENT_ITEM.value not in approver.permissions:
        raise ApiError(403, "approval_required", "The approving manager cannot void sent items.")
    if approver.store_id is not None and approver.store_id != store_id:
        raise ApiError(403, "store_scope", "The approving manager is not assigned to this store.")
    return approver


def _reason_code(reason: str | None) -> str:
    from app.services.cancellation_report import classify

    return classify(reason)[0]


def _fanout(order: OpenOrder, result: OrderOut, event_type: str, message: str, item_ids: list[str]) -> None:
    """Tell every screen on this store. The message stays free of staff reasons and internal notes."""
    from app.websockets.table_sync import publish

    publish(
        order.store_id,
        {
            "type": event_type,
            "store_id": str(order.store_id),
            "table_id": str(order.table_id) if order.table_id is not None else None,
            "table_label": result.table_label,
            "order_id": str(order.id),
            "item_ids": item_ids,
            "message": message,
        },
    )


def void_item(db: Session, principal: Principal, order_id: uuid.UUID, item_id: uuid.UUID, data: ItemVoid) -> OrderOut:
    order = _writable(db, principal, order_id, data.revision)
    actor = _actor(db, principal, data.user_id, order.store_id)
    item = next((line for line in order.items if line.id == item_id), None)
    if item is None or item.voided_at is not None:
        raise ApiError(404, "not_found", "That line is not on this order.")
    if item.paid_sale_id is not None:
        raise ApiError(409, "already_paid", "That line is already paid; refund it from Returns.")
    approver = _void_approver(db, data.approved_by_id, order.store_id) if item.sent_at is not None else None
    item.voided_at = _now()
    item.void_reason = data.reason.strip()
    item.voided_by_id = (approver or actor).id
    if item.sent_at is not None:
        for hook in ON_VOID:
            hook(db, order, [item])
        audit.record(
            db,
            action_type="ITEM_VOID",
            action="order.void_sent_item",
            target_entity="OpenOrder",
            target_entity_id=order.id,
            store_id=order.store_id,
            user_id=actor.id,
            approver_id=approver.id if approver else None,
            reason_notes=item.void_reason,
            details={
                "item_id": str(item.id),
                "product_id": str(item.product_id),
                "quantity": item.quantity,
                "reason_code": _reason_code(item.void_reason),
            },
        )
    if order.table_id is not None:
        from app.services.reservation_service import observe_order

        observe_order(db, order, "item_voided", "An item was removed.", actor.id)
    _touch(order)
    db.commit()
    result = orders_out(db, [order])[0]
    removed = next((item.product_name for item in result.items if item.id == item_id), "An item")
    label = result.table_label or result.name or f"#{result.number}"
    _fanout(order, result, "ORDER_ITEM_VOIDED", f"{label} — {removed} was removed.", [str(item_id)])
    return result


def request_bill(db: Session, principal: Principal, order_id: uuid.UUID, data: OrderAction) -> OrderOut:
    order = _writable(db, principal, order_id, data.revision)
    _actor(db, principal, data.user_id, order.store_id)
    order.bill_requested_at = _now()
    _touch(order)
    db.commit()
    result = orders_out(db, [order])[0]
    from app.websockets.table_sync import publish

    publish(
        order.store_id,
        {
            "type": "BILL_REQUESTED",
            "store_id": str(order.store_id),
            "table_id": str(order.table_id) if order.table_id is not None else None,
            "table_label": result.table_label,
            "order_id": str(order.id),
            "message": f"{result.table_label or 'A guest'} requested the bill.",
        },
    )
    from app.websockets.rooms import publish_table_alert

    publish_table_alert(
        order.store_id,
        alert="request-bill",
        table_id=order.table_id,
        table_name=result.table_label or "Table",
        total_amount=result.open_cents,
    )
    return result


def _cancel_stage(db: Session, order: OpenOrder) -> str:
    """Where this open tab is, using the statuses the kitchen and delivery channel already store."""
    if order.status == "SETTLED" or any(item.paid_sale_id is not None for item in order.items):
        return "completed"
    if order.channel_status in {"ACCEPTED", "COMPLETED"}:
        return "dispatched"
    sent = [item for item in live_items(order) if item.sent_at is not None]
    if not sent:
        return "draft"
    marks: dict[uuid.UUID, str] = {}
    for hook in KITCHEN_STATUS:
        marks.update(hook(db, [item.id for item in sent]))
    progress = set(marks.values())
    if "preparing" in progress:
        return "preparing"
    if "ready" in progress:
        return "ready"
    return "kitchen"


_INVENTORY_OUTCOME = {
    "draft": "none_reserved",
    "kitchen": "none_consumed",
    "preparing": "wastage_recorded",
    "ready": "wastage_recorded",
    "dispatched": "awaiting_return",
}


def void_order(db: Session, principal: Principal, order_id: uuid.UUID, data: ItemVoid) -> OrderOut:
    order = _order(db, principal, order_id, lock=True)
    if order.status == "VOID":
        return orders_out(db, [order])[0]
    if order.status == "SETTLED" or any(item.paid_sale_id is not None for item in order.items):
        raise ApiError(409, "already_paid", "This sale is complete. Refund it from Returns.")
    if order.status != "OPEN":
        raise ApiError(409, "order_closed", f"Order {order.number} is already {order.status.lower()}.")
    if data.revision != order.revision:
        raise ApiError(409, "stale_order", f"Order {order.number} changed on another register. Refresh and try again.")
    actor = _actor(db, principal, data.user_id, order.store_id)
    stage = _cancel_stage(db, order)
    sent = [item for item in live_items(order) if item.sent_at is not None]
    approver = _void_approver(db, data.approved_by_id, order.store_id) if stage != "draft" else None
    now = _now()
    reason = data.reason.strip()
    for item in live_items(order):
        item.voided_at = now
        item.void_reason = reason
        item.voided_by_id = (approver or actor).id
    if sent:
        for hook in ON_VOID:
            hook(db, order, sent)
    previous = order.status
    order.status = "VOID"
    order.closed_at = now
    audit.record(
        db,
        action_type="ITEM_VOID" if sent else "UPDATE",
        action="order.void",
        target_entity="OpenOrder",
        target_entity_id=order.id,
        store_id=order.store_id,
        user_id=actor.id,
        approver_id=approver.id if approver else None,
        reason_notes=reason,
        details={
            "number": order.number,
            "sent_lines": len(sent),
            "reason_code": _reason_code(reason),
            "stage": stage,
            "previous_status": previous,
            "outcome": "VOID",
            "inventory": _INVENTORY_OUTCOME[stage],
            "kitchen_notified": bool(sent),
            "delivery_notified": stage == "dispatched",
        },
    )
    if order.table_id is not None:
        from app.services.reservation_service import observe_order

        observe_order(db, order, "order_cancelled", f"Order {order.number} cancelled.", actor.id)
    _touch(order)
    db.commit()
    result = orders_out(db, [order])[0]
    label = result.table_label or result.name or f"#{result.number}"
    _fanout(order, result, "ORDER_CANCELLED", f"{label} was cancelled.", [])
    if order.table_id is not None:
        from app.websockets.table_sync import publish

        publish(
            order.store_id,
            {
                "type": "TABLE_SESSION_CLOSED",
                "store_id": str(order.store_id),
                "table_id": str(order.table_id),
                "table_label": result.table_label,
                "order_id": str(order.id),
            },
        )
    return result


def move_order(db: Session, principal: Principal, order_id: uuid.UUID, data: OrderMove) -> OrderOut:
    order = _writable(db, principal, order_id, data.revision)
    _actor(db, principal, data.user_id, order.store_id)
    _table(db, data.table_id, order.store_id)
    order.table_id = data.table_id
    _touch(order)
    db.commit()
    return orders_out(db, [order])[0]


def merge_order(db: Session, principal: Principal, order_id: uuid.UUID, data: OrderMerge) -> OrderOut:
    """Folds this order's unpaid lines into another open order at the same store; this order is voided."""
    if data.into_order_id == order_id:
        raise ApiError(422, "invalid_request", "Pick a different order to merge into.")
    source = _writable(db, principal, order_id, data.revision)
    target = _writable(db, principal, data.into_order_id, data.into_revision)
    actor = _actor(db, principal, data.user_id, source.store_id)
    if source.store_id != target.store_id:
        raise ApiError(422, "invalid_request", "Orders can only merge within one store.")
    if any(item.paid_sale_id is not None for item in source.items):
        raise ApiError(409, "already_paid", "Part of this order is paid; it cannot be merged.")
    position = max((item.position for item in target.items), default=-1) + 1
    moved = 0
    for item in list(live_items(source)):
        item.order_id = target.id
        item.position = position
        position += 1
        moved += 1
    source.status = "VOID"
    source.closed_at = _now()
    target.covers += source.covers
    audit.record(
        db,
        action_type="UPDATE",
        action="order.merge",
        target_entity="OpenOrder",
        target_entity_id=target.id,
        store_id=target.store_id,
        user_id=actor.id,
        details={"from_order": str(source.id), "from_number": source.number, "lines": moved},
    )
    _touch(source)
    _touch(target)
    db.commit()
    db.expire_all()
    return orders_out(db, [db.get(OpenOrder, target.id)])[0]  # type: ignore[list-item]


# --- Settling ---------------------------------------------------------------------------------------------


def settle(db: Session, data: SalePayload, sale_id: uuid.UUID) -> None:
    """Called by record_sale for a sale carrying order_id: marks the lines it paid and closes a fully paid order.

    A sale is real money, so a missing or already-closed order never rejects it; the link is just recorded."""
    if data.order_id is None:
        return
    order = db.get(OpenOrder, data.order_id)
    if order is None or order.store_id != data.store_id:
        audit.record(
            db,
            action_type="UPDATE",
            action="order.settle_unmatched",
            target_entity="Sale",
            target_entity_id=sale_id,
            store_id=data.store_id,
            client_device="system",
            details={"order_id": str(data.order_id)},
        )
        return
    wanted = set(data.order_item_ids) if data.order_item_ids else None
    for item in live_items(order):
        if item.paid_sale_id is None and (wanted is None or item.id in wanted):
            item.paid_sale_id = sale_id
    if all(item.paid_sale_id is not None for item in live_items(order)):
        order.status = "SETTLED"
        order.closed_at = _now()
        if order.channel_id is not None:
            order.channel_status = "COMPLETED"
    _touch(order)
    if order.table_id is not None:
        from app.services.reservation_service import observe_order

        discount = sum(item.discount_cents + item.manual_discount_cents for item in data.items)
        kind = "Payment completed." if order.status == "SETTLED" else "Partial payment recorded."
        observe_order(db, order, "payment", kind, data.cashier_id, discount_cents=discount)
    db.flush()


# --- Offline sync -----------------------------------------------------------------------------------------


def apply_open_order(db: Session, settings: Settings, payload: dict[str, object], ctx: SyncContext) -> uuid.UUID:
    data = parse_payload(OrderSyncPayload, payload)
    require_store(db, data.store_id)
    opener = db.get(User, data.opened_by_id)
    if opener is None:
        raise SyncRejected("The cashier who opened this order does not exist.")
    order = db.get(OpenOrder, data.id)
    created = order is None
    if order is None:
        if data.service_type == "DINE_IN" and data.table_id is not None:
            taken = _open_dine_in(db, data.table_id)
            if taken is not None:
                raise SyncRejected("That table already has an open order. Reopen it instead of starting another.")
        order = OpenOrder(
            id=data.id,
            store_id=data.store_id,
            number=_next_number(db, data.store_id),
            service_type=data.service_type,
            table_id=data.table_id if data.table_id and db.get(DiningTable, data.table_id) else None,
            covers=data.covers,
            name=(data.name or "").strip() or None,
            note=(data.note or "").strip() or None,
            opened_by_id=opener.id,
            revision=1,
            opened_at=_aware(data.opened_at) or _now(),
            updated_at=_now(),
        )
        db.add(order)
        db.flush()
    elif order.store_id != data.store_id:
        raise SyncRejected("This order belongs to another store.")
    if order.status == "OPEN" and "service_type" in payload and data.service_type != order.service_type:
        if data.name:
            order.name = data.name.strip() or order.name
        if data.note:
            order.note = data.note.strip() or order.note
        try:
            _convert_service(
                db,
                order,
                opener,
                target=data.service_type,
                table_id=data.table_id,
                reason="Synced from the register",
            )
        except ApiError as exc:
            raise SyncRejected(exc.message) from exc
    known = {item.id: item for item in order.items}
    position = max((item.position for item in order.items), default=-1) + 1
    fresh: list[OpenOrderItem] = []
    voided_now: list[OpenOrderItem] = []
    for line in data.items:
        existing = known.get(line.id)
        if existing is not None:
            if (
                order.status == "OPEN"
                and line.voided_at is not None
                and existing.voided_at is None
                and existing.paid_sale_id is None
            ):
                existing.voided_at = _aware(line.voided_at)
                existing.void_reason = (line.void_reason or "Cancelled offline").strip()[:160]
                voided_now.append(existing)
            continue
        if db.get(Product, line.product_id) is None:
            continue
        item = _item(order, line, position, opener.id)
        item.sent_at = _aware(line.sent_at)
        item.voided_at = _aware(line.voided_at)
        item.void_reason = line.void_reason
        order.items.append(item)
        if item.sent_at is not None and item.voided_at is None:
            fresh.append(item)
        position += 1
    if fresh and order.status == "OPEN":
        for hook in ON_SEND:
            hook(db, order, fresh)
    if voided_now and order.status == "OPEN":
        sent_voids = [item for item in voided_now if item.sent_at is not None]
        if sent_voids:
            for hook in ON_VOID:
                hook(db, order, sent_voids)
    if order.status == "OPEN" and order.items and not live_items(order):
        order.status = "VOID"
        order.closed_at = _now()
        audit.record(
            db,
            action_type="ITEM_VOID",
            action="order.void",
            target_entity="OpenOrder",
            target_entity_id=order.id,
            store_id=order.store_id,
            user_id=opener.id,
            reason_notes=next((item.void_reason for item in order.items if item.void_reason), "Cancelled offline"),
            details={"stage": "offline", "previous_status": "OPEN", "outcome": "VOID", "inventory": "none_consumed"},
        )
    from app.services.reservation_service import attach_order, observe_order

    attach_order(db, order, order.customer_id)
    if order.table_id is not None and created:
        observe_order(db, order, "order_created", f"Order {order.number} created.", opener.id)
    if fresh:
        observe_order(db, order, "items_added", f"{len(fresh)} item(s) added.", opener.id)
    if voided_now:
        observe_order(db, order, "item_voided", "An item was removed.", opener.id)
    if order.status == "VOID":
        observe_order(db, order, "order_cancelled", f"Order {order.number} cancelled.", opener.id)
    _touch(order)
    db.flush()
    return order.id


register_handler("open_order", apply_open_order)


# --- Floor plan -------------------------------------------------------------------------------------------


def service_phases(order: OpenOrder | None, kitchen: dict[uuid.UUID, str]) -> tuple[str, str, str]:
    """Kitchen, payment, and order progress from the open tab. Occupancy stays on the table status."""
    if order is None:
        return "none", "none", "none"
    live = live_items(order)
    sent = [item for item in live if item.sent_at is not None]
    paid = [item for item in live if item.paid_sale_id is not None]
    unpaid = [item for item in live if item.paid_sale_id is None]
    if order.bill_requested_at is not None and unpaid:
        payment = "pending"
    elif paid and unpaid:
        payment = "partial"
    elif unpaid:
        payment = "unpaid"
    elif paid:
        payment = "paid"
    else:
        payment = "none"
    marks = [kitchen[item.id] for item in sent if item.id in kitchen]
    if not sent:
        phase = "none"
    elif not marks:
        phase = "queued"
    elif len(marks) == len(sent) and all(mark == "bumped" for mark in marks):
        phase = "served"
    elif any(mark == "ready" for mark in marks) and any(mark in {"new", "preparing"} for mark in marks):
        phase = "partial"
    elif all(mark in {"ready", "bumped"} for mark in marks) and any(mark == "ready" for mark in marks):
        phase = "ready"
    elif any(mark == "preparing" for mark in marks):
        phase = "preparing"
    else:
        phase = "queued"
    if not live or not sent:
        progress = "draft"
    elif phase in {"preparing", "partial", "ready", "served"}:
        progress = "in_progress"
    else:
        progress = "submitted"
    return phase, payment, progress


def kitchen_counts(order: OpenOrder | None, kitchen: dict[uuid.UUID, str]) -> tuple[int, int]:
    """Ready-or-served lines over lines already sent. Voided lines and unsent drafts stay out of the count."""
    if order is None:
        return 0, 0
    sent = [item for item in live_items(order) if item.sent_at is not None]
    ready = sum(1 for item in sent if kitchen.get(item.id) in {"ready", "bumped"})
    return ready, len(sent)


def _table_out(table: DiningTable, order: OpenOrder | None, kitchen: dict[uuid.UUID, str]) -> DiningTableOut:
    status = "free"
    if order is not None:
        status = (
            "bill"
            if order.bill_requested_at is not None
            else "ordered"
            if any(item.sent_at is not None for item in live_items(order))
            else "seated"
        )
    phase, payment, progress = service_phases(order, kitchen)
    ready_count, sent_count = kitchen_counts(order, kitchen)
    return DiningTableOut(
        id=table.id,
        area_id=table.area_id,
        label=table.label,
        seats=table.seats,
        shape=table.shape,  # type: ignore[arg-type]
        x=table.x,
        y=table.y,
        w=table.w,
        h=table.h,
        is_active=table.is_active,
        status=status,  # type: ignore[arg-type]
        order_id=order.id if order else None,
        order_number=order.number if order else None,
        covers=order.covers if order else 0,
        seated_at=order.opened_at if order else None,
        open_cents=open_cents(order) if order else 0,
        guest_name=(order.name or "").strip() or None if order else None,
        kitchen=phase,  # type: ignore[arg-type]
        payment=payment,  # type: ignore[arg-type]
        order_progress=progress,  # type: ignore[arg-type]
        kitchen_ready=ready_count,
        kitchen_sent=sent_count,
    )


def floor(db: Session, principal: Principal, store_id: uuid.UUID) -> FloorOut:
    _scope(principal, store_id)
    areas = db.scalars(
        select(DiningArea).where(DiningArea.store_id == store_id).order_by(DiningArea.position, DiningArea.name)
    ).all()
    tables = (
        db.scalars(
            select(DiningTable).where(DiningTable.area_id.in_([area.id for area in areas])).order_by(DiningTable.label)
        ).all()
        if areas
        else []
    )
    open_by_table = {
        order.table_id: order
        for order in db.scalars(
            select(OpenOrder).where(
                OpenOrder.store_id == store_id, OpenOrder.status == "OPEN", OpenOrder.table_id.is_not(None)
            )
        )
    }
    kitchen: dict[uuid.UUID, str] = {}
    item_ids = [item.id for order in open_by_table.values() for item in order.items]
    for hook in KITCHEN_STATUS:
        kitchen.update(hook(db, item_ids))
    return FloorOut(
        store_id=store_id,
        areas=[
            DiningAreaOut(
                id=area.id,
                store_id=area.store_id,
                name=area.name,
                position=area.position,
                is_active=area.is_active,
                tables=[
                    _table_out(table, open_by_table.get(table.id), kitchen)
                    for table in tables
                    if table.area_id == area.id
                ],
            )
            for area in areas
        ],
    )


def save_area(db: Session, principal: Principal, area_id: uuid.UUID | None, data: DiningAreaIn) -> FloorOut:
    _scope(principal, data.store_id)
    area = db.get(DiningArea, area_id) if area_id else DiningArea()
    if area is None:
        raise ApiError(404, "not_found", "Dining area was not found.")
    area.store_id, area.name, area.position, area.is_active = (
        data.store_id,
        data.name.strip(),
        data.position,
        data.is_active,
    )
    db.add(area)
    db.commit()
    return floor(db, principal, data.store_id)


def save_table(db: Session, principal: Principal, table_id: uuid.UUID | None, data: DiningTableIn) -> FloorOut:
    area = db.get(DiningArea, data.area_id)
    if area is None:
        raise ApiError(404, "not_found", "Dining area was not found.")
    _scope(principal, area.store_id)
    table = db.get(DiningTable, table_id) if table_id else DiningTable()
    if table is None:
        raise ApiError(404, "not_found", "Table was not found.")
    clash = db.scalar(
        select(DiningTable.id).where(
            DiningTable.area_id == data.area_id, DiningTable.label == data.label.strip(), DiningTable.id != table.id
        )
    )
    if clash is not None:
        raise ApiError(409, "conflict", f"Table {data.label} already exists in {area.name}.")
    for name, value in data.model_dump().items():
        setattr(table, name, value.strip() if isinstance(value, str) and name == "label" else value)
    db.add(table)
    db.commit()
    return floor(db, principal, area.store_id)


def delete_table(db: Session, principal: Principal, table_id: uuid.UUID) -> None:
    table = db.get(DiningTable, table_id)
    if table is None:
        raise ApiError(404, "not_found", "Table was not found.")
    area = db.get(DiningArea, table.area_id)
    if area is None:
        raise ApiError(404, "not_found", "Dining area was not found.")
    _scope(principal, area.store_id)
    seated = db.scalar(select(OpenOrder.id).where(OpenOrder.table_id == table.id, OpenOrder.status == "OPEN"))
    if seated is not None:
        raise ApiError(
            409,
            "table_in_use",
            f"{table.label} has an open order. Settle or move it before deleting the table.",
        )
    db.delete(table)
    db.commit()


def orders_enabled(db: Session) -> bool:
    return has_capability(db, Capability.OPEN_ORDERS)
