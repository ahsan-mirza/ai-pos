from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class TenantRef:
    id: str
    slug: str
    name: str
    database_url: str
    # "shared" uses DATABASE_URL. "legacy" still opens this tenant's own database.
    data_plane: str = "legacy"


# Session.info key on control-database sessions; tenant-only hooks (audit trail, settings cache) skip them.
CONTROL_SESSION = "control_database"

_current: ContextVar[TenantRef | None] = ContextVar("ai_pos_tenant", default=None)
_store: ContextVar[str] = ContextVar("ai_pos_store", default="")
_device: ContextVar[str] = ContextVar("ai_pos_device", default="")


def current_tenant() -> TenantRef | None:
    return _current.get()


def current_store_id() -> str:
    return _store.get()


def current_device_id() -> str:
    return _device.get()


def bind_scope(store_id: object | None, device_id: object | None) -> None:
    """Remember the branch and terminal authorized for this request. Empty fails closed."""
    _store.set("" if store_id is None else str(store_id))
    _device.set("" if device_id is None else str(device_id))


def clear_scope() -> None:
    _store.set("")
    _device.set("")


@contextmanager
def use_tenant(tenant: TenantRef) -> Iterator[TenantRef]:
    """Binds a tenant for the duration of a request, job, or CLI command."""
    token = _current.set(tenant)
    try:
        yield tenant
    finally:
        _current.reset(token)
