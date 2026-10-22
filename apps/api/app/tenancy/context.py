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


# Session.info key on control-database sessions; tenant-only hooks (audit trail, settings cache) skip them.
CONTROL_SESSION = "control_database"

_current: ContextVar[TenantRef | None] = ContextVar("ai_pos_tenant", default=None)


def current_tenant() -> TenantRef | None:
    return _current.get()


@contextmanager
def use_tenant(tenant: TenantRef) -> Iterator[TenantRef]:
    """Binds a tenant for the duration of a request, job, or CLI command."""
    token = _current.set(tenant)
    try:
        yield tenant
    finally:
        _current.reset(token)
