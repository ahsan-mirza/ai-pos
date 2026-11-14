"""Free, Growth, and Pro AI sit beside Lite, Standard, and Pro. Issued invoices keep their fils."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from tests.governance_support import platform  # noqa: F401

from app.console.billing import (
    assign_free,
    cycle_amount,
    discount_bps_for,
    ensure_catalog,
    quote_for,
    start_trial,
)
from app.console.transfers import access_state, operational_block
from app.core.errors import ApiError
from app.models.sale import Sale
from app.models.user import User
from app.tenancy.models import (
    BillingCycle,
    BillingInvoice,
    BillingPlan,
    BillingPlanPrice,
    ControlBase,
    Subscription,
    Tenant,
)

API_KEY = "test-api-key-value"
STORE_ID = "00000000-0000-4000-8000-0000000000a1"
PRODUCT_ID = "00000000-0000-4000-8000-0000000000b1"


def _control() -> Session:
    engine = create_engine("sqlite://")
    ControlBase.metadata.create_all(engine)
    return Session(engine)


def _plan_line(quote, code: str) -> int:
    return next(line.amount_fils for line in quote.lines if line.code == code)


def test_uae_prices_and_the_new_annual_discount_leave_legacy_prices_alone() -> None:
    with _control() as db:
        ensure_catalog(db)
        db.commit()
        stored = {row.code: row.monthly_fils for row in db.scalars(select(BillingPlan))}
        assert set(stored) == {"FREE", "GROWTH", "PRO_AI", "ENTERPRISE"}
        assert stored["FREE"] == 0
        assert stored["GROWTH"] == 12_900
        assert stored["PRO_AI"] == 29_900
        annual = db.scalar(select(BillingCycle).where(BillingCycle.code == "ANNUAL"))
        assert annual is not None and annual.discount_bps == 2_500
        growth = db.scalar(select(BillingPlan).where(BillingPlan.code == "GROWTH"))
        assert growth is not None
        assert discount_bps_for(growth, annual) == 2_000
        historical = BillingPlan(code="STANDARD", name="Standard", monthly_fils=29_900, updated_at=datetime.now(UTC))
        assert discount_bps_for(historical, annual) == 2_500
        priced = quote_for(db, "GROWTH", "ANNUAL", [], country="AE")
        assert priced.currency == "AED"
        assert priced.discount_bps == 2_000
        assert _plan_line(priced, "GROWTH") == cycle_amount(12_900, 12, 2_000)
        monthly = quote_for(db, "PRO_AI", "MONTHLY", [], country="AE")
        assert _plan_line(monthly, "PRO_AI") == 29_900
        free = quote_for(db, "FREE", "MONTHLY", [], country="AE")
        assert free.total_fils == 0
        assert all(line.code != "onboarding" for line in free.lines)
        with pytest.raises(ApiError) as retired:
            quote_for(db, "STANDARD", "ANNUAL", [])
        assert retired.value.code == "plan_not_selectable"
        with pytest.raises(ApiError) as lite:
            quote_for(db, "LITE", "MONTHLY", [])
        assert lite.value.code == "plan_not_selectable"
        with pytest.raises(ApiError) as pro:
            quote_for(db, "PRO", "MONTHLY", [])
        assert pro.value.code == "plan_not_selectable"
        countries = set(db.scalars(select(BillingPlanPrice.country)))
        assert countries == {"AE"}
        with pytest.raises(ApiError) as missing:
            quote_for(db, "GROWTH", "MONTHLY", [], country="SA")
        assert missing.value.code == "price_unavailable"
        with pytest.raises(ApiError) as custom:
            quote_for(db, "ENTERPRISE", "MONTHLY", [], country="AE")
        assert custom.value.code == "custom_pricing"
        limits = db.scalar(select(BillingPlan).where(BillingPlan.code == "FREE"))
        assert limits is not None
        assert limits.resource_limits == {
            "branches": 1,
            "registers": 1,
            "staff": 2,
            "products": 500,
            "customers": 500,
            "sales_history_days": 30,
            "ai_questions_per_month": 10,
        }
        assert db.scalar(select(BillingPlan).where(BillingPlan.code == "LITE")) is None


def test_an_issued_invoice_keeps_its_fil_snapshot() -> None:
    with _control() as db:
        ensure_catalog(db)
        tenant = Tenant(slug="legacy", name="Legacy", status="active", database_url_encrypted="x")
        db.add(tenant)
        db.flush()
        invoice = BillingInvoice(
            tenant_id=tenant.id,
            status="pending",
            plan_code="LITE",
            cycle_code="ANNUAL",
            recurring_fils=134_100,
            total_fils=134_100,
            confirm_name="Legacy",
        )
        db.add(invoice)
        db.commit()
        invoice_id = invoice.id
        ensure_catalog(db)
        db.commit()
        stored = db.get(BillingInvoice, invoice_id)
        assert stored is not None
        assert stored.total_fils == 134_100
        assert stored.plan_code == "LITE"
        assert stored.recurring_fils == 134_100


def test_a_retired_plan_stays_readable_and_is_not_recreated() -> None:
    with _control() as db:
        ensure_catalog(db)
        now = datetime.now(UTC)
        tenant = Tenant(slug="still-lite", name="Still Lite", status="active", database_url_encrypted="x", plan="LITE")
        cycle = db.scalar(select(BillingCycle).where(BillingCycle.code == "MONTHLY"))
        assert cycle is not None
        plan = BillingPlan(
            code="LITE",
            name="Lite",
            monthly_fils=14_900,
            active=True,
            included_modules=["loyalty"],
            updated_at=now,
        )
        db.add_all([tenant, plan])
        db.flush()
        db.add(
            Subscription(
                tenant_id=tenant.id,
                plan_id=plan.id,
                cycle_id=cycle.id,
                status="active",
                current_period_end=now + timedelta(days=10),
            )
        )
        db.add(
            BillingInvoice(
                tenant_id=tenant.id,
                status="pending",
                plan_code="LITE",
                cycle_code="MONTHLY",
                recurring_fils=14_900,
                total_fils=14_900,
                confirm_name="Still Lite",
            )
        )
        db.commit()
        ensure_catalog(db)
        ensure_catalog(db)
        db.commit()
        kept = db.scalar(select(BillingPlan).where(BillingPlan.code == "LITE"))
        assert kept is not None
        assert kept.active is False
        assert kept.monthly_fils == 14_900
        assert kept.included_modules == ["loyalty"]
        assert db.scalar(select(func.count()).select_from(BillingPlan).where(BillingPlan.code == "LITE")) == 1
        subscription = db.scalar(select(Subscription).where(Subscription.tenant_id == tenant.id))
        invoice = db.scalar(select(BillingInvoice).where(BillingInvoice.tenant_id == tenant.id))
        assert subscription is not None and subscription.plan_id == kept.id and subscription.status == "active"
        assert invoice is not None and invoice.plan_code == "LITE" and invoice.total_fils == 14_900
        assert {row.code for row in db.scalars(select(BillingPlan).where(BillingPlan.active.is_(True)))} == {
            "FREE",
            "GROWTH",
            "PRO_AI",
            "ENTERPRISE",
        }


def _domain(slug: str) -> dict[str, str]:
    return {"X-Tenant-Domain": f"{slug}.axizpos.com", "X-Api-Key": API_KEY}


def _event(key: str, entity: str, payload: dict) -> dict:
    return {
        "idempotency_key": key,
        "entity_type": entity,
        "operation": "upsert",
        "payload": payload,
        "occurred_at": datetime.now(UTC).isoformat(),
    }


def _push(host, slug: str, events: list[dict]):
    return host.client.post(
        "/api/v1/sync/push",
        headers=_domain(slug),
        json={"device_id": "device-1", "events": events},
    )


def test_free_provision_is_operational_and_a_second_call_does_not_add_a_subscription(platform) -> None:  # noqa: F811
    with platform.control() as db:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == "alpha"))
        assert tenant is not None
        assign_free(db, tenant)
        assign_free(db, tenant)
        db.commit()
        assert db.scalar(select(func.count()).select_from(Subscription).where(Subscription.tenant_id == tenant.id)) == 1
        assert access_state(db, tenant.id) == "free"
        assert operational_block(db, tenant.id) is None
        other = db.scalar(select(Tenant).where(Tenant.slug == "bravo"))
        assert other is not None
        start_trial(db, other)
        assign_free(db, other)
        db.commit()
        assert access_state(db, other.id) == "free"
        assert other.plan == "FREE"
        growth = db.scalar(select(BillingPlan).where(BillingPlan.code == "GROWTH"))
        existing = db.scalar(select(Subscription).where(Subscription.tenant_id == other.id))
        assert growth is not None and existing is not None
        existing.plan_id = growth.id
        existing.status = "active"
        other.plan = "GROWTH"
        assign_free(db, other)
        db.commit()
        assert other.plan == "GROWTH"
        assert db.scalar(select(func.count()).select_from(Subscription).where(Subscription.tenant_id == other.id)) == 1
    store = platform.headers("alpha")
    settings = platform.client.get("/api/v1/settings", headers=store)
    assert settings.status_code == 200, settings.text
    assert settings.json()["subscription_operational"] is True
    access = platform.client.get("/api/v1/billing/access", headers=store)
    assert access.status_code == 200, access.text
    assert access.json()["state"] == "free"
    assert access.json()["operational"] is True
    products = platform.client.get("/api/v1/products", headers=store, params={"limit": 1})
    assert products.status_code == 200, products.text


def test_a_free_register_can_sell_and_a_locked_store_can_still_sync_the_sale(platform) -> None:  # noqa: F811
    with platform.control() as db:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == "alpha"))
        assert tenant is not None
        assign_free(db, tenant)
        db.commit()
    with platform.session("alpha") as db:
        cashier = db.scalar(select(User.id).where(User.username == "alpha-admin"))
        assert cashier is not None
    sale_id = str(uuid.uuid4())
    seeded = _push(
        platform,
        "alpha",
        [
            _event(
                "free-store",
                "store",
                {"id": STORE_ID, "code": "DT-01", "name": "Downtown", "currency": "USD"},
            ),
            _event(
                "free-product",
                "product",
                {
                    "id": PRODUCT_ID,
                    "store_id": STORE_ID,
                    "sku": "FREE-CABLE",
                    "barcode": "200000000001",
                    "name": "USB-C Cable",
                    "category": "Accessories",
                    "price_cents": 1500,
                    "currency": "USD",
                    "is_serialized": False,
                    "stock_quantity": 5,
                },
            ),
            _event(
                "free-sale",
                "sale",
                {
                    "id": sale_id,
                    "store_id": STORE_ID,
                    "cashier_id": str(cashier),
                    "currency": "USD",
                    "payment_method": "cash",
                    "subtotal_cents": 1500,
                    "tax_cents": 0,
                    "total_cents": 1500,
                    "client_sale_id": sale_id,
                    "items": [
                        {
                            "id": str(uuid.uuid4()),
                            "product_id": PRODUCT_ID,
                            "quantity": 1,
                            "unit_price_cents": 1500,
                            "tax_cents": 0,
                            "line_total_cents": 1500,
                        }
                    ],
                },
            ),
        ],
    )
    assert seeded.status_code == 200, seeded.text
    assert [item["status"] for item in seeded.json()["results"]] == ["applied", "applied", "applied"]
    store = platform.headers("alpha")
    sales = platform.client.get("/api/v1/sales", headers=store)
    assert sales.status_code == 200, sales.text
    assert any(row["id"] == sale_id for row in sales.json())

    with platform.session("alpha") as db:
        old = db.get(Sale, uuid.UUID(sale_id))
        assert old is not None
        old.created_at = datetime.now(UTC) - timedelta(days=10)
        db.commit()
    with platform.control() as db:
        plan = db.scalar(select(BillingPlan).where(BillingPlan.code == "FREE"))
        assert plan is not None
        plan.resource_limits = {**plan.resource_limits, "sales_history_days": 1, "products": 1, "branches": 1}
        flag_modified(plan, "resource_limits")
        db.commit()
    hidden = platform.client.get("/api/v1/sales", headers=store)
    assert hidden.status_code == 200
    assert all(row["id"] != sale_id for row in hidden.json())
    receipt = platform.client.get(f"/api/v1/sales/{sale_id}", headers=store)
    assert receipt.status_code == 200, receipt.text
    extra_product = _push(
        platform,
        "alpha",
        [
            _event(
                "free-product-2",
                "product",
                {
                    "id": str(uuid.uuid4()),
                    "store_id": STORE_ID,
                    "sku": "FREE-CASE",
                    "barcode": "200000000002",
                    "name": "Phone Case",
                    "category": "Accessories",
                    "price_cents": 900,
                    "currency": "USD",
                    "is_serialized": False,
                    "stock_quantity": 1,
                },
            )
        ],
    )
    assert extra_product.status_code == 409
    assert extra_product.json()["error"]["code"] == "plan_limit"
    extra_store = _push(
        platform,
        "alpha",
        [
            _event(
                "free-store-2",
                "store",
                {"id": str(uuid.uuid4()), "code": "DT-02", "name": "Uptown", "currency": "USD"},
            )
        ],
    )
    assert extra_store.status_code == 409
    assert extra_store.json()["error"]["code"] == "plan_limit"
    bravo_store = str(uuid.uuid4())
    other = _push(
        platform,
        "bravo",
        [
            _event(
                "bravo-store",
                "store",
                {"id": bravo_store, "code": "BR-01", "name": "Bravo", "currency": "USD"},
            ),
            _event(
                "bravo-product",
                "product",
                {
                    "id": str(uuid.uuid4()),
                    "store_id": bravo_store,
                    "sku": "BRAVO-CABLE",
                    "barcode": "300000000001",
                    "name": "Bravo Cable",
                    "category": "Accessories",
                    "price_cents": 500,
                    "currency": "USD",
                    "is_serialized": False,
                    "stock_quantity": 1,
                },
            ),
        ],
    )
    assert other.status_code == 200, other.text
    alpha_products = platform.client.get("/api/v1/products", headers=store, params={"limit": 50}).json()
    assert all(row["sku"] != "BRAVO-CABLE" for row in alpha_products)
    first = platform.client.post(
        "/api/v1/devices",
        headers=store,
        json={"store_id": STORE_ID, "code": "T1", "name": "Till 1"},
    )
    assert first.status_code == 201, first.text
    second = platform.client.post(
        "/api/v1/devices",
        headers=store,
        json={"store_id": STORE_ID, "code": "T2", "name": "Till 2"},
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "plan_limit"


def test_a_pending_bank_transfer_still_accepts_the_offline_sale(platform) -> None:  # noqa: F811
    with platform.session("alpha") as db:
        cashier = db.scalar(select(User.id).where(User.username == "alpha-admin"))
    store_id = str(uuid.uuid4())
    product_id = str(uuid.uuid4())
    opened = _push(
        platform,
        "alpha",
        [
            _event("lock-store", "store", {"id": store_id, "code": "LK-01", "name": "Locked", "currency": "USD"}),
            _event(
                "lock-product",
                "product",
                {
                    "id": product_id,
                    "store_id": store_id,
                    "sku": "LOCK-CABLE",
                    "barcode": "400000000001",
                    "name": "Locked Cable",
                    "category": "Accessories",
                    "price_cents": 1000,
                    "currency": "USD",
                    "is_serialized": False,
                    "stock_quantity": 2,
                },
            ),
        ],
    )
    assert opened.status_code == 200, opened.text
    with platform.control() as db:
        tenant_id = uuid.UUID(platform.tenant_id("alpha"))
        db.add(
            BillingInvoice(
                tenant_id=tenant_id,
                status="pending",
                plan_code="LITE",
                cycle_code="MONTHLY",
                recurring_fils=14_900,
                total_fils=14_900,
                confirm_name="Alpha",
            )
        )
        db.commit()
    bearer = platform.headers("alpha")
    blocked = platform.client.get("/api/v1/products", headers=bearer, params={"limit": 1})
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "subscription_payment_required"
    sale_id = str(uuid.uuid4())
    synced = _push(
        platform,
        "alpha",
        [
            _event(
                "locked-sale",
                "sale",
                {
                    "id": sale_id,
                    "store_id": store_id,
                    "cashier_id": str(cashier),
                    "currency": "USD",
                    "payment_method": "cash",
                    "subtotal_cents": 1000,
                    "tax_cents": 0,
                    "total_cents": 1000,
                    "client_sale_id": sale_id,
                    "items": [
                        {
                            "id": str(uuid.uuid4()),
                            "product_id": product_id,
                            "quantity": 1,
                            "unit_price_cents": 1000,
                            "tax_cents": 0,
                            "line_total_cents": 1000,
                        }
                    ],
                },
            )
        ],
    )
    assert synced.status_code == 200, synced.text
    assert synced.json()["results"] == [{"idempotency_key": "locked-sale", "status": "applied"}]
