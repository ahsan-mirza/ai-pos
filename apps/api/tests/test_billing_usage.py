"""Read-only usage counts stay inside the authenticated tenant."""

import time
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm.attributes import flag_modified
from tests.governance_support import platform as platform_fixture  # noqa: F401

from app.console.billing import assign_free
from app.console.usage import count_resources, present_metric
from app.core.permissions import SUPER_ADMIN_ROLE_ID
from app.models.customer import Customer
from app.models.device import Device
from app.models.product import Product
from app.models.store import Store
from app.models.user import User
from app.tenancy.models import BillingPlan, Subscription, Tenant

pytestmark = pytest.mark.usefixtures("platform")


def _assign(platform, slug: str, **limits: object) -> None:
    with platform.control() as db:
        tenant = db.get(Tenant, uuid.UUID(platform.tenant_id(slug)))
        assert tenant is not None
        assign_free(db, tenant)
        if limits:
            plan = db.scalar(select(BillingPlan).where(BillingPlan.code == "FREE"))
            assert plan is not None and plan.resource_limits is not None
            plan.resource_limits = {**plan.resource_limits, **limits}
            flag_modified(plan, "resource_limits")
        db.commit()


def _product(name: str, *, active: bool = True) -> Product:
    return Product(
        sku=name,
        barcode=uuid.uuid4().hex[:12],
        name=name,
        category="Retail",
        price_cents=100,
        currency="AED",
        item_type="PRE_PACKAGED",
        is_active=active,
    )


def _seed(platform, slug: str) -> None:
    with platform.session(slug) as db:
        first = Store(code=f"{slug[:1].upper()}1", name=f"{slug} main", currency="AED")
        warehouse = Store(
            code=f"{slug[:1].upper()}W",
            name=f"{slug} warehouse",
            currency="AED",
            is_warehouse=True,
            is_active=False,
        )
        db.add_all([first, warehouse])
        db.flush()
        db.add(Device(store_id=first.id, code="T1", name="Till", key_hash="a" * 64, key_hint="aaaaaa"))
        db.add(
            Device(
                store_id=first.id,
                code="OLD",
                name="Retired",
                key_hash="b" * 64,
                key_hint="bbbbbb",
                revoked_at=datetime.now(UTC),
            )
        )
        db.add(
            User(
                username=f"{slug}-disabled",
                email=f"disabled@{slug}.example",
                full_name="Disabled",
                is_active=False,
                role_id=uuid.UUID(SUPER_ADMIN_ROLE_ID),
            )
        )
        db.add(_product(f"{slug}-live"))
        db.add(_product(f"{slug}-inactive", active=False))
        db.add(Customer(code=f"{slug[:1].upper()}C1", name="Walk in"))
        db.add(Customer(code=f"{slug[:1].upper()}C2", name="Closed", is_active=False))
        db.commit()


