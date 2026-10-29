"""Fashion rentals stay on the catalogue product and refuse overlapping bookings."""

import uuid
from datetime import date, timedelta

from sqlalchemy import select

from app.core import capabilities as catalog
from app.models.inventory import InventoryLevel
from wholesale_support import CABLE, STORE, admin, create_customer, seed


def _enable(client, headers: dict[str, str]) -> None:
    modules = [item.value for item in catalog.PROFILES["retail_fashion"]] + ["fashion_rental"]
    response = client.put(
        "/api/v1/settings/profile",
        headers=headers,
        json={"business_profile": "retail_fashion", "capabilities": modules},
    )
    assert response.status_code == 200, response.text


def _terms(client, headers: dict[str, str], **extra: object) -> None:
    body = {
        "enabled": True,
        "offer": "BOTH",
        "price_per_day_cents": 1000,
        "deposit_cents": 500,
        "min_days": 1,
        "default_days": 1,
        "buffer_days": 1,
        "late_fee_per_day_cents": 200,
        "cleaning_fee_cents": 0,
        "requires_inspection": True,
    }
    body.update(extra)
    saved = client.put(f"/api/v1/rentals/products/{CABLE}", headers=headers, json=body)
    assert saved.status_code == 200, saved.text


def _book(client, headers: dict[str, str], customer_id: str, start: date, end: date, **extra: object):
    body = {
        "client_request_id": str(uuid.uuid4()),
        "customer_id": customer_id,
        "store_id": STORE,
        "product_id": CABLE,
        "start_date": start.isoformat(),
        "return_date": end.isoformat(),
        "quantity": 1,
        "pay_charge_cents": 0,
        "pay_deposit_cents": 500,
    }
    body.update(extra)
    return client.post("/api/v1/rentals", headers=headers, json=body)


def test_overlap_deposit_and_module_gate(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    today = date.today()
    blocked = client.get("/api/v1/rentals", headers=headers)
    assert blocked.status_code == 403

    _enable(client, headers)
    level = session.scalar(select(InventoryLevel).where(InventoryLevel.product_id == uuid.UUID(CABLE)))
    assert level is not None
    level.quantity_on_hand = 1
    session.commit()
    customer = create_customer(client, headers)
    _terms(client, headers)

    first = _book(client, headers, customer["id"], today, today + timedelta(days=1))
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["deposit_held_cents"] == 500
    assert body["agreed_net_cents"] == 2000
    assert body["deposit_due_cents"] == 500

    again = _book(client, headers, customer["id"], today, today)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "rental_unavailable"

    buffered = _book(client, headers, customer["id"], today + timedelta(days=2), today + timedelta(days=2))
    assert buffered.status_code == 409

    later = _book(client, headers, customer["id"], today + timedelta(days=3), today + timedelta(days=3))
    assert later.status_code == 200, later.text

    summary = client.get(
        "/api/v1/rentals/summary",
        headers=headers,
        params={"from": today.isoformat(), "to": (today + timedelta(days=4)).isoformat()},
    )
    assert summary.status_code == 200, summary.text
    figures = summary.json()
    assert figures["deposits_held_cents"] == 1000
    assert figures["rental_revenue_cents"] == 2000 + 1000
    assert figures["rental_revenue_cents"] != figures["deposits_held_cents"]

    other = client.get("/api/v1/rentals", headers=headers, params={"store_id": str(uuid.uuid4())})
    assert other.status_code == 200
    assert other.json() == [] or all(row["store_id"] == STORE for row in other.json())


def test_a_repeated_request_does_not_create_a_second_booking(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    _enable(client, headers)
    level = session.scalar(select(InventoryLevel).where(InventoryLevel.product_id == uuid.UUID(CABLE)))
    assert level is not None
    level.quantity_on_hand = 1
    session.commit()
    customer = create_customer(client, headers)
    _terms(client, headers, buffer_days=0)
    request_id = str(uuid.uuid4())
    today = date.today()
    payload = {
        "client_request_id": request_id,
        "customer_id": customer["id"],
        "store_id": STORE,
        "product_id": CABLE,
        "start_date": today.isoformat(),
        "return_date": today.isoformat(),
        "quantity": 1,
        "pay_deposit_cents": 0,
    }
    first = client.post("/api/v1/rentals", headers=headers, json=payload)
    second = client.post("/api/v1/rentals", headers=headers, json=payload)
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    listed = client.get("/api/v1/rentals", headers=headers)
    assert len(listed.json()) == 1


def test_rental_only_items_are_refused_at_sale(client, session) -> None:
    from wholesale_support import event, line, push, sale

    seed(client)
    headers, _ = admin(client)
    _enable(client, headers)
    _terms(client, headers, offer="RENT", buffer_days=0, deposit_cents=0)
    response = push(client, [event("rent-only-sale", "sale", sale([line(CABLE, 1, 1500)]))])
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "sync_rejected"
