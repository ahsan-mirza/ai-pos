import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.test_capabilities import change_profile
from tests.test_menu import enable
from tests.test_orders import line, open_order, settle
from tests.test_returns import (
    API_KEY,
    CABLE_ID,
    CASHIER_ID,
    STORE_ID,
    admin_id,
    admin_token,
    bearer,
    device,
    push,
    seed_catalog,
)

from app.models import KitchenTicket, Product

MODULES = ("menu_modifiers", "open_orders", "tables", "kds")
BURGER_ID = "00000000-0000-4000-8000-000000000077"


def stations(client, token: str, session: Session) -> tuple[dict, dict]:
    cable = session.get(Product, uuid.UUID(CABLE_ID))
    assert cable is not None and cable.category_id is not None
    bar = client.post(
        "/api/v1/kds/stations",
        headers=bearer(token),
        json={"store_id": STORE_ID, "name": "Bar", "category_ids": [str(cable.category_id)]},
    )
    kitchen = client.post(
        "/api/v1/kds/stations",
        headers=bearer(token),
        json={"store_id": STORE_ID, "name": "Kitchen", "is_default": True, "position": 1},
    )
    assert bar.status_code == 201 and kitchen.status_code == 201, bar.text + kitchen.text
    return bar.json(), kitchen.json()


def floor_table(client, token: str) -> dict:
    floor = client.post("/api/v1/dining/areas", headers=bearer(token), json={"store_id": STORE_ID, "name": "Main"})
    area = floor.json()["areas"][0]
    tables = client.post("/api/v1/dining/tables", headers=bearer(token), json={"area_id": area["id"], "label": "4"})
    return tables.json()["areas"][0]["tables"][0]


def board(client, station: dict, since: str | None = None) -> dict:
    params = {"since": since} if since else {}
    response = client.get(f"/api/v1/kds/stations/{station['id']}/tickets", headers=device(), params=params)
    assert response.status_code == 200, response.text
    return response.json()


def status(client, ticket_id: str, value: str):
    return client.post(f"/api/v1/kds/tickets/{ticket_id}/status", headers=device(), json={"status": value})


def test_sending_fires_tickets_per_station_and_tracks_progress(client, session: Session) -> None:
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
    sent = client.post(
        f"/api/v1/orders/{order['id']}/send", headers=device(), json={"revision": 1, "user_id": CASHIER_ID}
    )
    assert sent.status_code == 200, sent.text
    assert {item["kitchen_status"] for item in sent.json()["items"]} == {"new"}

    bar_board = board(client, bar)
    assert len(bar_board["tickets"]) == 1
    ticket = bar_board["tickets"][0]
    assert (ticket["label"], ticket["number"], ticket["status"]) == ("Table 4", order["number"], "NEW")
    assert [(item["quantity"], item["seat"]) for item in ticket["items"]] == [(2, 1)]
    assert len(board(client, kitchen)["tickets"]) == 1
    assert board(client, bar, bar_board["server_time"])["tickets"] == []

    assert change_profile(client, bearer(token), "restaurant").status_code == 200
    with client.websocket_connect(f"/api/v1/ws/stores/{STORE_ID}/tables?token={API_KEY}") as socket:
        assert status(client, ticket["id"], "READY").status_code == 200
        progress = socket.receive_json()
        assert progress["type"] == "ORDER_STATUS_CHANGED"
        assert progress["status"] == "ready"
        assert progress["kitchen_status"] == "ready"
        assert progress["ticket_id"] == ticket["id"]
        assert progress["order_id"] == order["id"]
        assert socket.receive_json()["type"] == "KDS_ITEM_READY"
        assert status(client, ticket["id"], "PREPARING").status_code == 409
        bumped = status(client, ticket["id"], "BUMPED").json()
        assert bumped["bumped_at"] is not None and bumped["ready_at"] is not None
        completed = socket.receive_json()
        assert completed["type"] == "ORDER_STATUS_CHANGED"
        assert completed["status"] == "completed"
        assert completed["kitchen_status"] == "bumped"
        changed = board(client, bar, bar_board["server_time"])["tickets"]
        assert [item["status"] for item in changed] == ["BUMPED"]
        recalled = client.post(f"/api/v1/kds/tickets/{ticket['id']}/recall", headers=device())
        assert recalled.status_code == 200 and recalled.json()["status"] == "READY"
        assert socket.receive_json()["status"] == "ready"
    refreshed = client.get(f"/api/v1/orders/{order['id']}", headers=device()).json()
    assert refreshed["items"][0]["kitchen_status"] == "ready"

    burger_item = next(item for item in refreshed["items"] if item["product_id"] == BURGER_ID)
    voided = client.post(
        f"/api/v1/orders/{order['id']}/items/{burger_item['id']}/void",
        headers=device(),
        json={
            "revision": refreshed["revision"],
            "user_id": CASHIER_ID,
            "reason": "Kitchen ran out",
            "approved_by_id": admin_id(client),
        },
    )
    assert voided.status_code == 200, voided.text
    kitchen_ticket = board(client, kitchen)["tickets"][0]
    assert kitchen_ticket["status"] == "BUMPED" and kitchen_ticket["items"][0]["voided_at"] is not None


def test_counter_sales_fire_without_an_order(client, session: Session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    enable(client, token, *MODULES)
    bar, _ = stations(client, token, session)
    table = floor_table(client, token)
    order = open_order(client, table, line())
    sale = settle(order, [order["items"][0]["id"]])
    sale.pop("order_id")
    sale.pop("order_item_ids")
    sale["sold_at"] = datetime.now(UTC).isoformat()
    assert push(client, "sale", sale).status_code == 200
    tickets = session.scalars(select(KitchenTicket).where(KitchenTicket.sale_id == uuid.UUID(sale["id"]))).all()
    assert len(tickets) == 1 and tickets[0].station_id == uuid.UUID(bar["id"]) and tickets[0].number == 1
