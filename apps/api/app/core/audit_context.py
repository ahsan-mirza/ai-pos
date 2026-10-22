"""Per-request facts the audit trail needs: who is calling, from where, and on which device."""

from __future__ import annotations

import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@dataclass
class RequestContext:
    method: str
    path: str
    ip_address: str | None
    client_device: str
    user_id: uuid.UUID | None = None
    user_name: str | None = None
    user_role: str | None = None
    store_id: uuid.UUID | None = None
    entries: int = 0
    changed: bool = False

    @property
    def mutating(self) -> bool:
        return self.method in MUTATING_METHODS


_current: ContextVar[RequestContext | None] = ContextVar("audit_request_context", default=None)


def detect_device(declared: str | None, user_agent: str | None) -> str:
    """Clients announce themselves with X-Client-Device; the Tauri webview is recognised as a fallback."""
    value = (declared or "").strip().lower()
    if value in {"web", "desktop"}:
        return value
    agent = (user_agent or "").lower()
    if "tauri" in agent:
        return "desktop"
    if "mozilla" in agent:
        return "web"
    return "api"


def begin(context: RequestContext) -> Token[RequestContext | None]:
    return _current.set(context)


def end(token: Token[RequestContext | None]) -> None:
    _current.reset(token)


def current() -> RequestContext | None:
    return _current.get()


def bind_user(user_id: uuid.UUID, full_name: str, role_name: str | None, store_id: uuid.UUID | None) -> None:
    context = _current.get()
    if context is None:
        return
    context.user_id = user_id
    context.user_name = full_name
    context.user_role = role_name
    context.store_id = store_id
