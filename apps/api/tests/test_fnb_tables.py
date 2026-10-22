"""Waiter rounds, guest attach, and the live table socket."""

import uuid

from tests.test_capabilities import change_profile
from tests.test_menu import enable
from tests.test_orders import settle
from tests.test_returns import API_KEY, CABLE_ID, STORE_ID, admin_token, bearer, device, push, seed_catalog


def _table(client, token: str) -> dict:
    floor = client.post("/api/v1/dining/areas", headers=bearer(token), json={"store_id": STORE_ID, "name": "Terrace"})
    assert floor.status_code == 201, floor.text
    area = floor.json()["areas"][0]
    tables = client.post(
        "/api/v1/dining/tables", headers=bearer(token), json={"area_id": area["id"], "label": "T4", "seats": 4}
    )
    assert tables.status_code == 201, tables.text
    return tables.json()["areas"][0]["tables"][0]


def test_electronics_cannot_open_a_table_session(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    enable(client, token, "open_orders", "tables")
    table = _table(client, token)
    response = client.post(
        f"/api/v1/fnb/tables/{table['id']}/session/start",
        headers=device(),
        json={"phone": "0551234567"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_waiter_rounds_reach_the_cashier_and_payment_closes_the_table(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    assert change_profile(client, bearer(token), "restaurant").status_code == 200
    table = _table(client, token)
    menu = client.get("/api/v1/fnb/menu", headers=device(), params={"store_id": STORE_ID})
    assert menu.status_code == 200, menu.text
    assert any(item["id"] == CABLE_ID for item in menu.json()["items"])

    with client.websocket_connect(f"/api/v1/ws/stores/{STORE_ID}/tables?token={API_KEY}") as socket:
        started = client.post(
            f"/api/v1/fnb/tables/{table['id']}/session/start",
            headers=device(),
            json={"phone": "0551234567", "covers": 3},
        )
        assert started.status_code == 200, started.text
        session = started.json()
        assert session["status"] == "OCCUPIED"
        assert session["phone"] == "0551234567"
        assert session["customer_name"] == "Guest 0551234567"
        assert session["order"]["covers"] == 3
        order_id = session["order"]["id"]

        again = client.post(
            f"/api/v1/fnb/tables/{table['id']}/session/start",
            headers=device(),
            json={"phone": "0551234567"},
        )
        assert again.json()["order"]["id"] == order_id

        round_id = str(uuid.uuid4())
        body = {"client_round_id": round_id, "items": [{"product_id": CABLE_ID, "quantity": 1, "note": "Less spice"}]}
        first = client.post(f"/api/v1/fnb/tables/{table['id']}/orders/add-round", headers=device(), json=body)
        assert first.status_code == 200, first.text
        assert len(first.json()["order"]["items"]) == 1
        assert first.json()["order"]["items"][0]["sent_at"] is not None
        added = socket.receive_json()
        assert added["type"] == "TABLE_ITEMS_ADDED"
        assert added["table_label"] == "T4"
        assert added["order_id"] == order_id
        assert added["items"][0]["quantity"] == 1
        progress = socket.receive_json()
        assert progress["type"] == "ORDER_STATUS_CHANGED"
        assert progress["status"] == "preparing"
        assert progress["kitchen_status"] == "new"
        assert progress["order_id"] == order_id
        assert progress["table_id"] == table["id"]
        assert progress["item_ids"] == [added["items"][0]["id"]]

        retry = client.post(f"/api/v1/fnb/tables/{table['id']}/orders/add-round", headers=device(), json=body)
        assert retry.status_code == 200, retry.text
        assert len(retry.json()["order"]["items"]) == 1

        second = client.post(
            f"/api/v1/fnb/tables/{table['id']}/orders/add-round",
            headers=device(),
            json={"items": [{"product_id": CABLE_ID, "quantity": 2}]},
        )
        assert second.status_code == 200, second.text
        assert len(second.json()["order"]["items"]) == 2
        assert socket.receive_json()["type"] == "TABLE_ITEMS_ADDED"
        assert socket.receive_json()["type"] == "ORDER_STATUS_CHANGED"

        active = client.get(f"/api/v1/fnb/tables/{table['id']}/active-session", headers=device())
        assert active.status_code == 200
        order = active.json()["order"]
        assert order["open_cents"] == sum(item["unit_price_cents"] * item["quantity"] for item in order["items"])

        paid = push(client, "sale", settle(order, [item["id"] for item in order["items"]]))
        assert paid.status_code == 200, paid.text
        closed = socket.receive_json()
        assert closed["type"] == "TABLE_SESSION_CLOSED"
        assert closed["table_id"] == table["id"]
        assert client.get(f"/api/v1/fnb/tables/{table['id']}/active-session", headers=device()).status_code == 404


def test_walk_in_guest_skips_the_customer_profile(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    assert change_profile(client, bearer(token), "restaurant").status_code == 200
    table = _table(client, token)
    started = client.post(f"/api/v1/fnb/tables/{table['id']}/session/start", headers=device(), json={"covers": 1})
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["phone"] is None
    assert body["customer_name"] == "Walk-in guest"
    assert body["order"]["customer_id"] is None


def test_guest_can_call_a_waiter_and_request_the_bill(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    assert change_profile(client, bearer(token), "restaurant").status_code == 200
    table = _table(client, token)
    menu = client.get("/api/v1/fnb/menu", headers=device(), params={"store_id": STORE_ID})
    assert menu.status_code == 200, menu.text
    dish = next(item for item in menu.json()["items"] if item["id"] == CABLE_ID)
    assert "image_url" in dish and isinstance(dish["currency"], str) and dish["price_cents"] > 0

    started = client.post(f"/api/v1/fnb/tables/{table['id']}/session/start", headers=device(), json={"covers": 2})
    assert started.status_code == 200, started.text
    order = started.json()["order"]
    with client.websocket_connect(f"/api/v1/ws/stores/{STORE_ID}/tables?token={API_KEY}") as socket:
        called = client.post(f"/api/v1/fnb/tables/{table['id']}/call-waiter", headers=device())
        assert called.status_code == 200, called.text
        event = socket.receive_json()
        assert event["type"] == "CALL_WAITER"
        assert event["table_label"] == table["label"]
        assert "waiter" in event["message"]

        bill = client.post(f"/api/v1/fnb/tables/{table['id']}/request-bill", headers=device())
        assert bill.status_code == 200, bill.text
        assert bill.json()["order"]["bill_requested_at"] is not None
        requested = socket.receive_json()
        assert requested["type"] == "BILL_REQUESTED"
        assert requested["order_id"] == order["id"]


def _until(socket, kind: str, limit: int = 8) -> dict:
    last = None
    for _ in range(limit):
        last = socket.receive_json()
        if last["type"] == kind:
            return last
    raise AssertionError(f"expected {kind}, last event was {last}")


def test_guest_socket_alerts_reach_pos_terminals(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    assert change_profile(client, bearer(token), "restaurant").status_code == 200
    table = _table(client, token)
    started = client.post(f"/api/v1/fnb/tables/{table['id']}/session/start", headers=device(), json={"covers": 2})
    assert started.status_code == 200, started.text

    pos_url = f"/api/v1/ws/stores/{STORE_ID}/tables?token={API_KEY}&role=pos"
    guest_url = f"/api/v1/ws/stores/{STORE_ID}/tables?token={API_KEY}"
    with client.websocket_connect(pos_url) as pos, client.websocket_connect(guest_url) as guest:
        guest.send_json({"type": "table:call-waiter", "tableId": table["id"], "tableName": table["label"]})
        called = _until(pos, "pos:table-alert")
        assert called["alert"] == "call-waiter"
        assert called["tableId"] == table["id"]
        assert called["tableName"] == table["label"]
        assert called["totalAmount"] is None
        guest_event = guest.receive_json()
        assert guest_event["type"] == "CALL_WAITER"

        guest.send_json(
            {"type": "table:request-bill", "tableId": table["id"], "tableName": table["label"], "totalAmount": 1}
        )
        bill = _until(pos, "pos:table-alert")
        assert bill["alert"] == "request-bill"
        assert bill["tableName"] == table["label"]
        assert isinstance(bill["totalAmount"], int)

        pos.send_json({"type": "pos:table-alert-ack", "alertId": bill["id"], "tableId": table["id"]})
        cleared = _until(pos, "pos:table-alert-cleared")
        assert cleared["alertId"] == bill["id"]
        assert cleared["tableId"] == table["id"]
