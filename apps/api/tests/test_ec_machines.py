"""Pay by Card is a package module. An EC machine is a separate purchase. No adapter approves a live charge."""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.console import hardware
from app.console.billing import ensure_catalog, grant_card_terminals_where_seed_unchanged, quote_for
from app.core.errors import ApiError
from app.integrations.terminals.base import TerminalNotConfigured, TerminalTestDouble, live_adapter
from app.schemas.hardware import EcAssignIn, EcRegisterIn, FulfillmentIn, HardwareItemIn, HardwarePick
from app.tenancy.models import (
    BillingCycle,
    BillingInvoice,
    BillingPlan,
    HardwareAssignment,
    HardwareItem,
    HardwareOrderLine,
    Subscription,
    Tenant,
)
from test_hardware import _operator, _session


def test_live_adapter_never_approves_a_charge() -> None:
    adapter = live_adapter("ngenius", True)
    try:
        adapter.initiate(amount_cents=100, currency="AED", reference="A1", idempotency_key="idem-1")
    except TerminalNotConfigured:
        return
    raise AssertionError("a live charge was approved")


def test_the_test_adapter_labels_itself() -> None:
    result = TerminalTestDouble("DECLINED").initiate(
        amount_cents=100, currency="AED", reference="A2", idempotency_key="idem-2"
    )
    assert result.status == "DECLINED" and result.test_adapter is True
    assert "Test adapter" in result.detail
    assert live_adapter("simulator", False).status("A1").status == "UNKNOWN"


def test_card_terminals_are_added_only_to_an_unchanged_seed() -> None:
    with _session() as db:
        ensure_catalog(db)
        db.commit()
        stored = db.scalar(select(BillingPlan).where(BillingPlan.code == "GROWTH"))
        free = db.scalar(select(BillingPlan).where(BillingPlan.code == "FREE"))
        assert stored is not None and free is not None
        stored.included_modules = ["sales_insights", "fleet_dispatch"]
        free.included_modules = ["loyalty"]
        db.commit()
        assert grant_card_terminals_where_seed_unchanged(db) == 1
        db.refresh(stored)
        db.refresh(free)
        assert stored.included_modules == ["sales_insights", "fleet_dispatch", "card_terminals"]
        assert free.included_modules == ["loyalty"]


def test_wired_and_android_prices_are_independent() -> None:
    with _session() as db:
        ensure_catalog(db)
        db.commit()
        operator = _operator(db)
        category = hardware.list_categories(db)[0]
        wired = hardware.create_item(
            db,
            operator,
            HardwareItemIn(
                sku="ECWIRED",
                name="Wired terminal",
                category_id=category.id,
                purchase_available=True,
                lease_available=False,
                purchase_fils=150_000,
                device_type="WIRED",
                warranty_months=12,
                installation_fils=5_000,
                specifications={"connectivity": "Ethernet"},
                reason="Add a wired machine",
            ),
        )
        android = hardware.create_item(
            db,
            operator,
            HardwareItemIn(
                sku="ECANDROID",
                name="Android terminal",
                category_id=category.id,
                purchase_available=True,
                lease_available=False,
                purchase_fils=220_000,
                device_type="ANDROID",
                warranty_months=24,
                reason="Add an Android machine",
            ),
        )
        assert wired.purchase_fils == 150_000 and android.purchase_fils == 220_000
        quote = quote_for(
            db,
            "GROWTH",
            "MONTHLY",
            [],
            [HardwarePick(item_id=wired.id, quantity=1, mode="purchase", store_label="Counter")],
        )
        assert quote.one_time_fils >= 150_000


