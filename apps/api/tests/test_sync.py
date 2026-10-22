import uuid

from app.services.identifiers import is_valid_imei

API_KEY = "test-api-key-value"
STORE_ID = "00000000-0000-4000-8000-000000000001"
PRODUCT_ID = "00000000-0000-4000-8000-000000000010"
CASHIER_ID = "00000000-0000-4000-8000-000000000002"


def headers() -> dict[str, str]:
    return {"X-Api-Key": API_KEY}


def event(key: str, entity: str, payload: dict) -> dict:
    return {
        "idempotency_key": key,
        "entity_type": entity,
        "operation": "upsert",
        "payload": payload,
        "occurred_at": "2026-10-19T08:00:00Z",
    }


def push(client, events: list[dict], device: str = "device-1"):
    return client.post("/api/v1/sync/push", headers=headers(), json={"device_id": device, "events": events})


def store_payload() -> dict:
    return {"id": STORE_ID, "code": "DT-01", "name": "Downtown Flagship", "currency": "USD"}


def product_payload(**overrides) -> dict:
    payload = {
        "id": PRODUCT_ID,
        "store_id": STORE_ID,
        "sku": "ACC-CABLE-USBC",
        "barcode": "100000000001",
        "name": "USB-C Cable",
        "category": "Accessories",
        "price_cents": 1500,
        "currency": "USD",
        "is_serialized": False,
        "stock_quantity": 10,
    }
    payload.update(overrides)
    return payload


def seed_store_and_product(client) -> None:
    response = push(
        client,
        [
            event("store-seed-key", "store", store_payload()),
            event("product-seed-key", "product", product_payload()),
        ],
    )
    assert response.status_code == 200, response.text


def test_health(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_sync_requires_api_key(client) -> None:
    response = client.post("/api/v1/sync/push", json={"device_id": "device-1", "events": []})
    assert response.status_code == 401


def test_duplicate_event_does_not_apply_twice(client) -> None:
    seed_store_and_product(client)
    sale = sale_payload(quantity=2)
    first = push(client, [event("sale-key-1", "sale", sale)])
    assert first.status_code == 200, first.text
    assert first.json()["results"] == [{"idempotency_key": "sale-key-1", "status": "applied"}]

    second = push(client, [event("sale-key-1", "sale", sale)])
    assert second.status_code == 200, second.text
    assert second.json()["results"] == [{"idempotency_key": "sale-key-1", "status": "duplicate"}]

    product = client.get(f"/api/v1/products/{PRODUCT_ID}", headers=headers())
    assert product.json()["stock_quantity"] == 8


def test_cash_checkout_decrements_stock_once(client) -> None:
    seed_store_and_product(client)
    sale = sale_payload(quantity=3, payment_method="cash", tax=225)
    batch = [
        event("cash-store-key", "store", store_payload()),
        event("cash-product-key", "product", product_payload(stock_quantity=999)),
        event("cash-sale-key", "sale", sale),
    ]

    first = push(client, batch)
    assert first.status_code == 200, first.text
    assert [item["status"] for item in first.json()["results"]] == ["applied", "applied", "applied"]

    replay = push(client, batch)
    assert replay.status_code == 200, replay.text
    assert [item["status"] for item in replay.json()["results"]] == ["duplicate", "duplicate", "duplicate"]

    product = client.get(f"/api/v1/products/{PRODUCT_ID}", headers=headers()).json()
    assert product["stock_quantity"] == 7

    sales = client.get("/api/v1/sales", headers=headers()).json()
    assert len(sales) == 1
    assert sales[0]["payment_method"] == "cash"
    assert sales[0]["total_cents"] == 1500 * 3 + 225
    assert sales[0]["items"][0]["quantity"] == 3


def test_idempotency_key_conflict(client) -> None:
    seed_store_and_product(client)
    changed = product_payload(name="Braided USB-C Cable")
    response = push(client, [event("product-seed-key", "product", changed)])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "idempotency_conflict"
    product = client.get(f"/api/v1/products/{PRODUCT_ID}", headers=headers())
    assert product.json()["name"] == "USB-C Cable"


def test_batch_rolls_back_when_one_event_fails(client) -> None:
    seed_store_and_product(client)
    missing = product_payload(
        id=str(uuid.uuid4()),
        sku="MISSING-STOCK",
        barcode="100000000099",
        stock_quantity=1,
    )
    sale = sale_payload(product_id=missing["id"], quantity=4, unit_price_cents=1000)
    response = push(
        client,
        [
            event("new-product-key", "product", missing),
            event("bad-sale-key", "sale", sale),
        ],
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "sync_rejected"
    products = client.get("/api/v1/products", headers=headers())
    barcodes = {item["barcode"] for item in products.json()}
    assert "100000000099" not in barcodes


def test_serialized_sale_validates_imei(client) -> None:
    seed_store_and_product(client)
    phone_id = str(uuid.uuid4())
    phone = product_payload(
        id=phone_id,
        sku="PHN-PIXEL-9",
        barcode="100000000003",
        name="Pixel 9",
        category="Phones",
        price_cents=79900,
        is_serialized=True,
        stock_quantity=0,
    )
    imei = next(f"49015420323751{digit}" for digit in range(10) if is_valid_imei(f"49015420323751{digit}"))
    created = push(client, [event("phone-key", "product", phone)])
    assert created.status_code == 200, created.text

    rejected = push(
        client,
        [
            event(
                "bad-imei-sale",
                "sale",
                sale_payload(
                    product_id=phone_id,
                    quantity=1,
                    unit_price_cents=79900,
                    serial_value="490154203237519",
                    serial_kind="imei",
                ),
            )
        ],
    )
    assert rejected.status_code == 422

    accepted = push(
        client,
        [
            event(
                "good-imei-sale",
                "sale",
                sale_payload(
                    product_id=phone_id,
                    quantity=1,
                    unit_price_cents=79900,
                    serial_value=imei,
                    serial_kind="imei",
                ),
            )
        ],
    )
    assert accepted.status_code == 200, accepted.text
    sale_id = accepted.json()["results"][0]["idempotency_key"]
    assert sale_id == "good-imei-sale"
    sales = client.get("/api/v1/sales", headers=headers())
    values = [item["serial_value"] for sale in sales.json() for item in sale["items"]]
    assert imei in values


def sale_payload(
    *,
    quantity: int = 1,
    unit_price_cents: int = 1500,
    product_id: str = PRODUCT_ID,
    serial_value: str | None = None,
    serial_kind: str | None = None,
    payment_method: str = "card",
    tax: int = 0,
) -> dict:
    line_total = unit_price_cents * quantity + tax
    return {
        "id": str(uuid.uuid4()),
        "store_id": STORE_ID,
        "cashier_id": CASHIER_ID,
        "currency": "USD",
        "payment_method": payment_method,
        "subtotal_cents": unit_price_cents * quantity,
        "tax_cents": tax,
        "total_cents": line_total,
        "client_sale_id": str(uuid.uuid4()),
        "items": [
            {
                "id": str(uuid.uuid4()),
                "product_id": product_id,
                "quantity": quantity,
                "unit_price_cents": unit_price_cents,
                "tax_cents": tax,
                "line_total_cents": line_total,
                "serial_value": serial_value,
                "serial_kind": serial_kind,
            }
        ],
    }
