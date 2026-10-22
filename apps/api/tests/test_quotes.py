import uuid
from datetime import UTC, datetime, timedelta

from app.models.sale import Sale
from wholesale_support import (
    CABLE,
    CASHIER_ID,
    PHONE,
    STORE,
    admin,
    create_customer,
    device,
    event,
    line,
    push,
    sale,
    seed,
    set_cable_tiers,
)


def quote_body(items: list[dict], **extra) -> dict:
    total = sum(item["line_total_cents"] for item in items)
    body = {
        "id": str(uuid.uuid4()),
        "store_id": STORE,
        "cashier_id": CASHIER_ID,
        "currency": "USD",
        "sale_type": "WHOLESALE",
        "valid_days": 7,
        "subtotal_cents": total,
        "tax_cents": 0,
        "total_cents": total,
        "items": items,
    }
    body.update(extra)
    return body


def reserved(client, product_id: str) -> int:
    return client.get(f"/api/v1/products/{product_id}", headers=device()).json()["quantity_reserved"]


def test_quote_reserves_and_converts_with_auto_imeis(client) -> None:
    values = seed(client, phone_units=3)
    headers, _ = admin(client)
    customer = create_customer(client, headers, credit_limit_cents=1_000_000)
    body = quote_body(
        [line(CABLE, 40, 1500), line(PHONE, 2, 79900)],
        customer_id=customer["id"],
        sale_type="RETAIL",
    )
    created = client.post("/api/v1/quotes", headers=device(), json=body)
    assert created.status_code == 201, created.text
    assert created.json()["quote_status"] == "OPEN"
    assert created.json()["number"] == "DT-01-QUO-000001"
    assert reserved(client, CABLE) == 40
    assert reserved(client, PHONE) == 2

    listing = client.get("/api/v1/quotes", headers=headers).json()
    assert listing["stats"]["open_count"] == 1
    assert client.get("/api/v1/sales", headers=device()).json() == []

    converted = client.post(
        f"/api/v1/quotes/{body['id']}/convert",
        headers=headers,
        json={
            "payment_method": "on_account",
            "tenders": [
                {"method": "transfer", "amount_cents": 50_000, "reference": "CHQ-12"},
                {"method": "on_account", "amount_cents": body["total_cents"] - 50_000},
            ],
        },
    )
    assert converted.status_code == 200, converted.text
    result = converted.json()
    assert result["quote_status"] == "CONVERTED"
    assert reserved(client, CABLE) == 0

    sale_out = client.get(f"/api/v1/sales/{result['converted_sale_id']}", headers=device()).json()
    phone_lines = [item for item in sale_out["items"] if item["product_id"] == PHONE]
    assert len(phone_lines) == 2
    assert {item["serial_value"] for item in phone_lines} <= set(values)
    assert sale_out["payment_status"] == "PARTIAL"

    stats = client.get("/api/v1/quotes", headers=headers).json()["stats"]
    assert stats["converted_count"] == 1 and stats["conversion_rate_bps"] == 10_000


def test_quoted_imei_cannot_be_sold_elsewhere(client) -> None:
    values = seed(client, phone_units=2)
    headers, _ = admin(client)
    body = quote_body([line(PHONE, 1, 79900, serial=values[0])], sale_type="RETAIL")
    assert client.post("/api/v1/quotes", headers=device(), json=body).status_code == 201

    blocked = push(client, [event("quote-held", "sale", sale([line(PHONE, 1, 79900, serial=values[0])]))])
    assert blocked.status_code == 422
    assert "reserved on quote" in blocked.json()["error"]["message"]

    free = client.get("/api/v1/inventory/register-serials", headers=device(), params={"store_id": STORE}).json()
    assert [item["value"] for item in free] == [values[1]]

    cancelled = client.post(f"/api/v1/quotes/{body['id']}/cancel", headers=headers)
    assert cancelled.status_code == 200 and cancelled.json()["quote_status"] == "CANCELLED"
    sold = push(client, [event("quote-released", "sale", sale([line(PHONE, 1, 79900, serial=values[0])]))])
    assert sold.status_code == 200, sold.text


def test_quote_needs_available_stock_and_blocks_sales(client) -> None:
    seed(client)
    too_many = quote_body([line(CABLE, 600, 1500)], sale_type="RETAIL")
    rejected = client.post("/api/v1/quotes", headers=device(), json=too_many)
    assert rejected.status_code == 422

    held = quote_body([line(CABLE, 450, 1500)], sale_type="RETAIL")
    assert client.post("/api/v1/quotes", headers=device(), json=held).status_code == 201
    short = push(client, [event("quote-short", "sale", sale([line(CABLE, 60, 1500)]))])
    assert short.status_code == 422


def test_expired_quote_releases_stock(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    body = quote_body([line(CABLE, 10, 1500)], sale_type="RETAIL")
    assert client.post("/api/v1/quotes", headers=device(), json=body).status_code == 201
    row = session.get(Sale, uuid.UUID(body["id"]))
    row.quote_expiry_date = datetime.now(UTC) - timedelta(minutes=1)
    session.commit()

    detail = client.get(f"/api/v1/quotes/{body['id']}", headers=headers).json()
    assert detail["quote_status"] == "EXPIRED"
    assert reserved(client, CABLE) == 0
    convert = client.post(f"/api/v1/quotes/{body['id']}/convert", headers=headers, json={"payment_method": "cash"})
    assert convert.status_code == 422


def test_quote_pdf(client) -> None:
    seed(client)
    headers, _ = admin(client)
    set_cable_tiers(client, headers)
    customer = create_customer(client, headers)
    body = quote_body([line(CABLE, 30, 1000, unit_type="BOX_10")], customer_id=customer["id"])
    assert client.post("/api/v1/quotes", headers=device(), json=body).status_code == 201
    pdf = client.get(f"/api/v1/quotes/{body['id']}/pdf", headers=device())
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
