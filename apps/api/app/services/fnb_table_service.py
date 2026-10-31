"""Table sessions for restaurant, cafe, and quick-service businesses.

A session is the store's open order for that table. Starting one attaches (or creates) the guest.
Each round is appended to the same order and fired to the kitchen, until the cashier settles it.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.capabilities import FOOD_AND_BEVERAGE
from app.core.deps import Principal
from app.core.errors import ApiError, SyncRejected
from app.models.customer import Customer
from app.models.product import Product
from app.models.restaurant import DiningArea, DiningTable, OpenOrder
from app.models.user import User
from app.schemas.fnb_tables import (
    ActiveSessionOut,
    AddRound,
    RoundItem,
    SessionStart,
    TableMenuItem,
    TableMenuOut,
    WaiterCallOut,
)
from app.schemas.orders import OrderAction, OrderCreate, OrderItemIn, OrderItemsAdd
from app.schemas.payloads import ModifierChoice
from app.schemas.wholesale import CustomerWrite
from app.services import menu_service, order_service, product_image_service
from app.services.customer_service import new_customer
from app.services.settings_service import cached_settings


def _food(db: Session) -> None:
    profile = cached_settings(db).business_profile
    if profile not in FOOD_AND_BEVERAGE:
        raise ApiError(
            403,
            "forbidden",
            "Table ordering is only available for restaurant, cafe, and quick-service businesses.",
        )


def _digits(value: str) -> str:
    return "".join(character for character in value if character.isdigit())


def _table(db: Session, principal: Principal, table_id: uuid.UUID) -> tuple[DiningTable, DiningArea]:
    table = db.get(DiningTable, table_id)
    area = db.get(DiningArea, table.area_id) if table is not None else None
    if table is None or area is None or not table.is_active or not area.is_active:
        raise ApiError(404, "not_found", "That table was not found.")
    if principal.store_id is not None and principal.store_id != area.store_id:
        raise ApiError(403, "store_scope", "You can only work tables in your own store.")
    return table, area


def _open_order(db: Session, table_id: uuid.UUID) -> OpenOrder | None:
    return db.scalar(
        select(OpenOrder)
        .where(OpenOrder.table_id == table_id, OpenOrder.status == "OPEN")
        .order_by(OpenOrder.opened_at.desc())
        .limit(1)
    )


def _server_id(db: Session, principal: Principal, store_id: uuid.UUID, user_id: uuid.UUID | None) -> uuid.UUID:
    if principal.user is not None:
        return principal.user.id
    if user_id is not None:
        return user_id
    user = db.scalar(
        select(User)
        .where(User.is_active.is_(True), User.has_pos_access.is_(True))
        .order_by(User.created_at)
        .limit(1)
    )
    if user is None:
        raise ApiError(422, "invalid_request", "No cashier is set up to open tables.")
    if user.store_id is not None and user.store_id != store_id:
        raise ApiError(403, "store_scope", "That cashier is not assigned to this store.")
    return user.id


def _attach_customer(db: Session, phone: str) -> Customer:
    digits = _digits(phone)
    if len(digits) < 8 or len(digits) > 15:
        raise ApiError(422, "invalid_phone", "Enter a mobile number, for example 0551234567.")
    suffix = digits[-9:]
    for customer in db.scalars(select(Customer).where(Customer.phone.is_not(None), Customer.phone.contains(suffix))):
        if _digits(customer.phone or "").endswith(suffix):
            return customer
    shown = phone.strip()
    customer = new_customer(
        db,
        CustomerWrite(name=f"Guest {shown}"[:120], phone=shown, customer_type="RETAIL"),
    )
    db.flush()
    return customer


def _session(db: Session, table: DiningTable, order: OpenOrder | None) -> ActiveSessionOut:
    customer = db.get(Customer, order.customer_id) if order is not None and order.customer_id is not None else None
    shown = order_service.orders_out(db, [order])[0] if order is not None else None
    if shown is not None:
        shown = shown.model_copy(
            update={"items": [item.model_copy(update={"void_reason": None}) for item in shown.items]}
        )
    return ActiveSessionOut(
        status="OCCUPIED" if order is not None else "FREE",
        table_id=table.id,
        table_label=table.label,
        order=shown,
        customer_name=customer.name if customer is not None else (order.name if order is not None else None),
        phone=customer.phone if customer is not None else None,
        loyalty_points=customer.loyalty_points if customer is not None else 0,
    )


def _course(category: str) -> str:
    text = category.lower()
    if any(word in text for word in ("starter", "appet", "soup", "salad")):
        return "Starters"
    if any(word in text for word in ("drink", "beverage", "coffee", "tea", "juice")):
        return "Beverages"
    if any(word in text for word in ("dessert", "sweet", "cake")):
        return "Desserts"
    return "Mains"


def menu(db: Session, principal: Principal, store_id: uuid.UUID) -> TableMenuOut:
    _food(db)
    if principal.store_id is not None and principal.store_id != store_id:
        raise ApiError(403, "store_scope", "You can only read the menu of your own store.")
    register = menu_service.register_menu(db)
    groups = {group.id: group for group in register.groups}
    items: list[TableMenuItem] = []
    products = list(
        db.scalars(
            select(Product)
            .where(
                Product.item_type != "RAW_INGREDIENT",
                Product.is_serialized.is_(False),
                Product.sold_by_weight.is_(False),
            )
            .order_by(Product.category, Product.name)
            .limit(500)
        )
    )
    covers = product_image_service.cover_urls(db, products)
    for product in products:
        linked = []
        for group_id in register.products.get(str(product.id), []):
            group = groups.get(group_id)
            if group is not None:
                linked.append(group)
        image_url, thumb_url = covers.get(product.id, (None, None))
        items.append(
            TableMenuItem(
                id=product.id,
                name=product.name,
                course=_course(product.category),  # type: ignore[arg-type]
                price_cents=product.price_cents,
                currency=product.currency,
                image_url=thumb_url or image_url,
                groups=linked,
            )
        )
    return TableMenuOut(items=items)


def call_waiter(db: Session, principal: Principal, table_id: uuid.UUID) -> WaiterCallOut:
    """Tells every screen watching this store that the table wants a server. Nothing is stored."""
    _food(db)
    table, area = _table(db, principal, table_id)
    order = _open_order(db, table.id)
    message = f"Table {table.label} is calling for a waiter."
    from app.websockets.table_sync import publish

    publish(
        area.store_id,
        {
            "type": "CALL_WAITER",
            "store_id": str(area.store_id),
            "table_id": str(table.id),
            "table_label": table.label,
            "order_id": str(order.id) if order is not None else None,
            "message": message,
        },
    )
    from app.websockets.rooms import publish_table_alert

    publish_table_alert(
        area.store_id,
        alert="call-waiter",
        table_id=table.id,
        table_name=table.label,
        total_amount=None,
    )
    return WaiterCallOut(table_id=table.id, table_label=table.label, message=message)


def request_table_bill(db: Session, principal: Principal, table_id: uuid.UUID) -> ActiveSessionOut:
    """Guest asked for the check. The tablet has no cashier, so the store's server is recorded on the order."""
    _food(db)
    table, area = _table(db, principal, table_id)
    order = _open_order(db, table.id)
    if order is None:
        raise ApiError(404, "not_found", "This table has no open order.")
    server_id = _server_id(db, principal, area.store_id, None)
    order_service.request_bill(db, principal, order.id, OrderAction(revision=order.revision, user_id=server_id))
    return _session(db, table, _open_order(db, table.id))


