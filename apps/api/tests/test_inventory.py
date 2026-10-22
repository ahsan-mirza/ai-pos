import uuid

API_KEY = "test-api-key-value"
ADMIN_PASSWORD = "root-password-123"
CASHIER_ID = "00000000-0000-4000-8000-000000000002"
STORE_MANAGER_ROLE = "00000000-0000-4000-8000-0000000000a2"
DT = "00000000-0000-4000-8000-000000000001"
WH = "00000000-0000-4000-8000-000000000005"
SHJ = "00000000-0000-4000-8000-000000000006"
CABLE = "00000000-0000-4000-8000-000000000010"
PHONE = "00000000-0000-4000-8000-000000000012"
IMEIS = ["490154203237518", "356938035643809", "353918053131210"]


def device() -> dict[str, str]:
    return {"X-Api-Key": API_KEY}


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


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


def admin(client) -> dict[str, str]:
    response = client.post("/api/v1/auth/login-password", json={"username": "admin", "password": ADMIN_PASSWORD})
    assert response.status_code == 200, response.text
    return bearer(response.json()["access_token"])


def seed(client) -> None:
    stores = [
        event(f"store-{code}", "store", {"id": sid, "code": code, "name": code, "currency": "USD", **extra})
        for sid, code, extra in (
            (DT, "DT-01", {}),
            (WH, "WH-01", {"is_warehouse": True}),
            (SHJ, "SHJ-02", {}),
        )
    ]
    products = [
        event(
            "product-cable",
            "product",
            {
                "id": CABLE,
                "store_id": DT,
                "sku": "ACC-CABLE-USBC",
                "barcode": "100000000001",
                "name": "USB-C Cable",
                "category": "Accessories",
                "sub_category": "Cables",
                "price_cents": 1500,
                "currency": "USD",
                "is_serialized": False,
                "stock_quantity": 10,
            },
        ),
        event(
            "product-phone",
            "product",
            {
                "id": PHONE,
                "store_id": WH,
                "sku": "PHN-PIXEL-9",
                "barcode": "100000000003",
                "name": "Pixel 9",
                "category": "Phones",
                "sub_category": "Smartphones",
                "price_cents": 79900,
                "currency": "USD",
                "is_serialized": True,
                "stock_quantity": 0,
            },
        ),
    ]
    response = push(client, stores + products)
    assert response.status_code == 200, response.text


