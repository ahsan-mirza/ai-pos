"""Hardware catalogue pricing stays separate from the subscription, and payment does not deliver hardware."""

import uuid

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.console import hardware
from app.console.billing import ensure_catalog, quote_for
from app.console.security import OperatorPrincipal
from app.core.errors import ApiError
from app.schemas.hardware import DepositDecisionIn, FulfillmentIn, HardwareItemIn, HardwarePick
from app.tenancy.models import (
    BillingInvoice,
    ControlBase,
    HardwareAssignment,
    HardwareItem,
    HardwareOrderLine,
    Operator,
    Tenant,
)


def _session() -> Session:
    engine = create_engine("sqlite://")
    ControlBase.metadata.create_all(engine)
    return Session(engine)


def _operator(db: Session) -> OperatorPrincipal:
    row = Operator(email="ops@example.com", full_name="Ops", password_hash="x", totp_secret_enc="x", role="ADMIN")
    db.add(row)
    db.commit()
    return OperatorPrincipal(id=row.id, email=row.email, full_name=row.full_name, role=row.role, ip=None)


def _tenant(db: Session) -> Tenant:
    row = Tenant(slug="hardware-shop", name="Hardware Shop", database_url_encrypted="x")
    db.add(row)
    db.commit()
    return row


def _item(
    db: Session,
    operator: OperatorPrincipal,
    *,
    sku: str,
    name: str,
    monthly: int,
    deposit: int = 0,
    registers: bool = False,
    stock: int | None = None,
) -> uuid.UUID:
    category = hardware.list_categories(db)[0]
    saved = hardware.create_item(
        db,
        operator,
        HardwareItemIn(
            sku=sku,
            name=name,
            category_id=category.id,
            monthly_fils=monthly,
            deposit_fils=deposit,
            counts_as_register=registers,
            stock_qty=stock,
            reason="Opening catalogue",
        ),
    )
    return saved.id


def test_lease_and_deposit_are_separate_and_optional():
    with _session() as db:
        ensure_catalog(db)
        db.commit()
        empty = quote_for(db, "STANDARD", "MONTHLY", [])
        assert empty.hardware_monthly_fils == 0
        assert empty.deposit_fils == 0
        assert all(not line.code.startswith("h") for line in empty.lines)

        operator = _operator(db)
        terminal = _item(db, operator, sku="TERM-1", name="Terminal", monthly=5_000, deposit=50_000, registers=True)
        printer = _item(db, operator, sku="PRN-1", name="Printer", monthly=2_000)
        store_a = uuid.uuid4()
        store_b = uuid.uuid4()
        stores = {store_a: "Store A", store_b: "Store B"}
        picks = [
            HardwarePick(item_id=terminal, quantity=2, store_id=store_a),
            HardwarePick(item_id=printer, quantity=2, store_id=store_a),
            HardwarePick(item_id=terminal, quantity=1, store_id=store_b),
            HardwarePick(item_id=printer, quantity=1, store_id=store_b),
        ]
        priced = quote_for(db, "STANDARD", "MONTHLY", [], picks, stores)
        assert priced.hardware_monthly_fils == 21_000
        assert priced.deposit_fils == 150_000
        deposit_lines = [line for line in priced.lines if line.refundable]
        assert sum(line.amount_fils for line in deposit_lines) == 150_000
        assert priced.hardware_monthly_fils not in {line.amount_fils for line in priced.lines if line.recurring}
        assert priced.recurring_fils == 29_900 + 21_000


def test_the_example_does_not_treat_the_deposit_as_rent():
    with _session() as db:
        ensure_catalog(db)
        db.commit()
        operator = _operator(db)
        terminal = _item(db, operator, sku="TERM-1", name="Terminal", monthly=5_000, deposit=50_000)
        printer = _item(db, operator, sku="PRN-1", name="Printer", monthly=2_000)
        picks = [
            HardwarePick(item_id=terminal, quantity=2, store_label="Store A"),
            HardwarePick(item_id=printer, quantity=2, store_label="Store A"),
        ]
        priced = quote_for(db, "STANDARD", "MONTHLY", [], picks, {})
        assert priced.hardware_monthly_fils == 14_000
        assert priced.deposit_fils == 100_000
        assert priced.recurring_fils == 29_900 + 14_000
        assert priced.one_time_fils >= 100_000