def test_a_terminal_quote_does_not_include_the_package_price() -> None:
    from app.console.billing import quote_ec_machines
    from app.schemas.hardware import HardwarePick
    from app.tenancy.models import BillingCycle, BillingPlan, Subscription, Tenant

    with _session() as db:
        ensure_catalog(db)
        db.commit()
        operator = _operator(db)
        category = hardware.list_categories(db)[0]
        wired = hardware.create_item(
            db,
            operator,
            HardwareItemIn(
                sku="ECQUOTE",
                name="Quoted terminal",
                category_id=category.id,
                purchase_available=True,
                lease_available=False,
                purchase_fils=100_000,
                installation_fils=2_000,
                device_type="WIRED",
                reason="Quote a machine",
            ),
        )
        plan = db.scalar(select(BillingPlan).where(BillingPlan.code == "FREE"))
        cycle = db.scalar(select(BillingCycle).limit(1))
        tenant = Tenant(slug="ec-shop", name="EC Shop", database_url_encrypted="x")
        db.add(tenant)
        db.flush()
        assert plan is not None and cycle is not None
        db.add(Subscription(tenant_id=tenant.id, plan_id=plan.id, cycle_id=cycle.id, status="active"))
        db.commit()
        before = plan.id
        quote = quote_ec_machines(
            db, tenant, [HardwarePick(item_id=wired.id, quantity=1, mode="purchase", store_label="Counter")], None
        )
        db.refresh(plan)
        assert quote.recurring_fils == 0
        assert quote.total_fils == 102_000
        assert quote.plan_code == "FREE"
        assert plan.id == before
        assert all(not line.recurring for line in quote.lines)


def test_a_second_business_cannot_take_the_same_serial() -> None:
    with _session() as db:
        ensure_catalog(db)
        db.commit()
        operator = _operator(db)
        category = hardware.list_categories(db)[0]
        saved = hardware.create_item(
            db,
            operator,
            HardwareItemIn(
                sku="ECSERIAL",
                name="Machine",
                category_id=category.id,
                purchase_available=True,
                lease_available=False,
                purchase_fils=10_000,
                device_type="WIRED",
                reason="Stock a machine",
            ),
        )
        item = db.get(HardwareItem, saved.id)
        assert item is not None
        db.add(
            HardwareAssignment(
                tenant_id=uuid.uuid4(),
                order_line_id=uuid.uuid4(),
                item_id=item.id,
                serial="SN-1",
                quantity=1,
                device_type="WIRED",
                status="active",
            )
        )
        db.commit()
        try:
            hardware._claim_serials(db, ["SN-1"], uuid.uuid4(), uuid.uuid4())
        except ApiError as exc:
            assert exc.status_code == 409
            return
        raise AssertionError("serial was reused")


def test_a_second_active_serial_or_register_is_rejected_by_the_database() -> None:
    with _session() as db:
        item_id = uuid.uuid4()
        db.add(HardwareItem(id=item_id, sku="ECLOCK", name="Lock", category_id=uuid.uuid4()))
        db.commit()
        first = HardwareAssignment(
            tenant_id=uuid.uuid4(),
            order_line_id=uuid.uuid4(),
            item_id=item_id,
            serial="SN-LOCK",
            quantity=1,
            status="active",
            register_id=uuid.uuid4(),
        )
        db.add(first)
        db.commit()
        register_id = first.register_id
        db.add(
            HardwareAssignment(
                tenant_id=uuid.uuid4(),
                order_line_id=uuid.uuid4(),
                item_id=item_id,
                serial="SN-LOCK",
                quantity=1,
                status="active",
            )
        )
        try:
            db.commit()
            raise AssertionError("duplicate serial was stored")
        except IntegrityError:
            db.rollback()
        db.add(
            HardwareAssignment(
                tenant_id=uuid.uuid4(),
                order_line_id=uuid.uuid4(),
                item_id=item_id,
                serial="SN-OTHER",
                quantity=1,
                status="active",
                register_id=register_id,
            )
        )
        try:
            db.commit()
            raise AssertionError("duplicate register was stored")
        except IntegrityError:
            db.rollback()


