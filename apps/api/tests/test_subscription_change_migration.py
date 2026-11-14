"""control_0034 adds request history and leaves existing commercial rows untouched.

The older control revisions use ALTER statements SQLite cannot run, so a full
chain on SQLite stops at control_0017. This file stamps a current schema at
control_0033 and migrates only control_0034 there. When the local Postgres
server accepts a connection, a second test runs the whole chain on a new
database and drops that database. It does not migrate qios_control.
"""

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.tenancy.models import (
    BillingCycle,
    BillingInvoice,
    BillingPlan,
    ControlBase,
    Subscription,
    SubscriptionChangeRequest,
    Tenant,
)

API = Path(__file__).resolve().parents[1]
REPO = API.parents[1]
DISPOSABLE = "axiz_phase3_mig"


def _config(url: str) -> Config:
    config = Config(str(API / "alembic_control.ini"))
    config.set_main_option("script_location", str(API / "alembic_control"))
    config.attributes["database_url"] = url
    return config


def _seed(url: str, *, reuse_catalog: bool = False) -> tuple[str, str, str]:
    engine = create_engine(url)
    Session = sessionmaker(bind=engine)
    now = datetime.now(UTC)
    with Session() as db:
        tenant = Tenant(slug="kept", name="Kept Store", database_url_encrypted="unused")
        db.add(tenant)
        if reuse_catalog:
            plan = db.scalar(select(BillingPlan).where(BillingPlan.code == "FREE"))
            assert plan is not None
            cycle = db.scalar(select(BillingCycle).where(BillingCycle.code == "MONTHLY"))
            if cycle is None:
                cycle = BillingCycle(code="MONTHLY", name="Monthly", months=1, updated_at=now)
                db.add(cycle)
        else:
            plan = BillingPlan(code="FREE", name="Free", included_modules=[], updated_at=now)
            cycle = BillingCycle(code="MONTHLY", name="Monthly", months=1, updated_at=now)
            db.add_all([plan, cycle])
        db.flush()
        subscription = Subscription(tenant_id=tenant.id, plan_id=plan.id, cycle_id=cycle.id, status="active")
        invoice = BillingInvoice(
            tenant_id=tenant.id,
            status="pending",
            plan_code="FREE",
            cycle_code="MONTHLY",
            confirm_name="Kept Store",
        )
        db.add_all([subscription, invoice])
        db.commit()
        ids = (str(tenant.id), str(subscription.id), str(invoice.id))
    engine.dispose()
    return ids


