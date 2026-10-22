import json
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session
from tests.test_menu import enable
from tests.test_orders import settle
from tests.test_returns import CASHIER_ID, STORE_ID, admin_token, bearer, device, push, seed_catalog

from app.models import OpenOrder
from app.services import channel_service

MODULES = ("menu_modifiers", "open_orders", "delivery_channels")


def channel(client, token: str, **changes) -> tuple[dict, str]:
    body = {"name": "Talabat", "code": "talabat", "store_id": STORE_ID, "commission_bps": 2000, **changes}
    response = client.post("/api/v1/channels", headers=bearer(token), json=body)
    assert response.status_code == 201, response.text
    created = response.json()
    return created["channel"], created["webhook_secret"]


def deliver(client, code: str, secret: str | None, payload: dict, *, signature: str | None = None):
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if secret is not None or signature is not None:
        headers["X-Channel-Signature"] = signature or f"sha256={channel_service.sign(secret, body)}"
    return client.post(f"/api/v1/channels/{code}/orders", content=body, headers=headers)


def incoming(external_id: str, sku: str = "ACC-CABLE-USBC") -> dict:
    return {
        "external_id": external_id,
        "customer": {"name": "Sara", "phone": "+971500000000"},
        "items": [{"sku": sku, "quantity": 2, "unit_price_cents": 1500, "note": "no ice"}],
        "paid": True,
    }


def test_webhook_orders_are_signed_deduplicated_accepted_and_settled(client, session: Session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    enable(client, token, *MODULES)
    talabat, secret = channel(client, token)
    assert talabat["webhook_path"] == "/api/v1/channels/talabat/orders"

    assert deliver(client, "talabat", None, incoming("T-1")).status_code == 401
    assert deliver(client, "talabat", None, incoming("T-1"), signature="sha256=deadbeef").status_code == 401
    unknown = deliver(client, "talabat", secret, incoming("T-0", sku="NOPE"))
    assert unknown.status_code == 422 and unknown.json()["error"]["details"]["unknown"] == ["NOPE"]

    first = deliver(client, "talabat", secret, incoming("T-1"))
    assert first.status_code == 200, first.text
    assert (first.json()["result"], first.json()["channel_status"]) == ("created", "PENDING")
    again = deliver(client, "talabat", secret, incoming("T-1"))
    assert again.json()["result"] == "duplicate" and again.json()["order_id"] == first.json()["order_id"]

    order = client.get(f"/api/v1/orders/{first.json()['order_id']}", headers=device()).json()
    assert order["service_type"] == "DELIVERY" and order["channel_name"] == "Talabat"
    assert order["items"][0]["sent_at"] is None
    accepted = client.post(
        f"/api/v1/channels/orders/{order['id']}/accept",
        headers=device(),
        json={"revision": order["revision"], "user_id": CASHIER_ID, "prep_minutes": 15},
    )
    assert accepted.status_code == 200, accepted.text
    order = accepted.json()
    assert (order["channel_status"], order["prep_minutes"]) == ("ACCEPTED", 15)
    assert all(item["sent_at"] for item in order["items"])

    sale = settle(order, [order["items"][0]["id"]])
    sale["payment_method"] = "channel"
    sale["tenders"] = [{"method": "channel", "amount_cents": sale["total_cents"], "reference": "talabat"}]
    assert push(client, "sale", sale).status_code == 200
    session.expire_all()
    settled = session.get(OpenOrder, uuid.UUID(order["id"]))
    assert (settled.status, settled.channel_status) == ("SETTLED", "COMPLETED")

    walk_in = settle(order, [order["items"][0]["id"]])
    walk_in.pop("order_id")
    walk_in.pop("order_item_ids")
    walk_in["payment_method"] = "channel"
    walk_in["tenders"] = [{"method": "channel", "amount_cents": walk_in["total_cents"], "reference": ""}]
    assert push(client, "sale", walk_in).status_code == 422

    today = datetime.now(UTC).date().isoformat()
    report = client.get(
        "/api/v1/channels/settlement", headers=bearer(token), params={"from": "2026-10-01", "to": today}
    )
    assert report.status_code == 200, report.text
    row = report.json()["rows"][0]
    gross = sale["total_cents"]
    assert (row["orders"], row["gross_cents"], row["commission_cents"]) == (1, gross, round(gross * 0.2))
    assert row["outstanding_cents"] == gross - round(gross * 0.2)
    paid = client.post(
        f"/api/v1/channels/{talabat['id']}/payouts",
        headers=bearer(token),
        json={"amount_cents": row["net_cents"], "commission_cents": row["commission_cents"], "reference": "PO-1"},
    )
    assert paid.status_code == 201, paid.text
    after = client.get("/api/v1/channels/settlement", headers=bearer(token), params={"from": "2026-10-01", "to": today})
    assert after.json()["rows"][0]["outstanding_cents"] == 0


def test_rejecting_and_keying_in_delivery_orders(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    enable(client, token, *MODULES)
    talabat, secret = channel(client, token, auto_accept=False)
    received = deliver(client, "talabat", secret, incoming("T-9")).json()
    order = client.get(f"/api/v1/orders/{received['order_id']}", headers=device()).json()
    rejected = client.post(
        f"/api/v1/channels/orders/{order['id']}/reject",
        headers=device(),
        json={"revision": order["revision"], "user_id": CASHIER_ID, "reason": "Kitchen closing"},
    )
    assert rejected.status_code == 200 and rejected.json()["status"] == "VOID"
    assert rejected.json()["channel_status"] == "REJECTED"

    keyed = client.post(
        "/api/v1/channels/manual-orders",
        headers=device(),
        json={"channel_id": talabat["id"], "external_ref": "T-10", "customer_name": "Omar", "user_id": CASHIER_ID},
    )
    assert keyed.status_code == 201, keyed.text
    assert (keyed.json()["channel_status"], keyed.json()["external_ref"]) == ("ACCEPTED", "T-10")
    twice = client.post(
        "/api/v1/channels/manual-orders",
        headers=device(),
        json={"channel_id": talabat["id"], "external_ref": "T-10", "user_id": CASHIER_ID},
    )
    assert twice.status_code == 409
    listed = client.get("/api/v1/channels", headers=device()).json()
    assert [item["code"] for item in listed] == ["talabat"] and "webhook_secret" not in listed[0]


def test_auto_accept_sends_straight_to_the_kitchen(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    enable(client, token, *MODULES)
    _, secret = channel(client, token, code="deliveroo", name="Deliveroo", auto_accept=True, default_prep_minutes=25)
    result = deliver(
        client, "deliveroo", secret, {**incoming("D-1"), "items": [{"sku": "ACC-CABLE-USBC", "quantity": 1}]}
    )
    assert result.json()["channel_status"] == "ACCEPTED"
    order = client.get(f"/api/v1/orders/{result.json()['order_id']}", headers=device()).json()
    assert order["prep_minutes"] == 25 and order["items"][0]["sent_at"] is not None
    assert order["items"][0]["unit_price_cents"] == 1500
