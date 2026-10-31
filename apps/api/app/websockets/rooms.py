"""Named rooms for kitchen stations, registers, and customer displays.

A kitchen screen joins only ``station:kitchen-{stationId}``. A register joins
``terminal:{terminalId}``. Its customer display joins ``customer-display:{terminalId}``.
Publishers run in request threads, so delivery is handed to the server loop.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket
from sqlalchemy import event
from sqlalchemy.orm import Session

logger = logging.getLogger("ai_pos.rooms")

QUEUE = "live_room_events"

_loop: asyncio.AbstractEventLoop | None = None
_lock: asyncio.Lock | None = None
_rooms: dict[str, set[WebSocket]] = defaultdict(set)
_members: dict[WebSocket, set[str]] = {}
_carts: dict[str, dict[str, Any]] = {}
_counts: dict[str, int] = {}
_seen: dict[str, datetime] = {}


def tenant_prefix() -> str:
    from app.tenancy.context import current_tenant

    tenant = current_tenant()
    if tenant is None or not tenant.id:
        return "unscoped"
    return tenant.id


def kitchen_room(station_id: object) -> str:
    return f"{tenant_prefix()}:station:kitchen-{station_id}"


def terminal_room(terminal_id: object) -> str:
    return f"{tenant_prefix()}:terminal:{terminal_id}"


def customer_display_room(terminal_id: object) -> str:
    return f"{tenant_prefix()}:customer-display:{terminal_id}"


def pos_terminals_room(store_id: object) -> str:
    """Every register watching one store. The tenant id keeps another store from joining the room."""
    return f"{tenant_prefix()}:pos:terminals:{store_id}"


def room_count(room: str) -> int:
    """Open sockets in one room. A missing room is zero, which is a confirmed absence, not an unknown."""
    return _counts.get(room, 0)


def last_seen(room: str) -> datetime | None:
    return _seen.get(room)


def _bump(room: str, delta: int) -> None:
    count = _counts.get(room, 0) + delta
    if count <= 0:
        _counts.pop(room, None)
    else:
        _counts[room] = count
    if delta > 0:
        _seen[room] = datetime.now(UTC)


def publish_table_alert(
    store_id: object,
    *,
    alert: str,
    table_id: object | None,
    table_name: str,
    total_amount: int | None,
) -> None:
    """`pos:table-alert` for Call Waiter and Bill Requested."""
    from datetime import UTC, datetime
    from uuid import uuid4

    publish(
        pos_terminals_room(store_id),
        {
            "type": "pos:table-alert",
            "id": str(uuid4()),
            "alert": alert,
            "tableId": str(table_id) if table_id is not None else None,
            "tableName": table_name,
            "totalAmount": total_amount,
            "createdAt": datetime.now(UTC).isoformat(),
        },
    )


def bind_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop, _lock
    _loop = loop
    _lock = asyncio.Lock()


def remember_cart(terminal_id: str, state: dict[str, Any]) -> None:
    _carts[terminal_id] = state


def latest_cart(terminal_id: str) -> dict[str, Any] | None:
    return _carts.get(terminal_id)


def queue(db: Session, room: str, payload: dict[str, Any]) -> None:
    """Hold an event until this session commits, so a rolled-back order is never announced."""
    pending: list[tuple[str, dict[str, Any]]] = db.info.setdefault(QUEUE, [])
    pending.append((room, payload))


async def join(socket: WebSocket, *names: str) -> None:
    assert _lock is not None
    async with _lock:
        joined = _members.setdefault(socket, set())
        for name in names:
            room = _rooms[name]
            if socket not in room:
                room.add(socket)
                _bump(name, 1)
            joined.add(name)


async def leave(socket: WebSocket) -> None:
    if _lock is None:
        return
    async with _lock:
        for name in _members.pop(socket, ()):
            room = _rooms.get(name)
            if room is None or socket not in room:
                continue
            room.discard(socket)
            _bump(name, -1)
            if not room:
                _rooms.pop(name, None)


async def broadcast(room: str, payload: dict[str, Any]) -> None:
    if _lock is None:
        return
    async with _lock:
        sockets = list(_rooms.get(room, ()))
    stale: list[WebSocket] = []
    for socket in sockets:
        try:
            await socket.send_json(payload)
        except Exception:
            stale.append(socket)
    if stale:
        for socket in stale:
            await leave(socket)


def publish(room: str, payload: dict[str, Any]) -> None:
    """Deliver `payload` to one room. Safe to call after a commit from a request thread."""
    if _loop is None or not _loop.is_running():
        return
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is _loop:
        _loop.create_task(broadcast(room, payload))
        return
    future = asyncio.run_coroutine_threadsafe(broadcast(room, payload), _loop)
    try:
        future.result(timeout=2)
    except Exception:
        logger.exception("Could not broadcast %s to %s", payload.get("type"), room)


def _after_commit(session: Session) -> None:
    queued: list[tuple[str, dict[str, Any]]] = session.info.pop(QUEUE, [])
    for room, payload in queued:
        publish(room, payload)


def _after_rollback(session: Session) -> None:
    session.info.pop(QUEUE, None)


event.listen(Session, "after_commit", _after_commit)
event.listen(Session, "after_rollback", _after_rollback)