def test_a_tenant_confirms_only_its_delivered_serial_and_one_register() -> None:
    with _session() as db:
        ensure_catalog(db)
        db.commit()
        operator = _operator(db)
        category = hardware.list_categories(db)[0]
        saved = hardware.create_item(
            db,
            operator,
            HardwareItemIn(
                sku="ECSELF",
                name="Counter terminal",
                category_id=category.id,
                purchase_available=True,
                lease_available=False,
                purchase_fils=80_000,
                device_type="WIRED",
                warranty_months=12,
                reason="Stock a machine",
            ),
        )
        plan = db.scalar(select(BillingPlan).where(BillingPlan.code == "GROWTH"))
        cycle = db.scalar(select(BillingCycle).limit(1))
        assert plan is not None and cycle is not None
        owner = Tenant(slug="owner-shop", name="Owner", database_url_encrypted="x")
        other = Tenant(slug="other-shop", name="Other", database_url_encrypted="x")
        db.add_all([owner, other])
        db.flush()
        db.add(Subscription(tenant_id=owner.id, plan_id=plan.id, cycle_id=cycle.id, status="active"))
        invoice = BillingInvoice(tenant_id=owner.id, plan_code="FREE", cycle_code=cycle.code, confirm_name="Terminal")
        db.add(invoice)
        db.commit()
        order = hardware.open_order(
            db,
            tenant_id=owner.id,
            invoice_id=invoice.id,
            picks=[HardwarePick(item_id=saved.id, quantity=1, mode="purchase", store_label="Counter")],
            stores=None,
        )
        assert order is not None
        db.commit()
        hardware.mark_paid(db, invoice.id)
        db.commit()
        line = db.scalar(select(HardwareOrderLine).where(HardwareOrderLine.order_id == order.id))
        assert line is not None
        hardware.fulfill(
            db,
            operator,
            order.id,
            FulfillmentIn(line_id=line.id, fulfilled_qty=1, serials=["SN-9"], reason="Delivered to the counter"),
        )
        assignment = db.scalar(select(HardwareAssignment).where(HardwareAssignment.order_line_id == line.id))
        assert assignment is not None and assignment.delivered_at is not None
        try:
            hardware.confirm_ec_registration(db, other.id, assignment.id, EcRegisterIn(serial="SN-9"), uuid.uuid4())
            raise AssertionError("another business registered the machine")
        except ApiError as exc:
            assert exc.status_code == 404
        try:
            hardware.confirm_ec_registration(db, owner.id, assignment.id, EcRegisterIn(serial="SN-OTHER"), uuid.uuid4())
            raise AssertionError("a different serial was accepted")
        except ApiError as exc:
            assert exc.code == "serial_mismatch"
        actor = uuid.uuid4()
        confirmed = hardware.confirm_ec_registration(db, owner.id, assignment.id, EcRegisterIn(serial="sn-9"), actor)
        assert confirmed.registered is True
        assert confirmed.payment_ready is False
        store_a = uuid.uuid4()
        store_b = uuid.uuid4()
        register_a = uuid.uuid4()
        register_b = uuid.uuid4()
        foreign = uuid.uuid4()
        stores = {store_a: "Main", store_b: "Mall"}
        registers = {register_a: (store_a, True), register_b: (store_b, True)}
        try:
            hardware.assign_ec_register(
                db,
                owner.id,
                assignment.id,
                EcAssignIn(store_id=foreign, register_id=register_a),
                stores=stores,
                registers=registers,
                actor_id=actor,
            )
            raise AssertionError("a foreign branch was accepted")
        except ApiError as exc:
            assert exc.code == "unknown_store"
        try:
            hardware.assign_ec_register(
                db,
                owner.id,
                assignment.id,
                EcAssignIn(store_id=store_b, register_id=register_a),
                stores=stores,
                registers=registers,
                actor_id=actor,
            )
            raise AssertionError("a register from another branch was accepted")
        except ApiError as exc:
            assert exc.code == "register_store"
        placed = hardware.assign_ec_register(
            db,
            owner.id,
            assignment.id,
            EcAssignIn(store_id=store_a, register_id=register_a),
            stores=stores,
            registers=registers,
            actor_id=actor,
        )
        moved = hardware.assign_ec_register(
            db,
            owner.id,
            assignment.id,
            EcAssignIn(store_id=store_b, register_id=register_b),
            stores=stores,
            registers=registers,
            actor_id=actor,
        )
        assert placed.register_id == register_a
        assert moved.register_id == register_b
        assert any(event.get("previous_register_id") == str(register_a) for event in moved.history)
        ready = hardware.ec_readiness(db, owner.id, assignment.id)
        assert ready.production_ready is False
        assert "INTEGRATION_NOT_CERTIFIED" in ready.blockers
        assert ready.device_connected is False
        cleared = hardware.unassign_ec_register(db, owner.id, assignment.id, actor)
        assert cleared.register_id is None
        assert any(event.get("action") == "unassign" for event in cleared.history)
        assert any(event.get("previous_register_id") == str(register_b) for event in cleared.history)
