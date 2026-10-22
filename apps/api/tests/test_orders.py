import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.test_menu import enable
from tests.test_returns import CABLE_ID, CASHIER_ID, STORE_ID, admin_id, admin_token, bearer, device, push, seed_catalog

from app.models import AuditLog, OpenOrder, Sale

RESTAURANT = ("menu_modifiers", "open_orders", "tables")


def setup(client) -> tuple[str, dict]:
    seed_catalog(client)
    token = admin_token(client)
    enable(client, token, *RESTAURANT)
    floor = client.post("/api/v1/dining/areas", headers=bearer(token), json={"store_id": STORE_ID, "name": "Terrace"})
    assert floor.status_code == 201, floor.text
    area = floor.json()["areas"][0]
    tables = client.post(
        "/api/v1/dining/tables", headers=bearer(token), json={"area_id": area["id"], "label": "T1", "seats": 4}
    )
    assert tables.status_code == 201, tables.text
    return token, tables.json()["areas"][0]["tables"][0]


def line(quantity: int = 1, seat: int | None = None) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "product_id": CABLE_ID,
        "quantity": quantity,
        "unit_price_cents": 1500,
        "seat": seat,
    }


def open_order(client, table: dict, *items: dict) -> dict:
    response = client.post(
        "/api/v1/orders",
        headers=device(),
        json={
            "id": str(uuid.uuid4()),
            "store_id": STORE_ID,
            "table_id": table["id"],
            "covers": 2,
            "user_id": CASHIER_ID,
            "items": list(items),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def settle(order: dict, item_ids: list[str], *, tip: int = 0, service: int = 0) -> dict:
    lines = [item for item in order["items"] if item["id"] in item_ids]
    sale_id = str(uuid.uuid4())
    subtotal = sum(item["unit_price_cents"] * item["quantity"] for item in lines)
    tax = round(subtotal * 500 / 10_000)
    return {
        "id": sale_id,
        "store_id": STORE_ID,
        "cashier_id": CASHIER_ID,
        "currency": "USD",
        "payment_method": "cash",
        "subtotal_cents": subtotal + service,
        "tax_cents": tax,
        "total_cents": subtotal + tax + service,
        "client_sale_id": sale_id,
        "order_id": order["id"],
        "order_item_ids": item_ids,
        "service_charge_cents": service,
        "tip_cents": tip,
        "tenders": [{"method": "cash", "amount_cents": subtotal + tax + service + tip}],
        "items": [
            {
                "id": str(uuid.uuid4()),
                "product_id": item["product_id"],
                "quantity": item["quantity"],
                "unit_price_cents": item["unit_price_cents"],
                "tax_cents": round(item["unit_price_cents"] * item["quantity"] * 500 / 10_000),
                "line_total_cents": item["unit_price_cents"] * item["quantity"]
                + round(item["unit_price_cents"] * item["quantity"] * 500 / 10_000),
            }
            for item in lines
        ],
    }


def test_tab_lifecycle_with_revisions_voids_and_split_settlement(client, session: Session) -> None:
    token, table = setup(client)
    order = open_order(client, table, line(seat=1), line(2, seat=2))
    assert (order["number"], order["revision"], order["open_cents"]) == (1, 1, 4500)
    assert client.get("/api/v1/orders", headers=device(), params={"store_id": STORE_ID}).json()[0]["id"] == order["id"]

    stale = client.post(
        f"/api/v1/orders/{order['id']}/items",
        headers=device(),
        json={"revision": 0, "user_id": CASHIER_ID, "items": [line()]},
    )
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "stale_order"
    sent = client.post(
        f"/api/v1/orders/{order['id']}/send", headers=device(), json={"revision": 1, "user_id": CASHIER_ID}
    )
    assert sent.status_code == 200, sent.text
    order = sent.json()
    assert all(item["sent_at"] for item in order["items"])
    floor = client.get("/api/v1/dining/floor", headers=device(), params={"store_id": STORE_ID}).json()
    assert floor["areas"][0]["tables"][0]["status"] == "ordered"

    first = order["items"][0]["id"]
    refused = client.post(
        f"/api/v1/orders/{order['id']}/items/{first}/void",
        headers=device(),
        json={"revision": order["revision"], "user_id": CASHIER_ID, "reason": "Customer changed mind"},
    )
    assert refused.status_code == 403 and refused.json()["error"]["code"] == "approval_required"
    voided = client.post(
        f"/api/v1/orders/{order['id']}/items/{first}/void",
        headers=device(),
        json={
            "revision": order["revision"],
            "user_id": CASHIER_ID,
            "reason": "Customer changed mind",
            "approved_by_id": admin_id(client),
        },
    )
    assert voided.status_code == 200, voided.text
    order = voided.json()
    assert order["open_cents"] == 3000
    assert session.scalar(select(AuditLog).where(AuditLog.action == "order.void_sent_item")) is not None

    order = client.post(
        f"/api/v1/orders/{order['id']}/items",
        headers=device(),
        json={"revision": order["revision"], "user_id": CASHIER_ID, "items": [line(seat=3)]},
    ).json()
    unpaid = [item["id"] for item in order["items"] if item["voided_at"] is None]
    seat_two, seat_three = unpaid

    first_check = settle(order, [seat_two], tip=200)
    paid = push(client, "sale", first_check)
    assert paid.status_code == 200, paid.text
    session.expire_all()
    assert session.get(OpenOrder, uuid.UUID(order["id"])).status == "OPEN"
    sale = session.get(Sale, uuid.UUID(first_check["id"]))
    assert (sale.order_id, sale.tip_cents) == (uuid.UUID(order["id"]), 200)

    second = push(client, "sale", settle(order, [seat_three], service=150))
    assert second.status_code == 200, second.text
    session.expire_all()
    closed = session.get(OpenOrder, uuid.UUID(order["id"]))
    assert closed.status == "SETTLED" and closed.closed_at is not None
    floor = client.get("/api/v1/dining/floor", headers=device(), params={"store_id": STORE_ID}).json()
    assert floor["areas"][0]["tables"][0]["status"] == "free"


def test_offline_orders_sync_and_merge(client) -> None:
    token, table = setup(client)
    offline_id = str(uuid.uuid4())
    sent_line = {**line(), "sent_at": "2026-10-19T08:00:00Z"}
    payload = {
        "id": offline_id,
        "store_id": STORE_ID,
        "table_id": table["id"],
        "covers": 3,
        "opened_by_id": CASHIER_ID,
        "opened_at": "2026-10-19T07:55:00Z",
        "items": [sent_line],
    }
    event = {
        "idempotency_key": f"order-{offline_id}",
        "entity_type": "open_order",
        "operation": "upsert",
        "payload": payload,
        "occurred_at": "2026-10-19T08:00:00Z",
    }
    synced = client.post("/api/v1/sync/push", headers=device(), json={"device_id": "register-1", "events": [event]})
    assert synced.status_code == 200, synced.text
    assert synced.json()["results"][0]["status"] == "applied"

    again = {**payload, "items": [sent_line, line()]}
    event2 = {**event, "idempotency_key": f"order-{offline_id}-2", "payload": again}
    client.post("/api/v1/sync/push", headers=device(), json={"device_id": "register-1", "events": [event2]})
    synced_order = client.get(f"/api/v1/orders/{offline_id}", headers=device()).json()
    assert len(synced_order["items"]) == 2 and synced_order["covers"] == 3

    other = open_order(client, table, line(3))
    merged = client.post(
        f"/api/v1/orders/{other['id']}/merge",
        headers=device(),
        json={
            "revision": other["revision"],
            "user_id": CASHIER_ID,
            "into_order_id": offline_id,
            "into_revision": synced_order["revision"],
        },
    )
    assert merged.status_code == 200, merged.text
    assert len(merged.json()["items"]) == 3 and merged.json()["covers"] == 5
    assert client.get(f"/api/v1/orders/{other['id']}", headers=device()).json()["status"] == "VOID"


def test_bill_split_equally_takes_one_tender_per_guest(client) -> None:
    token, table = setup(client)
    order = open_order(client, table, line(4))
    sale = settle(order, [order["items"][0]["id"]])
    total = sale["total_cents"]
    for guests, status in ((12, 200), (13, 422)):
        shares = [total // guests + (1 if index < total % guests else 0) for index in range(guests)]
        split = {**sale, "id": str(uuid.uuid4()), "client_sale_id": str(uuid.uuid4()), "payment_method": "card"}
        split["tenders"] = [
            {"method": "card", "amount_cents": cents, "reference": f"Guest {i + 1}"} for i, cents in enumerate(shares)
        ]
        response = push(client, "sale", split)
        assert response.status_code == status, response.text


def test_tips_need_tenders_that_cover_them(client) -> None:
    token, table = setup(client)
    order = open_order(client, table, line())
    sale = settle(order, [order["items"][0]["id"]], tip=300)
    sale["tenders"][0]["amount_cents"] -= 300
    assert push(client, "sale", sale).status_code == 422
