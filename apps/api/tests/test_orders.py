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
    seated = floor["areas"][0]["tables"][0]
    assert seated["status"] == "ordered"
    assert seated["order_progress"] == "submitted"
    assert seated["payment"] == "unpaid"
    assert seated["kitchen"] == "queued"
    assert seated["kitchen_sent"] == 2
    assert seated["kitchen_ready"] == 0

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

    other = client.post(
        "/api/v1/orders",
        headers=device(),
        json={
            "id": str(uuid.uuid4()),
            "store_id": STORE_ID,
            "service_type": "TAKEAWAY",
            "covers": 2,
            "user_id": CASHIER_ID,
            "items": [line(3)],
        },
    )
    assert other.status_code == 201, other.text
    other = other.json()
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


def test_floor_phases_follow_the_open_tab_not_occupancy() -> None:
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from app.services.order_service import service_phases

    item_id = uuid.uuid4()
    sent = SimpleNamespace(id=item_id, sent_at=datetime.now(UTC), voided_at=None, paid_sale_id=None)
    order = SimpleNamespace(name="Noor", bill_requested_at=None, items=[sent])
    assert service_phases(None, {}) == ("none", "none", "none")
    assert service_phases(order, {}) == ("queued", "unpaid", "submitted")
    assert service_phases(order, {item_id: "preparing"}) == ("preparing", "unpaid", "in_progress")
    order.bill_requested_at = datetime.now(UTC)
    assert service_phases(order, {item_id: "ready"}) == ("ready", "pending", "in_progress")
    paid = SimpleNamespace(id=item_id, sent_at=sent.sent_at, voided_at=None, paid_sale_id=uuid.uuid4())
    settled = SimpleNamespace(name="Noor", bill_requested_at=None, items=[paid])
    assert service_phases(settled, {item_id: "bumped"}) == ("served", "paid", "in_progress")


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


def test_unsent_order_settles_without_a_kitchen_round(client, session: Session) -> None:
    """Payment does not require a kitchen send, and it does not mark the lines as sent."""
    _token, table = setup(client)
    order = open_order(client, table, line())
    assert order["items"][0]["sent_at"] is None
    paid = push(client, "sale", settle(order, [order["items"][0]["id"]]))
    assert paid.status_code == 200, paid.text
    session.expire_all()
    closed = session.get(OpenOrder, uuid.UUID(order["id"]))
    assert closed is not None and closed.status == "SETTLED" and closed.closed_at is not None
    assert all(item.sent_at is None for item in closed.items)


def test_unsent_order_changes_type_and_a_sent_order_does_not(client, session: Session) -> None:
    _token, table = setup(client)
    order = open_order(client, table, line())
    takeaway = client.patch(
        f"/api/v1/orders/{order['id']}",
        headers=device(),
        json={
            "revision": order["revision"],
            "user_id": CASHIER_ID,
            "service_type": "TAKEAWAY",
            "reason": "Guest is leaving",
        },
    )
    assert takeaway.status_code == 200, takeaway.text
    assert takeaway.json()["service_type"] == "TAKEAWAY" and takeaway.json()["table_id"] is None
    floor = client.get("/api/v1/dining/floor", headers=device(), params={"store_id": STORE_ID}).json()
    assert floor["areas"][0]["tables"][0]["status"] == "free"
    session.expire_all()
    trail = session.scalar(select(AuditLog).where(AuditLog.action == "order.service_change"))
    assert trail is not None and trail.details["from"] == "DINE_IN" and trail.details["to"] == "TAKEAWAY"

    missing = client.patch(
        f"/api/v1/orders/{order['id']}",
        headers=device(),
        json={
            "revision": takeaway.json()["revision"],
            "user_id": CASHIER_ID,
            "service_type": "DELIVERY",
            "name": "Asha",
        },
    )
    assert missing.status_code == 422 and missing.json()["error"]["code"] == "delivery_required"
    delivered = client.patch(
        f"/api/v1/orders/{order['id']}",
        headers=device(),
        json={
            "revision": takeaway.json()["revision"],
            "user_id": CASHIER_ID,
            "service_type": "DELIVERY",
            "name": "Asha",
            "note": "12 Marina Walk",
        },
    )
    assert delivered.status_code == 200, delivered.text
    assert delivered.json()["service_type"] == "DELIVERY"

    seated = client.patch(
        f"/api/v1/orders/{order['id']}",
        headers=device(),
        json={
            "revision": delivered.json()["revision"],
            "user_id": CASHIER_ID,
            "service_type": "DINE_IN",
            "table_id": table["id"],
        },
    )
    assert seated.status_code == 200, seated.text
    assert seated.json()["table_id"] == table["id"] and seated.json()["service_type"] == "DINE_IN"

    sent = client.post(
        f"/api/v1/orders/{order['id']}/send",
        headers=device(),
        json={"revision": seated.json()["revision"], "user_id": CASHIER_ID},
    )
    assert sent.status_code == 200, sent.text
    blocked = client.patch(
        f"/api/v1/orders/{order['id']}",
        headers=device(),
        json={"revision": sent.json()["revision"], "user_id": CASHIER_ID, "service_type": "TAKEAWAY"},
    )
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "order_in_kitchen"


