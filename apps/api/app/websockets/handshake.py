"""WebSocket credentials.

Every client authenticates with the first text frame. A token in the query string is refused
unless WS_QUERY_TOKEN_UNTIL is a future UTC timestamp. The access log redacts it either way.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from app.core.config import get_settings

_FRAME_WAIT_SECONDS = 5


async def read_socket_credentials(
    websocket: WebSocket,
    *,
    roles: set[str],
    default_role: str = "",
) -> tuple[str, str, dict[str, str], bool] | None:
    """Return token, role, extra ids, and whether the socket is already accepted.

    A token in the query string is refused. The access log would keep it.
    """
    token = websocket.query_params.get("token") or ""
    role = websocket.query_params.get("role") or default_role
    if token:
        if not get_settings().query_token_allowed or role not in roles:
            await websocket.close(code=1008)
            return None
        return token, role, {}, False
    await websocket.accept()
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=_FRAME_WAIT_SECONDS)
        message = json.loads(raw)
    except (TimeoutError, json.JSONDecodeError, TypeError, ValueError, WebSocketDisconnect):
        await websocket.close(code=1008)
        return None
    if not isinstance(message, dict) or message.get("type") != "auth":
        await websocket.close(code=1008)
        return None
    frame_token = message.get("token")
    frame_role = message.get("role") or role
    token_ok = isinstance(frame_token, str) and frame_token != ""
    role_ok = isinstance(frame_role, str) and frame_role in roles
    if not token_ok or not role_ok:
        await websocket.close(code=1008)
        return None
    extras: dict[str, str] = {}
    for key in ("terminal_id", "station_id", "store_id"):
        value = message.get(key)
        if isinstance(value, str) and value != "":
            extras[key] = value
    return frame_token, frame_role, extras, True
