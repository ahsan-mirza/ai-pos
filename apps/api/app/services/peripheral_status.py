"""Live status for companion screens and the branch card terminal.

A configuration row is never treated as a connection. Green requires an open
socket or a provider check that is still fresh. Local printers and keyboards
are observed on the register, not here, so an API outage does not speak for them.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.capabilities import Capability, has_capability
from app.core.config import Settings
from app.core.deps import Principal
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.models.kitchen import KitchenStation, KitchenTicket
from app.models.restaurant import DiningArea, DiningTable
from app.schemas.payments import TerminalCheck
from app.schemas.peripherals import PeripheralOut, PeripheralSnapshot
from app.services import integrated_payment_service
from app.websockets import rooms, table_sync

CHECK_FRESH = timedelta(minutes=15)
_OPEN_TICKETS = ("NEW", "PREPARING", "READY")


def kds_light(configured: int, connected: int) -> str | None:
    if configured <= 0:
        return None
    if connected <= 0:
        return "red"
    if connected < configured:
        return "amber"
    return "green"


def table_light(configured: bool, connected: int, ever_seen: bool) -> str | None:
    if not configured:
        return None
    if connected > 0:
        return "green"
    if ever_seen:
        return "red"
    return "gray"


def terminal_light(checked_at: datetime | None, ok: bool | None, *, now: datetime, fresh: timedelta) -> str:
    if ok is None or checked_at is None:
        return "gray"
    if not ok:
        return "red"
    seen = checked_at if checked_at.tzinfo is not None else checked_at.replace(tzinfo=UTC)
    if now - seen > fresh:
        return "amber"
    return "green"


def display_light(connected: int, ever_seen: bool) -> str | None:
    if connected > 0:
        return "green"
    if ever_seen:
        return "red"
    return None


def _store_id(principal: Principal) -> uuid.UUID:
    store_id = principal.store_id
    if store_id is None:
        raise ApiError(422, "register_unscoped", "This register is not assigned to a branch.")
    return store_id


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _kds(db: Session, store_id: uuid.UUID) -> PeripheralOut | None:
    if not has_capability(db, Capability.KDS):
        return None
    stations = list(
        db.scalars(
            select(KitchenStation)
            .where(KitchenStation.store_id == store_id, KitchenStation.is_active.is_(True))
            .order_by(KitchenStation.position)
        )
    )
    if not stations:
        return None
    connected = 0
    last: datetime | None = None
    prints_here = False
    for station in stations:
        room = rooms.kitchen_room(station.id)
        if rooms.room_count(room) > 0:
            connected += 1
        seen = rooms.last_seen(room)
        if seen is not None and (last is None or seen > last):
            last = seen
        prints_here = prints_here or station.print_tickets
    light = kds_light(len(stations), connected)
    pending = db.scalar(
        select(func.count(KitchenTicket.id)).where(
            KitchenTicket.store_id == store_id, KitchenTicket.status.in_(_OPEN_TICKETS)
        )
    ) or 0
    if light == "green":
        status = f"{connected} of {len(stations)} kitchen screens are connected."
    elif light == "amber":
        status = f"{connected} of {len(stations)} kitchen screens are connected. The others have no open socket."
    else:
        status = "No kitchen screen is connected. A station record alone is not a connection."
    if prints_here:
        status = f"{status} Stations set to print use the receipt printer on the register."
    return PeripheralOut(
        id=f"kds:{store_id}",
        kind="kds",
        label="KDS",
        name="Kitchen display",
        light=light,  # type: ignore[arg-type]
        status=status,
        connection="WebSocket",
        last_seen_at=last,
        last_ok_at=last if connected else None,
        pending=int(pending),
        connected=connected,
        configured=len(stations),
    )


def _tables(db: Session, store_id: uuid.UUID) -> PeripheralOut | None:
    if not has_capability(db, Capability.TABLES):
        return None
    configured = db.scalar(
        select(func.count(DiningTable.id))
        .join(DiningArea, DiningTable.area_id == DiningArea.id)
        .where(DiningArea.store_id == store_id, DiningArea.is_active.is_(True), DiningTable.is_active.is_(True))
    ) or 0
    if configured <= 0:
        return None
    key = f"{rooms.tenant_prefix()}:{store_id}"
    connected, last = table_sync.customer_presence(key)
    light = table_light(True, connected, last is not None)
    if connected > 0:
        status = (
            f"{connected} table-order session{'s' if connected != 1 else ''} connected. "
            "Waiter handhelds and table tablets share this session and are not listed separately."
        )
    elif last is not None:
        status = "A table-order session was connected and has disconnected."
    else:
        status = "Tables are configured. No waiter or table tablet has connected to this server."
    return PeripheralOut(
        id=f"tables:{store_id}",
        kind="table_apps",
        label="Tables",
        name="Table ordering",
        light=light,  # type: ignore[arg-type]
        status=status,
        connection="WebSocket",
        last_seen_at=last,
        last_ok_at=last if connected else None,
        connected=connected,
        configured=int(configured),
    )


def _display(principal: Principal) -> PeripheralOut | None:
    device = principal.device
    if device is None:
        return None
    room = rooms.customer_display_room(device.id)
    connected = rooms.room_count(room)
    seen = rooms.last_seen(room)
    light = display_light(connected, seen is not None)
    if light is None:
        return None
    if connected > 0:
        status = "A customer display is paired with this register over its socket."
    else:
        status = "The customer display socket disconnected. This is not a sale session."
    return PeripheralOut(
        id=f"display:{device.id}",
        kind="customer_display",
        label="Display",
        name="Customer display",
        light=light,  # type: ignore[arg-type]
        status=status,
        connection="WebSocket",
        last_seen_at=seen,
        last_ok_at=seen if connected else None,
        connected=connected,
        configured=1,
    )


def _terminal(db: Session, principal: Principal, store_id: uuid.UUID, now: datetime) -> PeripheralOut | None:
    if not has_capability(db, Capability.CARD_TERMINALS):
        return None
    rows = integrated_payment_service.active_terminals(db, store_id)
    if not rows:
        return None
    device_id = principal.device.id if principal.device is not None else None
    row = next((item for item in rows if device_id is not None and item.device_id == device_id), rows[0])
    checked = _aware(row.last_checked_at)
    light = terminal_light(checked, row.last_check_ok, now=now, fresh=CHECK_FRESH)
    if light == "green":
        status = "The provider accepted a connection check recently. Card numbers are not stored here."
    elif light == "amber":
        status = "The last provider check succeeded, but it is older than the freshness window."
    elif light == "red":
        status = "The last provider check failed."
    else:
        status = "A terminal is configured. The provider has not been checked, so this is not a live connection."
    assigned = "Assigned to this register." if row.device_id == device_id else "Store default terminal."
    return PeripheralOut(
        id=f"card:{row.id}",
        kind="card_terminal",
        label="Card",
        name=row.label,
        light=light,  # type: ignore[arg-type]
        status=f"{status} {assigned}",
        connection=row.provider,
        last_seen_at=checked,
        last_ok_at=checked if row.last_check_ok else None,
        last_error=None if row.last_check_ok is not False else "The last provider check failed.",
        connected=1 if light == "green" else 0,
        configured=len(rows),
    )


def snapshot(db: Session, principal: Principal, *, now: datetime | None = None) -> PeripheralSnapshot:
    store_id = _store_id(principal)
    moment = now or datetime.now(UTC)
    items = [
        item
        for item in (
            _kds(db, store_id),
            _tables(db, store_id),
            _display(principal),
            _terminal(db, principal, store_id, moment),
        )
        if item is not None
    ]
    return PeripheralSnapshot(items=items)


def check_card(db: Session, settings: Settings, principal: Principal) -> TerminalCheck:
    if principal.kind == "user" and not principal.has(Permission.DEVICES_MANAGE):
        raise ApiError(403, "forbidden", "You do not have permission to check the card terminal.")
    store_id = _store_id(principal)
    if not has_capability(db, Capability.CARD_TERMINALS):
        raise ApiError(404, "not_found", "No card terminal is configured for this branch.")
    rows = integrated_payment_service.active_terminals(db, store_id)
    if not rows:
        raise ApiError(404, "not_found", "No card terminal is configured for this branch.")
    device_id = principal.device.id if principal.device is not None else None
    row = next((item for item in rows if device_id is not None and item.device_id == device_id), rows[0])
    return integrated_payment_service.check_terminal(db, settings, row.id, store_id)