def test_register_limit_and_store_ownership_and_unavailable_items():
    with _session() as db:
        ensure_catalog(db)
        db.commit()
        operator = _operator(db)
        terminal = _item(db, operator, sku="TERM-1", name="Terminal", monthly=5_000, registers=True)
        mine = uuid.uuid4()
        try:
            quote_for(
                db,
                "STANDARD",
                "MONTHLY",
                [],
                [HardwarePick(item_id=terminal, quantity=4, store_id=mine)],
                {mine: "Only store"},
            )
            raise AssertionError("expected the register limit")
        except ApiError as exc:
            assert exc.code == "register_limit"
        try:
            quote_for(
                db,
                "STANDARD",
                "MONTHLY",
                [],
                [HardwarePick(item_id=terminal, quantity=1, store_id=uuid.uuid4())],
                {mine: "Only store"},
            )
            raise AssertionError("expected a store rejection")
        except ApiError as exc:
            assert exc.code == "unknown_store"
        row = db.get(HardwareItem, terminal)
        assert row is not None
        row.archived = True
        db.commit()
        try:
            quote_for(db, "STANDARD", "MONTHLY", [], [HardwarePick(item_id=terminal, quantity=1, store_label="A")], {})
            raise AssertionError("expected an unavailable item")
        except ApiError as exc:
            assert exc.code == "hardware_unavailable"


def test_a_catalogue_edit_does_not_rewrite_the_order_and_payment_is_not_delivery():
    with _session() as db:
        ensure_catalog(db)
        db.commit()
        operator = _operator(db)
        tenant = _tenant(db)
        terminal = _item(db, operator, sku="TERM-1", name="Terminal", monthly=5_000, deposit=50_000, stock=2)
        invoice = BillingInvoice(
            tenant_id=tenant.id, plan_code="STANDARD", cycle_code="MONTHLY", confirm_name="Hardware Shop"
        )
        db.add(invoice)
        db.commit()
        pick = HardwarePick(item_id=terminal, quantity=2, store_label="Store A")
        order = hardware.open_order(db, tenant_id=tenant.id, invoice_id=invoice.id, picks=[pick], stores=None)
        assert order is not None
        db.commit()
        item = db.get(HardwareItem, terminal)
        assert item is not None
        item.monthly_fils = 9_000
        db.commit()
        stored = db.scalar(select(HardwareOrderLine).where(HardwareOrderLine.order_id == order.id))
        assert stored is not None
        assert stored.monthly_fils == 5_000
        try:
            hardware.fulfill(
                db,
                operator,
                order.id,
                FulfillmentIn(line_id=stored.id, fulfilled_qty=1, reason="Too soon"),
            )
            raise AssertionError("expected unpaid fulfillment to be refused")
        except ApiError as exc:
            assert exc.code == "unpaid"
        hardware.mark_paid(db, invoice.id)
        db.commit()
        assignment = db.scalar(select(HardwareAssignment).where(HardwareAssignment.order_line_id == stored.id))
        assert assignment is not None
        assert assignment.delivered_at is None
        assert assignment.deposit_decision == "held"
        assert order.payment_status == "paid"
        assert order.fulfillment_status == "awaiting_fulfillment"
        try:
            hardware.decide_deposit(
                db,
                operator,
                DepositDecisionIn(assignment_id=assignment.id, decision="refund_approved", reason="Customer asked"),
            )
            raise AssertionError("expected a condition note")
        except ApiError as exc:
            assert exc.code == "condition"
        hardware.fulfill(
            db,
            operator,
            order.id,
            FulfillmentIn(line_id=stored.id, fulfilled_qty=1, serials=["SN-1"], reason="Handed over one unit"),
        )
        assert order.fulfillment_status == "partial"
        assert item.stock_qty == 1
        assert assignment.delivered_at is not None
        other = BillingInvoice(
            tenant_id=tenant.id, plan_code="STANDARD", cycle_code="MONTHLY", confirm_name="Hardware Shop"
        )
        db.add(other)
        db.commit()
        waiting = hardware.open_order(db, tenant_id=tenant.id, invoice_id=other.id, picks=[pick], stores=None)
        assert waiting is not None
        hardware.mark_under_review(db, other.id)
        db.commit()
        assert waiting.payment_status == "under_review"
        assert waiting.fulfillment_status == "under_review"
        try:
            hardware.open_order(db, tenant_id=tenant.id, invoice_id=other.id, picks=[pick], stores=None)
            raise AssertionError("expected the reviewed order to stay locked")
        except ApiError as exc:
            assert exc.code == "hardware_locked"
        hardware.release_review(db, other.id)
        db.commit()
        assert waiting.payment_status == "awaiting_payment"
