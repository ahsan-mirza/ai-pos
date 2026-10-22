"""Station rooms receive only their own tickets, and a cart reaches only that register's display."""

import uuid

import pytest
from starlette.websockets import WebSocketDisconnect
from tests.test_kds import BURGER_ID, MODULES, floor_table, stations
from tests.test_menu import enable
from tests.test_orders import line, open_order
from tests.test_returns import API_KEY, CASHIER_ID, STORE_ID, admin_id, admin_token, bearer, device, push, seed_catalog


def _register(client, token: str, code: str) -> str:
    created = client.post(
        "/api/v1/devices",
        headers=bearer(token),
        json={"store_id": STORE_ID, "code": code, "name": f"Till {code}"},
    )
    assert created.status_code == 201, created.text
    return created.json()["device"]["id"]


def _live(role: str, **params: str) -> str:
    query = "&".join(f"{key}={value}" for key, value in params.items())
    return f"/api/v1/ws/live?token={API_KEY}&role={role}&{query}"


def test_kitchen_events_stay_inside_the_station_room(client, session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    enable(client, token, *MODULES)
    bar, kitchen = stations(client, token, session)
    table = floor_table(client, token)
    burger = {
        "id": BURGER_ID,
        "sku": "FD-BURGER",
        "barcode": "100000000077",
        "name": "Burger",
        "category": "Mains",
        "price_cents": 1500,
        "is_serialized": False,
        "stock_quantity": 50,
    }
    assert push(client, "product", {**burger, "store_id": STORE_ID, "currency": "USD"}).status_code == 200
    order = open_order(client, table, line(2, seat=1), {**line(), "product_id": BURGER_ID})

    with (
        client.websocket_connect(_live("kds", station_id=bar["id"])) as bar_socket,
        client.websocket_connect(_live("kds", station_id=kitchen["id"])) as kitchen_socket,
    ):
        sent = client.post(
            f"/api/v1/orders/{order['id']}/send",
            headers=device(),
            json={"revision": order["revision"], "user_id": CASHIER_ID},
        )
        assert sent.status_code == 200, sent.text
        bar_event = bar_socket.receive_json()
        kitchen_event = kitchen_socket.receive_json()
        assert bar_event["type"] == "kitchen:new-order"
        assert bar_event["station_id"] == bar["id"]
        assert kitchen_event["type"] == "kitchen:new-order"
        assert kitchen_event["station_id"] == kitchen["id"]
        assert bar_event["ticket"]["id"] != kitchen_event["ticket"]["id"]
        assert all(item["product_name"] != "Burger" for item in bar_event["ticket"]["items"])
        assert any(item["product_name"] == "Burger" for item in kitchen_event["ticket"]["items"])

        bar_socket.send_json(
            {"type": "kitchen:status", "ticket_id": bar_event["ticket"]["id"], "status": "START"}
        )
        updated = bar_socket.receive_json()
        assert updated["type"] == "kitchen:order-updated"
        assert updated["station_id"] == bar["id"]
        assert updated["ticket"]["status"] == "PREPARING"

        current = client.get(f"/api/v1/orders/{order['id']}", headers=device()).json()
        burger_item = next(item for item in current["items"] if item["product_id"] == BURGER_ID)
        voided = client.post(
            f"/api/v1/orders/{order['id']}/items/{burger_item['id']}/void",
            headers=device(),
            json={
                "revision": current["revision"],
                "user_id": CASHIER_ID,
                "reason": "Kitchen ran out",
                "approved_by_id": admin_id(client),
            },
        )
        assert voided.status_code == 200, voided.text
        cancelled = kitchen_socket.receive_json()
        assert cancelled["type"] == "kitchen:order-cancelled"
        assert cancelled["station_id"] == kitchen["id"]
        assert cancelled["ticket"]["status"] == "BUMPED"


def test_cart_updates_reach_only_that_terminals_display(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    till_a = _register(client, token, "D1")
    till_b = _register(client, token, "D2")
    with (
        client.websocket_connect(_live("pos", terminal_id=till_a)) as pos_a,
        client.websocket_connect(_live("customer-display", terminal_id=till_a)) as display_a,
        client.websocket_connect(_live("pos", terminal_id=till_b)) as pos_b,
        client.websocket_connect(_live("customer-display", terminal_id=till_b)) as display_b,
    ):
        pos_a.send_json({"type": "customer-display:cart", "state": {"storeName": "Till 1", "lines": [{"name": "Tea"}]}})
        assert display_a.receive_json() == {
            "type": "customer-display:cart",
            "state": {"storeName": "Till 1", "lines": [{"name": "Tea"}]},
        }
        pos_b.send_json({"type": "customer-display:cart", "state": {"storeName": "Till 2", "lines": []}})
        assert display_b.receive_json()["state"]["storeName"] == "Till 2"

    with client.websocket_connect(_live("customer-display", terminal_id=till_a)) as again:
        replay = again.receive_json()
        assert replay["state"]["storeName"] == "Till 1"


def test_unknown_terminal_is_refused(client) -> None:
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(_live("pos", terminal_id=str(uuid.uuid4()))):
            pass