def start_session(db: Session, principal: Principal, table_id: uuid.UUID, data: SessionStart) -> ActiveSessionOut:
    _food(db)
    table, area = _table(db, principal, table_id)
    server_id = _server_id(db, principal, area.store_id, data.user_id)
    phone = (data.phone or "").strip()
    customer = _attach_customer(db, phone) if phone else None
    order = _open_order(db, table.id)
    if order is None:
        created = order_service.create_order(
            db,
            principal,
            OrderCreate(
                id=uuid.uuid4(),
                store_id=area.store_id,
                service_type="DINE_IN",
                table_id=table.id,
                covers=data.covers,
                name=(customer.name if customer is not None else "Walk-in guest")[:80],
                customer_id=customer.id if customer is not None else None,
                user_id=server_id,
            ),
        )
        order = db.get(OpenOrder, created.id)
    else:
        if customer is not None and order.customer_id is None:
            order.customer_id = customer.id
            order.name = customer.name[:80]
        if data.covers:
            order.covers = data.covers
        db.commit()
        db.refresh(order)
    assert order is not None
    from app.services.reservation_service import ensure_seating_for_order

    ensure_seating_for_order(db, order)
    return _session(db, table, db.get(OpenOrder, order.id) or order)


def active_session(db: Session, principal: Principal, table_id: uuid.UUID) -> ActiveSessionOut:
    _food(db)
    table, _area = _table(db, principal, table_id)
    order = _open_order(db, table.id)
    if order is None:
        raise ApiError(404, "no_session", "This table has no open session.")
    return _session(db, table, order)