def test_dine_in_conversion_refuses_an_occupied_table(client) -> None:
    _token, table = setup(client)
    open_order(client, table, line())
    counter = client.post(
        "/api/v1/orders",
        headers=device(),
        json={
            "id": str(uuid.uuid4()),
            "store_id": STORE_ID,
            "service_type": "TAKEAWAY",
            "name": "Window",
            "user_id": CASHIER_ID,
            "items": [line()],
        },
    )
    assert counter.status_code == 201, counter.text
    refused = client.patch(
        f"/api/v1/orders/{counter.json()['id']}",
        headers=device(),
        json={
            "revision": counter.json()["revision"],
            "user_id": CASHIER_ID,
            "service_type": "DINE_IN",
            "table_id": table["id"],
        },
    )
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "table_occupied"
    bare = client.patch(
        f"/api/v1/orders/{counter.json()['id']}",
        headers=device(),
        json={"revision": counter.json()["revision"], "user_id": CASHIER_ID, "service_type": "DINE_IN"},
    )
    assert bare.status_code == 422 and bare.json()["error"]["code"] == "table_required"


def test_offline_type_change_syncs_until_the_kitchen_has_the_order(client) -> None:
    _token, table = setup(client)
    order = open_order(client, table, line())
    event = {
        "idempotency_key": f"type-{order['id']}",
        "entity_type": "open_order",
        "operation": "upsert",
        "payload": {
            "id": order["id"],
            "store_id": STORE_ID,
            "service_type": "TAKEAWAY",
            "covers": 2,
            "opened_by_id": CASHIER_ID,
            "opened_at": order["opened_at"],
            "items": [],
        },
        "occurred_at": "2026-10-31T08:00:00Z",
    }
    synced = client.post("/api/v1/sync/push", headers=device(), json={"device_id": "register-1", "events": [event]})
    assert synced.status_code == 200, synced.text
    moved = client.get(f"/api/v1/orders/{order['id']}", headers=device()).json()
    assert moved["service_type"] == "TAKEAWAY" and moved["table_id"] is None

    seated = client.patch(
        f"/api/v1/orders/{order['id']}",
        headers=device(),
        json={"revision": moved["revision"], "user_id": CASHIER_ID, "service_type": "DINE_IN", "table_id": table["id"]},
    )
    assert seated.status_code == 200, seated.text
    sent = client.post(
        f"/api/v1/orders/{order['id']}/send",
        headers=device(),
        json={"revision": seated.json()["revision"], "user_id": CASHIER_ID},
    )
    assert sent.status_code == 200, sent.text
    rejected = client.post(
        "/api/v1/sync/push",
        headers=device(),
        json={
            "device_id": "register-1",
            "events": [
                {
                    **event,
                    "idempotency_key": f"type-{order['id']}-late",
                    "payload": {**event["payload"], "service_type": "DELIVERY", "name": "Asha", "note": "Marina"},
                }
            ],
        },
    )
    assert rejected.status_code == 422
    assert client.get(f"/api/v1/orders/{order['id']}", headers=device()).json()["service_type"] == "DINE_IN"


