"""Scheduling and manual dispatch stay on the sales order. A plan does not invoice or mark payment."""

import uuid
from decimal import Decimal

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import CHAR, Column, MetaData, Table, create_engine, inspect, select

from app.core import capabilities as catalog
from app.models.attribute import ProductAttributeDefinition, ProductAttributeValue
from app.models.fleet import DeliveryZone
from app.models.sales_order import DeliveryNote, SalesOrder, SalesOrderEvent
from app.models.store import Store
from app.services.fleet_service import Cargo, judge_capacity
from app.tenancy.context import TenantRef, use_tenant
from wholesale_support import CABLE, STORE, admin, create_customer, event, push, seed

PROMISED = "2026-11-16"
OTHER_STORE = "00000000-0000-4000-8000-000000000002"
SIGNATURE = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def enable(client, *, fleet: bool = True) -> None:
    headers, _ = admin(client)
    chosen = [capability.value for capability in catalog.ELECTRONICS_WHOLESALE] + ["sales_orders"]
    if fleet:
        chosen.append("fleet_dispatch")
    response = client.put(
        "/api/v1/settings/profile",
        headers=headers,
        json={"business_profile": "electronics_wholesale", "capabilities": chosen},
    )
    assert response.status_code == 200, response.text


def open_order(client, headers) -> dict:
    customer = create_customer(client, headers, credit_limit_cents=10_000_000)
    created = client.post(
        "/api/v1/sales-orders",
        headers=headers,
        json={
            "store_id": STORE,
            "customer_id": customer["id"],
            "lines": [{"product_id": CABLE, "quantity": 2}],
            "confirm": True,
            "requested_date": "2026-11-01",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "CONFIRMED"
    assert body["scheduling_status"] == "UNSCHEDULED"
    assert body["promised_on"] is None
    assert body["created_at"][:10] != PROMISED
    return body


def zone(client, headers, *, code: str = "NORTH") -> dict:
    created = client.post(
        "/api/v1/fleet/zones",
        headers=headers,
        json={"store_id": STORE, "code": code, "name": "North", "fee_cents": 500},
    )
    assert created.status_code == 201, created.text
    return created.json()


def slot(client, headers, zone_id: str, start: str = "08:00:00", end: str = "12:00:00", weekday: int = 0) -> None:
    response = client.post(
        f"/api/v1/fleet/zones/{zone_id}/slots",
        headers=headers,
        json={"weekday": weekday, "start_time": start, "end_time": end},
    )
    assert response.status_code == 201, response.text


def vehicle(client, headers, *, weight: str | None = "1", volume: str | None = "1", code: str = "VAN1") -> dict:
    body: dict = {
        "store_id": STORE,
        "code": code,
        "registration": "A 12345",
        "vehicle_type": "van",
        "weight_unit": "kg",
        "volume_unit": "m3",
        "availability": "AVAILABLE",
    }
    if weight is not None:
        body["weight_amount"] = weight
    if volume is not None:
        body["volume_amount"] = volume
    created = client.post("/api/v1/fleet/vehicles", headers=headers, json=body)
    assert created.status_code == 201, created.text
    return created.json()


def driver(client, headers, user_id: str, *, expiry: str = "2027-01-01", availability: str = "AVAILABLE") -> dict:
    created = client.post(
        "/api/v1/fleet/drivers",
        headers=headers,
        json={
            "user_id": user_id,
            "store_id": STORE,
            "phone": "+971500000000",
            "license_number": "LIC-1",
            "license_expiry": expiry,
            "availability": availability,
        },
    )
    assert created.status_code == 201, created.text
    return created.json()


def schedule(client, headers, order_id: str, **extra) -> dict:
    body = {"promised_on": PROMISED, "window_start": "09:00:00", "window_end": "11:00:00", **extra}
    response = client.post(f"/api/v1/fleet/orders/{order_id}/schedule", headers=headers, json=body)
    return response


def test_null_capacity_is_neither_zero_nor_unlimited() -> None:
    unknown = judge_capacity(Cargo(0, 0, False, False), None, None)
    assert unknown.blocked
    assert unknown.remaining_weight_grams is None
    assert unknown.vehicle_weight_grams is None
    missing = judge_capacity(Cargo(100, 0, True, False), 1000, 1000)
    assert missing.blocked and missing.cargo_weight_incomplete
    over = judge_capacity(Cargo(1500, 10, False, False), 1000, 1000)
    assert over.weight_over and over.remaining_weight_grams == -500
    fits = judge_capacity(Cargo(400, 10, False, False), 1000, 1000)
    assert not fits.blocked
    assert fits.remaining_weight_grams == 600


def test_requested_date_is_not_a_promise_and_windows_use_the_business_clock(client) -> None:
    seed(client)
    enable(client)
    headers, _ = admin(client)
    order = open_order(client, headers)
    assert order["requested_date"] == "2026-11-01"
    assert order["promised_on"] is None

    zone_id = zone(client, headers)["id"]
    slot(client, headers, zone_id)
    outside = schedule(
        client,
        headers,
        order["id"],
        delivery_zone_id=zone_id,
        window_start="13:00:00",
        window_end="14:00:00",
    )
    assert outside.status_code == 422
    assert outside.json()["error"]["code"] == "outside_window"
    backwards = schedule(client, headers, order["id"], window_start="11:00:00", window_end="09:00:00")
    assert backwards.status_code == 422

    changed = client.put("/api/v1/settings/timezone", headers=headers, json={"timezone": "America/New_York"})
    assert changed.status_code == 200, changed.text
    gap = schedule(
        client,
        headers,
        order["id"],
        promised_on="2026-03-08",
        window_start="02:15:00",
        window_end="02:45:00",
        delivery_zone_id=None,
    )
    assert gap.status_code == 422
    assert gap.json()["error"]["code"] == "invalid_window"

    client.put("/api/v1/settings/timezone", headers=headers, json={"timezone": "Asia/Dubai"})
    promised = schedule(client, headers, order["id"], delivery_zone_id=zone_id)
    assert promised.status_code == 200, promised.text
    body = promised.json()
    assert body["scheduling_status"] == "SCHEDULED"
    assert body["promised_on"] == PROMISED
    assert body["promised_on"] != body["created_at"][:10]
    assert body["requested_date"] == "2026-11-01"
    assert body["status"] == "CONFIRMED"
    assert body["deliveries"] == []


def test_missing_dimensions_block_until_an_authorized_override(client, session) -> None:
    seed(client)
    enable(client)
    headers, user_id = admin(client)
    order = open_order(client, headers)
    area = zone(client, headers)
    slot(client, headers, area["id"])
    van = vehicle(client, headers)
    empty = vehicle(client, headers, weight=None, volume=None, code="NONE")
    assert empty["max_weight_grams"] is None
    assert empty["max_volume_cm3"] is None
    assert van["max_weight_grams"] == 1000
    assert van["max_volume_cm3"] == 1_000_000
    driver(client, headers, user_id)
    assert schedule(client, headers, order["id"], delivery_zone_id=area["id"]).status_code == 200

    plan = client.post(
        "/api/v1/fleet/plans",
        headers=headers,
        json={
            "store_id": STORE,
            "service_date": PROMISED,
            "vehicle_id": van["id"],
            "driver_user_id": user_id,
            "order_ids": [order["id"]],
        },
    )
    assert plan.status_code == 201, plan.text
    draft = plan.json()
    assert draft["capacity"]["blocked"]
    assert draft["capacity"]["cargo_weight_incomplete"]
    assert draft["status"] == "DRAFT"

    blocked = client.post(f"/api/v1/fleet/plans/{draft['id']}/confirm", headers=headers, json={})
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "capacity_blocked"

    role = client.post(
        "/api/v1/roles",
        headers=headers,
        json={"name": "Dispatcher", "permissions": ["sales:orders", "portal:access"]},
    )
    assert role.status_code == 201, role.text
    clerk = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": "dispatcher",
            "email": "dispatcher@example.com",
            "full_name": "Dispatcher",
            "role_id": role.json()["id"],
            "password": "dispatcher-pass-1",
            "has_portal_access": True,
        },
    )
    assert clerk.status_code == 201, clerk.text
    logged = client.post(
        "/api/v1/auth/login-password",
        json={"username": "dispatcher", "password": "dispatcher-pass-1"},
    )
    desk = {"Authorization": f"Bearer {logged.json()['access_token']}"}
    denied = client.post(
        f"/api/v1/fleet/plans/{draft['id']}/confirm",
        headers=desk,
        json={"override": True, "reason": "Dimensions not on the cable"},
    )
    assert denied.status_code == 403

    confirmed = client.post(
        f"/api/v1/fleet/plans/{draft['id']}/confirm",
        headers=headers,
        json={"override": True, "reason": "Dimensions not on the cable"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "CONFIRMED"
    again = client.post(f"/api/v1/fleet/plans/{draft['id']}/confirm", headers=headers, json={})
    assert again.status_code == 409

    session.expire_all()
    stored = session.get(SalesOrder, uuid.UUID(order["id"]))
    assert stored is not None
    assert stored.status == "CONFIRMED"
    assert stored.scheduling_status == "SCHEDULED"
    kinds = set(session.scalars(select(SalesOrderEvent.kind).where(SalesOrderEvent.order_id == stored.id)).all())
    assert {"scheduled", "plan_assigned", "capacity_override", "plan_confirmed"} <= kinds
    assert session.scalars(select(DeliveryNote).where(DeliveryNote.order_id == stored.id)).first() is None


def _measure(session, grams: str, ml: str) -> None:
    weight = ProductAttributeDefinition(key="weight", name="Weight", data_type="measurement", unit="kg")
    volume = ProductAttributeDefinition(key="volume", name="Volume", data_type="measurement", unit="ml")
    session.add_all([weight, volume])
    session.flush()
    session.add_all(
        [
            ProductAttributeValue(
                product_id=uuid.UUID(CABLE),
                definition_id=weight.id,
                number_value=Decimal(grams),
                unit="kg",
            ),
            ProductAttributeValue(
                product_id=uuid.UUID(CABLE),
                definition_id=volume.id,
                number_value=Decimal(ml),
                unit="ml",
            ),
        ]
    )
    session.commit()


def test_weight_and_volume_and_duplicate_assignment(client, session) -> None:
    seed(client)
    enable(client)
    headers, user_id = admin(client)
    _measure(session, "0.2", "500")
    order = open_order(client, headers)
    second = open_order(client, headers)
    area = zone(client, headers)
    slot(client, headers, area["id"])
    van = vehicle(client, headers, weight="0.1", volume="1", code="SMALL")
    driver(client, headers, user_id)
    assert schedule(client, headers, order["id"], delivery_zone_id=area["id"]).status_code == 200
    assert schedule(client, headers, second["id"], delivery_zone_id=area["id"]).status_code == 200

    over = client.post(
        "/api/v1/fleet/plans",
        headers=headers,
        json={
            "store_id": STORE,
            "service_date": PROMISED,
            "vehicle_id": van["id"],
            "driver_user_id": user_id,
            "order_ids": [order["id"]],
        },
    )
    assert over.status_code == 201, over.text
    assert over.json()["capacity"]["weight_over"]
    refused = client.post(f"/api/v1/fleet/plans/{over.json()['id']}/confirm", headers=headers, json={})
    assert refused.status_code == 409

    fitting = vehicle(client, headers, weight="10", volume="2", code="BIG")
    moved = client.patch(
        f"/api/v1/fleet/plans/{over.json()['id']}",
        headers=headers,
        json={"vehicle_id": fitting["id"]},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["capacity"]["blocked"] is False
    confirmed = client.post(f"/api/v1/fleet/plans/{over.json()['id']}/confirm", headers=headers, json={})
    assert confirmed.status_code == 200, confirmed.text

    other = client.post(
        "/api/v1/fleet/plans",
        headers=headers,
        json={
            "store_id": STORE,
            "service_date": PROMISED,
            "vehicle_id": fitting["id"],
            "driver_user_id": user_id,
            "order_ids": [order["id"]],
        },
    )
    assert other.status_code == 409
    assert other.json()["error"]["code"] == "already_assigned"

    fresh_van = vehicle(client, headers, code="VAN2")
    other_driver = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": "driver.two",
            "email": "driver.two@example.com",
            "full_name": "Second Driver",
            "role_id": role_id(client, headers),
            "password": "driver-pass-123",
            "has_portal_access": True,
        },
    )
    assert other_driver.status_code == 201, other_driver.text
    driver(client, headers, other_driver.json()["id"])
    reassignment = client.post(
        "/api/v1/fleet/plans",
        headers=headers,
        json={
            "store_id": STORE,
            "service_date": PROMISED,
            "vehicle_id": fresh_van["id"],
            "driver_user_id": other_driver.json()["id"],
            "order_ids": [second["id"]],
        },
    )
    assert reassignment.status_code == 201, reassignment.text
    removed = client.delete(
        f"/api/v1/fleet/plans/{reassignment.json()['id']}/orders/{second['id']}",
        headers=headers,
    )
    assert removed.status_code == 200, removed.text
    added = client.post(
        f"/api/v1/fleet/plans/{reassignment.json()['id']}/orders",
        headers=headers,
        json={"order_id": second["id"]},
    )
    assert added.status_code == 200, added.text


def role_id(client, headers) -> str:
    created = client.post(
        "/api/v1/roles",
        headers=headers,
        json={"name": f"Desk {uuid.uuid4().hex[:8]}", "permissions": ["sales:orders", "portal:access"]},
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def test_unavailable_driver_and_expired_license_block_confirmation(client) -> None:
    seed(client)
    enable(client)
    headers, user_id = admin(client)
    order = open_order(client, headers)
    area = zone(client, headers)
    slot(client, headers, area["id"])
    van = vehicle(client, headers)
    driver(client, headers, user_id, expiry="2026-11-01")
    assert schedule(client, headers, order["id"], delivery_zone_id=area["id"]).status_code == 200
    plan = client.post(
        "/api/v1/fleet/plans",
        headers=headers,
        json={
            "store_id": STORE,
            "service_date": PROMISED,
            "vehicle_id": van["id"],
            "driver_user_id": user_id,
            "order_ids": [order["id"]],
        },
    )
    assert plan.status_code == 201, plan.text
    expired = client.post(
        f"/api/v1/fleet/plans/{plan.json()['id']}/confirm",
        headers=headers,
        json={"override": True, "reason": "License is expired"},
    )
    assert expired.status_code == 409
    assert expired.json()["error"]["code"] == "license_expired"


def test_another_branch_cannot_schedule_and_fleet_is_an_entitlement(client) -> None:
    seed(client)
    enable(client, fleet=False)
    headers, _ = admin(client)
    order = open_order(client, headers)
    hidden = client.get("/api/v1/fleet/orders", headers=headers, params={"view": "unscheduled"})
    assert hidden.status_code == 403
    assert hidden.json()["error"]["code"] == "capability_disabled"

    enable(client)
    push(
        client,
        [event("ws-store-2", "store", {"id": OTHER_STORE, "code": "DT-02", "name": "Harbor", "currency": "USD"})],
    )
    role = role_id(client, headers)
    created = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": "harbor.desk",
            "email": "harbor@example.com",
            "full_name": "Harbor Desk",
            "role_id": role,
            "store_id": OTHER_STORE,
            "password": "harbor-password-1",
            "has_portal_access": True,
        },
    )
    assert created.status_code == 201, created.text
    logged = client.post(
        "/api/v1/auth/login-password",
        json={"username": "harbor.desk", "password": "harbor-password-1"},
    )
    desk = {"Authorization": f"Bearer {logged.json()['access_token']}"}
    denied = schedule(client, desk, order["id"])
    assert denied.status_code == 404
    own = client.get("/api/v1/fleet/orders", headers=desk, params={"view": "unscheduled"})
    assert own.status_code == 200
    assert own.json() == []


