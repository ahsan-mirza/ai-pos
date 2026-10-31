"""In-process fan-out for one store's tables.

Waiter tablets, the cashier POS, and the kitchen display all subscribe to
`/api/v1/ws/stores/{store_id}/tables`. Publishers run inside ordinary request
threads, so events are handed to the server loop and the HTTP call waits until
every connected screen has the message.

The cashier's own SQLite cache is the offline copy: this process only reaches
devices that can currently see the API (cloud or the store LAN).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict
from datetime import UTC, datetime

from fastapi import WebSocket

logger = logging.getLogger("ai_pos.table_sync")

_loop: asyncio.AbstractEventLoop | None = None
_rooms: dict[str, set[WebSocket]] = defaultdict(set)
_lock: asyncio.Lock | None = None
_customers: dict[str, int] = {}
_last_customer: dict[str, datetime] = {}


def bind_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Called once when the API process starts."""
    global _loop, _lock
    _loop = loop
    _lock = asyncio.Lock()


def observe_customer(presence_key: str, joined: bool) -> None:
    """Count table-order sessions. The cashier's own socket is not one of them."""
    current = _customers.get(presence_key, 0)
    if joined:
        _customers[presence_key] = current + 1
        _last_customer[presence_key] = datetime.now(UTC)
        return
    if current <= 1:
        _customers.pop(presence_key, None)
    else:
        _customers[presence_key] = current - 1


def customer_presence(presence_key: str) -> tuple[int, datetime | None]:
    return _customers.get(presence_key, 0), _last_customer.get(presence_key)


async def connect(store_id: uuid.UUID, socket: WebSocket, presence_key: str, role: str) -> None:
    await socket.accept()
    assert _lock is not None
    async with _lock:
        _rooms[str(store_id)].add(socket)
        if role == "customer":
            observe_customer(presence_key, True)


async def disconnect(store_id: uuid.UUID, socket: WebSocket, presence_key: str, role: str) -> None:
    if _lock is None:
        return
    async with _lock:
        _rooms[str(store_id)].discard(socket)
        if role == "customer":
            observe_customer(presence_key, False)


async def _broadcast(store_id: str, event: dict[str, object]) -> None:
    assert _lock is not None
    async with _lock:
        sockets = list(_rooms.get(store_id, ()))
    stale: list[WebSocket] = []
    for socket in sockets:
        try:
            await socket.send_json(event)
        except Exception:
            stale.append(socket)
    if stale and _lock is not None:
        async with _lock:
            room = _rooms.get(store_id)
            if room is not None:
                for socket in stale:
                    room.discard(socket)


def publish_order_status(
    store_id: uuid.UUID,
    *,
    order_id: uuid.UUID | None,
    table_id: uuid.UUID | None,
    table_label: str | None,
    ticket_id: uuid.UUID | None,
    status: str,
    kitchen_status: str,
    item_ids: list[str],
    message: str,
) -> None:
    """Broadcast `ORDER_STATUS_CHANGED` after the database commit.

    status is preparing | ready | completed. kitchen_status is the line badge
    (new | preparing | ready | bumped). item_ids are the open-order lines on this ticket.
    """
    from datetime import UTC, datetime

    publish(
        store_id,
        {
            "type": "ORDER_STATUS_CHANGED",
            "store_id": str(store_id),
            "order_id": str(order_id) if order_id is not None else None,
            "table_id": str(table_id) if table_id is not None else None,
            "table_label": table_label,
            "ticket_id": str(ticket_id) if ticket_id is not None else None,
            "status": status,
            "kitchen_status": kitchen_status,
            "item_ids": item_ids,
            "message": message,
            "updated_at": datetime.now(UTC).isoformat(),
        },
    )


def publish(store_id: uuid.UUID, event: dict[str, object]) -> None:
    """Deliver `event` to every screen watching this store. Safe to call after a commit."""
    if _loop is None or not _loop.is_running():
        return
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is _loop:
        _loop.create_task(_broadcast(str(store_id), event))
        return
    future = asyncio.run_coroutine_threadsafe(_broadcast(str(store_id), event), _loop)
    try:
        future.result(timeout=2)
    except Exception:
        logger.exception("Could not broadcast %s for store %s", event.get("type"), store_id)
