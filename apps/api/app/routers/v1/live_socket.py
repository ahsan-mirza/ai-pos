"""Live rooms for a kitchen station, the register, and that register's customer display."""

from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.capabilities import Capability, has_capability
from app.core.deps import Principal
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.models.device import Device
from app.models.kitchen import KitchenStation, KitchenTicket
from app.routers.v1.fnb_table_orders import _socket_principal, _socket_session
from app.services import kitchen_service
from app.websockets import rooms

router = APIRouter()

_ROLES = {"kds", "pos", "customer-display"}
_STATUS_ALIASES = {"START": "PREPARING", "PREPARING": "PREPARING", "READY": "READY", "BUMPED": "BUMPED"}
_CART_LIMIT = 65_536


def _kds_allowed(db: Session, principal: Principal, station_id: uuid.UUID) -> bool:
    if principal.kind == "user" and Permission.KDS_OPERATE.value not in principal.permissions:
        return False
    if not has_capability(db, Capability.KDS):
        return False
    station = db.get(KitchenStation, station_id)
    if station is None or not station.is_active:
        return False
    return principal.store_id is None or principal.store_id == station.store_id


def _terminal_allowed(db: Session, principal: Principal, terminal_id: uuid.UUID) -> bool:
    if principal.kind != "device":
        return False
    row = db.get(Device, terminal_id)
    if row is None or row.revoked_at is not None:
        return False
    if principal.device is not None and principal.device.id != row.id:
        return False
    return principal.store_id is None or principal.store_id == row.store_id


def _apply_status(
    websocket: WebSocket, token: str, station_id: uuid.UUID, ticket_id: uuid.UUID, status: str
) -> str | None:
    sessions = _socket_session(websocket)
    try:
        db = next(sessions)
        principal = _socket_principal(db, token)
        if principal is None or not _kds_allowed(db, principal, station_id):
            return "This kitchen screen is not allowed to update tickets."
        ticket = db.get(KitchenTicket, ticket_id)
        if ticket is None or ticket.station_id != station_id:
            return "That ticket is not on this station."
        kitchen_service.set_status(db, principal, ticket_id, status)
        return None
    except ApiError as exc:
        return exc.message
    finally:
        sessions.close()


@router.websocket("/live")
async def live_events(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token") or ""
    role = websocket.query_params.get("role") or ""
    if not token or role not in _ROLES:
        await websocket.close(code=1008)
        return
    station_id: uuid.UUID | None = None
    terminal_id: uuid.UUID | None = None
    sessions = _socket_session(websocket)
    try:
        db = next(sessions)
        principal = _socket_principal(db, token)
        if principal is None:
            await websocket.close(code=1008)
            return
        if role == "kds":
            try:
                station_id = uuid.UUID(websocket.query_params.get("station_id") or "")
            except ValueError:
                await websocket.close(code=1008)
                return
            if not _kds_allowed(db, principal, station_id):
                await websocket.close(code=1008)
                return
            room = rooms.kitchen_room(station_id)
        else:
            try:
                terminal_id = uuid.UUID(websocket.query_params.get("terminal_id") or "")
            except ValueError:
                await websocket.close(code=1008)
                return
            if not _terminal_allowed(db, principal, terminal_id):
                await websocket.close(code=1008)
                return
            room = rooms.terminal_room(terminal_id) if role == "pos" else rooms.customer_display_room(terminal_id)
    except ApiError:
        await websocket.close(code=1008)
        return
    finally:
        sessions.close()

    await websocket.accept()
    await rooms.join(websocket, room)
    if role == "customer-display" and terminal_id is not None:
        current = rooms.latest_cart(str(terminal_id))
        if current is not None:
            await websocket.send_json({"type": "customer-display:cart", "state": current})
    try:
        while True:
            raw = await websocket.receive_text()
            await _on_message(websocket, raw, token, role, station_id, terminal_id)
    except WebSocketDisconnect:
        pass
    finally:
        await rooms.leave(websocket)


async def _on_message(
    websocket: WebSocket,
    raw: str,
    token: str,
    role: str,
    station_id: uuid.UUID | None,
    terminal_id: uuid.UUID | None,
) -> None:
    try:
        message = json.loads(raw)
    except json.JSONDecodeError:
        return
    if not isinstance(message, dict):
        return
    kind = message.get("type")
    if role == "kds" and kind == "kitchen:status" and station_id is not None:
        status = _STATUS_ALIASES.get(str(message.get("status") or "").upper())
        try:
            ticket_id = uuid.UUID(str(message.get("ticket_id") or ""))
        except ValueError:
            return
        if status is None:
            await websocket.send_json(
                {"type": "kitchen:status-rejected", "ticket_id": str(ticket_id), "message": "Unknown ticket status."}
            )
            return
        reason = await asyncio.to_thread(_apply_status, websocket, token, station_id, ticket_id, status)
        if reason is not None:
            await websocket.send_json(
                {"type": "kitchen:status-rejected", "ticket_id": str(ticket_id), "message": reason}
            )
        return
    if role == "pos" and kind == "customer-display:cart" and terminal_id is not None:
        state = message.get("state")
        if not isinstance(state, dict) or len(raw) > _CART_LIMIT:
            return
        terminal = str(terminal_id)
        rooms.remember_cart(terminal, state)
        await rooms.broadcast(rooms.customer_display_room(terminal), {"type": "customer-display:cart", "state": state})