def test_occupied_table_reopens_the_same_order(client, session: Session) -> None:
    """One occupied table keeps one dine-in order through reopen, extra items, partial pay, and cancel."""
    token, table = setup(client)
    customer = client.post(
        "/api/v1/customers",
        headers=bearer(token),
        json={"name": "Asha", "phone": "+971509998877"},
    )
    assert customer.status_code == 201, customer.text
    original = line()
    created = client.post(
        "/api/v1/orders",
        headers=device(),
        json={
            "id": str(uuid.uuid4()),
            "store_id": STORE_ID,
            "table_id": table["id"],
            "covers": 2,
            "name": "Asha",
            "customer_id": customer.json()["id"],
            "user_id": CASHIER_ID,
            "items": [original],
        },
    )
    assert created.status_code == 201, created.text
    order = created.json()
    assert order["name"] == "Asha" and order["customer_id"] == customer.json()["id"]
    assert order["items"][0]["id"] == original["id"]

    duplicate = client.post(
        "/api/v1/orders",
        headers=device(),
        json={
            "id": str(uuid.uuid4()),
            "store_id": STORE_ID,
            "table_id": table["id"],
            "covers": 4,
            "user_id": CASHIER_ID,
            "items": [line()],
        },
    )
    assert duplicate.status_code == 409
    body = duplicate.json()["error"]
    assert body["code"] == "table_occupied" and body["details"]["order_id"] == order["id"]
    opened = client.get(f"/api/v1/orders/{order['id']}", headers=device())
    assert opened.status_code == 200
    order = opened.json()
    assert order["status"] == "OPEN" and order["name"] == "Asha" and order["customer_id"] == customer.json()["id"]
    assert len(order["items"]) == 1
    floor = client.get("/api/v1/dining/floor", headers=device(), params={"store_id": STORE_ID}).json()
    assert floor["areas"][0]["tables"][0]["status"] != "free"
    assert floor["areas"][0]["tables"][0]["order_id"] == order["id"]

    extra = line()
    added = client.post(
        f"/api/v1/orders/{order['id']}/items",
        headers=device(),
        json={"revision": order["revision"], "user_id": CASHIER_ID, "items": [extra]},
    )
    assert added.status_code == 200, added.text
    order = added.json()
    assert order["id"] == created.json()["id"]
    ids = {item["id"] for item in order["items"]}
    assert original["id"] in ids and extra["id"] in ids
    grown = client.post(
        f"/api/v1/orders/{order['id']}/items/{original['id']}/quantity",
        headers=device(),
        json={"revision": order["revision"], "user_id": CASHIER_ID, "quantity": 3},
    )
    assert grown.status_code == 200, grown.text
    order = grown.json()
    first = next(item for item in order["items"] if item["id"] == original["id"])
    assert first["quantity"] == 3 and first["sent_at"] is None
    assert session.scalar(select(AuditLog).where(AuditLog.action == "order.item_quantity")) is not None

    sent = client.post(
        f"/api/v1/orders/{order['id']}/send",
        headers=device(),
        json={"revision": order["revision"], "user_id": CASHIER_ID},
    )
    assert sent.status_code == 200, sent.text
    order = sent.json()
    sent_at = next(item["sent_at"] for item in order["items"] if item["id"] == original["id"])
    assert sent_at is not None
    later = line()
    added = client.post(
        f"/api/v1/orders/{order['id']}/items",
        headers=device(),
        json={"revision": order["revision"], "user_id": CASHIER_ID, "items": [later]},
    )
    assert added.status_code == 200, added.text
    order = added.json()
    kept = next(item for item in order["items"] if item["id"] == original["id"])
    fresh = next(item for item in order["items"] if item["id"] == later["id"])
    assert kept["sent_at"] == sent_at and kept["quantity"] == 3 and fresh["sent_at"] is None
    blocked = client.post(
        f"/api/v1/orders/{order['id']}/items/{original['id']}/quantity",
        headers=device(),
        json={"revision": order["revision"], "user_id": CASHIER_ID, "quantity": 1},
    )
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "already_sent"

    clash = {
        "id": str(uuid.uuid4()),
        "store_id": STORE_ID,
        "table_id": table["id"],
        "covers": 1,
        "opened_by_id": CASHIER_ID,
        "opened_at": "2026-10-31T09:00:00Z",
        "items": [line()],
    }
    synced = client.post(
        "/api/v1/sync/push",
        headers=device(),
        json={
            "device_id": "register-1",
            "events": [
                {
                    "idempotency_key": f"order-{clash['id']}",
                    "entity_type": "open_order",
                    "operation": "upsert",
                    "payload": clash,
                    "occurred_at": "2026-10-31T09:00:00Z",
                }
            ],
        },
    )
    assert synced.status_code == 422
    assert "already has an open order" in synced.json()["error"]["message"]
    assert client.get(f"/api/v1/orders/{order['id']}", headers=device()).json()["status"] == "OPEN"

    from types import SimpleNamespace

    from app.core.errors import ApiError
    from app.services.order_service import _scope

    try:
        _scope(SimpleNamespace(store_id=uuid.uuid4()), uuid.UUID(order["store_id"]))
    except ApiError as exc:
        assert exc.status_code == 403 and exc.code == "store_scope"
    else:
        raise AssertionError("another branch was allowed to read this order")
    _scope(SimpleNamespace(store_id=uuid.UUID(order["store_id"])), uuid.UUID(order["store_id"]))

    partial = push(client, "sale", settle(order, [later["id"]]))
    assert partial.status_code == 200, partial.text
    session.expire_all()
    still = session.get(OpenOrder, uuid.UUID(order["id"]))
    assert still is not None and still.status == "OPEN"
    floor = client.get("/api/v1/dining/floor", headers=device(), params={"store_id": STORE_ID}).json()
    assert floor["areas"][0]["tables"][0]["status"] != "free"
    owing = client.get(f"/api/v1/orders/{order['id']}", headers=device()).json()
    assert owing["open_cents"] > 0 and owing["id"] == order["id"]
    unpaid = [item["id"] for item in owing["items"] if item["paid_sale_id"] is None and item["voided_at"] is None]
    closed = push(client, "sale", settle(owing, unpaid))
    assert closed.status_code == 200, closed.text
    assert closed.json()["results"][0]["status"] == "applied"
    session.expire_all()
    assert session.get(OpenOrder, uuid.UUID(order["id"])).status == "SETTLED"
    floor = client.get("/api/v1/dining/floor", headers=device(), params={"store_id": STORE_ID}).json()
    assert floor["areas"][0]["tables"][0]["status"] == "free"

    again = open_order(client, table, line())
    cancelled = client.post(
        f"/api/v1/orders/{again['id']}/void",
        headers=device(),
        json={"revision": again["revision"], "user_id": CASHIER_ID, "reason": "Guest left before ordering"},
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "VOID"
    floor = client.get("/api/v1/dining/floor", headers=device(), params={"store_id": STORE_ID}).json()
    assert floor["areas"][0]["tables"][0]["status"] == "free"
    voided = session.scalar(
        select(AuditLog).where(AuditLog.action == "order.void", AuditLog.target_entity_id == uuid.UUID(again["id"]))
    )
    assert voided is not None