def _body(platform, slug: str, **params: str) -> dict:
    response = platform.client.get("/api/v1/billing/usage", headers=platform.headers(slug), params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_near_limit_is_eighty_percent_and_does_not_invent_a_count() -> None:
    near = present_metric("staff", 4, {"staff": 5})
    assert near.status == "near_limit"
    assert near.percentage == 80
    assert near.available == 1
    below = present_metric("staff", 3, {"staff": 5})
    assert below.status == "available"
    assert below.percentage == 60
    missing = present_metric("products", None, {"products": 10})
    assert missing.usage_available is False
    assert missing.used is None
    assert missing.status == "unavailable"


def test_unauthenticated_usage_is_rejected(platform) -> None:
    denied = platform.client.get("/api/v1/billing/usage", headers={"X-Tenant-Domain": "alpha.axizpos.com"})
    assert denied.status_code == 401


def test_counts_follow_the_live_cap_rules_and_ignore_a_forged_tenant(platform) -> None:
    _assign(platform, "alpha", products=10, customers=10, branches=5, registers=5, staff=5)
    _assign(platform, "bravo")
    _seed(platform, "alpha")
    _seed(platform, "bravo")
    with platform.session("bravo") as db:
        db.add(Store(code="B2", name="Bravo second", currency="AED"))
        db.commit()

    alpha = _body(platform, "alpha", tenant_id=platform.tenant_id("bravo"))
    bravo = _body(platform, "bravo", tenant_id=platform.tenant_id("alpha"))
    assert "tenant_id" not in alpha
    assert alpha["plan_code"] == "FREE"
    assert alpha["metrics"]["branches"]["used"] == 2
    assert alpha["metrics"]["registers"]["used"] == 1
    assert alpha["metrics"]["staff"]["used"] == 1
    assert alpha["metrics"]["products"]["used"] == 2
    assert alpha["metrics"]["customers"]["used"] == 2
    assert bravo["metrics"]["branches"]["used"] == 3
    assert bravo["metrics"]["products"]["used"] == 2
    assert alpha["metrics"]["products"]["used"] != bravo["metrics"]["branches"]["used"]


def test_finite_unlimited_missing_and_exceeded_limits(platform) -> None:
    _assign(platform, "alpha", products=1, branches=None)
    with platform.session("alpha") as db:
        db.add_all([_product("one"), _product("two")])
        db.commit()
    body = _body(platform, "alpha")
    products = body["metrics"]["products"]
    assert products["used"] == 2
    assert products["limit"] == 1
    assert products["available"] == 0
    assert products["percentage"] == 100
    assert products["status"] == "limit_reached"
    assert products["exceeded"] is True
    branches = body["metrics"]["branches"]
    assert branches["status"] == "unlimited"
    assert branches["limit"] is None
    assert branches["percentage"] is None
    assert branches["used"] == 0

    with platform.control() as db:
        plan = db.scalar(select(BillingPlan).where(BillingPlan.code == "FREE"))
        assert plan is not None and plan.resource_limits is not None
        trimmed = dict(plan.resource_limits)
        trimmed.pop("customers", None)
        plan.resource_limits = trimmed
        flag_modified(plan, "resource_limits")
        db.commit()
    missing = _body(platform, "alpha")["metrics"]["customers"]
    assert missing["status"] == "unconfigured"
    assert missing["used"] == 0
    assert missing["limit"] is None
    assert missing["usage_available"] is True


def test_zero_usage_is_a_real_count_and_a_canceled_plan_is_not_unlimited(platform) -> None:
    _assign(platform, "alpha", products=500)
    fresh = _body(platform, "alpha")["metrics"]["products"]
    assert fresh["used"] == 0
    assert fresh["status"] == "available"
    assert fresh["percentage"] == 0
    assert fresh["available"] == 500

    with platform.control() as db:
        row = db.scalar(select(Subscription).where(Subscription.tenant_id == uuid.UUID(platform.tenant_id("alpha"))))
        assert row is not None
        row.status = "canceled"
        db.commit()
    canceled = _body(platform, "alpha")["metrics"]["products"]
    assert canceled["status"] == "unconfigured"
    assert canceled["used"] == 0
    assert canceled["limit"] is None


def test_usage_reads_do_not_write_and_stay_aggregate(platform) -> None:
    _assign(platform, "alpha")
    with platform.session("alpha") as db:
        db.add_all([_product(f"sku-{index}") for index in range(200)])
        db.commit()
        before = int(db.scalar(select(func.count()).select_from(Product)) or 0)
        engine = db.get_bind()
        seen: list[str] = []

        def hear(_conn, _cursor, statement, _params, _context, _executemany) -> None:
            if statement.lstrip().upper().startswith("SELECT"):
                seen.append(statement)

        event.listen(engine, "before_cursor_execute", hear)
        try:
            started = time.perf_counter()
            counts = count_resources(db)
            small = time.perf_counter() - started
        finally:
            event.remove(engine, "before_cursor_execute", hear)
        after = int(db.scalar(select(func.count()).select_from(Product)) or 0)
    assert before == after == 200
    assert counts["products"] == 200
    assert len(seen) == 5
    assert all("COUNT" in statement.upper() for statement in seen)
    assert small < 1

    with platform.session("alpha") as db:
        db.add_all([_product(f"more-{index}") for index in range(1800)])
        db.commit()
    started = time.perf_counter()
    large = _body(platform, "alpha")
    elapsed = time.perf_counter() - started
    assert large["metrics"]["products"]["used"] == 2000
    assert elapsed < 2
    with platform.session("alpha") as db:
        assert int(db.scalar(select(func.count()).select_from(Product)) or 0) == 2000
