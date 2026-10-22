import uuid

API_KEY = "test-api-key-value"
STORE_ID = "00000000-0000-4000-8000-000000000001"
CASHIER_ID = "00000000-0000-4000-8000-000000000002"
PIXEL_ID = "00000000-0000-4000-8000-000000000012"
IMEI = "490154203237518"


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


def product(product_id: str, sku: str, barcode: str, name: str, category: str, **extra) -> dict:
    return {
        "id": product_id,
        "store_id": STORE_ID,
        "sku": sku,
        "barcode": barcode,
        "name": name,
        "category": category,
        "price_cents": 1000,
        "currency": "USD",
        "is_serialized": False,
        "stock_quantity": 5,
        **extra,
    }


def seed(client) -> None:
    events = [
        event("search-store", "store", {"id": STORE_ID, "code": "DT-01", "name": "Downtown", "currency": "USD"}),
        event(
            "search-cable",
            "product",
            product(
                "00000000-0000-4000-8000-000000000010",
                "ACC-CABLE-USBC",
                "100000000001",
                "USB-C Cable",
                "Accessories",
                brand="Volt",
                model_number="VC-USBC-1M",
            ),
        ),
        event(
            "search-case",
            "product",
            product(
                "00000000-0000-4000-8000-000000000011",
                "ACC-CASE-SLIM",
                "100000000002",
                "Slim Silicone Case",
                "Accessories",
                brand="Shield",
            ),
        ),
        event(
            "search-pixel",
            "product",
            product(
                PIXEL_ID,
                "PHN-PIXEL-9",
                "100000000003",
                "Pixel 9",
                "Phones",
                brand="Google",
                model_number="GA05843-US",
                is_serialized=True,
                stock_quantity=0,
            ),
        ),
    ]
    response = client.post("/api/v1/sync/push", headers=headers(), json={"device_id": "seed", "events": events})
    assert response.status_code == 200, response.text


def search(client, q: str) -> list[dict]:
    response = client.get("/api/v1/products/search", headers=headers(), params={"q": q})
    assert response.status_code == 200, response.text
    return response.json()


def names(hits: list[dict]) -> list[str]:
    return [hit["product"]["name"] for hit in hits]


def test_search_requires_credentials(client) -> None:
    assert client.get("/api/v1/products/search", params={"q": "pixel"}).status_code == 401


def test_name_is_case_insensitive_and_partial(client) -> None:
    seed(client)
    assert names(search(client, "PIX")) == ["Pixel 9"]
    assert names(search(client, "silicone")) == ["Slim Silicone Case"]


def test_tokens_match_across_fields(client) -> None:
    seed(client)
    assert names(search(client, "google pixel")) == ["Pixel 9"]
    assert names(search(client, "accessories volt")) == ["USB-C Cable"]
    assert names(search(client, "phones shield")) == []


def test_model_sku_and_category(client) -> None:
    seed(client)
    assert names(search(client, "ga05843")) == ["Pixel 9"]
    assert names(search(client, "GA05843US")) == ["Pixel 9"]
    assert names(search(client, "acc-case")) == ["Slim Silicone Case"]
    assert sorted(names(search(client, "accessories"))) == ["Slim Silicone Case", "USB-C Cable"]


def test_exact_barcode_ranks_first(client) -> None:
    seed(client)
    hits = search(client, "100000000003")
    assert names(hits) == ["Pixel 9"]
    assert hits[0]["match"] == "exact"
    assert len(search(client, "10000000000")) == 3


def test_like_wildcards_are_literal(client) -> None:
    seed(client)
    assert search(client, "%") == []
    assert search(client, "_") == []


def test_imei_finds_parent_product(client) -> None:
    seed(client)
    tax = 0
    sale = {
        "id": str(uuid.uuid4()),
        "store_id": STORE_ID,
        "cashier_id": CASHIER_ID,
        "currency": "USD",
        "payment_method": "cash",
        "subtotal_cents": 1000,
        "tax_cents": tax,
        "total_cents": 1000,
        "client_sale_id": str(uuid.uuid4()),
        "items": [
            {
                "id": str(uuid.uuid4()),
                "product_id": PIXEL_ID,
                "quantity": 1,
                "unit_price_cents": 1000,
                "tax_cents": tax,
                "line_total_cents": 1000,
                "serial_value": IMEI,
                "serial_kind": "imei",
            }
        ],
    }
    pushed = client.post(
        "/api/v1/sync/push",
        headers=headers(),
        json={"device_id": "register", "events": [event("search-sale", "sale", sale)]},
    )
    assert pushed.status_code == 200, pushed.text

    hits = search(client, IMEI)
    assert names(hits) == ["Pixel 9"]
    assert hits[0]["match"] == "identifier"
    assert hits[0]["serial_kind"] == "imei"
    assert hits[0]["serial_status"] == "sold"
    assert search(client, IMEI[:-1]) == []


def test_product_upsert_without_new_fields_keeps_them(client) -> None:
    seed(client)
    legacy = product(PIXEL_ID, "PHN-PIXEL-9", "100000000003", "Pixel 9", "Phones", is_serialized=True, stock_quantity=0)
    response = client.post(
        "/api/v1/sync/push",
        headers=headers(),
        json={"device_id": "old-register", "events": [event("legacy-pixel", "product", legacy)]},
    )
    assert response.status_code == 200, response.text
    pixel = client.get(f"/api/v1/products/{PIXEL_ID}", headers=headers()).json()
    assert pixel["brand"] == "Google"
    assert pixel["model_number"] == "GA05843-US"
