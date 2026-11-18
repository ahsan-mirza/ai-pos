"""Demo tenants stay active and stay out of commercial totals."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text  # noqa: TID251
from tests.governance_support import platform  # noqa: F401

from app.console.billing import assign_free, ensure_catalog, list_subscriptions, overview, plan_impact
from app.console.modules import summary
from app.console.promotional_trial import expire_due
from app.console.stats import collect_all
from app.core.config import get_settings
from app.services.messaging_service import dispatch_across_tenants
from app.tenancy.context import use_tenant
from app.tenancy.models import BillingInvoice, BillingPlan, PromotionalTrial, Subscription, Tenant, TenantStats

API = Path(__file__).resolve().parents[1]


def _growth(db, tenant: Tenant) -> int:
    ensure_catalog(db)
    assign_free(db, tenant)
    plan = db.scalar(select(BillingPlan).where(BillingPlan.code == "GROWTH"))
    subscription = db.scalar(select(Subscription).where(Subscription.tenant_id == tenant.id))
    assert plan is not None and subscription is not None
    subscription.plan_id = plan.id
    subscription.status = "active"
    tenant.plan = "GROWTH"
    return int(plan.monthly_fils)


def test_overview_mrr_and_subscription_lists_skip_demo_tenants(platform) -> None:  # noqa: F811
    with platform.control() as db:
        alpha = db.scalar(select(Tenant).where(Tenant.slug == "alpha"))
        bravo = db.scalar(select(Tenant).where(Tenant.slug == "bravo"))
        assert alpha is not None and bravo is not None
        price = _growth(db, alpha)
        _growth(db, bravo)
        bravo.is_demo = True
        bravo.demo_business_type = "electronics"
        bravo.demo_status = "active"
        bravo.demo_access_enabled = True
        db.add(TenantStats(tenant_id=alpha.id, stores=2, registers=3))
        db.add(TenantStats(tenant_id=bravo.id, stores=9, registers=9))
        db.add(
            BillingInvoice(
                tenant_id=alpha.id,
                status="pending",
                plan_code="GROWTH",
                cycle_code="MONTHLY",
                total_fils=price,
                confirm_name="Alpha",
            )
        )
        db.add(
            BillingInvoice(
                tenant_id=bravo.id,
                status="pending",
                plan_code="GROWTH",
                cycle_code="MONTHLY",
                total_fils=99_000,
                confirm_name="Demo",
            )
        )
        db.commit()
        alpha_id = alpha.id
        growth_id = db.scalar(select(BillingPlan.id).where(BillingPlan.code == "GROWTH"))
        assert growth_id is not None
        body = overview(db)
        listed = list_subscriptions(db)
        impact = plan_impact(db, growth_id)
        modules = summary(db)

    assert body.tenants == 1
    assert body.active_tenants == 1
    assert body.paying_subscriptions == 1
    assert body.mrr_fils == price
    assert body.arr_fils == price * 12
    assert body.stores == 2
    assert body.registers == 3
    assert body.unpaid_checkouts == 1
    assert body.unpaid_checkouts_fils == price
    assert body.by_plan[0].paying_tenants == 1
    assert [item.tenant_id for item in listed] == [alpha_id]
    assert impact.tenants == 1
    assert impact.open_invoices == 1
    assert modules.active_subscriptions == 1


def test_trial_expiry_and_stats_and_messaging_skip_demo_tenants(platform, monkeypatch) -> None:  # noqa: F811
    past = datetime.now(UTC) - timedelta(days=2)
    with platform.control() as db:
        alpha = db.scalar(select(Tenant).where(Tenant.slug == "alpha"))
        bravo = db.scalar(select(Tenant).where(Tenant.slug == "bravo"))
        assert alpha is not None and bravo is not None
        bravo.is_demo = True
        bravo.demo_business_type = "restaurant"
        bravo.demo_status = "active"
        for tenant in (alpha, bravo):
            db.add(
                PromotionalTrial(
                    tenant_id=tenant.id,
                    trial_type="PRO_AI_PROMOTIONAL",
                    status="active",
                    base_plan_code="FREE",
                    promotional_plan_code="PRO_AI",
                    starts_at=past - timedelta(days=14),
                    expires_at=past,
                    consumed_at=past - timedelta(days=14),
                )
            )
        db.commit()
    expire_due(get_settings(), datetime.now(UTC))
    with platform.control() as db:
        rows = {
            tenant.slug: trial.status
            for trial, tenant in db.execute(
                select(PromotionalTrial, Tenant).join(Tenant, Tenant.id == PromotionalTrial.tenant_id)
            )
        }
    assert rows["alpha"] == "expired"
    assert rows["bravo"] == "active"
    measured, failed = collect_all(get_settings())
    assert measured == 1
    assert failed == 0

    seen: list[str] = []
    real_use = use_tenant

    def spy(tenant):
        seen.append(tenant.slug)
        return real_use(tenant)

    monkeypatch.setattr("app.tenancy.context.use_tenant", spy)
    dispatch_across_tenants(get_settings())
    assert set(seen) == {"alpha"}


def test_demo_columns_upgrade_preserves_the_tenant_and_downgrade_removes_them(tmp_path) -> None:
    from app.core.database import build_engine

    url = f"sqlite:///{(tmp_path / 'control.db').as_posix()}"
    config = Config(str(API / "alembic_control.ini"))
    config.set_main_option("script_location", str(API / "alembic_control"))
    config.attributes["database_url"] = url
    engine = build_engine(url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE tenants ("
                "id CHAR(32) NOT NULL PRIMARY KEY, slug VARCHAR(32) NOT NULL, name VARCHAR(120) NOT NULL, "
                "status VARCHAR(16) NOT NULL, profile VARCHAR(32) NOT NULL, database_url_encrypted TEXT NOT NULL, "
                "data_plane VARCHAR(16) NOT NULL, plan VARCHAR(32) NOT NULL, practice_mode BOOLEAN NOT NULL, "
                "created_at DATETIME, updated_at DATETIME)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO tenants (id, slug, name, status, profile, database_url_encrypted, data_plane, plan, "
                "practice_mode) VALUES ('kept-id', 'kept', 'Kept Store', 'active', 'grocery', 'unused', 'shared', "
                "'FREE', 1)"
            )
        )
    command.stamp(config, "control_0037")
    command.upgrade(config, "head")
    with engine.connect() as conn:
        row = conn.execute(text("SELECT slug, is_demo, demo_access_enabled FROM tenants")).one()
        indexes = {item["name"] for item in inspect(engine).get_indexes("tenants")}
    assert row.slug == "kept"
    assert row.is_demo in (0, False)
    assert row.demo_access_enabled in (0, False)
    assert "ix_tenants_is_demo_demo_status" in indexes
    assert "ix_tenants_demo_expires_at" in indexes
    command.downgrade(config, "control_0037")
    with engine.connect() as conn:
        kept = conn.execute(text("SELECT slug FROM tenants")).scalar()
        columns = {item["name"] for item in inspect(engine).get_columns("tenants")}
    assert kept == "kept"
    assert "is_demo" not in columns
    command.upgrade(config, "head")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT is_demo FROM tenants")).scalar() in (0, False)
    engine.dispose()


def test_active_tenants_still_includes_a_demo_store(platform) -> None:  # noqa: F811
    from app.tenancy.registry import active_tenants

    with platform.control() as db:
        bravo = db.scalar(select(Tenant).where(Tenant.slug == "bravo"))
        assert bravo is not None
        bravo.is_demo = True
        bravo.status = "active"
        db.commit()
    slugs = {tenant.slug for tenant in active_tenants(get_settings())}
    assert slugs == {"alpha", "bravo"}
