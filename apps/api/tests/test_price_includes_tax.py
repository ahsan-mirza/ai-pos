"""Product prices either already include tax or have it added. The sale stores the mode it used."""

from app.services.tax import line_tax
from test_foundations import set_tax, taxed_line, taxed_sale
from wholesale_support import CABLE, STORE, admin, device, event, line, push, seed


def _patch(client, headers, product_id: str, **fields) -> dict:
    response = client.patch(f"/api/v1/products/{product_id}", headers=headers, json=fields)
    assert response.status_code == 200, response.text
    return response.json()


def test_existing_products_are_tax_exclusive_until_edited(client) -> None:
    seed(client)
    headers, _ = admin(client)
    product = client.get(f"/api/v1/products/{CABLE}", headers=device()).json()
    assert product["price_includes_tax"] is False
    saved = _patch(client, headers, CABLE, price_includes_tax=True)
    assert saved["price_includes_tax"] is True
    again = client.get(f"/api/v1/products/{CABLE}", headers=device()).json()
    assert again["price_includes_tax"] is True


def test_inclusive_and_exclusive_lines_share_one_sale(client) -> None:
    seed(client)
    headers, _ = admin(client)
    set_tax(client, headers)
    cable = client.get(f"/api/v1/products/{CABLE}", headers=headers).json()
    other = client.post(
        "/api/v1/inventory/products",
        headers=headers,
        json={
            "sku": "TAX-EXCL",
            "barcode": "200000000099",
            "name": "Exclusive item",
            "category_id": cable["category_id"],
            "price_cents": 10000,
            "price_includes_tax": False,
            "opening_store_id": STORE,
            "opening_quantity": 5,
        },
    )
    assert other.status_code == 201, other.text
    _patch(client, headers, CABLE, price_cents=10000, price_includes_tax=True)
    inclusive = taxed_line(10000, 1, inclusive=True)
    inclusive["product_id"] = CABLE
    exclusive = taxed_line(10000, 1, inclusive=False)
    exclusive["product_id"] = other.json()["id"]
    body = taxed_sale([inclusive, exclusive])
    assert (body["subtotal_cents"], body["tax_cents"], body["total_cents"]) == (19524, 976, 20500)
    response = push(client, [event("mixed-tax", "sale", body)])
    assert response.status_code == 200, response.text
    stored = client.get(f"/api/v1/sales/{body['id']}", headers=device()).json()
    by_product = {item["product_id"]: item for item in stored["items"]}
    assert by_product[CABLE]["price_includes_tax"] is True
    assert by_product[CABLE]["tax_cents"] == 476
    assert by_product[other.json()["id"]]["price_includes_tax"] is False
    assert by_product[other.json()["id"]]["tax_cents"] == 500

    _patch(client, headers, CABLE, price_includes_tax=False)
    again = client.get(f"/api/v1/sales/{body['id']}", headers=device()).json()
    assert {item["product_id"]: item["tax_cents"] for item in again["items"]} == {
        CABLE: 476,
        other.json()["id"]: 500,
    }
    assert next(item for item in again["items"] if item["product_id"] == CABLE)["price_includes_tax"] is True


def test_zero_and_exempt_prices_do_not_gain_tax(client) -> None:
    seed(client)
    headers, _ = admin(client)
    set_tax(client, headers)
    for category in ("ZERO", "EXEMPT"):
        _patch(client, headers, CABLE, price_includes_tax=True, tax_category=category)
        body = taxed_sale([taxed_line(10000, 1, inclusive=True, rate=0)])
        assert body["tax_cents"] == 0 and body["total_cents"] == 10000
        response = push(client, [event(f"no-tax-{category}", "sale", body)])
        assert response.status_code == 200, response.text


def test_discount_is_removed_before_tax_is_extracted(client) -> None:
    seed(client)
    headers, admin_id = admin(client)
    set_tax(client, headers)
    _patch(client, headers, CABLE, price_cents=10000, price_includes_tax=True)
    priced = line_tax(9000, 1, 500, inclusive=True)
    item = line(CABLE, 1, 10000)
    item.update(
        manual_discount_cents=1000,
        discount_reason="staff",
        discount_override={"approved_by_id": admin_id, "note": "VIP"},
        tax_cents=priced.tax_cents,
        line_total_cents=priced.line_total_cents,
    )
    body = taxed_sale([item])
    response = push(client, [event("inclusive-discount", "sale", body)])
    assert response.status_code == 200, response.text
    stored = client.get(f"/api/v1/sales/{body['id']}", headers=device()).json()
    assert stored["items"][0]["tax_cents"] == priced.tax_cents
    assert stored["total_cents"] == priced.line_total_cents
