import uuid

from tests.test_inventory import CABLE, DT, PHONE, WH, admin, bearer, push, row, seed, stock

STORE_MANAGER_ROLE = "00000000-0000-4000-8000-0000000000a2"
IMEIS = ["490154203237518", "356938035643809", "353918053131210"]


def adjustment(product_id: str, store_id: str, mode: str, quantity: int, reason: str, **extra) -> dict:
    return {
        "adjustment_id": str(uuid.uuid4()),
        "product_id": product_id,
        "store_id": store_id,
        "mode": mode,
        "quantity": quantity,
        "reason_code": reason,
        "note": "Found during the annual floor audit",
        **extra,
    }


def adjust(client, headers, body: dict):
    return client.post("/api/v1/inventory/adjust", headers=headers, json=body)


def portal_user(client, admin_headers, username: str, role_id: str, store_id: str | None) -> dict[str, str]:
    created = client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "username": username,
            "email": f"{username}@example.com",
            "full_name": username.title(),
            "role_id": role_id,
            "store_id": store_id,
            "password": "portal-password-1",
            "has_portal_access": True,
        },
    )
    assert created.status_code == 201, created.text
    token = client.post(
        "/api/v1/auth/login-password", json={"username": username, "password": "portal-password-1"}
    ).json()["access_token"]
    return bearer(token)


def test_add_remove_and_set_exact_count_write_reasoned_ledger_rows(client) -> None:
    seed(client)
    headers = admin(client)

    added = adjust(client, headers, adjustment(CABLE, DT, "add", 5, "SUPPLIER_SAMPLE_IN"))
    assert added.status_code == 201, added.text
    assert added.json()["quantity_change"] == 5
    assert added.json()["row"]["quantity_on_hand"] == 15

    removed = adjust(client, headers, adjustment(CABLE, DT, "remove", 3, "STOLEN_SHRINKAGE"))
    assert removed.json()["row"]["quantity_on_hand"] == 12
    assert removed.json()["movements"][0]["movement_type"] == "DAMAGE_SHRINKAGE"

    counted = adjust(client, headers, adjustment(CABLE, DT, "set", 9, "PHYSICAL_COUNT_AUDIT"))
    assert counted.json()["quantity_change"] == -3
    assert counted.json()["row"]["quantity_on_hand"] == 9

    ledger = client.get(
        "/api/v1/inventory/movements", headers=headers, params={"product_id": CABLE, "store_id": DT}
    ).json()
    manual = [movement for movement in ledger if movement["reference_type"] == "manual_adjustment"]
    assert [(m["movement_type"], m["quantity"], m["reason_code"]) for m in manual] == [
        ("AUDIT_ADJUSTMENT", -3, "PHYSICAL_COUNT_AUDIT"),
        ("DAMAGE_SHRINKAGE", -3, "STOLEN_SHRINKAGE"),
        ("AUDIT_ADJUSTMENT", 5, "SUPPLIER_SAMPLE_IN"),
    ]
    assert all(m["note"] == "Found during the annual floor audit" and m["user_name"] == "Root Admin" for m in manual)


def test_validation_rules(client) -> None:
    seed(client)
    headers = admin(client)
    short_note = adjustment(CABLE, DT, "add", 1, "OTHER", note="too short")
    assert adjust(client, headers, short_note).status_code == 422
    assert adjust(client, headers, adjustment(CABLE, DT, "add", 1, "DAMAGED_OR_EXPIRED")).status_code == 422
    assert adjust(client, headers, adjustment(CABLE, DT, "remove", 1, "SUPPLIER_SAMPLE_IN")).status_code == 422
    no_change = adjust(client, headers, adjustment(CABLE, DT, "set", 10, "PHYSICAL_COUNT_AUDIT"))
    assert no_change.status_code == 422
    assert no_change.json()["error"]["code"] == "no_change"
    assert adjust(client, headers, adjustment(CABLE, DT, "add", 0, "OTHER")).status_code == 422


def test_replaying_an_adjustment_does_not_apply_twice(client) -> None:
    seed(client)
    headers = admin(client)
    body = adjustment(CABLE, DT, "add", 4, "INCORRECT_ENTRY_CORRECTION")
    first = adjust(client, headers, body)
    replay = adjust(client, headers, body)
    assert (first.status_code, replay.status_code) == (201, 200)
    assert replay.json()["duplicate"] is True
    assert replay.json()["row"]["quantity_on_hand"] == 14


