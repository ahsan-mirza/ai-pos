"""The Pro AI promotion sits beside the subscription. It does not replace it or open an invoice."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified
from tests.governance_support import platform  # noqa: F401

from app.console.billing import assign_free, ensure_catalog, start_trial
from app.console.promotional_trial import (
    TRIAL_DAYS,
    effective_limits,
    effective_status,
    expire_due,
    set_trial_enabled,
    start,
)
from app.core.config import get_settings
from app.core.errors import ApiError
from app.models.user import User
from app.tenancy.models import BillingInvoice, BillingPlan, ControlBase, PromotionalTrial, Subscription, Tenant


def _control():
    engine = create_engine("sqlite://")
    ControlBase.metadata.create_all(engine)
    from sqlalchemy.orm import Session

    return Session(engine)


def _tenant(db, slug: str, status: str = "active") -> Tenant:
    tenant = Tenant(slug=slug, name=slug, status=status, database_url_encrypted="x", plan="FREE")
    db.add(tenant)
    db.flush()
    return tenant


def test_free_and_growth_can_start_once_and_other_plans_cannot() -> None:
    with _control() as db:
        ensure_catalog(db)
        free = _tenant(db, "free")
        growth = _tenant(db, "growth")
        assign_free(db, free)
        assign_free(db, growth)
        growth_plan = db.scalar(select(BillingPlan).where(BillingPlan.code == "GROWTH"))
        growth_sub = db.scalar(select(Subscription).where(Subscription.tenant_id == growth.id))
        assert growth_plan is not None and growth_sub is not None
        growth_sub.plan_id = growth_plan.id
        growth.plan = "GROWTH"
        pro_ai = db.scalar(select(BillingPlan).where(BillingPlan.code == "PRO_AI"))
        assert pro_ai is not None
        pro_ai.included_modules = ["gift_cards", "axiz_reach"]
        flag_modified(pro_ai, "included_modules")
        db.flush()
        opened = start(db, free, uuid.uuid4())
        plan_id = db.scalar(select(Subscription.plan_id).where(Subscription.tenant_id == free.id))
        again = start(db, free, uuid.uuid4())
        assert again.id == opened.id
        assert again.expires_at == opened.expires_at
        assert again.expires_at - again.starts_at == timedelta(days=TRIAL_DAYS)
        assert db.scalar(select(Subscription.plan_id).where(Subscription.tenant_id == free.id)) == plan_id
        assert db.scalar(select(func.count()).select_from(BillingInvoice)) == 0
        widened = effective_limits(db, free.id)
        assert widened is not None and widened["products"] == 25_000
        opened.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        assert effective_status(opened) == "expired"
        restored = effective_limits(db, free.id)
        assert restored is not None and restored["products"] == 500
        with pytest.raises(ApiError) as consumed:
            start(db, free, None)
        assert consumed.value.code == "trial_consumed"
        assert start(db, growth, None).base_plan_code == "GROWTH"
        for code, slug in (("STANDARD", "std"), ("PRO", "pro"), ("ENTERPRISE", "ent")):
            tenant = _tenant(db, slug)
            assign_free(db, tenant)
            plan = db.scalar(select(BillingPlan).where(BillingPlan.code == code))
            sub = db.scalar(select(Subscription).where(Subscription.tenant_id == tenant.id))
            assert plan is not None and sub is not None
            sub.plan_id = plan.id
            sub.status = "active"
            with pytest.raises(ApiError) as denied:
                start(db, tenant, None)
            assert denied.value.code == "trial_ineligible"
        legacy = _tenant(db, "legacy")
        start_trial(db, legacy)
        with pytest.raises(ApiError) as practice:
            start(db, legacy, None)
        assert practice.value.code == "trial_ineligible"
        paused = _tenant(db, "paused", status="suspended")
        assign_free(db, paused)
        with pytest.raises(ApiError) as suspended:
            start(db, paused, None)
        assert suspended.value.code == "trial_ineligible"
        set_trial_enabled(db, False)
        blocked = _tenant(db, "off")
        assign_free(db, blocked)
        with pytest.raises(ApiError) as disabled:
            start(db, blocked, None)
        assert disabled.value.code == "trial_disabled"
        duplicate = PromotionalTrial(
            tenant_id=free.id,
            trial_type="PRO_AI_PROMOTIONAL",
            status="active",
            base_plan_code="FREE",
            promotional_plan_code="PRO_AI",
            starts_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(days=1),
            consumed_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(duplicate)
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()


def test_one_store_cannot_read_or_restart_another_stores_trial(platform) -> None:  # noqa: F811
    from app.console.billing import assign_free, ensure_catalog

    with platform.control() as db:
        ensure_catalog(db)
        for slug in ("alpha", "bravo"):
            tenant = db.scalar(select(Tenant).where(Tenant.slug == slug))
            assert tenant is not None
            assign_free(db, tenant)
        plan = db.scalar(select(BillingPlan).where(BillingPlan.code == "PRO_AI"))
        assert plan is not None
        plan.included_modules = ["gift_cards"]
        flag_modified(plan, "included_modules")
        db.commit()
    alpha = platform.headers("alpha")
    bravo = platform.headers("bravo")
    created = platform.client.post(
        "/api/v1/users",
        headers=alpha,
        json={
            "username": "manager-alpha",
            "email": "manager@alpha.example",
            "full_name": "Alpha Manager",
            "role_id": "00000000-0000-4000-8000-0000000000a2",
            "password": "manager-password-1",
            "has_portal_access": True,
        },
    )
    assert created.status_code == 201, created.text
    manager_login = platform.client.post(
        "/api/v1/auth/login-password",
        headers={"X-Tenant-Domain": "alpha.axizpos.com"},
        json={"username": "manager-alpha", "password": "manager-password-1"},
    )
    assert manager_login.status_code == 200, manager_login.text
    manager = {
        "X-Tenant-Domain": "alpha.axizpos.com",
        "Authorization": f"Bearer {manager_login.json()['access_token']}",
    }
    forbidden = platform.client.post("/api/v1/billing/promotional-trial", headers=manager)
    assert forbidden.status_code == 403
    started = platform.client.post("/api/v1/billing/promotional-trial", headers=alpha)
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["base_plan_code"] == "FREE"
    assert body["capabilities"] == ["Gift cards"]
    again = platform.client.post("/api/v1/billing/promotional-trial", headers=alpha)
    assert again.status_code == 200
    assert again.json()["expires_at"] == body["expires_at"]
    other = platform.client.get("/api/v1/billing/promotional-trial", headers=bravo)
    assert other.status_code == 200
    assert other.json()["status"] == "not_started"
    assert other.json()["expires_at"] is None
    stolen = platform.client.post(
        "/api/v1/billing/promotional-trial",
        headers=bravo,
        json={"tenant_id": body.get("id")},
    )
    assert stolen.status_code == 200
    assert stolen.json()["base_plan_code"] == "FREE"
    assert stolen.json()["expires_at"] != body["expires_at"]
    settings = platform.client.get("/api/v1/settings", headers=alpha)
    assert settings.status_code == 200
    assert "gift_cards" in settings.json()["capabilities"]
    assert "axiz_reach" not in settings.json()["capabilities"]
    with platform.control() as db:
        assert db.scalar(select(func.count()).select_from(BillingInvoice)) == 0
        tenant = db.scalar(select(Tenant).where(Tenant.slug == "alpha"))
        assert tenant is not None and tenant.plan == "FREE"
        sub = db.scalar(select(Subscription).where(Subscription.tenant_id == tenant.id))
        assert sub is not None and sub.status == "active"
        row = db.scalar(select(PromotionalTrial).where(PromotionalTrial.tenant_id == tenant.id))
        assert row is not None
        row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()
    late = platform.client.get("/api/v1/billing/promotional-trial", headers=alpha)
    assert late.json()["status"] == "expired"
    first = expire_due(get_settings())
    second = expire_due(get_settings())
    assert first.startswith("1 ")
    assert second.startswith("0 ")
    with platform.session("alpha") as db:
        assert db.scalar(select(User.id).where(User.username == "alpha-admin")) is not None
    cleared = platform.client.get("/api/v1/settings", headers=alpha)
    assert "gift_cards" not in cleared.json().get("promotional_capabilities", [])