def stock(client, headers: dict[str, str], **params) -> dict:
    response = client.get("/api/v1/inventory/stock", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def row(summary: dict, sku: str) -> dict:
    return next(item for item in summary["rows"] if item["sku"] == sku)


def sale(store_id: str, product_id: str, quantity: int, serial: str | None = None) -> dict:
    unit = 1500 if product_id == CABLE else 79900
    return {
        "id": str(uuid.uuid4()),
        "store_id": store_id,
        "cashier_id": CASHIER_ID,
        "currency": "USD",
        "payment_method": "cash",
        "subtotal_cents": unit * quantity,
        "tax_cents": 0,
        "total_cents": unit * quantity,
        "client_sale_id": str(uuid.uuid4()),
        "items": [
            {
                "id": str(uuid.uuid4()),
                "product_id": product_id,
                "quantity": quantity,
                "unit_price_cents": unit,
                "tax_cents": 0,
                "line_total_cents": unit * quantity,
                "serial_value": serial,
                "serial_kind": "imei" if serial else None,
            }
        ],
    }


def test_categories_are_created_from_sync_and_filterable(client) -> None:
    seed(client)
    headers = admin(client)
    categories = client.get("/api/v1/categories", headers=headers).json()
    names = {item["name"]: [sub["name"] for sub in item["sub_categories"]] for item in categories}
    assert names == {"Accessories": ["Cables"], "Phones": ["Smartphones"]}

    phones = next(item for item in categories if item["name"] == "Phones")
    filtered = stock(client, headers, category_id=phones["id"])
    assert [item["sku"] for item in filtered["rows"]] == ["PHN-PIXEL-9"]
    smart = phones["sub_categories"][0]["id"]
    assert [item["sku"] for item in stock(client, headers, sub_category_id=smart)["rows"]] == ["PHN-PIXEL-9"]


def test_category_crud_and_rename_propagates(client) -> None:
    headers = admin(client)
    created = client.post("/api/v1/categories", headers=headers, json={"name": "Computers"})
    assert created.status_code == 201, created.text
    category = created.json()
    assert category["code"] == "COMPUTERS"
    with_sub = client.post(
        f"/api/v1/categories/{category['id']}/sub-categories", headers=headers, json={"name": "Gaming PCs"}
    ).json()
    assert [sub["name"] for sub in with_sub["sub_categories"]] == ["Gaming PCs"]
    duplicate = client.post("/api/v1/categories", headers=headers, json={"name": "computers"})
    assert duplicate.status_code == 409

    seed(client)
    accessories = next(
        c for c in client.get("/api/v1/categories", headers=headers).json() if c["name"] == "Accessories"
    )
    renamed = client.patch(f"/api/v1/categories/{accessories['id']}", headers=headers, json={"name": "Add-ons"})
    assert renamed.status_code == 200
    product = client.get(f"/api/v1/products/{CABLE}", headers=headers).json()
    assert product["category"] == "Add-ons"
    assert client.delete(f"/api/v1/categories/{accessories['id']}", headers=headers).status_code == 409


def test_sales_decrement_only_the_selling_branch(client) -> None:
    seed(client)
    headers = admin(client)
    sold = push(client, [event("sale-downtown", "sale", sale(DT, CABLE, 3))])
    assert sold.status_code == 200, sold.text
    shortfall = push(client, [event("sale-shj", "sale", sale(SHJ, CABLE, 1))])
    assert shortfall.status_code == 422
    assert shortfall.json()["error"]["message"] == "Insufficient stock."

    assert row(stock(client, headers, store_id=DT), "ACC-CABLE-USBC")["quantity_on_hand"] == 7
    assert row(stock(client, headers, store_id=SHJ), "ACC-CABLE-USBC")["quantity_on_hand"] == 0
    movements = client.get("/api/v1/inventory/movements", headers=headers, params={"product_id": CABLE}).json()
    assert [(m["movement_type"], m["quantity"], m["quantity_after"]) for m in movements] == [
        ("SALE_OUT", -3, 7),
        ("AUDIT_ADJUSTMENT", 10, 10),
    ]


def test_purchase_order_lifecycle_receives_into_destination(client, session) -> None:
    seed(client)
    headers = admin(client)
    created = client.post(
        "/api/v1/inventory/purchase-orders",
        headers=headers,
        json={
            "supplier_name": "Volt Distribution",
            "destination_store_id": WH,
            "lines": [
                {"product_id": CABLE, "quantity_ordered": 50, "unit_cost_cents": 600},
                {"product_id": PHONE, "quantity_ordered": 2, "unit_cost_cents": 60000},
            ],
        },
    )
    assert created.status_code == 201, created.text
    order = created.json()
    assert order["status"] == "draft"
    lines = {line["sku"]: line["id"] for line in order["lines"]}

    early = client.post(f"/api/v1/inventory/purchase-orders/{order['id']}/receive", headers=headers, json={"lines": []})
    assert early.status_code == 422
    assert client.post(f"/api/v1/inventory/purchase-orders/{order['id']}/order", headers=headers).status_code == 200

    partial = client.post(
        f"/api/v1/inventory/purchase-orders/{order['id']}/receive",
        headers=headers,
        json={
            "lines": [
                {"purchase_order_line_id": lines["ACC-CABLE-USBC"], "quantity": 30, "aisle_shelf_location": "R3-B2"},
                {
                    "purchase_order_line_id": lines["PHN-PIXEL-9"],
                    "quantity": 2,
                    "serials": [{"kind": "imei", "value": IMEIS[0]}, {"kind": "imei", "value": IMEIS[1]}],
                },
            ]
        },
    )
    assert partial.status_code == 200, partial.text
    assert partial.json()["status"] == "partially_received"
    over = client.post(
        f"/api/v1/inventory/purchase-orders/{order['id']}/receive",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": lines["ACC-CABLE-USBC"], "quantity": 21}]},
    )
    assert over.status_code == 422
    final = client.post(
        f"/api/v1/inventory/purchase-orders/{order['id']}/receive",
        headers=headers,
        json={"lines": [{"purchase_order_line_id": lines["ACC-CABLE-USBC"], "quantity": 20}]},
    ).json()
    assert final["status"] == "received"
    assert len(final["receipts"]) == 2

    warehouse = stock(client, headers, store_id=WH)
    assert row(warehouse, "ACC-CABLE-USBC")["quantity_on_hand"] == 50
    assert row(warehouse, "ACC-CABLE-USBC")["aisle_shelf_location"] == "R3-B2"
    assert row(warehouse, "PHN-PIXEL-9")["quantity_on_hand"] == 2
    assert row(stock(client, headers, store_id=DT), "ACC-CABLE-USBC")["quantity_on_hand"] == 10
    consolidated = stock(client, headers)
    assert consolidated["consolidated"] is True
    assert row(consolidated, "ACC-CABLE-USBC")["quantity_on_hand"] == 60

    trace = client.get("/api/v1/inventory/serials/trace", headers=headers, params={"value": IMEIS[0]}).json()
    assert trace["location"]["store_code"] == "WH-01"
    assert trace["location"]["status"] == "in_stock"
    assert [m["movement_type"] for m in trace["history"]] == ["PURCHASE_IN"]

    wrong_branch = push(client, [event("sale-wrong-branch", "sale", sale(DT, PHONE, 1, IMEIS[0]))])
    assert wrong_branch.status_code == 422
    assert "WH-01" in wrong_branch.json()["error"]["message"]


def receive_phones_at_warehouse(client, headers) -> None:
    order = client.post(
        "/api/v1/inventory/purchase-orders",
        headers=headers,
        json={
            "supplier_name": "Google",
            "destination_store_id": WH,
            "lines": [{"product_id": PHONE, "quantity_ordered": 2}],
        },
    ).json()
    client.post(f"/api/v1/inventory/purchase-orders/{order['id']}/order", headers=headers)
    response = client.post(
        f"/api/v1/inventory/purchase-orders/{order['id']}/receive",
        headers=headers,
        json={
            "lines": [
                {
                    "purchase_order_line_id": order["lines"][0]["id"],
                    "quantity": 2,
                    "serials": [{"kind": "imei", "value": IMEIS[0]}, {"kind": "imei", "value": IMEIS[1]}],
                }
            ]
        },
    )
    assert response.status_code == 200, response.text


def test_transfer_moves_stock_and_imeis_between_branches(client) -> None:
    seed(client)
    headers = admin(client)
    receive_phones_at_warehouse(client, headers)

    created = client.post(
        "/api/v1/inventory/transfers",
        headers=headers,
        json={
            "source_store_id": DT,
            "destination_store_id": SHJ,
            "lines": [{"product_id": CABLE, "quantity": 4}],
        },
    )
    assert created.status_code == 201, created.text
    cable_transfer = created.json()
    dt = row(stock(client, headers, store_id=DT), "ACC-CABLE-USBC")
    assert (dt["quantity_on_hand"], dt["quantity_reserved"], dt["quantity_available"]) == (10, 4, 6)
    blocked = push(client, [event("sale-reserved", "sale", sale(DT, CABLE, 7))])
    assert blocked.status_code == 422

    shipped = client.post(f"/api/v1/inventory/transfers/{cable_transfer['id']}/ship", headers=headers, json={})
    assert shipped.json()["status"] == "in_transit"
    dt = row(stock(client, headers, store_id=DT), "ACC-CABLE-USBC")
    assert (dt["quantity_on_hand"], dt["quantity_reserved"]) == (6, 0)
    received = client.post(f"/api/v1/inventory/transfers/{cable_transfer['id']}/receive", headers=headers)
    assert received.json()["status"] == "received"
    assert row(stock(client, headers, store_id=SHJ), "ACC-CABLE-USBC")["quantity_on_hand"] == 4

    phone_transfer = client.post(
        "/api/v1/inventory/transfers",
        headers=headers,
        json={"source_store_id": WH, "destination_store_id": DT, "lines": [{"product_id": PHONE, "quantity": 1}]},
    ).json()
    missing = client.post(f"/api/v1/inventory/transfers/{phone_transfer['id']}/ship", headers=headers, json={})
    assert missing.status_code == 422
    ship = client.post(
        f"/api/v1/inventory/transfers/{phone_transfer['id']}/ship",
        headers=headers,
        json={
            "serial_lines": [
                {"transfer_line_id": phone_transfer["lines"][0]["id"], "serials": [{"kind": "imei", "value": IMEIS[0]}]}
            ]
        },
    )
    assert ship.status_code == 200, ship.text
    in_transit = push(client, [event("sale-in-transit", "sale", sale(DT, PHONE, 1, IMEIS[0]))])
    assert in_transit.status_code == 422
    client.post(f"/api/v1/inventory/transfers/{phone_transfer['id']}/receive", headers=headers)

    trace = client.get("/api/v1/inventory/serials/trace", headers=headers, params={"value": IMEIS[0]}).json()
    assert trace["location"]["store_code"] == "DT-01"
    assert [m["movement_type"] for m in trace["history"]] == ["TRANSFER_IN", "TRANSFER_OUT", "PURCHASE_IN"]
    assert trace["transfers"][0]["number"] == phone_transfer["number"]
    assert row(stock(client, headers, store_id=WH), "PHN-PIXEL-9")["quantity_on_hand"] == 1
    assert row(stock(client, headers, store_id=DT), "PHN-PIXEL-9")["quantity_on_hand"] == 1

    sold = push(client, [event("sale-phone-dt", "sale", sale(DT, PHONE, 1, IMEIS[0]))])
    assert sold.status_code == 200, sold.text
    assert row(stock(client, headers, store_id=DT), "PHN-PIXEL-9")["quantity_on_hand"] == 0


def test_availability_shows_every_branch_and_imei_location(client) -> None:
    seed(client)
    headers = admin(client)
    receive_phones_at_warehouse(client, headers)
    by_product = client.get("/api/v1/inventory/availability", headers=device(), params={"product_id": CABLE}).json()
    assert [(b["store_code"], b["quantity_available"]) for b in by_product["branches"]] == [("DT-01", 10)]
    by_serial = client.get("/api/v1/inventory/availability", headers=device(), params={"serial": IMEIS[1]}).json()
    assert by_serial["product"]["sku"] == "PHN-PIXEL-9"
    assert by_serial["serial"]["store_code"] == "WH-01"
    assert by_serial["serial"]["last4"] == IMEIS[1][-4:]
    assert (
        client.get("/api/v1/inventory/availability", headers=device(), params={"serial": "00000000"}).status_code == 404
    )


def test_adjustments_and_levels(client) -> None:
    seed(client)
    headers = admin(client)
    damage = client.post(
        "/api/v1/inventory/adjust",
        headers=headers,
        json={
            "adjustment_id": str(uuid.uuid4()),
            "product_id": CABLE,
            "store_id": DT,
            "mode": "remove",
            "quantity": 2,
            "reason_code": "DAMAGED_OR_EXPIRED",
            "note": "Crushed in delivery, two cables",
        },
    )
    assert damage.status_code == 201, damage.text
    assert damage.json()["row"]["quantity_on_hand"] == 8
    too_many = client.post(
        "/api/v1/inventory/adjust",
        headers=headers,
        json={
            "adjustment_id": str(uuid.uuid4()),
            "product_id": CABLE,
            "store_id": DT,
            "mode": "remove",
            "quantity": 9,
            "reason_code": "PHYSICAL_COUNT_AUDIT",
            "note": "Shelf count came up short",
        },
    )
    assert too_many.status_code == 422
    level = client.patch(
        f"/api/v1/inventory/levels/{CABLE}/{DT}",
        headers=headers,
        json={"min_reorder_level": 8, "max_stock_level": 40, "aisle_shelf_location": "A1-02"},
    )
    assert level.json()["status"] == "low"
    assert stock(client, headers, store_id=DT, status="low")["low_count"] == 1


def test_store_manager_is_limited_to_own_branch(client) -> None:
    seed(client)
    headers = admin(client)
    client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": "manager.dt",
            "email": "manager@example.com",
            "full_name": "Manager",
            "role_id": STORE_MANAGER_ROLE,
            "store_id": DT,
            "password": "manager-password-1",
            "has_portal_access": True,
        },
    )
    token = client.post(
        "/api/v1/auth/login-password", json={"username": "manager.dt", "password": "manager-password-1"}
    ).json()["access_token"]
    manager = bearer(token)
    own = stock(client, manager)
    assert own["consolidated"] is False
    assert own["store_id"] == DT
    assert client.get("/api/v1/inventory/stock", headers=manager, params={"store_id": WH}).status_code == 403
    foreign = client.post(
        "/api/v1/inventory/adjust",
        headers=manager,
        json={
            "adjustment_id": str(uuid.uuid4()),
            "product_id": CABLE,
            "store_id": WH,
            "mode": "add",
            "quantity": 5,
            "reason_code": "PHYSICAL_COUNT_AUDIT",
            "note": "Counted five extra units",
        },
    )
    assert foreign.status_code == 403
    category = client.post("/api/v1/categories", headers=manager, json={"name": "Audio"})
    assert category.status_code == 403
    request = client.post(
        "/api/v1/inventory/transfers",
        headers=manager,
        json={"source_store_id": WH, "destination_store_id": SHJ, "lines": [{"product_id": CABLE, "quantity": 1}]},
    )
    assert request.status_code == 403


def test_portal_product_creation_with_opening_stock(client) -> None:
    headers = admin(client)
    seed(client)
    category = client.post("/api/v1/categories", headers=headers, json={"name": "Audio"}).json()
    sub = client.post(
        f"/api/v1/categories/{category['id']}/sub-categories", headers=headers, json={"name": "Earbuds"}
    ).json()["sub_categories"][0]
    created = client.post(
        "/api/v1/inventory/products",
        headers=headers,
        json={
            "sku": "AUD-EARBUDS-01",
            "barcode": "100000000009",
            "name": "Wireless Earbuds",
            "category_id": category["id"],
            "sub_category_id": sub["id"],
            "price_cents": 4900,
            "opening_store_id": SHJ,
            "opening_quantity": 12,
            "min_reorder_level": 3,
        },
    )
    assert created.status_code == 201, created.text
    product = created.json()
    assert (product["category"], product["sub_category"], product["stock_quantity"]) == ("Audio", "Earbuds", 12)
    earbuds = row(stock(client, headers, store_id=SHJ), "AUD-EARBUDS-01")
    assert (earbuds["quantity_on_hand"], earbuds["min_reorder_level"]) == (12, 3)