def test_permission_and_store_scope(client, session) -> None:
    seed(client)
    headers = admin(client)
    clerk_role = client.post(
        "/api/v1/roles",
        headers=headers,
        json={"name": "Stock Viewer", "permissions": ["portal:access", "portal:inventory_manage"]},
    ).json()
    clerk = portal_user(client, headers, "clerk", clerk_role["id"], DT)
    forbidden = adjust(client, clerk, adjustment(CABLE, DT, "add", 1, "PHYSICAL_COUNT_AUDIT"))
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["details"]["missing"] == ["inventory:adjust_stock"]

    manager = portal_user(client, headers, "manager", STORE_MANAGER_ROLE, DT)
    assert adjust(client, manager, adjustment(CABLE, DT, "add", 1, "PHYSICAL_COUNT_AUDIT")).status_code == 201
    assert adjust(client, manager, adjustment(CABLE, WH, "add", 1, "PHYSICAL_COUNT_AUDIT")).status_code == 403

    cashier = client.post(
        "/api/v1/auth/login-pin",
        json={"username": "cashier", "pin": "1357"},
        headers={"X-Api-Key": "test-api-key-value"},
    ).json()["access_token"]
    assert adjust(client, bearer(cashier), adjustment(CABLE, DT, "add", 1, "OTHER")).status_code == 403
    device = client.post(
        "/api/v1/inventory/adjust",
        headers={"X-Api-Key": "test-api-key-value"},
        json=adjustment(CABLE, DT, "add", 1, "OTHER"),
    )
    assert device.status_code == 403


def test_serialized_units_are_scanned_in_and_written_off_by_id(client) -> None:
    seed(client)
    headers = admin(client)
    missing = adjust(client, headers, adjustment(PHONE, DT, "add", 2, "PHYSICAL_COUNT_AUDIT"))
    assert missing.status_code == 422
    scanned = adjust(
        client,
        headers,
        adjustment(
            PHONE,
            DT,
            "add",
            2,
            "PHYSICAL_COUNT_AUDIT",
            new_serials=[{"kind": "imei", "value": IMEIS[0]}, {"kind": "imei", "value": IMEIS[1]}],
        ),
    )
    assert scanned.status_code == 201, scanned.text
    assert row(stock(client, headers, store_id=DT), "PHN-PIXEL-9")["quantity_on_hand"] == 2

    units = client.get(
        "/api/v1/inventory/serials", headers=headers, params={"product_id": PHONE, "store_id": DT}
    ).json()
    assert sorted(unit["value"] for unit in units) == sorted(IMEIS[:2])
    damaged = next(unit for unit in units if unit["value"] == IMEIS[0])

    written_off = adjust(
        client,
        headers,
        adjustment(PHONE, DT, "remove", 1, "DAMAGED_OR_EXPIRED", remove_serial_ids=[damaged["id"]]),
    )
    assert written_off.status_code == 201, written_off.text
    assert written_off.json()["row"]["quantity_on_hand"] == 1
    trace = client.get("/api/v1/inventory/serials/trace", headers=headers, params={"value": IMEIS[0]}).json()
    assert trace["location"]["status"] == "defective"

    other = next(unit for unit in units if unit["value"] == IMEIS[1])
    counted = adjust(
        client,
        headers,
        adjustment(PHONE, DT, "set", 0, "STOLEN_SHRINKAGE", remove_serial_ids=[other["id"]]),
    )
    assert counted.json()["row"]["quantity_on_hand"] == 0
    trace = client.get("/api/v1/inventory/serials/trace", headers=headers, params={"value": IMEIS[1]}).json()
    assert trace["location"]["status"] == "scrapped"

    sold = push(
        client,
        [
            {
                "idempotency_key": "sale-scrapped-unit",
                "entity_type": "sale",
                "operation": "upsert",
                "payload": {
                    "id": str(uuid.uuid4()),
                    "store_id": DT,
                    "cashier_id": "00000000-0000-4000-8000-000000000002",
                    "currency": "USD",
                    "payment_method": "cash",
                    "subtotal_cents": 79900,
                    "tax_cents": 0,
                    "total_cents": 79900,
                    "client_sale_id": str(uuid.uuid4()),
                    "items": [
                        {
                            "id": str(uuid.uuid4()),
                            "product_id": PHONE,
                            "quantity": 1,
                            "unit_price_cents": 79900,
                            "tax_cents": 0,
                            "line_total_cents": 79900,
                            "serial_value": IMEIS[1],
                            "serial_kind": "imei",
                        }
                    ],
                },
                "occurred_at": "2026-10-19T08:00:00Z",
            }
        ],
    )
    assert sold.status_code == 422
