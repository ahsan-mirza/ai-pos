"""A receipt is not a payment. Approval records the credit once and activates the subscription."""

import uuid
from datetime import UTC, datetime

from tests.governance_support import platform  # noqa: F401

from app.console.billing import add_calendar_months, ensure_catalog
from app.tenancy.models import BillingInvoice, BillingPayment, Subscription

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def test_calendar_months_clamp_month_end() -> None:
    start = datetime(2026, 1, 31, tzinfo=UTC)
    assert add_calendar_months(start, 1) == datetime(2026, 2, 28, tzinfo=UTC)
    assert add_calendar_months(datetime(2024, 1, 31, tzinfo=UTC), 1) == datetime(2024, 2, 29, tzinfo=UTC)


def test_receipt_does_not_pay_until_an_admin_approves(platform) -> None:  # noqa: F811
    admin = platform.operator()
    support = platform.operator(email="finance-support@axizpos.com", role="SUPPORT")
    created = platform.client.post(
        "/api/v1/super-admin/billing/bank-accounts",
        headers=admin,
        json={
            "display_name": "AxizPOS",
            "bank_name": "Example Bank",
            "holder_name": "AxizPOS LLC",
            "iban": "AE070331234567890123456",
            "currency": "AED",
            "country": "AE",
        },
    )
    assert created.status_code == 201, created.text
    tenant_id = uuid.UUID(platform.tenant_id("alpha"))
    with platform.control() as db:
        ensure_catalog(db)
        invoice = BillingInvoice(
            tenant_id=tenant_id,
            status="pending",
            plan_code="LITE",
            cycle_code="MONTHLY",
            recurring_fils=14_900,
            total_fils=14_900,
            confirm_name="Alpha",
        )
        db.add(invoice)
        db.commit()
        invoice_id = str(invoice.id)
    store = platform.headers("alpha")
    form = {
        "invoice_id": invoice_id,
        "amount_fils": "14900",
        "transferred_on": "2026-10-26",
        "idempotency_key": "transfer-key-1",
        "bank_reference": "BANK-1001",
    }
    files = {"receipt": ("pay.png", PNG, "image/png")}
    submitted = platform.client.post("/api/v1/billing/transfers", headers=store, data=form, files=files)
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "pending_review"
    again = platform.client.post("/api/v1/billing/transfers", headers=store, data=form, files=files)
    assert again.json()["id"] == submitted.json()["id"]
    with platform.control() as db:
        invoice = db.get(BillingInvoice, uuid.UUID(invoice_id))
        assert invoice is not None and invoice.status == "pending"
    denied = platform.client.post(
        f"/api/v1/super-admin/billing/transfers/{submitted.json()['id']}/approve", headers=support
    )
    assert denied.status_code == 403
    approved = platform.client.post(
        f"/api/v1/super-admin/billing/transfers/{submitted.json()['id']}/approve", headers=admin
    )
    assert approved.status_code == 200, approved.text
    repeated = platform.client.post(
        f"/api/v1/super-admin/billing/transfers/{submitted.json()['id']}/approve", headers=admin
    )
    assert repeated.json()["id"] == approved.json()["id"]
    with platform.control() as db:
        invoice = db.get(BillingInvoice, uuid.UUID(invoice_id))
        assert invoice is not None and invoice.status == "paid"
        assert db.query(BillingPayment).count() == 1
        row = db.query(Subscription).filter(Subscription.tenant_id == invoice.tenant_id).one()
        assert row.status == "active" and row.current_period_end is not None
        end = row.current_period_end
        if end.tzinfo is None:
            end = end.replace(tzinfo=UTC)
        assert 28 <= (end - datetime.now(UTC)).days <= 31


def test_rejection_leaves_the_invoice_unpaid(platform) -> None:  # noqa: F811
    admin = platform.operator(email="reject-admin@axizpos.com")
    tenant_id = uuid.UUID(platform.tenant_id("bravo"))
    with platform.control() as db:
        ensure_catalog(db)
        invoice = BillingInvoice(
            tenant_id=tenant_id,
            status="pending",
            plan_code="LITE",
            cycle_code="MONTHLY",
            recurring_fils=14_900,
            total_fils=14_900,
            confirm_name="Bravo",
        )
        db.add(invoice)
        db.commit()
        invoice_id = str(invoice.id)
    submitted = platform.client.post(
        "/api/v1/billing/transfers",
        headers=platform.headers("bravo"),
        data={
            "invoice_id": invoice_id,
            "amount_fils": "14900",
            "transferred_on": "2026-10-26",
            "idempotency_key": "transfer-key-2",
            "bank_reference": "BANK-2002",
        },
        files={"receipt": ("pay.png", PNG, "image/png")},
    )
    assert submitted.status_code == 200, submitted.text
    empty = platform.client.post(
        f"/api/v1/super-admin/billing/transfers/{submitted.json()['id']}/reject",
        headers=admin,
        json={"reason": "no"},
    )
    assert empty.status_code == 422
    rejected = platform.client.post(
        f"/api/v1/super-admin/billing/transfers/{submitted.json()['id']}/reject",
        headers=admin,
        json={"reason": "The bank statement does not show this credit."},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"
    with platform.control() as db:
        invoice = db.get(BillingInvoice, uuid.UUID(invoice_id))
        assert invoice is not None and invoice.status == "pending"
        assert db.query(Subscription).filter(Subscription.tenant_id == invoice.tenant_id).count() == 0


def test_transfer_checkout_does_not_mark_the_invoice_paid(platform) -> None:  # noqa: F811
    created = platform.client.post(
        "/api/v1/super-admin/billing/bank-accounts",
        headers=platform.operator(email="checkout-admin@axizpos.com"),
        json={
            "display_name": "AxizPOS",
            "bank_name": "Example Bank",
            "holder_name": "AxizPOS LLC",
            "iban": "AE070331234567890123456",
            "currency": "AED",
            "country": "AE",
        },
    )
    assert created.status_code == 201, created.text
    with platform.control() as db:
        ensure_catalog(db)
        db.commit()
    started = platform.client.post(
        "/api/v1/billing/checkout",
        headers=platform.headers("alpha"),
        json={
            "plan_code": "LITE",
            "cycle_code": "MONTHLY",
            "mode": "keep",
            "opening_stock": "keep",
            "confirm": "Alpha",
            "tax_acknowledged": True,
            "payment": "transfer",
        },
    )
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["mode"] == "transfer"
    assert body["bank"]["iban"] == "AE070331234567890123456"
    with platform.control() as db:
        invoice = db.get(BillingInvoice, uuid.UUID(body["checkout_id"]))
        assert invoice is not None and invoice.status == "pending"
        assert invoice.bank_snapshot["iban"] == "AE070331234567890123456"
