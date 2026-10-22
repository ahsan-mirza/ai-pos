"""Waiter and table-tablet API. Sessions are the store's open orders; the socket fans changes out live."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.capabilities import FOOD_AND_BEVERAGE, Capability, has_capability
from app.core.config import get_settings
from app.core.database import get_db, get_session_factory
from app.core.deps import Principal, authorize, device_from_key
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.core.security import decode_access_token
from app.models.restaurant import DiningArea, DiningTable
from app.models.user import User
from app.schemas.fnb_tables import ActiveSessionOut, AddRound, SessionStart, TableMenuOut, WaiterCallOut
from app.services import fnb_table_service
from app.services.settings_service import cached_settings
from app.tenancy.context import use_tenant
from app.websockets import rooms, table_sync

router = APIRouter()
ws_router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
CanOrder = Annotated[Principal, Depends(authorize(Permission.POS_ORDERS, allow_device=True, scopes=("portal", "pos")))]


def _socket_session(websocket: WebSocket) -> Iterator[Session]:
    """Bind the socket's tenant, then yield the same session a normal request would get."""
    settings = get_settings()
    context = None
    if settings.tenancy_enabled:
        from app.tenancy import registry

        named = websocket.query_params.get("tenant") or websocket.headers.get("x-tenant-domain")
        slug = registry.slug_from_domain(named, settings) if named else settings.default_tenant
        found = registry.lookup(slug, settings) if slug else None
        tenant = found.tenant if found is not None else None
        if tenant is None:
            raise ApiError(404, "tenant_not_found", "No store is registered at that address.")
        context = use_tenant(tenant)
        context.__enter__()
    try:
        override = websocket.scope["app"].dependency_overrides.get(get_db)
        if override is not None:
            yield from override()
            return
        db = get_session_factory()()
        try:
            yield db
        finally:
            db.close()
    finally:
        if context is not None:
            context.__exit__(None, None, None)


def _socket_principal(db: Session, token: str) -> Principal | None:
    settings = get_settings()
    if token.lower().startswith("bearer "):
        token = token.split(" ", 1)[1].strip()
    device = device_from_key(db, settings, token)
    if device is not None:
        return device
    try:
        claims = decode_access_token(token, settings=settings)
        user_id = uuid.UUID(str(claims["sub"]))
    except Exception:
        return None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return None
    return Principal(kind="user", scope="pos", user=user, permissions=frozenset(user.permissions))


def _socket_allowed(db: Session, principal: Principal, store_id: uuid.UUID) -> bool:
    if cached_settings(db).business_profile not in FOOD_AND_BEVERAGE:
        return False
    if not has_capability(db, Capability.OPEN_ORDERS) or not has_capability(db, Capability.TABLES):
        return False
    if principal.kind == "user" and Permission.POS_ORDERS.value not in principal.permissions:
        return False
    return principal.store_id is None or principal.store_id == store_id


@router.get("/menu", response_model=TableMenuOut)
def table_menu(store_id: uuid.UUID, db: Db, principal: CanOrder) -> TableMenuOut:
    return fnb_table_service.menu(db, principal, store_id)


@router.post("/tables/{table_id}/session/start", response_model=ActiveSessionOut)
def start_session(table_id: uuid.UUID, payload: SessionStart, db: Db, principal: CanOrder) -> ActiveSessionOut:
    return fnb_table_service.start_session(db, principal, table_id, payload)


@router.get("/tables/{table_id}/active-session", response_model=ActiveSessionOut)
def active_session(table_id: uuid.UUID, db: Db, principal: CanOrder) -> ActiveSessionOut:
    return fnb_table_service.active_session(db, principal, table_id)


@router.post("/tables/{table_id}/orders/add-round", response_model=ActiveSessionOut)
def add_round(table_id: uuid.UUID, payload: AddRound, db: Db, principal: CanOrder) -> ActiveSessionOut:
    return fnb_table_service.add_round(db, principal, table_id, payload)


@router.post("/tables/{table_id}/call-waiter", response_model=WaiterCallOut)
def call_waiter(table_id: uuid.UUID, db: Db, principal: CanOrder) -> WaiterCallOut:
    return fnb_table_service.call_waiter(db, principal, table_id)


@router.post("/tables/{table_id}/request-bill", response_model=ActiveSessionOut)
def request_table_bill(table_id: uuid.UUID, db: Db, principal: CanOrder) -> ActiveSessionOut:
    return fnb_table_service.request_table_bill(db, principal, table_id)


def _apply_guest_alert(websocket: WebSocket, token: str, store_id: uuid.UUID, message: dict) -> str | None:
    """Guest tablet sent `table:call-waiter` or `table:request-bill`. Same work as the HTTP routes."""
    sessions = _socket_session(websocket)
    try:
        db = next(sessions)
        principal = _socket_principal(db, token)
        if principal is None or not _socket_allowed(db, principal, store_id):
            return "This table is not allowed to send alerts."
        try:
            table_id = uuid.UUID(str(message.get("tableId") or ""))
        except ValueError:
            return "That table was not found."
        table = db.get(DiningTable, table_id)
        area = db.get(DiningArea, table.area_id) if table is not None else None
        if area is None or area.store_id != store_id:
            return "That table is not on this floor."
        kind = message.get("type")
        if kind == "table:call-waiter":
            fnb_table_service.call_waiter(db, principal, table_id)
            return None
        if kind == "table:request-bill":
            fnb_table_service.request_table_bill(db, principal, table_id)
            return None
        return None
    except ApiError as exc:
        return exc.message
    finally:
        sessions.close()


@ws_router.websocket("/stores/{store_id}/tables")
async def table_events(websocket: WebSocket, store_id: uuid.UUID) -> None:
    token = websocket.query_params.get("token") or ""
    role = websocket.query_params.get("role") or "customer"
    if not token or role not in {"customer", "pos"}:
        await websocket.close(code=1008)
        return
    sessions = _socket_session(websocket)
    try:
        db = next(sessions)
        principal = _socket_principal(db, token)
        allowed = principal is not None and _socket_allowed(db, principal, store_id)
    except ApiError:
        await websocket.close(code=1008)
        return
    finally:
        sessions.close()
    if not allowed:
        await websocket.close(code=1008)
        return
    await table_sync.connect(store_id, websocket)
    if role == "pos":
        await rooms.join(websocket, rooms.pos_terminals_room(store_id))
    try:
        while True:
            raw = await websocket.receive_text()
            await _on_table_message(websocket, raw, token, store_id, role)
    except WebSocketDisconnect:
        pass
    finally:
        await table_sync.disconnect(store_id, websocket)
        await rooms.leave(websocket)


async def _on_table_message(
    websocket: WebSocket, raw: str, token: str, store_id: uuid.UUID, role: str
) -> None:
    try:
        message = json.loads(raw)
    except json.JSONDecodeError:
        return
    if not isinstance(message, dict):
        return
    kind = message.get("type")
    if kind in {"table:call-waiter", "table:request-bill"}:
        reason = await asyncio.to_thread(_apply_guest_alert, websocket, token, store_id, message)
        if reason is not None:
            await websocket.send_json({"type": "table:alert-rejected", "message": reason})
        return
    if role == "pos" and kind == "pos:table-alert-ack":
        alert_id = str(message.get("alertId") or "")
        table_id = str(message.get("tableId") or "")
        if not alert_id or not table_id:
            return
        await rooms.broadcast(
            rooms.pos_terminals_room(store_id),
            {"type": "pos:table-alert-cleared", "alertId": alert_id, "tableId": table_id},
        )