def test_cancel_schedule_and_partial_delivery_still_invoice(client, session) -> None:
    seed(client)
    enable(client)
    headers, user_id = admin(client)
    order = open_order(client, headers)
    area = zone(client, headers)
    slot(client, headers, area["id"])
    van = vehicle(client, headers)
    driver(client, headers, user_id)
    assert schedule(client, headers, order["id"], delivery_zone_id=area["id"]).status_code == 200
    cancelled = client.post(f"/api/v1/fleet/orders/{order['id']}/cancel-schedule", headers=headers)
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["scheduling_status"] == "CANCELLED"
    assert cancelled.json()["status"] == "CONFIRMED"
    session.expire_all()
    kinds = set(
        session.scalars(
            select(SalesOrderEvent.kind).where(SalesOrderEvent.order_id == uuid.UUID(order["id"]))
        ).all()
    )
    assert "schedule_cancelled" in kinds

    again = schedule(client, headers, order["id"], delivery_zone_id=area["id"])
    assert again.status_code == 200, again.text
    plan = client.post(
        "/api/v1/fleet/plans",
        headers=headers,
        json={
            "store_id": STORE,
            "service_date": PROMISED,
            "vehicle_id": van["id"],
            "driver_user_id": user_id,
            "order_ids": [order["id"]],
        },
    )
    assert plan.status_code == 201, plan.text
    confirmed = client.post(
        f"/api/v1/fleet/plans/{plan.json()['id']}/confirm",
        headers=headers,
        json={"override": True, "reason": "Cable has no dimensions"},
    )
    assert confirmed.status_code == 200, confirmed.text
    held = client.post(f"/api/v1/fleet/orders/{order['id']}/cancel-schedule", headers=headers)
    assert held.status_code == 409

    picked = client.post(f"/api/v1/sales-orders/{order['id']}/pick", headers=headers)
    assert picked.status_code == 200, picked.text
    line_id = picked.json()["lines"][0]["id"]
    dispatched = client.post(
        f"/api/v1/sales-orders/{order['id']}/dispatch",
        headers=headers,
        json={"lines": [{"order_line_id": line_id, "quantity": 1}], "vehicle": "VAN-1"},
    )
    assert dispatched.status_code == 200, dispatched.text
    state = dispatched.json()
    assert state["status"] == "PARTIALLY_DELIVERED"
    assert state["scheduling_status"] == "SCHEDULED"
    note = state["deliveries"][0]
    assert note["invoice_total_cents"] == 1500
    delivered = client.post(
        f"/api/v1/sales-orders/deliveries/{note['id']}/deliver",
        headers=headers,
        json={"receiver_name": "Omar", "signature": SIGNATURE},
    )
    assert delivered.status_code == 200, delivered.text
    assert delivered.json()["status"] == "DELIVERED"
    current = client.get(f"/api/v1/sales-orders/{order['id']}", headers=headers)
    assert current.json()["status"] == "PARTIALLY_DELIVERED"
    assert current.json()["scheduling_status"] == "SCHEDULED"


