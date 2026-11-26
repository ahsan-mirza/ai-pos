"""Plus and minus on an open table. The original kitchen ticket is not rewritten."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from tests.test_kds import stations
from tests.test_menu import enable
from tests.test_orders import line, open_order, setup
from tests.test_returns import CASHIER_ID, admin_id, device

from app.models import AuditLog, KitchenTicket, KitchenTicketItem, StockMovement

REASON = "[wrong_quantity] Quantity reduced at the table"


def _send(client, order: dict) -> dict:
    sent = client.post(
        f"/api/v1/orders/{order['id']}/send",
        headers=device(),
        json={"revision": order["revision"], "user_id": CASHIER_ID},
    )
    assert sent.status_code == 200, sent.text
    return sent.json()


def _increase(client, order: dict, item_id: str, quantity: int, event_id: str | None = None) -> object:
    body: dict = {"revision": order["revision"], "user_id": CASHIER_ID, "quantity": quantity}
    if event_id is not None:
        body["event_id"] = event_id
    return client.post(f"/api/v1/orders/{order['id']}/items/{item_id}/increase", headers=device(), json=body)


def _decrease(client, order: dict, item_id: str, event_id: str | None = None) -> object:
    body: dict = {"revision": order["revision"], "user_id": CASHIER_ID, "reason": REASON}
    if event_id is not None:
        body["event_id"] = event_id
    return client.post(f"/api/v1/orders/{order['id']}/items/{item_id}/decrease", headers=device(), json=body)


def _live(order: dict, item_id: str) -> dict:
    return next(item for item in order["items"] if item["id"] == item_id and item["voided_at"] is None)


def test_unsent_quantity_and_removal_do_not_fire_the_kitchen(client, session: Session) -> None:
    _token, table = setup(client)
    order = open_order(client, table, line(1))
    item_id = order["items"][0]["id"]
    event = str(uuid.uuid4())
    raised = client.post(
        f"/api/v1/orders/{order['id']}/items/{item_id}/quantity",
        headers=device(),
        json={"revision": order["revision"], "user_id": CASHIER_ID, "quantity": 2, "event_id": event},
    )
    assert raised.status_code == 200, raised.text
    order = raised.json()
    assert order["items"][0]["quantity"] == 2
    assert order["open_cents"] == 3000
    replay = client.post(
        f"/api/v1/orders/{order['id']}/items/{item_id}/quantity",
        headers=device(),
        json={"revision": 1, "user_id": CASHIER_ID, "quantity": 9, "event_id": event},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["items"][0]["quantity"] == 2
    removed = client.post(
        f"/api/v1/orders/{order['id']}/items/{item_id}/void",
        headers=device(),
        json={"revision": order["revision"], "user_id": CASHIER_ID, "reason": "Removed before sending"},
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["open_cents"] == 0
    assert removed.json()["status"] == "OPEN"
    assert session.scalar(select(func.count()).select_from(KitchenTicket)) == 0


def test_plus_and_minus_keep_the_original_ticket(client, session: Session) -> None:
    token, table = setup(client)
    enable(client, token, "kds")
    stations(client, token, session)
    before = session.scalar(select(func.count()).select_from(StockMovement)) or 0
    original = line(1)
    order = _send(client, open_order(client, table, original))
    item_id = original["id"]
    blocked = _decrease(client, order, item_id)
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "original_quantity"
    sent_order = order
    event = str(uuid.uuid4())
    raised = _increase(client, sent_order, item_id, 2, event)
    assert raised.status_code == 200, raised.text
    order = raised.json()
    extra = next(item for item in order["items"] if item["id"] != item_id)
    assert extra["quantity"] == 1 and extra["source_item_id"] == item_id
    assert _live(order, item_id)["quantity"] == 1
    assert order["open_cents"] == 3000
    assert order["status"] == "OPEN"
    replay = _increase(client, order, item_id, 4, event)
    assert replay.status_code == 200, replay.text
    assert sum(item["quantity"] for item in replay.json()["items"] if item["voided_at"] is None) == 2
    stale = _increase(client, sent_order, item_id, 3, str(uuid.uuid4()))
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "stale_order"
    original_ticket = session.scalars(
        select(KitchenTicketItem).where(KitchenTicketItem.order_item_id == uuid.UUID(item_id))
    ).all()
    assert original_ticket and all(row.quantity == 1 and row.voided_at is None for row in original_ticket)
    extra_ticket = session.scalars(
        select(KitchenTicketItem).where(KitchenTicketItem.order_item_id == uuid.UUID(extra["id"]))
    ).all()
    assert extra_ticket and all(row.quantity == 1 and row.voided_at is None for row in extra_ticket)
    dropped = _decrease(client, order, item_id, str(uuid.uuid4()))
    assert dropped.status_code == 200, dropped.text
    order = dropped.json()
    assert _live(order, item_id)["quantity"] == 1
    assert all(item["id"] == item_id or item["voided_at"] is not None for item in order["items"])
    session.expire_all()
    original_ticket = session.scalars(
        select(KitchenTicketItem).where(KitchenTicketItem.order_item_id == uuid.UUID(item_id))
    ).all()
    assert all(row.quantity == 1 and row.voided_at is None for row in original_ticket)
    cancelled = session.scalars(
        select(KitchenTicketItem).where(KitchenTicketItem.order_item_id == uuid.UUID(extra["id"]))
    ).all()
    assert cancelled and all(row.voided_at is not None for row in cancelled)
    audit = session.scalar(select(AuditLog).where(AuditLog.action == "order.sent_quantity_decrease"))
    assert audit is not None and audit.user_id == uuid.UUID(CASHIER_ID) and audit.reason_notes == REASON
    stopped = _decrease(client, order, item_id)
    assert stopped.status_code == 409 and stopped.json()["error"]["code"] == "original_quantity"
    assert (session.scalar(select(func.count()).select_from(StockMovement)) or 0) == before


def test_two_extras_on_an_original_three_return_to_three(client, session: Session) -> None:
    token, table = setup(client)
    enable(client, token, "kds")
    stations(client, token, session)
    original = line(3)
    order = _send(client, open_order(client, table, original))
    item_id = original["id"]
    raised = _increase(client, order, item_id, 5)
    assert raised.status_code == 200, raised.text
    order = raised.json()
    extra = next(item for item in order["items"] if item["source_item_id"] == item_id)
    assert extra["quantity"] == 2
    order = _decrease(client, order, item_id).json()
    extra = next(item for item in order["items"] if item["id"] == extra["id"])
    assert extra["quantity"] == 1 and extra["voided_at"] is None
    order = _decrease(client, order, item_id).json()
    assert _live(order, item_id)["quantity"] == 3
    assert next(item for item in order["items"] if item["id"] == extra["id"])["voided_at"] is not None
    ticket = session.scalars(
        select(KitchenTicketItem).where(KitchenTicketItem.order_item_id == uuid.UUID(item_id))
    ).one()
    assert ticket.quantity == 3 and ticket.voided_at is None


def test_removing_a_sent_line_keeps_the_ticket_and_served_still_needs_a_manager(client, session: Session) -> None:
    token, table = setup(client)
    enable(client, token, "kds")
    stations(client, token, session)
    original = line(1)
    order = _send(client, open_order(client, table, original))
    item_id = original["id"]
    wrong = client.post(
        f"/api/v1/orders/{uuid.uuid4()}/items/{item_id}/void",
        headers=device(),
        json={"revision": order["revision"], "user_id": CASHIER_ID, "reason": "Wrong order"},
    )
    assert wrong.status_code == 404
    stranger = client.post(
        f"/api/v1/orders/{order['id']}/items/{item_id}/void",
        headers=device(),
        json={"revision": order["revision"], "user_id": str(uuid.uuid4()), "reason": "Not this cashier"},
    )
    assert stranger.status_code == 403
    removed = client.post(
        f"/api/v1/orders/{order['id']}/items/{item_id}/void",
        headers=device(),
        json={"revision": order["revision"], "user_id": CASHIER_ID, "reason": "[changed_mind] Customer changed mind"},
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["status"] == "OPEN"
    assert removed.json()["open_cents"] == 0
    session.expire_all()
    ticket = session.scalars(
        select(KitchenTicketItem).where(KitchenTicketItem.order_item_id == uuid.UUID(item_id))
    ).one()
    assert ticket.voided_at is not None
    other = line(1)
    second = _send(client, open_order(client, _another_table(client, token), other))
    other_id = other["id"]
    row = session.scalars(select(KitchenTicket).where(KitchenTicket.order_id == uuid.UUID(second["id"]))).one()
    row.status = "BUMPED"
    session.commit()
    refused = client.post(
        f"/api/v1/orders/{second['id']}/items/{other_id}/void",
        headers=device(),
        json={"revision": second["revision"], "user_id": CASHIER_ID, "reason": "Already served"},
    )
    assert refused.status_code == 403 and refused.json()["error"]["code"] == "approval_required"
    approved = client.post(
        f"/api/v1/orders/{second['id']}/items/{other_id}/void",
        headers=device(),
        json={
            "revision": second["revision"],
            "user_id": CASHIER_ID,
            "reason": "Already served",
            "approved_by_id": admin_id(client),
        },
    )
    assert approved.status_code == 200, approved.text


def _another_table(client, token: str) -> dict:
    from tests.test_returns import STORE_ID, bearer

    floor = client.post("/api/v1/dining/areas", headers=bearer(token), json={"store_id": STORE_ID, "name": "Garden"})
    area = floor.json()["areas"][0]
    tables = client.post(
        "/api/v1/dining/tables", headers=bearer(token), json={"area_id": area["id"], "label": "T9", "seats": 2}
    )
    assert tables.status_code == 201, tables.text
    return tables.json()["areas"][0]["tables"][0]
