"""The channel constraint keeps empty references apart and rejects a repeated external id."""

import importlib.util
import uuid
from pathlib import Path

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import CHAR, Column, MetaData, String, Table, create_engine, insert, inspect
from sqlalchemy.exc import IntegrityError


def _revision():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "20261112_0105_sales_order_events.py"
    spec = importlib.util.spec_from_file_location("sales_order_events_0105", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _orders() -> tuple[MetaData, Table]:
    meta = MetaData()
    Table("users", meta, Column("id", CHAR(32), primary_key=True))
    orders = Table(
        "sales_orders",
        meta,
        Column("id", CHAR(32), primary_key=True),
        Column("tenant_id", CHAR(32), nullable=False),
        Column("source", String(12), nullable=False),
        Column("channel_ref", String(64)),
    )
    return meta, orders


def _row(tenant: str, source: str, channel_ref: str | None) -> dict[str, str | None]:
    return {"id": str(uuid.uuid4()), "tenant_id": tenant, "source": source, "channel_ref": channel_ref}


def test_upgrade_allows_blank_refs_and_downgrade_removes_the_constraint() -> None:
    engine = create_engine("sqlite://")
    meta, orders = _orders()
    meta.create_all(engine)
    tenant = str(uuid.uuid4())
    with engine.begin() as connection:
        connection.execute(insert(orders).values(**_row(tenant, "manual", None)))
    revision = _revision()
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            revision.upgrade()
    with engine.begin() as connection:
        connection.execute(insert(orders).values(**_row(tenant, "manual", None)))
        connection.execute(insert(orders).values(**_row(tenant, "ecommerce", "EXT-1")))
    with engine.begin() as connection:
        try:
            connection.execute(insert(orders).values(**_row(tenant, "ecommerce", "EXT-1")))
        except IntegrityError:
            pass
        else:
            raise AssertionError("a repeated external reference was stored twice")
    with engine.begin() as connection:
        connection.execute(insert(orders).values(**_row(str(uuid.uuid4()), "ecommerce", "EXT-1")))
        assert inspect(connection).has_table("sales_order_events")
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            revision.downgrade()
        assert inspect(connection).has_table("sales_order_events") is False
        connection.execute(insert(orders).values(**_row(tenant, "ecommerce", "EXT-1")))
