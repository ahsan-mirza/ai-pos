"""Published plan modules gate premium capabilities. The business-type preset stays available on Free."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.console.billing import ensure_catalog, ensure_module_addons
from app.console.feature_access import explain
from app.tenancy.models import BillingCycle, BillingPlan, ControlBase, Subscription, Tenant


def _db() -> Session:
    engine = create_engine("sqlite://")
    ControlBase.metadata.create_all(engine)
    return Session(engine)


def _subscribe(db: Session, code: str, slug: str) -> Tenant:
    ensure_catalog(db)
    ensure_module_addons(db)
    tenant = Tenant(slug=slug, name=slug, status="active", database_url_encrypted="x", plan=code)
    db.add(tenant)
    db.flush()
    plan = db.scalar(select(BillingPlan).where(BillingPlan.code == code))
    if plan is None and code in {"LITE", "STANDARD", "PRO"}:
        plan = BillingPlan(code=code, name=code, included_modules=[], active=False, updated_at=datetime.now(UTC))
        db.add(plan)
        db.flush()
    cycle = db.scalar(select(BillingCycle).where(BillingCycle.code == "MONTHLY"))
    assert plan is not None and cycle is not None
    end = None if code == "FREE" else datetime.now(UTC) + timedelta(days=30)
    db.add(
        Subscription(
            tenant_id=tenant.id,
            plan_id=plan.id,
            cycle_id=cycle.id,
            status="active",
            current_period_end=end,
        )
    )
    db.flush()
    return tenant


def _state(rows, key: str) -> str:
    return next(row.state for row in rows if row.feature_key == key)


def test_free_keeps_the_cafe_preset_and_asks_for_the_published_plan() -> None:
    with _db() as db:
        tenant = _subscribe(db, "FREE", "bayrut")
        rows = explain(db, tenant, profile="cafe", purchased=[], promotional=[], managed={}, country="AE")
        loyalty = next(row for row in rows if row.feature_key == "loyalty")
        assert loyalty.state == "INCLUDED"
        assert loyalty.baseline is True
        assert loyalty.grandfathered is False
        assert _state(rows, "recipes") == "INCLUDED"
        assert _state(rows, "tables") == "SWITCHED_OFF"
        sales = next(row for row in rows if row.feature_key == "sales_insights")
        assert sales.state == "UPGRADE_REQUIRED"
        assert sales.baseline is False
        assert sales.required_plan == "GROWTH"
        assert sales.price_published is True
        assert sales.price_fils == 12_900
        assert sales.currency == "AED"
        insights = next(row for row in rows if row.feature_key == "ai_insights")
        assert insights.state == "UPGRADE_REQUIRED"
        assert insights.required_plan == "PRO_AI"
        assert insights.price_fils == 29_900
        assert insights.trial_available is True
        reach = next(row for row in rows if row.feature_key == "axiz_reach")
        assert reach.state == "PLUGIN_REQUIRED"
        assert reach.required_plan is None
        assert reach.price_published is False
        assert _state(rows, "delivery_integrations") == "PLUGIN_REQUIRED"
        assert _state(rows, "b2b_credit") == "BUSINESS_TYPE_UNAVAILABLE"


def test_growth_opens_sales_insights_and_still_blocks_pro_ai() -> None:
    with _db() as db:
        tenant = _subscribe(db, "GROWTH", "growth")
        rows = explain(db, tenant, profile="grocery", purchased=[], promotional=[], managed={}, country="AE")
        assert _state(rows, "sales_insights") == "INCLUDED"
        assert _state(rows, "ai_insights") == "UPGRADE_REQUIRED"
        assert _state(rows, "deep_analytics") == "UPGRADE_REQUIRED"
        assert _state(rows, "axiz_reach") == "PLUGIN_REQUIRED"


def test_an_active_trial_grants_only_the_promotional_keys() -> None:
    with _db() as db:
        tenant = _subscribe(db, "FREE", "trial")
        rows = explain(
            db,
            tenant,
            profile="cafe",
            purchased=[],
            promotional=["ai_insights"],
            managed={},
            country="AE",
        )
        assert _state(rows, "ai_insights") == "TRIAL_INCLUDED"
        assert _state(rows, "deep_analytics") == "UPGRADE_REQUIRED"
        assert _state(rows, "axiz_reach") == "PLUGIN_REQUIRED"


def test_legacy_standard_keeps_the_pages_it_already_had() -> None:
    with _db() as db:
        tenant = _subscribe(db, "STANDARD", "standard")
        rows = explain(db, tenant, profile="cafe", purchased=[], promotional=[], managed={}, country="AE")
        insights = next(row for row in rows if row.feature_key == "ai_insights")
        assert insights.state == "INCLUDED"
        assert insights.grandfathered is True
        assert insights.baseline is False
        assert _state(rows, "sales_insights") == "INCLUDED"
        assert _state(rows, "loyalty") == "INCLUDED"


def test_a_cleared_plan_list_is_not_refilled() -> None:
    with _db() as db:
        ensure_catalog(db)
        growth = db.scalar(select(BillingPlan).where(BillingPlan.code == "GROWTH"))
        assert growth is not None
        assert "sales_insights" in growth.included_modules
        growth.included_modules = []
        db.flush()
        ensure_catalog(db)
        db.refresh(growth)
        assert growth.included_modules == []
