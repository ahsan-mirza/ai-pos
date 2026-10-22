from test_inventory import (
    CABLE,
    DT,
    IMEIS,
    PHONE,
    STORE_MANAGER_ROLE,
    WH,
    admin,
    bearer,
    event,
    push,
    sale,
    seed,
)


def order_and_receive(client, headers, lines: list[dict], receive: list[dict]) -> dict:
    order = client.post(
        "/api/v1/inventory/purchase-orders",
        headers=headers,
        json={"supplier_name": "Volt Distribution", "destination_store_id": WH, "lines": lines},
    ).json()
    client.post(f"/api/v1/inventory/purchase-orders/{order['id']}/order", headers=headers)
    by_product = {line["product_id"]: line["id"] for line in order["lines"]}
    lines_in = [
        {key: value for key, value in item.items() if key != "product_id"}
        | {"purchase_order_line_id": by_product[item["product_id"]]}
        for item in receive
    ]
    response = client.post(
        f"/api/v1/inventory/purchase-orders/{order['id']}/receive", headers=headers, json={"lines": lines_in}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_sales_history_summarises_every_sale_of_the_product(client) -> None:
    seed(client)
    headers = admin(client)
    assert (
        push(
            client,
            [event("history-sale-1", "sale", sale(DT, CABLE, 3)), event("history-sale-2", "sale", sale(DT, CABLE, 1))],
        ).status_code
        == 200
    )

    body = client.get(f"/api/v1/products/{CABLE}/sales-history", headers=headers).json()
    assert body["units_sold"] == 4
    assert body["revenue_cents"] == 6000
    assert body["average_selling_price_cents"] == 1500
    assert body["sale_count"] == 2
    first = body["rows"][0]
    assert first["store_code"] == "DT-01"
    assert first["cashier_name"] == "Front Cashier"
    assert first["invoice"].startswith("DT-01-S-")

    limited = client.get(f"/api/v1/products/{CABLE}/sales-history", headers=headers, params={"limit": 1}).json()
    assert len(limited["rows"]) == 1
    assert limited["units_sold"] == 4
    assert client.get(f"/api/v1/products/{PHONE}/sales-history", headers=headers).json()["rows"] == []


def test_purchase_history_lists_receipts_and_open_lines(client) -> None:
    seed(client)
    headers = admin(client)
    order_and_receive(
        client,
        headers,
        [{"product_id": CABLE, "quantity_ordered": 20, "unit_cost_cents": 600}],
        [{"product_id": CABLE, "quantity": 20}],
    )
    order_and_receive(
        client,
        headers,
        [{"product_id": CABLE, "quantity_ordered": 10, "unit_cost_cents": 900}],
        [{"product_id": CABLE, "quantity": 10}],
    )
    client.post(
        "/api/v1/inventory/purchase-orders",
        headers=headers,
        json={
            "supplier_name": "Late Supplier",
            "destination_store_id": WH,
            "lines": [{"product_id": CABLE, "quantity_ordered": 5, "unit_cost_cents": 700}],
        },
    )

    body = client.get(f"/api/v1/products/{CABLE}/purchase-history", headers=headers).json()
    assert body["latest_unit_cost_cents"] == 900
    assert body["average_unit_cost_cents"] == 700
    assert body["units_received"] == 30
    assert body["total_spend_cents"] == 21000
    received = [row for row in body["rows"] if row["grn_number"] is not None]
    assert [row["unit_cost_cents"] for row in received] == [900, 600]
    pending = [row for row in body["rows"] if row["grn_number"] is None]
    assert [(row["supplier_name"], row["po_status"], row["total_cost_cents"]) for row in pending] == [
        ("Late Supplier", "draft", 3500)
    ]


def test_serials_show_last_four_and_match_exact_or_suffix(client) -> None:
    seed(client)
    headers = admin(client)
    order_and_receive(
        client,
        headers,
        [{"product_id": PHONE, "quantity_ordered": 2, "unit_cost_cents": 60000}],
        [
            {
                "product_id": PHONE,
                "quantity": 2,
                "serials": [{"kind": "imei", "value": IMEIS[0]}, {"kind": "imei", "value": IMEIS[1]}],
            }
        ],
    )
    assert push(client, [event("sell-phone", "sale", sale(WH, PHONE, 1, IMEIS[0]))]).status_code == 200

    body = client.get(f"/api/v1/products/{PHONE}/serials", headers=headers).json()
    assert body["total"] == 2
    assert body["status_counts"] == {"in_stock": 1, "sold": 1}
    assert IMEIS[0] not in str(body)
    sold = next(row for row in body["rows"] if row["status"] == "sold")
    assert sold["last4"] == IMEIS[0][-4:]
    assert sold["sale_invoice"] is not None and sold["store_code"] == "WH-01"

    exact = client.get(f"/api/v1/products/{PHONE}/serials", headers=headers, params={"q": IMEIS[1]}).json()
    assert [row["last4"] for row in exact["rows"]] == [IMEIS[1][-4:]]
    suffix = client.get(f"/api/v1/products/{PHONE}/serials", headers=headers, params={"q": IMEIS[0][-4:]}).json()
    assert [row["status"] for row in suffix["rows"]] == ["sold"]
    unknown = client.get(f"/api/v1/products/{PHONE}/serials", headers=headers, params={"q": "359999999999999"})
    assert unknown.json()["rows"] == []
    in_stock = client.get(f"/api/v1/products/{PHONE}/serials", headers=headers, params={"status": "in_stock"})
    assert [row["last4"] for row in in_stock.json()["rows"]] == [IMEIS[1][-4:]]


def test_movements_and_store_scope(client) -> None:
    seed(client)
    headers = admin(client)
    assert push(client, [event("history-sale-1", "sale", sale(DT, CABLE, 2))]).status_code == 200

    movements = client.get(f"/api/v1/products/{CABLE}/movements", headers=headers).json()
    assert [(m["movement_type"], m["quantity"]) for m in movements] == [("SALE_OUT", -2), ("AUDIT_ADJUSTMENT", 10)]
    missing = client.get("/api/v1/products/00000000-0000-4000-8000-0000000000ff/movements", headers=headers)
    assert missing.status_code == 404

    client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": "manager.wh",
            "email": "manager.wh@example.com",
            "full_name": "Warehouse Manager",
            "role_id": STORE_MANAGER_ROLE,
            "store_id": WH,
            "password": "manager-password-1",
            "has_portal_access": True,
        },
    )
    login = client.post(
        "/api/v1/auth/login-password", json={"username": "manager.wh", "password": "manager-password-1"}
    )
    manager = bearer(login.json()["access_token"])
    scoped = client.get(f"/api/v1/products/{CABLE}/sales-history", headers=manager).json()
    assert scoped["rows"] == [] and scoped["units_sold"] == 0
    other = client.get(f"/api/v1/products/{CABLE}/movements", headers=manager, params={"store_id": DT})
    assert other.status_code == 403