def _assert_constraints(url: str, tenant_id: str, subscription_id: str, invoice_id: str) -> None:
    engine = create_engine(url)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        other = Tenant(slug="other", name="Other", database_url_encrypted="unused")
        db.add(other)
        db.flush()
        with pytest.raises(SQLAlchemyError):
            db.add(
                SubscriptionChangeRequest(
                    tenant_id=other.id,
                    subscription_id=uuid.UUID(subscription_id),
                    reference="SCR-CROSS",
                    current_plan_code="FREE",
                    requested_plan_code="GROWTH",
                    requested_cycle_code="MONTHLY",
                    status="quoted",
                    quote_snapshot={"currency": "AED"},
                    invoice_id=uuid.UUID(invoice_id),
                    correlation_id=uuid.uuid4(),
                )
            )
            db.commit()
        db.rollback()
        kept = uuid.UUID(tenant_id)
        db.add(
            SubscriptionChangeRequest(
                tenant_id=kept,
                subscription_id=uuid.UUID(subscription_id),
                reference="SCR-A",
                current_plan_code="FREE",
                requested_plan_code="GROWTH",
                requested_cycle_code="MONTHLY",
                status="quoted",
                quote_snapshot={"currency": "AED"},
                correlation_id=uuid.uuid4(),
            )
        )
        db.commit()
        db.add(
            SubscriptionChangeRequest(
                tenant_id=kept,
                reference="SCR-B",
                current_plan_code="FREE",
                requested_plan_code="PRO_AI",
                requested_cycle_code="ANNUAL",
                status="quoted",
                quote_snapshot={"currency": "AED"},
                correlation_id=uuid.uuid4(),
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
    engine.dispose()


def test_control_0034_upgrades_existing_rows_on_sqlite(tmp_path) -> None:
    url = f"sqlite:///{(tmp_path / 'control.db').as_posix()}"
    engine = create_engine(url)
    ControlBase.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS subscription_change_events"))
        conn.execute(text("DROP TABLE IF EXISTS subscription_change_requests"))
    engine.dispose()
    config = _config(url)
    command.stamp(config, "control_0033")
    tenant_id, subscription_id, invoice_id = _seed(url)
    command.upgrade(config, "head")
    engine = create_engine(url)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM subscription_change_requests")).scalar() == 0
        assert conn.execute(text("SELECT status FROM subscriptions")).scalar() == "active"
        assert conn.execute(text("SELECT plan_code FROM billing_invoices")).scalar() == "FREE"
        indexes = {row[1] for row in conn.execute(text("PRAGMA index_list('subscription_change_requests')"))}
    assert "uq_subscription_changes_one_open" in indexes
    engine.dispose()
    command.downgrade(config, "control_0033")
    engine = create_engine(url)
    names = set(inspect(engine).get_table_names())
    assert "subscription_change_requests" not in names
    assert "subscription_change_events" not in names
    with engine.connect() as conn:
        assert conn.execute(text("SELECT status FROM subscriptions")).scalar() == "active"
        assert conn.execute(text("SELECT status, plan_code FROM billing_invoices")).one() == ("pending", "FREE")
    engine.dispose()
    command.upgrade(config, "head")
    _assert_constraints(url, tenant_id, subscription_id, invoice_id)


def _env_value(name: str) -> str | None:
    path = REPO / ".env"
    if not path.exists():
        return None
    prefix = f"{name}="
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            return line.split("=", 1)[1].strip().strip('"')
    return None


def _development_control_url() -> str | None:
    return _env_value("CONTROL_DATABASE_URL")


def _revision(url: str) -> str | None:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            for table in ("alembic_version", "control_alembic_version"):
                found = conn.execute(
                    text("SELECT 1 FROM information_schema.tables WHERE table_name = :name"),
                    {"name": table},
                ).first()
                if found is None:
                    continue
                return conn.execute(text(f"SELECT version_num FROM {table}")).scalar()
    except SQLAlchemyError:
        return None
    finally:
        engine.dispose()
    return None


def test_control_chain_on_a_disposable_postgres_database() -> None:
    raw = _development_control_url()
    if not raw or not raw.startswith("postgresql"):
        pytest.skip("No local Postgres control URL.")
    admin_url = make_url(raw).set(database="postgres")
    disposable = make_url(raw).set(database=DISPOSABLE)
    shared = _env_value("DATABASE_URL")
    dev_before = _revision(shared) if shared and shared.startswith("postgresql") else None
    try:
        admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{DISPOSABLE}"'))
            conn.execute(text(f'CREATE DATABASE "{DISPOSABLE}"'))
        admin.dispose()
    except SQLAlchemyError as exc:
        pytest.skip(f"Postgres is not available for a disposable database: {type(exc).__name__}")
    url = disposable.render_as_string(hide_password=False)
    config = _config(url)
    try:
        command.upgrade(config, "control_0033")
        tenant_id, subscription_id, invoice_id = _seed(url, reuse_catalog=True)
        command.upgrade(config, "head")
        engine = create_engine(url)
        with engine.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM subscription_change_requests")).scalar() == 0
            assert conn.execute(text("SELECT status FROM subscriptions")).scalar() == "active"
            assert conn.execute(text("SELECT plan_code FROM billing_invoices")).scalar() == "FREE"
        engine.dispose()
        command.downgrade(config, "control_0033")
        engine = create_engine(url)
        names = set(inspect(engine).get_table_names())
        assert "subscription_change_requests" not in names
        with engine.connect() as conn:
            assert conn.execute(text("SELECT status FROM subscriptions")).scalar() == "active"
            assert conn.execute(text("SELECT plan_code FROM billing_invoices")).scalar() == "FREE"
        engine.dispose()
        command.upgrade(config, "head")
        _assert_constraints(url, tenant_id, subscription_id, invoice_id)
    finally:
        if shared and shared.startswith("postgresql"):
            assert _revision(shared) == dev_before
        admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": DISPOSABLE},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{DISPOSABLE}"'))
        admin.dispose()