def test_two_tenants_keep_their_own_zones(session) -> None:
    first, second = uuid.uuid4(), uuid.uuid4()
    first_store, second_store = uuid.uuid4(), uuid.uuid4()

    def ref(tenant_id: uuid.UUID) -> TenantRef:
        return TenantRef(id=str(tenant_id), slug="store", name="Store", database_url="sqlite://")

    with use_tenant(ref(first)):
        session.add(Store(id=first_store, code="DT-01", name="Downtown", currency="USD"))
        session.commit()
        session.add(DeliveryZone(store_id=first_store, code="NORTH", name="North"))
        session.commit()
    with use_tenant(ref(second)):
        session.add(Store(id=second_store, code="DT-02", name="Harbor", currency="USD"))
        session.commit()
        session.add(DeliveryZone(store_id=second_store, code="NORTH", name="North"))
        session.commit()
    with use_tenant(ref(first)):
        rows = session.scalars(select(DeliveryZone).where(DeliveryZone.code == "NORTH")).all()
        assert [row.tenant_id for row in rows] == [first]


def test_fleet_migration_upgrades_and_rolls_back() -> None:
    engine = create_engine("sqlite://")
    meta = MetaData()
    Table("users", meta, Column("id", CHAR(32), primary_key=True))
    Table("stores", meta, Column("id", CHAR(32), primary_key=True))
    Table("sales_orders", meta, Column("id", CHAR(32), primary_key=True))
    Table("business_settings", meta, Column("id", CHAR(32), primary_key=True))
    meta.create_all(engine)
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "20261112_0107_fleet_dispatch.py"
    spec = importlib.util.spec_from_file_location("fleet_0107", path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
        assert inspect(connection).has_table("dispatch_plans")
        assert "promised_on" in {column["name"] for column in inspect(connection).get_columns("sales_orders")}
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            module.downgrade()
        assert inspect(connection).has_table("dispatch_plans") is False
        assert "promised_on" not in {column["name"] for column in inspect(connection).get_columns("sales_orders")}


@pytest.mark.parametrize("profile", ("restaurant", "cafe", "quick_service"))
def test_food_profiles_do_not_gain_fleet_dispatch(profile: str) -> None:
    assert catalog.Capability.FLEET_DISPATCH not in catalog.PROFILES[profile]
    assert catalog.Capability.FLEET_DISPATCH not in catalog.COMPATIBLE[profile]


def test_a_known_capacity_order_can_be_confirmed_without_changing_payment(client, session) -> None:
    seed(client)
    enable(client)
    headers, user_id = admin(client)
    _measure(session, "0.2", "500")
    order = open_order(client, headers)
    area = zone(client, headers, code="EAST")
    slot(client, headers, area["id"])
    van = vehicle(client, headers, code="FIT")
    driver(client, headers, user_id)
    assert schedule(client, headers, order["id"], delivery_zone_id=area["id"]).status_code == 200
    plan = client.post(
        "/api/v1/fleet/plans",
        headers=headers,
        json={
            "store_id": STORE,
            "service_date": PROMISED,
            "vehicle_id": van["id"],
            "driver_user_id": user_id,
            "order_ids": [order["id"]],
        },
    )
    assert plan.status_code == 201, plan.text
    assert plan.json()["capacity"]["remaining_weight_grams"] == 1000 - 400
    confirmed = client.post(f"/api/v1/fleet/plans/{plan.json()['id']}/confirm", headers=headers, json={})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["capacity_override_by_id"] is None
    current = client.get(f"/api/v1/sales-orders/{order['id']}", headers=headers)
    assert current.json()["status"] == "CONFIRMED"
    assert current.json()["deliveries"] == []
    listed = client.get("/api/v1/fleet/orders", headers=headers, params={"view": "assigned"})
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [order["id"]]
    unassigned = client.get("/api/v1/fleet/orders", headers=headers, params={"view": "unassigned"})
    assert unassigned.json() == []


def test_off_duty_driver_cannot_be_confirmed(client) -> None:
    seed(client)
    enable(client)
    headers, user_id = admin(client)
    order = open_order(client, headers)
    area = zone(client, headers, code="WEST")
    slot(client, headers, area["id"])
    van = vehicle(client, headers, code="WEST1")
    record = driver(client, headers, user_id, availability="OFF_DUTY")
    assert schedule(client, headers, order["id"], delivery_zone_id=area["id"]).status_code == 200
    plan = client.post(
        "/api/v1/fleet/plans",
        headers=headers,
        json={
            "store_id": STORE,
            "service_date": PROMISED,
            "vehicle_id": van["id"],
            "driver_user_id": user_id,
            "order_ids": [order["id"]],
        },
    )
    assert plan.status_code == 201, plan.text
    refused = client.post(f"/api/v1/fleet/plans/{plan.json()['id']}/confirm", headers=headers, json={})
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "driver_unavailable"
    assert record["availability"] == "OFF_DUTY"


def test_check_constraint_names_keep_a_single_prefix() -> None:
    from app.models.fleet import DeliveryZoneSlot, DispatchPlan, FleetVehicle

    slot = [item.name for item in DeliveryZoneSlot.__table__.constraints if str(item.name).startswith("ck_")]
    vehicle = [item.name for item in FleetVehicle.__table__.constraints if str(item.name).startswith("ck_")]
    plan = [item.name for item in DispatchPlan.__table__.constraints if str(item.name).startswith("ck_")]
    assert slot == ["ck_delivery_zone_slots_weekday"]
    assert "ck_fleet_vehicles_availability" in vehicle
    assert "ck_fleet_vehicles_maintenance" in vehicle
    assert plan == ["ck_dispatch_plans_status"]
    assert all("_ck_" not in name for name in [*slot, *vehicle, *plan])


def test_orders_already_on_a_plan_stay_out_of_the_picker(client) -> None:
    seed(client)
    enable(client)
    headers, user_id = admin(client)
    first = open_order(client, headers)
    second = open_order(client, headers)
    area = zone(client, headers, code="EAST")
    slot(client, headers, area["id"])
    van = vehicle(client, headers, code="EAST1")
    driver(client, headers, user_id)
    assert schedule(client, headers, first["id"], delivery_zone_id=area["id"]).status_code == 200
    assert schedule(client, headers, second["id"], delivery_zone_id=area["id"]).status_code == 200
    created = client.post(
        "/api/v1/fleet/plans",
        headers=headers,
        json={
            "store_id": STORE,
            "service_date": PROMISED,
            "vehicle_id": van["id"],
            "driver_user_id": user_id,
            "order_ids": [first["id"]],
        },
    )
    assert created.status_code == 201, created.text
    listed = client.get(
        "/api/v1/fleet/orders",
        headers=headers,
        params={"view": "scheduled", "promised_on": PROMISED},
    )
    assert listed.status_code == 200, listed.text
    by_id = {row["id"]: row for row in listed.json()}
    assert by_id[first["id"]]["plan_id"] == created.json()["id"]
    assert by_id[second["id"]]["plan_id"] is None
    assert by_id[first["id"]]["scheduling_status"] == "SCHEDULED"
    waiting = [row for row in listed.json() if row["plan_id"] is None and row["scheduling_status"] != "CANCELLED"]
    assert [row["id"] for row in waiting] == [second["id"]]


def test_override_without_a_reason_is_refused(client) -> None:
    seed(client)
    enable(client)
    headers, user_id = admin(client)
    order = open_order(client, headers)
    area = zone(client, headers, code="TINY")
    slot(client, headers, area["id"])
    van = vehicle(client, headers, weight="0.01", volume="0.0001", code="TINY1")
    driver(client, headers, user_id)
    assert schedule(client, headers, order["id"], delivery_zone_id=area["id"]).status_code == 200
    draft = client.post(
        "/api/v1/fleet/plans",
        headers=headers,
        json={
            "store_id": STORE,
            "service_date": PROMISED,
            "vehicle_id": van["id"],
            "driver_user_id": user_id,
            "order_ids": [order["id"]],
        },
    )
    assert draft.status_code == 201, draft.text
    missing = client.post(f"/api/v1/fleet/plans/{draft.json()['id']}/confirm", headers=headers, json={"override": True})
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "reason_required"
    blank = client.post(
        f"/api/v1/fleet/plans/{draft.json()['id']}/confirm",
        headers=headers,
        json={"override": True, "reason": "no"},
    )
    assert blank.status_code == 422


def test_invalid_vehicle_capacity_and_empty_plan_are_rejected(client) -> None:
    seed(client)
    enable(client)
    headers, _user_id = admin(client)
    negative = client.post(
        "/api/v1/fleet/vehicles",
        headers=headers,
        json={
            "store_id": STORE,
            "code": "NEG1",
            "registration": "A 1",
            "vehicle_type": "van",
            "weight_amount": "-1",
            "weight_unit": "kg",
            "volume_amount": "-2",
            "volume_unit": "m3",
        },
    )
    assert negative.status_code == 422
    empty = client.post("/api/v1/fleet/plans", headers=headers, json={})
    assert empty.status_code == 422
