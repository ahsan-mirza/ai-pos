"""Shared setup for the wholesale tests: a branch, a cable with tier prices, a phone with IMEIs in stock,
and wholesale customers created through the portal API."""

import uuid

from app.services.identifiers import is_valid_imei

API_KEY = "test-api-key-value"
ADMIN_PASSWORD = "root-password-123"
CASHIER_ID = "00000000-0000-4000-8000-000000000002"
STORE = "00000000-0000-4000-8000-000000000001"
CABLE = "00000000-0000-4000-8000-000000000010"
PHONE = "00000000-0000-4000-8000-000000000012"


def imeis(count: int, prefix: str = "35693803564") -> list[str]:
    found: list[str] = []
    if count == 0:
        return found
    for body in range(10_000):
        stem = f"{prefix}{body:04d}"[:14]
        for digit in range(10):
            candidate = f"{stem}{digit}"
            if is_valid_imei(candidate) and candidate not in found:
                found.append(candidate)
                break
        if len(found) == count:
            return found
    raise AssertionError("Could not build IMEIs")


def device() -> dict[str, str]:
    return {"X-Api-Key": API_KEY}


def event(key: str, entity: str, payload: dict) -> dict:
    return {
        "idempotency_key": key,
        "entity_type": entity,
        "operation": "upsert",
        "payload": payload,
        "occurred_at": "2026-10-19T08:00:00Z",
    }


def push(client, events: list[dict]):
    return client.post("/api/v1/sync/push", headers=device(), json={"device_id": "register-1", "events": events})


def admin(client) -> tuple[dict[str, str], str]:
    response = client.post("/api/v1/auth/login-password", json={"username": "admin", "password": ADMIN_PASSWORD})
    assert response.status_code == 200, response.text
    body = response.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]["id"]


def seed(client, phone_units: int = 0) -> list[str]:
    events = [
        event("ws-store", "store", {"id": STORE, "code": "DT-01", "name": "Downtown", "currency": "USD"}),
        event(
            "ws-cable",
            "product",
            {
                "id": CABLE,
                "store_id": STORE,
                "sku": "ACC-CABLE-USBC",
                "barcode": "100000000001",
                "name": "USB-C Cable",
                "category": "Accessories",
                "price_cents": 1500,
                "currency": "USD",
                "is_serialized": False,
                "stock_quantity": 500,
            },
        ),
        event(
            "ws-phone",
            "product",
            {
                "id": PHONE,
                "store_id": STORE,
                "sku": "PHN-PIXEL-9",
                "barcode": "100000000003",
                "name": "Pixel 9",
                "category": "Phones",
                "price_cents": 79900,
                "currency": "USD",
                "is_serialized": True,
                "stock_quantity": 0,
            },
        ),
    ]
    values = imeis(phone_units)
    for index, value in enumerate(values):
        events.append(
            event(
                f"ws-imei-{index}",
                "serial_number",
                {
                    "id": str(uuid.uuid4()),
                    "product_id": PHONE,
                    "store_id": STORE,
                    "kind": "imei",
                    "value": value,
                    "status": "in_stock",
                },
            )
        )
    response = push(client, events)
    assert response.status_code == 200, response.text
    return values


def set_cable_tiers(client, headers: dict[str, str]) -> None:
    response = client.put(
        f"/api/v1/pricing/products/{CABLE}",
        headers=headers,
        json={
            "sellable_units": ["PIECE", "BOX_10"],
            "tiers": [
                {
                    "price_tier": "TIER_1",
                    "price_cents": 1200,
                    "min_order_quantity": 5,
                    "volume_discounts": [{"min_qty": 25, "price_cents": 1000}],
                }
            ],
        },
    )
    assert response.status_code == 200, response.text


def create_customer(client, headers: dict[str, str], **overrides) -> dict:
    body = {
        "name": "Ali Traders",
        "company_name": "Ali Traders LLC",
        "customer_type": "WHOLESALE",
        "price_tier": "TIER_1",
        "credit_limit_cents": 50_000,
        "payment_terms": "NET_30",
        "trn_vat_number": "100200300400003",
    }
    body.update(overrides)
    response = client.post("/api/v1/customers", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def line(
    product_id: str,
    quantity: int,
    unit: int,
    *,
    listed: int | None = None,
    unit_type: str = "PIECE",
    serial: str | None = None,
    override_by: str | None = None,
) -> dict:
    item = {
        "id": str(uuid.uuid4()),
        "product_id": product_id,
        "quantity": quantity,
        "unit_price_cents": unit,
        "tax_cents": 0,
        "line_total_cents": unit * quantity,
        "serial_value": serial,
        "serial_kind": "imei" if serial else None,
        "unit_type": unit_type,
        "list_price_cents": unit if listed is None else listed,
    }
    if override_by is not None:
        item["price_override"] = {"approved_by_id": override_by, "note": "Loyal customer"}
    return item


def sale(items: list[dict], **extra) -> dict:
    total = sum(item["line_total_cents"] for item in items)
    sale_id = str(uuid.uuid4())
    body = {
        "id": sale_id,
        "store_id": STORE,
        "cashier_id": CASHIER_ID,
        "currency": "USD",
        "payment_method": "cash",
        "subtotal_cents": total,
        "tax_cents": 0,
        "total_cents": total,
        "client_sale_id": sale_id,
        "items": items,
    }
    body.update(extra)
    return body
