"""Laundry intake orders, tags, photos, and accepted price snapshots."""

import base64
import uuid

from tests.conftest import ADMIN_PASSWORD

from app.core.capabilities import Capability
from app.core.permissions import CASHIER_ROLE_ID, STORE_MANAGER_ROLE_ID, SYSTEM_ROLES, Permission
from app.models.customer import Customer
from app.models.laundry import LaundryService
from app.models.store import Store
from app.tenancy.scoping import DEFAULT_TENANT_ID

JPEG = b"\xff\xd8\xff" + b"\x00" * 32


def _login(client) -> dict[str, str]:
    response = client.post("/api/v1/auth/login-password", json={"username": "admin", "password": ADMIN_PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _ready(client, headers, session):
    switched = client.put(
        "/api/v1/settings/profile",
        headers=headers,
        json={
            "business_profile": "laundry",
            "capabilities": [
                Capability.LOYALTY.value,
                Capability.PROMOTIONS.value,
                Capability.WEIGHED_ITEMS.value,
                Capability.CARD_TERMINALS.value,
                Capability.LAUNDRY_OPERATIONS.value,
            ],
        },
    )
    assert switched.status_code == 200, switched.text
    client.put(
        "/api/v1/settings/tax",
        headers=headers,
        json={
            "vat_registered": True,
            "trn": "100000000000003",
            "prices_include_vat": False,
            "standard_rate_bps": 500,
            "tax_authority": "fta",
        },
    )
    applied = client.post("/api/v1/laundry/templates/laundry_shop", headers=headers)
    assert applied.status_code == 200, applied.text
    services = client.get("/api/v1/laundry/services", headers=headers).json()
    shirt = next(row for row in services if row["code"] == "dry_clean_shirt")
    fold = next(row for row in services if row["code"] == "wash_fold")
    patched = client.patch(
        f"/api/v1/laundry/services/{shirt['id']}",
        headers=headers,
        json={"base_rate_cents": 1000, "express_surcharge_cents": 250, "allow_zero_rate": False},
    )
    assert patched.status_code == 200, patched.text
    folded = client.patch(
        f"/api/v1/laundry/services/{fold['id']}",
        headers=headers,
        json={"base_rate_cents": 1000, "min_charge_cents": 2000, "weight_precision": 3, "allow_zero_rate": False},
    )
    assert folded.status_code == 200, folded.text
    store = Store(code="A", name="Shop A", currency="AED", tenant_id=DEFAULT_TENANT_ID)
    customer = Customer(code="WALK", name="Walk in", tenant_id=DEFAULT_TENANT_ID)
    session.add_all([store, customer])
    session.commit()
    return shirt, fold, store, customer


def _order(shirt_id: str, store_id: str, customer_id: str, key: str, **extra):
    body = {
        "idempotency_key": key,
        "intake_store_id": store_id,
        "customer_id": customer_id,
        "order_type": "WALK_IN",
        "garments": [
            {
                "service_id": shirt_id,
                "quantity": 2,
                "description": "White shirt",
                "condition": "tear",
                "stains": "ink",
                "extras_cents": 100,
            }
        ],
    }
    body.update(extra)
    return body


def test_cashier_and_store_manager_do_not_receive_laundry_order_permissions() -> None:
    roles = {role["id"]: set(role["permissions"]) for role in SYSTEM_ROLES}
    blocked = {
        Permission.LAUNDRY_ORDERS_VIEW,
        Permission.LAUNDRY_ORDERS_CREATE,
        Permission.LAUNDRY_ORDERS_UPDATE,
        Permission.LAUNDRY_ORDERS_CANCEL,
        Permission.LAUNDRY_GARMENTS_VIEW,
        Permission.LAUNDRY_GARMENTS_UPDATE,
        Permission.LAUNDRY_TAGS_PRINT,
        Permission.LAUNDRY_PRICING_OVERRIDE,
        Permission.LAUNDRY_PHOTOS_UPLOAD,
    }
    assert blocked.isdisjoint(roles[CASHIER_ROLE_ID])
    assert blocked.isdisjoint(roles[STORE_MANAGER_ROLE_ID])


def test_intake_snapshots_tags_and_a_repeated_submit(client, session) -> None:
    headers = _login(client)
    shirt, fold, store, customer = _ready(client, headers, session)
    body = _order(shirt["id"], str(store.id), str(customer.id), "order-key-0001")
    body["bags"] = [{"service_id": fold["id"], "gross_weight": 2500, "tare_weight": 250}]
    body["deposit"] = {"amount_cents": 500, "method": "cash"}
    first = client.post("/api/v1/laundry/orders", headers=headers, json=body)
    assert first.status_code == 201, first.text
    created = first.json()
    assert created["total_cents"] > created["amount_paid_cents"]
    assert created["balance_due_cents"] == created["total_cents"] - 500
    assert created["payment_status"] == "PARTIAL"
    assert len(created["tags"]) == 2
    assert created["garments"][0]["condition"] == "tear"
    again = client.post("/api/v1/laundry/orders", headers=headers, json=body)
    assert again.status_code == 201
    assert again.json()["id"] == created["id"]
    session.get(LaundryService, uuid.UUID(shirt["id"])).base_rate_cents = 5000
    session.commit()
    kept = client.get(f"/api/v1/laundry/orders/{created['id']}", headers=headers)
    assert kept.json()["total_cents"] == created["total_cents"]
    assert kept.json()["pricing_snapshot"]["lines"][0]["unit_price_cents"] == 1000
    photo = client.post(
        f"/api/v1/laundry/orders/{created['id']}/photos",
        headers=headers,
        json={
            "mime": "image/jpeg",
            "content_base64": base64.b64encode(JPEG).decode(),
            "garment_id": created["garments"][0]["id"],
        },
    )
    assert photo.status_code == 201, photo.text
    rejected = client.post(
        f"/api/v1/laundry/orders/{created['id']}/photos",
        headers=headers,
        json={"mime": "image/png", "content_base64": base64.b64encode(JPEG).decode()},
    )
    assert rejected.status_code == 422
    tag = created["tags"][0]
    scanned = client.post(
        "/api/v1/laundry/tags/scan",
        headers=headers,
        json={"code": tag["code"], "order_id": created["id"], "idempotency_key": "scan-key-0001"},
    )
    assert scanned.status_code == 200, scanned.text
    repeat = client.post(
        "/api/v1/laundry/tags/scan",
        headers=headers,
        json={"code": tag["code"], "order_id": created["id"], "idempotency_key": "scan-key-0001"},
    )
    assert repeat.json()["id"] == scanned.json()["id"]
    unknown = client.post(
        "/api/v1/laundry/tags/scan",
        headers=headers,
        json={"code": "NO-SUCH-TAG", "idempotency_key": "scan-key-0002"},
    )
    assert unknown.status_code == 404
    other = client.post(
        "/api/v1/laundry/tags/scan",
        headers=headers,
        json={"code": tag["code"], "order_id": str(uuid.uuid4()), "idempotency_key": "scan-key-0003"},
    )
    assert other.status_code == 422
    assert other.json()["error"]["code"] == "wrong_order"
    replaced = client.post(
        f"/api/v1/laundry/tags/{tag['id']}/replace",
        headers=headers,
        json={"idempotency_key": "replace-key-01"},
    )
    assert replaced.status_code == 200, replaced.text
    old = client.post(
        "/api/v1/laundry/tags/scan",
        headers=headers,
        json={"code": tag["code"], "idempotency_key": "scan-key-0004"},
    )
    assert old.status_code == 409
    missing = client.post("/api/v1/laundry/orders", json=body)
    assert missing.status_code == 401


def test_express_capacity_and_edit_rules(client, session) -> None:
    headers = _login(client)
    shirt, _fold, store, customer = _ready(client, headers, session)
    closed = client.put(
        f"/api/v1/laundry/branches/{store.id}/express-capacity",
        headers=headers,
        json={"express_daily_capacity": 1},
    )
    assert closed.status_code == 200, closed.text
    first = client.post(
        "/api/v1/laundry/orders",
        headers=headers,
        json=_order(shirt["id"], str(store.id), str(customer.id), "express-key-001", express=True),
    )
    assert first.status_code == 201, first.text
    second = client.post(
        "/api/v1/laundry/orders",
        headers=headers,
        json=_order(shirt["id"], str(store.id), str(customer.id), "express-key-002", express=True),
    )
    assert second.status_code == 422
    assert second.json()["error"]["code"] == "express_capacity"
    order = first.json()
    blocked = client.post(
        f"/api/v1/laundry/orders/{order['id']}/quantity",
        headers=headers,
        json={"garment_id": order["garments"][0]["id"], "quantity": 3, "reason": "", "version": order["version"]},
    )
    assert blocked.status_code == 200, blocked.text
    started = client.post(
        f"/api/v1/laundry/orders/{order['id']}/production",
        headers=headers,
        json={"reason": "Sent to wash"},
    )
    assert started.status_code == 200, started.text
    denied = client.post(
        f"/api/v1/laundry/orders/{order['id']}/quantity",
        headers=headers,
        json={
            "garment_id": order["garments"][0]["id"],
            "quantity": 4,
            "reason": "",
            "version": started.json()["version"],
        },
    )
    assert denied.status_code == 422
    changed = client.post(
        f"/api/v1/laundry/orders/{order['id']}/quantity",
        headers=headers,
        json={
            "garment_id": order["garments"][0]["id"],
            "quantity": 4,
            "reason": "Customer added a shirt",
            "version": started.json()["version"],
        },
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["pricing_snapshot"]["lines"][0]["unit_price_cents"] == 1000
    bare = client.post(
        f"/api/v1/laundry/orders/{order['id']}/cancel",
        headers=headers,
        json={"reason": "", "version": changed.json()["version"]},
    )
    assert bare.status_code == 422
    cancelled = client.post(
        f"/api/v1/laundry/orders/{order['id']}/cancel",
        headers=headers,
        json={"reason": "Customer left", "version": changed.json()["version"]},
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["operational_status"] == "CANCELLED"
    assert any(event["kind"] == "created" for event in cancelled.json()["events"])


def test_same_order_payment_conflict_photo_and_sync(client, session) -> None:
    headers = _login(client)
    other = _login(client)
    shirt, fold, store, customer = _ready(client, headers, session)
    created = client.post(
        "/api/v1/laundry/orders",
        headers=headers,
        json=_order(
            shirt["id"],
            str(store.id),
            str(customer.id),
            "shared-order-0001",
            garments=[
                {"service_id": shirt["id"], "quantity": 1, "description": "White shirt", "condition": "tear"},
                {"service_id": shirt["id"], "quantity": 1, "description": "Blue shirt", "condition": "stain"},
            ],
        ),
    )
    assert created.status_code == 201, created.text
    order = created.json()
    assert len(order["garments"]) == 2
    assert len(order["tags"]) == 2
    found = client.get("/api/v1/laundry/orders", headers=other, params={"q": order["code"]})
    assert found.status_code == 200
    assert found.json()[0]["id"] == order["id"]
    detail = client.get(f"/api/v1/laundry/orders/{order['id']}", headers=other)
    assert detail.json()["total_cents"] == order["total_cents"]
    assert detail.json()["tax_cents"] == order["tax_cents"]
    assert detail.json()["balance_due_cents"] == order["balance_due_cents"]
    assert detail.json()["intake_store_id"] == str(store.id)
    deposit_id = str(uuid.uuid4())
    partial = client.post(
        f"/api/v1/laundry/orders/{order['id']}/deposits",
        headers=headers,
        json={"id": deposit_id, "amount_cents": 500, "method": "cash", "version": order["version"]},
    )
    assert partial.status_code == 200, partial.text
    assert partial.json()["amount_paid_cents"] == 500
    assert partial.json()["balance_due_cents"] == partial.json()["total_cents"] - 500
    replay = client.post(
        f"/api/v1/laundry/orders/{order['id']}/deposits",
        headers=other,
        json={"id": deposit_id, "amount_cents": 500, "method": "cash", "version": partial.json()["version"]},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["amount_paid_cents"] == 500
    over = client.post(
        f"/api/v1/laundry/orders/{order['id']}/deposits",
        headers=headers,
        json={
            "id": str(uuid.uuid4()),
            "amount_cents": partial.json()["balance_due_cents"] + 1,
            "method": "card",
            "version": partial.json()["version"],
        },
    )
    assert over.status_code == 422
    assert over.json()["error"]["code"] == "deposit_too_large"
    settled = client.post(
        f"/api/v1/laundry/orders/{order['id']}/deposits",
        headers=headers,
        json={
            "id": str(uuid.uuid4()),
            "amount_cents": partial.json()["balance_due_cents"],
            "method": "card",
            "version": partial.json()["version"],
        },
    )
    assert settled.status_code == 200, settled.text
    assert settled.json()["payment_status"] == "PAID"
    assert settled.json()["balance_due_cents"] == 0
    version = settled.json()["version"]
    first_edit = client.post(
        f"/api/v1/laundry/orders/{order['id']}/garments",
        headers=headers,
        json={"garment_id": order["garments"][0]["id"], "version": version, "description": "White shirt pressed"},
    )
    second_edit = client.post(
        f"/api/v1/laundry/orders/{order['id']}/garments",
        headers=other,
        json={"garment_id": order["garments"][1]["id"], "version": version, "condition": "fading"},
    )
    assert first_edit.status_code == 200, first_edit.text
    assert second_edit.status_code == 409
    assert second_edit.json()["error"]["code"] == "order_conflict"
    session.rollback()
    kept = client.get(f"/api/v1/laundry/orders/{order['id']}", headers=other).json()
    assert kept["garments"][0]["description"] == "White shirt pressed" or any(
        row["description"] == "White shirt pressed" for row in kept["garments"]
    )
    assert all(row["condition"] != "fading" for row in kept["garments"])
    tag = order["tags"][0]
    reprinted = client.post(
        f"/api/v1/laundry/tags/{tag['id']}/reprint",
        headers=headers,
        json={"idempotency_key": "reprint-key-0001"},
    )
    assert reprinted.status_code == 200, reprinted.text
    assert reprinted.json()["id"] == tag["id"]
    assert len(client.get(f"/api/v1/laundry/orders/{order['id']}", headers=headers).json()["tags"]) == 2
    photo = client.post(
        f"/api/v1/laundry/orders/{order['id']}/photos",
        headers=headers,
        json={"mime": "image/jpeg", "content_base64": base64.b64encode(JPEG).decode()},
    )
    assert photo.status_code == 201, photo.text
    stored = client.get(
        f"/api/v1/laundry/orders/{order['id']}/photos/{photo.json()['id']}",
        headers=other,
    )
    assert stored.status_code == 200
    assert stored.content.startswith(JPEG[:3])
    local_id = str(uuid.uuid4())
    queued = {
        "id": local_id,
        "idempotency_key": local_id,
        "intake_store_id": str(store.id),
        "customer_id": str(customer.id),
        "order_type": "DROP_OFF",
        "instructions": "Hang the shirts",
        "garments": [{"service_id": shirt["id"], "quantity": 1, "description": "Offline shirt"}],
    }
    event = {
        "idempotency_key": local_id,
        "entity_type": "laundry_order",
        "operation": "upsert",
        "payload": queued,
        "occurred_at": "2026-11-21T09:00:00Z",
    }
    sync_headers = {"X-Api-Key": "test-api-key-value"}
    applied = client.post(
        "/api/v1/sync/push",
        headers=sync_headers,
        json={"device_id": "laundry-acceptance-01", "events": [event]},
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["results"] == [{"idempotency_key": local_id, "status": "applied"}]
    duplicate = client.post(
        "/api/v1/sync/push",
        headers=sync_headers,
        json={"device_id": "laundry-acceptance-01", "events": [event]},
    )
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["results"][0]["status"] == "duplicate"
    synced = client.get(f"/api/v1/laundry/orders/{local_id}", headers=headers)
    assert synced.status_code == 200, synced.text
    assert synced.json()["code"].startswith("LD-")
    assert synced.json()["instructions"] == "Hang the shirts"
    assert fold["id"]