def _priced(db: Session, item: RoundItem) -> tuple[int, list[ModifierChoice]]:
    product = db.get(Product, item.product_id)
    if product is None:
        raise ApiError(422, "invalid_request", "An ordered product does not exist.")
    try:
        _delta, snapshot = menu_service.price_choices(db, product, item.modifiers)
    except SyncRejected as exc:
        raise ApiError(422, "invalid_modifier", exc.message) from exc
    choices = [
        ModifierChoice(
            group_id=uuid.UUID(row["group_id"]),
            option_id=uuid.UUID(row["option_id"]),
            group=row["group"],
            option=row["option"],
            price_delta_cents=int(row["price_delta_cents"]),
        )
        for row in (snapshot or [])
    ]
    return product.price_cents + sum(choice.price_delta_cents for choice in choices), choices


def _add_once(db: Session, principal: Principal, order: OpenOrder, data: AddRound, server_id: uuid.UUID) -> None:
    lines: list[OrderItemIn] = []
    for index, item in enumerate(data.items):
        unit, choices = _priced(db, item)
        item_id = (
            uuid.uuid5(uuid.NAMESPACE_URL, f"{data.client_round_id}:{index}")
            if data.client_round_id is not None
            else uuid.uuid4()
        )
        lines.append(
            OrderItemIn(
                id=item_id,
                product_id=item.product_id,
                quantity=item.quantity,
                unit_price_cents=unit,
                modifiers=choices,
                note=item.note,
            )
        )
    added = order_service.add_items(
        db, principal, order.id, OrderItemsAdd(revision=order.revision, user_id=server_id, items=lines)
    )
    try:
        order_service.send_order(db, principal, order.id, OrderAction(revision=added.revision, user_id=server_id))
    except ApiError as exc:
        if exc.code != "nothing_to_send":
            raise


def add_round(db: Session, principal: Principal, table_id: uuid.UUID, data: AddRound) -> ActiveSessionOut:
    _food(db)
    table, area = _table(db, principal, table_id)
    order = _open_order(db, table.id)
    if order is None:
        raise ApiError(409, "no_session", "Start a table session before sending dishes.")
    server_id = _server_id(db, principal, area.store_id, data.user_id)
    try:
        _add_once(db, principal, order, data, server_id)
    except ApiError as exc:
        if exc.code != "stale_order":
            raise
        fresh = _open_order(db, table.id)
        if fresh is None:
            raise
        _add_once(db, principal, fresh, data, server_id)
    refreshed = _open_order(db, table.id)
    assert refreshed is not None
    return _session(db, table, refreshed)
