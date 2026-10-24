"""Stamps and filters operational rows by the tenant bound to the current context.

When tenancy is off (the SQLite test suite, and a single-database install), every row uses
DEFAULT_TENANT_ID. A statement that must see every store passes execution option
include_all_tenants=True, or sets the same flag on session.info.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import bindparam, event
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria
from sqlalchemy.types import Uuid

from app.models.base import TenantScoped
from app.tenancy.context import CONTROL_SESSION, TenantRef, current_tenant, use_tenant

# Fixed id used by tests and by databases that are not registered in the control plane.
DEFAULT_TENANT_ID = uuid.UUID("00000000-0000-4000-8000-0000000000a1")
INCLUDE_ALL = "include_all_tenants"

_installed = False
_original_get = Session.get


def _scoped_get(self: Session, entity, ident, **kwargs):
    """Identity-map hits skip the SELECT filter, so hide another store's already-loaded row."""
    obj = _original_get(self, entity, ident, **kwargs)
    if obj is None or self.info.get(CONTROL_SESSION) or self.info.get(INCLUDE_ALL):
        return obj
    options = kwargs.get("execution_options") or {}
    if options.get(INCLUDE_ALL):
        return obj
    if isinstance(obj, TenantScoped) and _as_uuid(obj.tenant_id) != active_tenant_id():
        return None
    return obj


def active_tenant_id() -> uuid.UUID:
    tenant = current_tenant()
    if tenant is None or not tenant.id:
        return DEFAULT_TENANT_ID
    return uuid.UUID(tenant.id)


def _as_uuid(value: object) -> uuid.UUID | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _tenant_bind():
    return bindparam("tenant_scope_id", callable_=active_tenant_id, type_=Uuid(as_uuid=True))


def _skipped(session: Session, state: ORMExecuteState | None = None) -> bool:
    if session.info.get(CONTROL_SESSION):
        return True
    if session.info.get(INCLUDE_ALL):
        return True
    return state is not None and bool(state.execution_options.get(INCLUDE_ALL))


def _stamp(session: Session, _flush_context: object, _instances: object) -> None:
    if session.info.get(CONTROL_SESSION):
        return
    active = active_tenant_id()
    allow_all = bool(session.info.get(INCLUDE_ALL))
    for obj in list(session.new):
        if isinstance(obj, TenantScoped) and obj.tenant_id is None:
            obj.tenant_id = active
    if allow_all:
        return
    for obj in list(session.dirty):
        if not isinstance(obj, TenantScoped):
            continue
        if obj.tenant_id is None:
            obj.tenant_id = active
        elif _as_uuid(obj.tenant_id) != active:
            session.expunge(obj)


def _filter(state: ORMExecuteState) -> None:
    if _skipped(state.session, state):
        _bypass_rls(state)
        return
    if not state.is_orm_statement:
        return
    if state.is_select:
        if state.is_column_load or state.is_relationship_load:
            return
        state.statement = state.statement.options(
            with_loader_criteria(TenantScoped, lambda cls: cls.tenant_id == _tenant_bind(), include_aliases=True)
        )
        return
    if state.is_update or state.is_delete:
        mapper = state.bind_mapper
        if mapper is not None and issubclass(mapper.class_, TenantScoped):
            state.statement = state.statement.where(mapper.class_.tenant_id == _tenant_bind())


def _bypass_rls(state: ORMExecuteState) -> None:
    if not (state.execution_options.get(INCLUDE_ALL) or state.session.info.get(INCLUDE_ALL)):
        return
    from app.core.database import bypass_session_tenant

    bind = state.session.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        return
    bypass_session_tenant(state.session.connection())


def _set_rls(session: Session, _transaction: object, connection) -> None:
    if connection.dialect.name != "postgresql" or session.info.get(CONTROL_SESSION):
        return
    from app.core.database import bypass_session_tenant, set_session_tenant

    if session.info.get(INCLUDE_ALL):
        bypass_session_tenant(connection)
        return
    set_session_tenant(connection, str(active_tenant_id()))


def install() -> None:
    """Register the stamp and filter on every Session, including ones tests build themselves."""
    global _installed
    if _installed:
        return
    _installed = True
    Session.get = _scoped_get  # type: ignore[method-assign]
    event.listen(Session, "before_flush", _stamp)
    event.listen(Session, "do_orm_execute", _filter)
    event.listen(Session, "after_begin", _set_rls)


def _default_ref(url: str) -> TenantRef:
    return TenantRef(id=str(DEFAULT_TENANT_ID), slug="default", name="Default", database_url=url)


def _same_database(left: str, right: str) -> bool:
    from sqlalchemy.engine import make_url

    a, b = make_url(left), make_url(right)
    if a.get_backend_name() != b.get_backend_name() or not a.database or a.database != b.database:
        return False
    if a.get_backend_name() == "sqlite":
        return True
    return (a.host, a.port) == (b.host, b.port)


def tenant_ref_for_database(url: str) -> TenantRef:
    """The store registered for this database URL, or the default id when tenancy is off."""
    from sqlalchemy import select

    from app.core.config import get_settings
    from app.tenancy.models import Tenant
    from app.tenancy.registry import control_session, ref_for

    settings = get_settings()
    if not settings.tenancy_enabled:
        return _default_ref(url)
    with control_session(settings) as db:
        refs = [ref_for(row, settings) for row in db.scalars(select(Tenant)).all()]
    matched = [ref for ref in refs if _same_database(ref.database_url, url)]
    if len(matched) == 1:
        return matched[0]
    return _default_ref(url)


@contextmanager
def use_database_tenant(url: str) -> Iterator[None]:
    """Bind the tenant that owns `url` so new rows are stamped with that store's id."""
    with use_tenant(tenant_ref_for_database(url)):
        yield
