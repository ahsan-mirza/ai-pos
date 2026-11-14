"""control_0035 marks Lite, Standard, and Pro inactive and leaves their history in place.

Downgrade turns those three codes active again. It does not recreate a missing row
and it does not change a subscription or an invoice. The development database is
not upgraded or downgraded by this test.
"""

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import SQLAlchemyError
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
DISPOSABLE = "axiz_phase5_mig"


def _config(url: str) -> Config:
    config = Config(str(API / "alembic_control.ini"))
    config.set_main_option("script_location", str(API / "alembic_control"))
    config.attributes["database_url"] = url
    return config


def _seed_legacy(url: str) -> None:
    engine = create_engine(url)
    Session = sessionmaker(bind=engine)
    now = datetime.now(UTC)
    with Session() as db:
        tenant = Tenant(slug="historical", name="Historical", database_url_encrypted="unused", plan="STANDARD")
        cycle = db.scalar(select(BillingCycle).where(BillingCycle.code == "MONTHLY"))
        if cycle is None:
            cycle = BillingCycle(code="MONTHLY", name="Monthly", months=1, updated_at=now)
            db.add(cycle)
        lite = BillingPlan(code="LITE", name="Lite", monthly_fils=14_900, active=True, updated_at=now)
        standard = BillingPlan(code="STANDARD", name="Standard", monthly_fils=29_900, active=True, updated_at=now)
        pro = BillingPlan(code="PRO", name="Pro", monthly_fils=49_900, active=True, updated_at=now)
        db.add_all([tenant, lite, standard, pro])
        db.flush()
        db.add(Subscription(tenant_id=tenant.id, plan_id=standard.id, cycle_id=cycle.id, status="active"))
        db.add(
            BillingInvoice(
                tenant_id=tenant.id,
                status="pending",
                plan_code="STANDARD",
                cycle_code="MONTHLY",
                recurring_fils=29_900,
                total_fils=29_900,
                confirm_name="Historical",
            )
        )
        db.add(
            SubscriptionChangeRequest(
                tenant_id=tenant.id,
                reference="SCR-OLD",
                current_plan_code="STANDARD",
                requested_plan_code="PRO",
                requested_cycle_code="MONTHLY",
                status="completed",
                quote_snapshot={"total_fils": 29_900},
                correlation_id=uuid.uuid4(),
            )
        )
        db.commit()
    engine.dispose()


def _legacy_state(url: str) -> list[tuple[str, bool, int]]:
    engine = create_engine(url)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT code, active, monthly_fils FROM billing_plans WHERE code IN ('LITE', 'STANDARD', 'PRO') ORDER BY code")
        ).all()
        subscription = conn.execute(text("SELECT status FROM subscriptions")).scalar()
        invoice = conn.execute(text("SELECT status, plan_code, total_fils FROM billing_invoices")).one()
        change = conn.execute(text("SELECT status, current_plan_code, requested_plan_code FROM subscription_change_requests")).one()
    engine.dispose()
    assert subscription == "active"
    assert invoice == ("pending", "STANDARD", 29_900)
    assert change == ("completed", "STANDARD", "PRO")
    return [(code, bool(active), fils) for code, active, fils in rows]


def _env_value(name: str) -> str | None:
    path = REPO / ".env"
    if not path.exists():
        return None
    prefix = f"{name}="
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            return line.split("=", 1)[1].strip().strip('"')
    return None


def _revision(url: str) -> str | None:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            for table in ("control_alembic_version", "alembic_version"):
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


def test_control_0035_retires_existing_rows_on_sqlite(tmp_path) -> None:
    url = f"sqlite:///{(tmp_path / 'control.db').as_posix()}"
    engine = create_engine(url)
    ControlBase.metadata.create_all(engine)
    engine.dispose()
    config = _config(url)
    command.stamp(config, "control_0034")
    _seed_legacy(url)
    command.upgrade(config, "head")
    assert _legacy_state(url) == [("LITE", False, 14_900), ("PRO", False, 49_900), ("STANDARD", False, 29_900)]
    command.downgrade(config, "control_0034")
    assert _legacy_state(url) == [("LITE", True, 14_900), ("PRO", True, 49_900), ("STANDARD", True, 29_900)]
    command.upgrade(config, "head")
    assert _legacy_state(url) == [("LITE", False, 14_900), ("PRO", False, 49_900), ("STANDARD", False, 29_900)]


def test_control_0035_on_a_disposable_postgres_database() -> None:
    raw = _env_value("CONTROL_DATABASE_URL") or _env_value("DATABASE_URL")
    if not raw or not raw.startswith("postgresql"):
        pytest.skip("No local Postgres URL.")
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
        command.upgrade(config, "control_0034")
        _seed_legacy(url)
        command.upgrade(config, "head")
        assert _legacy_state(url) == [("LITE", False, 14_900), ("PRO", False, 49_900), ("STANDARD", False, 29_900)]
        command.downgrade(config, "control_0034")
        assert _legacy_state(url) == [("LITE", True, 14_900), ("PRO", True, 49_900), ("STANDARD", True, 29_900)]
        command.upgrade(config, "head")
        assert _legacy_state(url) == [("LITE", False, 14_900), ("PRO", False, 49_900), ("STANDARD", False, 29_900)]
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
