"""Copy one legacy tenant database into the shared operational database.

The command is resumable: each finished table is recorded on the control database. It does not drop or
alter the legacy database. Association tables, which have no ORM class, are inserted with SQLAlchemy
Core. Every mapped table is inserted through its ORM model.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.sql.schema import Table

from app.core.config import Settings
from app.core.currency import BUSINESS_SETTINGS_ID
from app.core.database import build_engine
from app.core.permissions import SYSTEM_ROLES
from app.models import Base
from app.models.customer import Customer
from app.models.inventory import InventoryLevel
from app.models.product import Product
from app.models.sale import Sale
from app.models.sale_tender import SaleTender
from app.tenancy import registry
from app.tenancy.context import TenantRef, use_tenant
from app.tenancy.models import Tenant, TenantMergeCheckpoint
from app.tenancy.scoping import include_all_tenants

FIXED_ROLE_IDS = {uuid.UUID(str(spec["id"])) for spec in SYSTEM_ROLES}
BATCH = 200


def _same_database(left: str, right: str) -> bool:
    from sqlalchemy.engine import make_url

    a, b = make_url(left), make_url(right)
    if a.get_backend_name() != b.get_backend_name() or a.database != b.database:
        return False
    if a.get_backend_name() == "sqlite":
        return True
    return (a.host, a.port) == (b.host, b.port)


def _class_for(table: Table):
    for mapper in Base.registry.mappers:
        if mapper.local_table is table:
            return mapper.class_
    return None


def _rewrite(value: Any, id_map: dict[uuid.UUID, uuid.UUID]) -> Any:
    if isinstance(value, uuid.UUID) and value in id_map:
        return id_map[value]
    return value


def _totals(session: Session, *, all_tenants: bool) -> dict[str, int]:
    def scalar(statement) -> int:
        if all_tenants:
            statement = statement.execution_options(include_all_tenants=True)
        value = session.scalar(statement)
        return int(value or 0)

    return {
        "products": scalar(select(func.count()).select_from(Product)),
        "sales_cents": scalar(select(func.coalesce(func.sum(Sale.total_cents), 0))),
        "tender_cents": scalar(select(func.coalesce(func.sum(SaleTender.amount_cents), 0))),
        "stock_on_hand": scalar(select(func.coalesce(func.sum(InventoryLevel.quantity_on_hand), 0))),
        "customer_balance_cents": scalar(select(func.coalesce(func.sum(Customer.current_balance_cents), 0))),
    }


def _checks(source: dict[str, int], dest: dict[str, int]) -> list[dict[str, object]]:
    return [
        {"name": key, "source": source[key], "destination": dest[key], "ok": source[key] == dest[key]}
        for key in source
    ]


def _exists(dest: Session, table: Table, data: dict[str, Any]) -> bool:
    clause = [table.c[column.name] == data[column.name] for column in table.primary_key.columns]
    statement = select(table).where(*clause)
    return dest.execute(statement).first() is not None


def _remember_ids(table: Table, source: Session, tenant_id: uuid.UUID, id_map: dict[uuid.UUID, uuid.UUID]) -> None:
    """A resumed copy still has to remap the fixed role and settings ids the first pass rewrote."""
    if table.name not in {"roles", "business_settings"}:
        return
    statement = select(table).execution_options(include_all_tenants=True)
    for raw in source.execute(statement).mappings():
        _prepare_row(table, dict(raw), tenant_id, id_map)


def _prepare_row(
    table: Table,
    raw: dict[str, Any],
    tenant_id: uuid.UUID,
    id_map: dict[uuid.UUID, uuid.UUID],
) -> dict[str, Any]:
    computed = {column.name for column in table.columns if column.computed is not None}
    data = {key: _rewrite(value, id_map) for key, value in raw.items() if key not in computed}
    data["tenant_id"] = tenant_id
    if table.name == "roles":
        current = data.get("id")
        if isinstance(current, uuid.UUID) and current in FIXED_ROLE_IDS:
            renamed = uuid.uuid5(tenant_id, str(data.get("name") or "role"))
            id_map[current] = renamed
            data["id"] = renamed
    if table.name == "business_settings" and data.get("id") == BUSINESS_SETTINGS_ID:
        renamed = uuid.uuid5(tenant_id, "business-settings")
        id_map[BUSINESS_SETTINGS_ID] = renamed
        data["id"] = renamed
    return data


def _copy_table(
    table: Table,
    source: Session,
    dest: Session,
    tenant_id: uuid.UUID,
    id_map: dict[uuid.UUID, uuid.UUID],
    *,
    write: bool,
) -> int:
    model = _class_for(table)
    statement = select(table).execution_options(include_all_tenants=True)
    copied = 0
    pending: list[Any] = []
    for raw in source.execute(statement).mappings():
        data = _prepare_row(table, dict(raw), tenant_id, id_map)
        if _exists(dest, table, data):
            continue
        if not write:
            copied += 1
            continue
        if model is None:
            pending.append(data)
        else:
            obj = model()
            for column in table.columns:
                if column.name not in data:
                    continue
                setattr(obj, column.key, data[column.name])
            pending.append(obj)
        if len(pending) >= BATCH:
            _flush_batch(dest, table, model, pending)
            copied += len(pending)
            pending = []
    if pending and write:
        _flush_batch(dest, table, model, pending)
        copied += len(pending)
    elif pending:
        copied += len(pending)
    return copied


def _flush_batch(dest: Session, table: Table, model: type | None, pending: list[Any]) -> None:
    if model is None:
        dest.execute(table.insert(), pending)
    else:
        dest.add_all(pending)
    dest.commit()


def merge_tenant(settings: Settings, slug: str, *, commit: bool) -> dict[str, object]:
    with registry.control_session(settings) as control:
        row = control.scalar(select(Tenant).where(Tenant.slug == slug))
        if row is None:
            return {"tenant": slug, "status": "missing", "mode": "commit" if commit else "dry-run", "checks": []}
        if row.data_plane == "shared":
            return {"tenant": slug, "status": "already_shared", "mode": "commit" if commit else "dry-run", "checks": []}
        tenant_id = row.id
        from app.core.security import decrypt_value

        source_url = decrypt_value(row.database_url_encrypted, settings)
        done = {
            item.table_name
            for item in control.scalars(
                select(TenantMergeCheckpoint).where(TenantMergeCheckpoint.tenant_id == tenant_id)
            )
        }
    if _same_database(source_url, settings.database_url):
        return {
            "tenant": slug,
            "status": "same_database",
            "mode": "commit" if commit else "dry-run",
            "checks": [],
        }
    ref = TenantRef(id=str(tenant_id), slug=slug, name=slug, database_url=source_url, data_plane="legacy")
    source_factory = sessionmaker(bind=build_engine(source_url), expire_on_commit=False)
    dest_factory = sessionmaker(bind=build_engine(settings.database_url), expire_on_commit=False)
    id_map: dict[uuid.UUID, uuid.UUID] = {}
    tables: dict[str, int] = {}
    with source_factory() as source, dest_factory() as dest, use_tenant(ref):
        with include_all_tenants(source):
            source_totals = _totals(source, all_tenants=True)
            for table in Base.metadata.sorted_tables:
                if table.name in done:
                    _remember_ids(table, source, tenant_id, id_map)
                    tables[table.name] = 0
                    continue
                copied = _copy_table(table, source, dest, tenant_id, id_map, write=commit)
                tables[table.name] = copied
                if commit:
                    with registry.control_session(settings) as control:
                        control.add(
                            TenantMergeCheckpoint(tenant_id=tenant_id, table_name=table.name, row_count=copied)
                        )
                        control.commit()
        dest_ref = TenantRef(
            id=str(tenant_id), slug=slug, name=slug, database_url=settings.database_url, data_plane="shared"
        )
    with dest_factory() as dest, use_tenant(dest_ref):
        dest_totals = _totals(dest, all_tenants=False) if commit else {key: 0 for key in source_totals}
    checks = _checks(source_totals, dest_totals) if commit else []
    status = "ok" if not commit or all(item["ok"] for item in checks) else "mismatch"
    if commit and status == "ok":
        with registry.control_session(settings) as control:
            stored = control.scalar(select(Tenant).where(Tenant.id == tenant_id))
            if stored is not None:
                stored.data_plane = "shared"
                control.commit()
        registry.invalidate(slug)
    return {
        "tenant": slug,
        "mode": "commit" if commit else "dry-run",
        "status": status,
        "source": source_totals,
        "destination": dest_totals,
        "tables": tables,
        "checks": checks,
    }
