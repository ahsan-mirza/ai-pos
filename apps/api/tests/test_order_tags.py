"""Takeaway and delivery tags are issued once and are not rewritten by a later edit."""

import uuid

from sqlalchemy import select

from app.models import AuditLog
from tests.test_orders import setup
from tests.test_returns import CASHIER_ID, STORE_ID, device


def issue(client, order_id: str, service: str = "TAKEAWAY", tag: str | None = None):
    body = {"id": order_id, "store_id": STORE_ID, "service_type": service}
    if tag is not None:
        body["display_tag"] = tag
    return client.post("/api/v1/orders/tags", headers=device(), json=body)


def test_tags_are_unique_stable_and_reject_a_typed_server_number(client, session) -> None:
    setup(client)
    first = str(uuid.uuid4())
    opened = issue(client, first)
    assert opened.status_code == 200, opened.text
    assert opened.json()["tag"] == "TW001"
    assert issue(client, first).json()["tag"] == "TW001"

    second = issue(client, str(uuid.uuid4()))
    assert second.status_code == 200, second.text
    assert second.json()["tag"] == "TW002"
    assert second.json()["tag"] != opened.json()["tag"]

    forged = issue(client, str(uuid.uuid4()), tag="TW009")
    assert forged.status_code == 422
    assert "typed" in forged.json()["error"]["message"].lower() or "assigned" in forged.json()["error"]["message"].lower()

    offline_id = str(uuid.uuid4())
    offline = issue(client, offline_id, tag="TW-AB12-001")
    assert offline.status_code == 200, offline.text
    assert offline.json()["tag"] == "TW-AB12-001"
    assert issue(client, offline_id, tag="TW-AB12-002").status_code == 422
    clash = issue(client, str(uuid.uuid4()), tag="TW-AB12-001")
    assert clash.status_code == 409

    delivery = issue(client, str(uuid.uuid4()), "DELIVERY")
    assert delivery.status_code == 200, delivery.text
    assert delivery.json()["tag"] == "DL001"

    other_store = issue(client, str(uuid.uuid4()))
    # The device is bound to this store. A different store is refused before a tag is minted.
    scoped = client.post(
        "/api/v1/orders/tags",
        headers=device(),
        json={"id": str(uuid.uuid4()), "store_id": str(uuid.uuid4()), "service_type": "TAKEAWAY"},
    )
    assert scoped.status_code == 404, scoped.text
    assert other_store.status_code == 200

    created = client.post(
        "/api/v1/orders",
        headers=device(),
        json={
            "id": first,
            "store_id": STORE_ID,
            "service_type": "TAKEAWAY",
            "user_id": CASHIER_ID,
            "name": "Amina",
            "display_tag": "TW001",
            "items": [],
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["display_tag"] == "TW001"
    changed = client.patch(
        f"/api/v1/orders/{first}",
        headers=device(),
        json={"revision": created.json()["revision"], "user_id": CASHIER_ID, "name": "Noura", "display_tag": "TW999"},
    )
    assert changed.status_code == 422
    updated = client.patch(
        f"/api/v1/orders/{first}",
        headers=device(),
        json={"revision": created.json()["revision"], "user_id": CASHIER_ID, "name": "Noura"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Noura"
    assert updated.json()["display_tag"] == "TW001"
    assert updated.json()["number"] == created.json()["number"]

    trail = session.scalar(select(AuditLog).where(AuditLog.action == "order.tag_issued", AuditLog.target_entity_id == uuid.UUID(first)))
    assert trail is not None
    assert trail.new_values["tag"] == "TW001"
    issued = session.scalars(select(AuditLog).where(AuditLog.action == "order.tag_issued")).all()
    assert all((row.new_values or {}).get("tag") != "TW009" for row in issued)
