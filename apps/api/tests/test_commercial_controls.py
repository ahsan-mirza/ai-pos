"""Console publishes commercial rules. It does not rewrite an open trial or an issued invoice."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from tests.governance_support import platform  # noqa: F401

from app.console.billing import assign_free, ensure_catalog
from app.console.promotional_trial import configure_trial, start
from app.core.errors import ApiError
from app.schemas.billing import PlanIn
from app.tenancy.models import BillingInvoice, BillingPlan, ControlBase, PromotionalTrial, Tenant


def _control() -> Session:
    engine = create_engine("sqlite://")
    ControlBase.metadata.create_all(engine)
    return Session(engine)


def _tenant(db: Session, slug: str) -> Tenant:
    tenant = Tenant(slug=slug, name=slug, status="active", database_url_encrypted="x", plan="FREE")
    db.add(tenant)
    db.flush()
    return tenant


def test_future_trial_settings_do_not_move_an_open_trial() -> None:
    with _control() as db:
        ensure_catalog(db)
        first = _tenant(db, "first")
        second = _tenant(db, "second")
        assign_free(db, first)
        assign_free(db, second)
        opened = start(db, first, uuid.uuid4())
        expiry = opened.expires_at
        configure_trial(db, enabled=False, days=21, plans=["FREE"])
        assert opened.expires_at == expiry
        assert opened.status == "active"
        with pytest.raises(ApiError) as disabled:
            start(db, second, None)
        assert disabled.value.code == "trial_disabled"
        configure_trial(db, enabled=True, days=21, plans=["FREE"])
        later = start(db, second, None)
        assert later.expires_at - later.starts_at == timedelta(days=21)
        assert db.get(PromotionalTrial, opened.id).expires_at == expiry
        assert db.scalar(select(func.count()).select_from(BillingInvoice)) == 0


def test_console_publish_grants_plan_modules_and_blocks_a_support_operator(platform) -> None:  # noqa: F811
    from app.console.billing import update_plan
    from app.console.security import OperatorPrincipal

    admin = platform.operator()
    support = platform.operator(email="support-commercial@axizpos.com", role="SUPPORT")
    with platform.control() as db:
        ensure_catalog(db)
        for slug in ("alpha", "bravo"):
            tenant = db.scalar(select(Tenant).where(Tenant.slug == slug))
            assert tenant is not None
            assign_free(db, tenant)
        plan = db.scalar(select(BillingPlan).where(BillingPlan.code == "FREE"))
        assert plan is not None
        plan_id = plan.id
        db.commit()
    denied = platform.client.patch(
        f"/api/v1/super-admin/billing/plans/{plan_id}",
        headers=support,
        json={
            "name": "Free",
            "included_registers": 1,
            "included_modules": ["gift_cards"],
            "monthly_fils": 0,
            "trial_days": 0,
            "active": True,
            "sort_order": 10,
            "reason": "support cannot publish",
        },
    )
    assert denied.status_code == 403
    with platform.control() as db:
        operator = OperatorPrincipal(id=uuid.uuid4(), email="it@axizpos.com", full_name="IT", role="ADMIN", ip=None)
        with pytest.raises(ApiError) as missing:
            update_plan(
                db,
                operator,
                plan_id,
                PlanIn(
                    name="Free",
                    included_registers=1,
                    included_modules=["recipes"],
                    monthly_fils=0,
                    trial_days=0,
                    active=True,
                    sort_order=10,
                    reason="missing dependency",
                ),
            )
        assert missing.value.code == "capability_dependencies"
    published = platform.client.patch(
        f"/api/v1/super-admin/billing/plans/{plan_id}",
        headers=admin,
        json={
            "name": "Free",
            "included_registers": 1,
            "included_modules": ["gift_cards"],
            "monthly_fils": 0,
            "trial_days": 0,
            "active": True,
            "sort_order": 10,
            "resource_limits": {
                "products": 500,
                "branches": 1,
                "registers": 1,
                "staff": 2,
                "customers": 500,
                "sales_history_days": 30,
                "ai_questions_per_month": 10,
            },
            "reason": "Include gift cards on Free",
        },
    )
    assert published.status_code == 200, published.text
    assert published.json()["included_modules"] == ["gift_cards"]
    settings = platform.client.get("/api/v1/settings", headers=platform.headers("alpha"))
    assert settings.status_code == 200, settings.text
    assert "gift_cards" in settings.json()["capabilities"]
    assert "recipes" not in settings.json()["capabilities"]
    with platform.control() as db:
        assert db.scalar(select(func.count()).select_from(BillingInvoice)) == 0
        tenant = db.scalar(select(Tenant).where(Tenant.slug == "alpha"))
        assert tenant is not None and tenant.plan == "FREE"
    history = platform.client.get("/api/v1/super-admin/billing/configuration-history", headers=admin)
    assert history.status_code == 200
    assert any(row["action"] == "billing.plan" for row in history.json())
    started = platform.client.post("/api/v1/billing/promotional-trial", headers=platform.headers("alpha"))
    assert started.status_code == 200, started.text
    expiry = started.json()["expires_at"]
    changed = platform.client.put(
        "/api/v1/super-admin/billing/pro-ai-trial",
        headers=admin,
        json={
            "enabled": True,
            "days": 21,
            "eligible_plans": ["FREE", "GROWTH"],
            "reason": "Future trials last 21 days",
        },
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["days"] == 21
    assert changed.json()["active_trials"] == 1
    current = platform.client.get("/api/v1/billing/promotional-trial", headers=platform.headers("alpha"))
    assert current.json()["expires_at"] == expiry
    assert current.json()["status"] == "active"
    nxt = platform.client.post("/api/v1/billing/promotional-trial", headers=platform.headers("bravo"))
    assert nxt.status_code == 200, nxt.text
    start_at = datetime.fromisoformat(nxt.json()["starts_at"].replace("Z", "+00:00"))
    end_at = datetime.fromisoformat(nxt.json()["expires_at"].replace("Z", "+00:00"))
    assert end_at - start_at == timedelta(days=21)
    assert end_at.tzinfo is UTC or end_at.tzinfo is not None
