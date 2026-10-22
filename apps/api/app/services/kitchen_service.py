"""Kitchen display. Sending an order fires its new lines as one ticket per station (routed by category); stations
poll their board with `since`, move tickets NEW -> PREPARING -> READY -> BUMPED, and can recall a bumped ticket."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.capabilities import Capability, has_capability
from app.core.deps import Principal
from app.core.errors import ApiError
from app.models.kitchen import TICKET_STATUSES, KitchenStation, KitchenTicket, KitchenTicketItem
from app.models.product import Product
from app.models.restaurant import DiningTable, OpenOrder, OpenOrderItem
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.schemas.kitchen import KitchenStationIn, KitchenStationOut, TicketBoard, TicketItemOut, TicketOut
from app.services import order_service
from app.services.settings_service import cached_settings

# Bumped tickets stay on the first load this long, so a station can recall one it bumped by mistake.
RECALL_WINDOW = timedelta(minutes=30)
COUNTER_FIRE_WINDOW = timedelta(hours=2)
SERVICE_LABELS = {"DINE_IN": "Dine in", "TAKEAWAY": "Takeaway", "DELIVERY": "Delivery"}


def _now() -> datetime:
    return datetime.now(UTC)


def _scope(principal: Principal, store_id: uuid.UUID) -> None:
    if principal.store_id is not None and principal.store_id != store_id:
        raise ApiError(403, "store_scope", "This kitchen screen belongs to another store.")


# --- Stations ---------------------------------------------------------------------------------------------


def _station_out(station: KitchenStation) -> KitchenStationOut:
    return KitchenStationOut(
        id=station.id,
        store_id=station.store_id,
        name=station.name,
        category_ids=[uuid.UUID(value) for value in station.category_ids or []],
        is_default=station.is_default,
        print_tickets=station.print_tickets,
        position=station.position,
        is_active=station.is_active,
    )


def list_stations(db: Session, principal: Principal, store_id: uuid.UUID) -> list[KitchenStationOut]:
    _scope(principal, store_id)
    stations = db.scalars(
        select(KitchenStation)
        .where(KitchenStation.store_id == store_id)
        .order_by(KitchenStation.position, KitchenStation.name)
    ).all()
    return [_station_out(station) for station in stations]


def save_station(
    db: Session, principal: Principal, station_id: uuid.UUID | None, data: KitchenStationIn
) -> KitchenStationOut:
    _scope(principal, data.store_id)
    station = db.get(KitchenStation, station_id) if station_id else KitchenStation()
    if station is None:
        raise ApiError(404, "not_found", "Kitchen station was not found.")
    station.store_id = data.store_id
    station.name = data.name.strip()
    station.category_ids = sorted({str(value) for value in data.category_ids})
    station.is_default = data.is_default
    station.print_tickets = data.print_tickets
    station.position = data.position
    station.is_active = data.is_active
    db.add(station)
    db.commit()
    return _station_out(station)


def _station(db: Session, principal: Principal, station_id: uuid.UUID) -> KitchenStation:
    station = db.get(KitchenStation, station_id)
    if station is None:
        raise ApiError(404, "not_found", "Kitchen station was not found.")
    _scope(principal, station.store_id)
    return station


# --- Tickets ----------------------------------------------------------------------------------------------


def _ticket_out(ticket: KitchenTicket, station: KitchenStation | None) -> TicketOut:
    return TicketOut(
        id=ticket.id,
        station_id=ticket.station_id,
        station_name=station.name if station else "Kitchen",
        print_tickets=bool(station and station.print_tickets),
        order_id=ticket.order_id,
        sale_id=ticket.sale_id,
        number=ticket.number,
        label=ticket.label,
        service_type=ticket.service_type,
        status=ticket.status,  # type: ignore[arg-type]
        fired_at=ticket.fired_at,
        started_at=ticket.started_at,
        ready_at=ticket.ready_at,
        bumped_at=ticket.bumped_at,
        updated_at=ticket.updated_at,
        items=[
            TicketItemOut(
                id=item.id,
                order_item_id=item.order_item_id,
                product_name=item.product_name,
                quantity=item.quantity,
                modifiers=item.modifiers or [],
                combo_name=item.combo_name,
                seat=item.seat,
                note=item.note,
                voided_at=item.voided_at,
            )
            for item in ticket.items
        ],
    )


def board(db: Session, principal: Principal, station_id: uuid.UUID, since: datetime | None) -> TicketBoard:
    """Without `since`: every live ticket plus recently bumped ones. With `since`: whatever changed after it,
    bumped tickets included, so the screen can drop them."""
    station = _station(db, principal, station_id)
    now = _now()
    statement = select(KitchenTicket).where(KitchenTicket.station_id == station.id)
    if since is not None:
        statement = statement.where(KitchenTicket.updated_at > since)
    else:
        statement = statement.where(
            (KitchenTicket.status != "BUMPED") | (KitchenTicket.bumped_at >= now - RECALL_WINDOW)
        )
    tickets = db.scalars(statement.order_by(KitchenTicket.fired_at)).all()
    timers = cached_settings(db).module_settings.kds
    return TicketBoard(
        server_time=now,
        station=_station_out(station),
        warn_minutes=timers.warn_minutes,
        late_minutes=timers.late_minutes,
        tickets=[_ticket_out(ticket, station) for ticket in tickets],
    )


def order_tickets(db: Session, principal: Principal, order_id: uuid.UUID) -> list[TicketOut]:
    order = db.get(OpenOrder, order_id)
    if order is None:
        raise ApiError(404, "not_found", "Order was not found.")
    _scope(principal, order.store_id)
    tickets = db.scalars(
        select(KitchenTicket).where(KitchenTicket.order_id == order_id).order_by(KitchenTicket.fired_at)
    ).all()
    return [_ticket_out(ticket, db.get(KitchenStation, ticket.station_id)) for ticket in tickets]


def _ticket(db: Session, principal: Principal, ticket_id: uuid.UUID) -> KitchenTicket:
    ticket = db.get(KitchenTicket, ticket_id, with_for_update=True)
    if ticket is None:
        raise ApiError(404, "not_found", "Ticket was not found.")
    _scope(principal, ticket.store_id)
    return ticket


def set_status(db: Session, principal: Principal, ticket_id: uuid.UUID, status: str) -> TicketOut:
    """Tickets only move forward here (a tap can skip a step); going back from BUMPED is a recall."""
    ticket = _ticket(db, principal, ticket_id)
    if TICKET_STATUSES.index(status) < TICKET_STATUSES.index(ticket.status):
        raise ApiError(409, "ticket_moved_on", "This ticket is already further along; refresh the screen.")
    now = _now()
    if status != "NEW" and ticket.started_at is None:
        ticket.started_at = now
    if status in ("READY", "BUMPED") and ticket.ready_at is None:
        ticket.ready_at = now
    if status == "BUMPED":
        ticket.bumped_at = now
    ticket.status = status
    ticket.updated_at = now
    db.commit()
    return _ticket_out(ticket, db.get(KitchenStation, ticket.station_id))


def recall(db: Session, principal: Principal, ticket_id: uuid.UUID) -> TicketOut:
    ticket = _ticket(db, principal, ticket_id)
    if ticket.status != "BUMPED":
        raise ApiError(409, "not_bumped", "Only a bumped ticket can be recalled.")
    ticket.status = "READY"
    ticket.bumped_at = None
    ticket.updated_at = _now()
    db.commit()
    return _ticket_out(ticket, db.get(KitchenStation, ticket.station_id))


# --- Order hooks ------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Line:
    product_id: uuid.UUID
    quantity: int
    modifiers: list | None
    order_item_id: uuid.UUID | None = None
    seat: int | None = None
    note: str | None = None
    components: list | None = None
    combo_name: str | None = None


def _expand(db: Session, lines: list[_Line]) -> list[_Line]:
    """A meal fires as its components, each to the station that makes it; the meal itself is never cooked."""
    meals = [line for line in lines if line.components]
    if not meals:
        return lines
    names = {
        product.id: product.name
        for product in db.scalars(select(Product).where(Product.id.in_({line.product_id for line in meals})))
    }
    out: list[_Line] = []
    for line in lines:
        if not line.components:
            out.append(line)
            continue
        for part in line.components:
            product_id = part.get("product_id") if isinstance(part, dict) else None
            if not product_id:
                continue
            out.append(
                _Line(
                    product_id=uuid.UUID(str(product_id)),
                    quantity=line.quantity,
                    modifiers=None,
                    order_item_id=line.order_item_id,
                    seat=line.seat,
                    note=line.note,
                    combo_name=names.get(line.product_id),
                )
            )
    return out


@dataclass(frozen=True)
class _Source:
    store_id: uuid.UUID
    number: int
    label: str
    service_type: str
    order_id: uuid.UUID | None = None
    sale_id: uuid.UUID | None = None


def _route(stations: list[KitchenStation], category_id: uuid.UUID | None) -> KitchenStation | None:
    """The station listing the item's category, else the default station; items neither claims don't fire."""
    if category_id is not None:
        key = str(category_id)
        for station in stations:
            if key in (station.category_ids or []):
                return station
    return next((station for station in stations if station.is_default), None)


def _fire(db: Session, source: _Source, lines: list[_Line]) -> None:
    if not lines or not has_capability(db, Capability.KDS):
        return
    stations = list(
        db.scalars(
            select(KitchenStation)
            .where(KitchenStation.store_id == source.store_id, KitchenStation.is_active.is_(True))
            .order_by(KitchenStation.position, KitchenStation.name)
        )
    )
    if not stations:
        return
    lines = _expand(db, lines)
    products = {
        product.id: product
        for product in db.scalars(select(Product).where(Product.id.in_({line.product_id for line in lines})))
    }
    grouped: dict[uuid.UUID, list[_Line]] = {}
    for line in lines:
        product = products.get(line.product_id)
        station = _route(stations, product.category_id if product else None)
        if station is not None:
            grouped.setdefault(station.id, []).append(line)
    now = _now()
    for station_id, routed in grouped.items():
        ticket = KitchenTicket(
            store_id=source.store_id,
            station_id=station_id,
            order_id=source.order_id,
            sale_id=source.sale_id,
            number=source.number,
            label=source.label,
            service_type=source.service_type,
            status="NEW",
            fired_at=now,
            updated_at=now,
        )
        for position, line in enumerate(routed):
            product = products.get(line.product_id)
            ticket.items.append(
                KitchenTicketItem(
                    order_item_id=line.order_item_id,
                    product_name=product.name if product else "Item",
                    quantity=line.quantity,
                    modifiers=line.modifiers or None,
                    combo_name=line.combo_name,
                    seat=line.seat,
                    note=line.note,
                    position=position,
                )
            )
        db.add(ticket)
    db.flush()


def _label(db: Session, order: OpenOrder) -> str:
    if order.table_id is not None:
        table = db.get(DiningTable, order.table_id)
        if table is not None:
            return f"Table {table.label}"
    return order.name or SERVICE_LABELS.get(order.service_type, order.service_type)


def fire(db: Session, order: OpenOrder, items: list[OpenOrderItem]) -> None:
    source = _Source(
        store_id=order.store_id,
        number=order.number,
        label=_label(db, order),
        service_type=order.service_type,
        order_id=order.id,
    )
    lines = [
        _Line(
            product_id=item.product_id,
            quantity=item.quantity,
            modifiers=item.modifiers,
            order_item_id=item.id,
            seat=item.seat,
            note=item.note,
            components=item.components,
        )
        for item in items
    ]
    _fire(db, source, lines)


def fire_sale(db: Session, sale: Sale, sold_at: datetime) -> None:
    """Counter service: a pay-first sale goes straight to the kitchen. A sale that syncs long after it was rung
    up (the register was offline) is history, not an order to cook."""
    if sale.order_id is not None or sold_at < _now() - COUNTER_FIRE_WINDOW:
        return
    if not has_capability(db, Capability.KDS):
        return
    items = db.scalars(select(SaleItem).where(SaleItem.sale_id == sale.id)).all()
    day_start = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    fired_today = db.scalar(
        select(func.count(func.distinct(KitchenTicket.sale_id))).where(
            KitchenTicket.store_id == sale.store_id,
            KitchenTicket.sale_id.is_not(None),
            KitchenTicket.fired_at >= day_start,
        )
    )
    source = _Source(
        store_id=sale.store_id,
        number=(fired_today or 0) + 1,
        label=sale.invoice_number or "Counter",
        service_type="TAKEAWAY",
        sale_id=sale.id,
    )
    _fire(
        db,
        source,
        [_Line(item.product_id, item.quantity, item.modifiers, components=item.components) for item in items],
    )


def void(db: Session, order: OpenOrder, items: list[OpenOrderItem]) -> None:
    """Strikes voided lines off their tickets; a ticket with nothing left is bumped off the screen."""
    ids = [item.id for item in items]
    if not ids:
        return
    lines = db.scalars(select(KitchenTicketItem).where(KitchenTicketItem.order_item_id.in_(ids))).all()
    now = _now()
    tickets: set[uuid.UUID] = set()
    for line in lines:
        if line.voided_at is None:
            line.voided_at = now
            tickets.add(line.ticket_id)
    db.flush()
    for ticket_id in tickets:
        ticket = db.get(KitchenTicket, ticket_id)
        if ticket is None:
            continue
        ticket.updated_at = now
        if all(line.voided_at is not None for line in ticket.items) and ticket.status != "BUMPED":
            ticket.status = "BUMPED"
            ticket.bumped_at = now
    db.flush()


def item_status(db: Session, item_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    """The kitchen progress of each order line (the latest ticket it is on), for the POS badges."""
    if not item_ids:
        return {}
    rows = db.execute(
        select(KitchenTicketItem.order_item_id, KitchenTicket.status)
        .join(KitchenTicket, KitchenTicket.id == KitchenTicketItem.ticket_id)
        .where(KitchenTicketItem.order_item_id.in_(item_ids), KitchenTicketItem.voided_at.is_(None))
        .order_by(KitchenTicket.fired_at)
    ).all()
    return {item_id: status.lower() for item_id, status in rows}


order_service.ON_SEND.append(fire)
order_service.ON_VOID.append(void)
order_service.KITCHEN_STATUS.append(item_status)
