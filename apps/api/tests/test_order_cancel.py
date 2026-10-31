"""Cancellation keeps the open-order lifecycle: VOID, a reason, and the kitchen ticket. Paid sales stay refunds."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from tests.test_kds import stations, status
from tests.test_menu import enable
from tests.test_orders import line, open_order, settle, setup
from tests.test_returns import CASHIER_ID, STORE_ID, admin_id, device, push

from app.models import AuditLog, OpenOrder, Sale


def _void(client, order: dict, **extra: object):
    body = {
        "revision": order["revision"],
        "user_id": CASHIER_ID,
        "reason": "[changed_mind] Customer changed their mind.",
    }
    body.update(extra)
    return client.post(f"/api/v1/orders/{order['id']}/void", headers=device(), json=body)


def _audit(session: Session) -> AuditLog:
    row = session.scalar(select(AuditLog).where(AuditLog.action == "order.void").order_by(AuditLog.occurred_at.desc()))
    assert row is not None
    return row


def test_unsubmitted_order_cancels_with_a_reason_and_does_not_touch_stock(client, session: Session) -> None:
    _token, table = setup(client)
    order = open_order(client, table, line())
    cancelled = _void(client, order, reason="[duplicate] Duplicate order.")
    assert cancelled.status_code == 200, cancelled.text
    body = cancelled.json()
    assert body["status"] == "VOID"
    assert body["items"][0]["void_reason"] == "[duplicate] Duplicate order."
    session.expire_all()
    entry = _audit(session)
    assert entry.details["stage"] == "draft"
    assert entry.details["previous_status"] == "OPEN"
    assert entry.details["inventory"] == "none_reserved"
    assert entry.details["reason_code"] == "duplicate"
    assert entry.approver_id is None
    assert session.scalar(select(func.count()).select_from(Sale).where(Sale.order_id == uuid.UUID(order["id"]))) == 0
    again = _void(client, body, reason="[wrong_item] Wrong items ordered.")
    assert again.status_code == 200 and again.json()["status"] == "VOID"
    assert session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "order.void")) == 1


def test_kitchen_sent_order_needs_approval_and_notifies_the_kitchen(client, session: Session) -> None:
    token, table = setup(client)
    enable(client, token, "kds")
    bar, _kitchen = stations(client, token, session)
    order = open_order(client, table, line())
    sent = client.post(
        f"/api/v1/orders/{order['id']}/send",
        headers=device(),
        json={"revision": order["revision"], "user_id": CASHIER_ID},
    )
    assert sent.status_code == 200, sent.text
    order = sent.json()
    refused = _void(client, order)
    assert refused.status_code == 403 and refused.json()["error"]["code"] == "approval_required"
    assert client.get(f"/api/v1/orders/{order['id']}", headers=device()).json()["status"] == "OPEN"
    approved = _void(
        client,
        order,
        approved_by_id=admin_id(client),
        reason="[changed_mind] Customer changed their mind.",
    )
    assert approved.status_code == 200, approved.text
    session.expire_all()
    entry = _audit(session)
    assert entry.details["stage"] == "kitchen"
    assert entry.details["kitchen_notified"] is True
    assert entry.user_id == uuid.UUID(CASHIER_ID)
    assert entry.approver_id == uuid.UUID(admin_id(client))
    tickets = client.get(f"/api/v1/kds/orders/{order['id']}/tickets", headers=device()).json()
    assert tickets and tickets[0]["status"] == "BUMPED"
    assert tickets[0]["items"][0]["voided_at"] is not None
    assert bar["id"]


def test_preparation_and_ready_record_wastage_without_restocking(client, session: Session) -> None:
    token, table = setup(client)
    enable(client, token, "kds")
    bar, _kitchen = stations(client, token, session)
    order = open_order(client, table, line())
    sent = client.post(
        f"/api/v1/orders/{order['id']}/send", headers=device(), json={"revision": 1, "user_id": CASHIER_ID}
    ).json()
    ticket = client.get(f"/api/v1/kds/stations/{bar['id']}/tickets", headers=device()).json()["tickets"][0]
    assert status(client, ticket["id"], "PREPARING").status_code == 200
    preparing = _void(
        client,
        sent,
        approved_by_id=admin_id(client),
        reason="[operational] Kitchen unable to fulfill order.",
    )
    assert preparing.status_code == 200, preparing.text
    session.expire_all()
    assert _audit(session).details["inventory"] == "wastage_recorded"

    ready_order = open_order(client, table, line())
    ready_sent = client.post(
        f"/api/v1/orders/{ready_order['id']}/send",
        headers=device(),
        json={"revision": 1, "user_id": CASHIER_ID},
    ).json()
    ready_ticket = client.get(f"/api/v1/kds/orders/{ready_order['id']}/tickets", headers=device()).json()[0]
    assert status(client, ready_ticket["id"], "READY").status_code == 200
    refused = _void(client, ready_sent)
    assert refused.status_code == 403
    ready = _void(client, ready_sent, approved_by_id=admin_id(client), reason="[stock] Item unavailable.")
    assert ready.status_code == 200, ready.text
    session.expire_all()
    assert _audit(session).details["stage"] == "ready"


def test_dispatched_order_waits_for_a_return_and_a_manager(client, session: Session) -> None:
    _token, table = setup(client)
    order = open_order(client, table, line())
    row = session.get(OpenOrder, uuid.UUID(order["id"]))
    row.channel_status = "ACCEPTED"
    session.commit()
    refused = _void(client, order, reason="[delivery] Delivery unavailable.")
    assert refused.status_code == 403
    cancelled = _void(client, order, approved_by_id=admin_id(client), reason="[delivery] Delivery unavailable.")
    assert cancelled.status_code == 200, cancelled.text
    session.expire_all()
    details = _audit(session).details
    assert details["stage"] == "dispatched"
    assert details["inventory"] == "awaiting_return"
    assert details["delivery_notified"] is True


def test_completed_sale_is_a_refund_not_a_void(client, session: Session) -> None:
    _token, table = setup(client)
    order = open_order(client, table, line())
    paid = push(client, "sale", settle(order, [order["items"][0]["id"]]))
    assert paid.status_code == 200, paid.text
    session.expire_all()
    closed = session.get(OpenOrder, uuid.UUID(order["id"]))
    assert closed.status == "SETTLED"
    refused = _void(client, {**order, "revision": closed.revision})
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "already_paid"
    session.expire_all()
    assert session.get(OpenOrder, uuid.UUID(order["id"])).status == "SETTLED"
    assert session.scalar(select(func.count()).select_from(Sale).where(Sale.order_id == uuid.UUID(order["id"]))) == 1


def test_unauthorized_and_other_branch_cannot_cancel(client, session: Session) -> None:
    from types import SimpleNamespace

    from app.core.errors import ApiError
    from app.services.order_service import _scope

    _token, table = setup(client)
    order = open_order(client, table, line())
    stranger = _void(client, order, user_id=str(uuid.uuid4()))
    assert stranger.status_code == 403
    try:
        _scope(SimpleNamespace(store_id=uuid.uuid4()), uuid.UUID(order["store_id"]))
    except ApiError as exc:
        assert exc.status_code == 403 and exc.code == "store_scope"
    else:
        raise AssertionError("another branch was allowed to cancel")
    assert session.get(OpenOrder, uuid.UUID(order["id"])).status == "OPEN"


def test_a_stale_revision_does_not_cancel_twice(client, session: Session) -> None:
    _token, table = setup(client)
    order = open_order(client, table, line())
    added = client.post(
        f"/api/v1/orders/{order['id']}/items",
        headers=device(),
        json={"revision": order["revision"], "user_id": CASHIER_ID, "items": [line()]},
    )
    assert added.status_code == 200, added.text
    stale = _void(client, order)
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "stale_order"
    assert client.get(f"/api/v1/orders/{order['id']}", headers=device()).json()["status"] == "OPEN"


def test_customer_event_omits_the_reason(client) -> None:
    from tests.test_returns import API_KEY

    _token, table = setup(client)
    order = open_order(client, table, line())
    with client.websocket_connect(f"/api/v1/ws/stores/{STORE_ID}/tables?token={API_KEY}") as socket:
        cancelled = _void(client, order, reason="[price] Incorrect pricing.")
        assert cancelled.status_code == 200, cancelled.text
        event = socket.receive_json()
    assert event["type"] == "ORDER_CANCELLED"
    assert "price" not in event["message"].lower()
    assert "reason" not in event


def test_offline_void_syncs_without_deleting_the_order(client, session: Session) -> None:
    _token, table = setup(client)
    order = open_order(client, table, line())
    item = order["items"][0]
    payload = {
        "id": order["id"],
        "store_id": STORE_ID,
        "service_type": "DINE_IN",
        "table_id": table["id"],
        "covers": 1,
        "opened_by_id": CASHIER_ID,
        "opened_at": "2026-10-31T12:00:00Z",
        "items": [
            {
                "id": item["id"],
                "product_id": item["product_id"],
                "quantity": item["quantity"],
                "unit_price_cents": item["unit_price_cents"],
                "voided_at": "2026-10-31T12:05:00Z",
                "void_reason": "[entry_mistake] Placed by mistake.",
            }
        ],
    }
    synced = client.post(
        "/api/v1/sync/push",
        headers=device(),
        json={
            "device_id": "register-1",
            "events": [
                {
                    "idempotency_key": f"void-{order['id']}",
                    "entity_type": "open_order",
                    "operation": "upsert",
                    "payload": payload,
                    "occurred_at": "2026-10-31T12:05:00Z",
                }
            ],
        },
    )
    assert synced.status_code == 200, synced.text
    session.expire_all()
    stored = session.get(OpenOrder, uuid.UUID(order["id"]))
    assert stored.status == "VOID"
    assert stored.items[0].void_reason == "[entry_mistake] Placed by mistake."
    assert client.get(f"/api/v1/orders/{order['id']}", headers=device()).json()["id"] == order["id"]
