"""Table reservations for restaurant and cafe: booking, seating, history, and isolation."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.test_orders import line, open_order, settle, setup
from tests.test_returns import CASHIER_ID, STORE_ID, bearer, device, push

from app.models import BusinessSettings, Reservation, TableActivityEvent, User
from app.services.settings_service import clear_settings_cache
from app.tenancy.scoping import INCLUDE_ALL

WHEN = "2026-11-02T12:00:00+04:00"


def _at(hour: int, day: int = 2) -> str:
    return f"2026-11-{day:02d}T{hour:02d}:00:00+04:00"


def _customer(client, token: str, name: str = "Noor", phone: str = "+971500000001", **extra) -> dict:
    response = client.post("/api/v1/customers", headers=bearer(token), json={"name": name, "phone": phone, **extra})
    assert response.status_code in (200, 201), response.text
    return response.json()


def _book(client, token: str, table: dict, **extra) -> object:
    body = {
        "store_id": STORE_ID,
        "table_id": table["id"],
        "starts_at": WHEN,
        "guest_count": 2,
        "source": "portal",
    }
    body.update(extra)
    return client.post("/api/v1/reservations", headers=bearer(token), json=body)


def _ready(client, token: str, table: dict, customer: dict) -> dict:
    created = _book(client, token, table, customer_id=customer["id"])
    assert created.status_code == 201, created.text
    arrived = client.post(f"/api/v1/reservations/{created.json()['id']}/arrive", headers=bearer(token))
    assert arrived.status_code == 200, arrived.text
    seated = client.post(f"/api/v1/reservations/{created.json()['id']}/seat", headers=bearer(token))
    assert seated.status_code == 200, seated.text
    return seated.json()


def test_reservation_requires_a_customer_and_confirms_with_a_table(client) -> None:
    token, table = setup(client)
    missing = client.post(
        "/api/v1/reservations",
        headers=bearer(token),
        json={"store_id": STORE_ID, "table_id": table["id"], "starts_at": WHEN, "guest_count": 2},
    )
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "customer_required"

    customer = _customer(client, token)
    created = _book(client, token, table, customer_id=customer["id"])
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["customer_id"] == customer["id"]
    assert body["status"] == "confirmed"
    assert body["table_id"] == table["id"]
    assert body["notification_status"] != "delivered"


def test_reservation_can_create_the_customer(client) -> None:
    token, table = setup(client)
    created = _book(
        client,
        token,
        table,
        customer={"name": "Lina", "phone": "+971500000002"},
        starts_at=_at(13),
    )
    assert created.status_code == 201, created.text
    assert created.json()["customer_name"] == "Lina"
    assert created.json()["customer_phone"] == "+971500000002"


def test_confirmation_needs_a_table(client) -> None:
    token, _table = setup(client)
    customer = _customer(client, token)
    created = client.post(
        "/api/v1/reservations",
        headers=bearer(token),
        json={"store_id": STORE_ID, "customer_id": customer["id"], "starts_at": WHEN, "guest_count": 2},
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "pending"
    confirmed = client.post(f"/api/v1/reservations/{created.json()['id']}/confirm", headers=bearer(token))
    assert confirmed.status_code == 422
    assert confirmed.json()["error"]["code"] == "invalid_table"


def test_availability_and_double_booking(client) -> None:
    token, table = setup(client)
    customer = _customer(client, token)
    free = client.get(
        "/api/v1/reservations/availability",
        headers=bearer(token),
        params={"store_id": STORE_ID, "starts_at": WHEN, "guest_count": 2},
    )
    assert free.status_code == 200, free.text
    assert free.json()["tables"][0]["available"] is True
    first = _book(client, token, table, customer_id=customer["id"])
    assert first.status_code == 201, first.text
    second = _book(client, token, table, customer_id=customer["id"])
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "table_unavailable"
    busy = client.get(
        "/api/v1/reservations/availability",
        headers=bearer(token),
        params={"store_id": STORE_ID, "starts_at": WHEN, "guest_count": 2},
    )
    assert busy.json()["tables"][0]["available"] is False


def test_a_later_party_can_use_the_same_table(client) -> None:
    token, table = setup(client)
    customer = _customer(client, token)
    assert _book(client, token, table, customer_id=customer["id"], starts_at=_at(12)).status_code == 201
    later = _book(client, token, table, customer_id=customer["id"], starts_at=_at(18))
    assert later.status_code == 201, later.text


def test_arrival_seating_attaches_the_customer_and_the_order(client) -> None:
    token, table = setup(client)
    customer = _customer(client, token)
    seated = _ready(client, token, table, customer)
    assert seated["customer_id"] == customer["id"]
    order = client.get(f"/api/v1/orders/{seated['order_id']}", headers=device())
    assert order.status_code == 200, order.text
    assert order.json()["customer_id"] == customer["id"]
    assert order.json()["table_id"] == table["id"]
    added = client.post(
        f"/api/v1/orders/{seated['order_id']}/items",
        headers=device(),
        json={"revision": order.json()["revision"], "user_id": CASHIER_ID, "items": [line(), line()]},
    )
    assert added.status_code == 200, added.text
    history = client.get(f"/api/v1/reservations/tables/{table['id']}/history", headers=bearer(token))
    assert history.status_code == 200, history.text
    kinds = [item["event_type"] for item in history.json()["events"]]
    assert "customer_arrived" in kinds
    assert "customer_seated" in kinds
    assert "customer_attached" in kinds
    assert "items_added" in kinds
    seated_events = [item for item in history.json()["events"] if item["event_type"] == "customer_seated"]
    assert all(item["customer_id"] == customer["id"] for item in seated_events)


def test_walk_in_does_not_create_a_reservation(client) -> None:
    token, table = setup(client)
    customer = _customer(client, token, name="Walk In", phone="+971500000003")
    seated = client.post(
        "/api/v1/reservations/walk-ins",
        headers=bearer(token),
        json={"store_id": STORE_ID, "table_id": table["id"], "customer_id": customer["id"], "guest_count": 2},
    )
    assert seated.status_code == 201, seated.text
    assert seated.json()["reservation_id"] is None
    listed = client.get("/api/v1/reservations", headers=bearer(token), params={"store_id": STORE_ID})
    assert listed.json() == []
    anonymous = client.post(
        "/api/v1/reservations/walk-ins",
        headers=bearer(token),
        json={"store_id": STORE_ID, "table_id": table["id"], "guest_count": 1},
    )
    assert anonymous.status_code == 422
    assert anonymous.json()["error"]["code"] == "customer_required"


def test_cancellation_keeps_its_reason_and_does_not_void_an_open_order(client) -> None:
    token, table = setup(client)
    customer = _customer(client, token)
    created = _book(client, token, table, customer_id=customer["id"], starts_at=_at(19))
    assert created.status_code == 201, created.text
    reservation_id = created.json()["id"]
    vague = client.post(
        f"/api/v1/reservations/{reservation_id}/cancel",
        headers=bearer(token),
        json={"reason": "other"},
    )
    assert vague.status_code == 422
    assert vague.json()["error"]["code"] == "reason_required"
    order = open_order(client, table, line())
    cancelled = client.post(
        f"/api/v1/reservations/{reservation_id}/cancel",
        headers=bearer(token),
        json={"reason": "customer_request", "notified": True},
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["customer_notified"] is True
    still = client.get(f"/api/v1/orders/{order['id']}", headers=device())
    assert still.json()["status"] == "OPEN"


def test_no_show_waits_for_the_grace_period(client, session: Session) -> None:
    token, table = setup(client)
    customer = _customer(client, token)
    created = _book(client, token, table, customer_id=customer["id"])
    early = client.post(f"/api/v1/reservations/{created.json()['id']}/no-show", headers=bearer(token), json={})
    assert early.status_code == 409
    assert early.json()["error"]["code"] == "grace_period"
    row = session.get(Reservation, uuid.UUID(created.json()["id"]))
    assert row is not None
    row.starts_at = datetime.now(UTC) - timedelta(hours=2)
    row.ends_at = row.starts_at + timedelta(minutes=90)
    row.blocked_until = row.ends_at
    session.commit()
    late = client.post(
        f"/api/v1/reservations/{created.json()['id']}/no-show",
        headers=bearer(token),
        json={"notes": "Did not arrive"},
    )
    assert late.status_code == 200, late.text
    assert late.json()["status"] == "no_show"


def test_checkout_releases_the_table_and_keeps_earlier_history(client) -> None:
    token, table = setup(client)
    customer = _customer(client, token)
    seated = _ready(client, token, table, customer)
    order = client.get(f"/api/v1/orders/{seated['order_id']}", headers=device()).json()
    added = client.post(
        f"/api/v1/orders/{order['id']}/items",
        headers=device(),
        json={"revision": order["revision"], "user_id": CASHIER_ID, "items": [line()]},
    )
    assert added.status_code == 200, added.text
    paid = push(client, "sale", settle(added.json(), [added.json()["items"][0]["id"]]))
    assert paid.status_code == 200, paid.text
    history = client.get(f"/api/v1/reservations/tables/{table['id']}/history", headers=bearer(token)).json()
    kinds = [item["event_type"] for item in history["events"]]
    assert "payment" in kinds
    assert "table_released" in kinds
    assert "table_available" in kinds
    again = client.post(
        "/api/v1/reservations/walk-ins",
        headers=bearer(token),
        json={
            "store_id": STORE_ID,
            "table_id": table["id"],
            "customer": {"name": "Second sitting", "phone": "+971500000004"},
            "guest_count": 2,
        },
    )
    assert again.status_code == 201, again.text
    later = client.get(f"/api/v1/reservations/tables/{table['id']}/history", headers=bearer(token)).json()
    kept = [item for item in later["events"] if item["event_type"] == "customer_seated"]
    assert any(item["customer_id"] == customer["id"] for item in kept)
    assert any(item["description"].startswith("Walk-in") for item in later["events"])


def test_history_defaults_to_the_previous_24_hours_and_is_append_only(client, session: Session) -> None:
    token, table = setup(client)
    customer = _customer(client, token)
    _ready(client, token, table, customer)
    recent = client.get(f"/api/v1/reservations/tables/{table['id']}/history", headers=bearer(token))
    assert recent.status_code == 200, recent.text
    assert recent.json()["events"]
    window = recent.json()
    started = datetime.fromisoformat(window["starts_at"])
    ended = datetime.fromisoformat(window["ends_at"])
    assert ended - started <= timedelta(hours=24, minutes=1)
    assert ended - started >= timedelta(hours=23, minutes=59)
    empty = client.get(
        f"/api/v1/reservations/tables/{table['id']}/history",
        headers=bearer(token),
        params={"from": "2020-01-01T00:00:00Z", "to": "2020-01-02T00:00:00Z"},
    )
    assert empty.json()["events"] == []
    kept = client.get(
        f"/api/v1/reservations/tables/{table['id']}/history",
        headers=bearer(token),
        params={"from": (datetime.now(UTC) - timedelta(days=2)).isoformat()},
    )
    assert kept.json()["events"]
    removed = client.delete(f"/api/v1/reservations/tables/{table['id']}/history", headers=bearer(token))
    assert removed.status_code == 405
    event_id = uuid.UUID(recent.json()["events"][0]["id"])
    with pytest.raises(RuntimeError, match="cannot be changed"):
        session.delete(session.get(TableActivityEvent, event_id))
        session.flush()
    session.rollback()


def test_branches_and_tenants_stay_separate(client, session: Session) -> None:
    token, table = setup(client)
    customer = _customer(client, token)
    _book(client, token, table, customer_id=customer["id"])
    other_store = str(uuid.uuid4())
    stored = push(client, "store", {"id": other_store, "code": "BR-02", "name": "Harbour", "currency": "USD"})
    assert stored.status_code == 200
    area = client.post(
        "/api/v1/dining/areas", headers=bearer(token), json={"store_id": other_store, "name": "Harbour room"}
    )
    assert area.status_code == 201, area.text
    other_table = client.post(
        "/api/v1/dining/tables",
        headers=bearer(token),
        json={"area_id": area.json()["areas"][0]["id"], "label": "H1", "seats": 2},
    )
    assert other_table.status_code == 201, other_table.text
    harbour = other_table.json()["areas"][0]["tables"][0]
    booked = client.post(
        "/api/v1/reservations",
        headers=bearer(token),
        json={
            "store_id": other_store,
            "table_id": harbour["id"],
            "customer_id": customer["id"],
            "starts_at": _at(14),
            "guest_count": 2,
        },
    )
    assert booked.status_code == 201, booked.text
    own = client.get(f"/api/v1/reservations/tables/{table['id']}/history", headers=bearer(token)).json()
    assert all(item["store_id"] == STORE_ID for item in own["events"])
    user = session.get(User, uuid.UUID(CASHIER_ID))
    assert user is not None
    user.store_id = uuid.UUID(STORE_ID)
    session.commit()
    cashier = client.post("/api/v1/auth/login-pin", json={"username": "cashier", "pin": "1357"}, headers=device())
    assert cashier.status_code == 200, cashier.text
    cashier_token = cashier.json()["access_token"]
    denied = client.get(
        "/api/v1/reservations",
        headers={"Authorization": f"Bearer {cashier_token}"},
        params={"store_id": other_store},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "store_scope"
    foreign_id = uuid.uuid4()
    session.info[INCLUDE_ALL] = True
    session.add(
        TableActivityEvent(
            id=foreign_id,
            tenant_id=uuid.uuid4(),
            store_id=uuid.UUID(STORE_ID),
            table_id=uuid.UUID(table["id"]),
            event_type="foreign",
            description="Another tenant",
        )
    )
    session.commit()
    session.info.pop(INCLUDE_ALL, None)
    visible = client.get(f"/api/v1/reservations/tables/{table['id']}/history", headers=bearer(token)).json()
    assert all(item["id"] != str(foreign_id) for item in visible["events"])


def test_cashier_cannot_read_table_history(client) -> None:
    token, table = setup(client)
    customer = _customer(client, token)
    _ready(client, token, table, customer)
    admin = client.get(f"/api/v1/reservations/tables/{table['id']}/history", headers=bearer(token))
    assert admin.status_code == 200
    cashier = client.post("/api/v1/auth/login-pin", json={"username": "cashier", "pin": "1357"}, headers=device())
    cashier_token = cashier.json()["access_token"]
    denied = client.get(
        f"/api/v1/reservations/tables/{table['id']}/history",
        headers={"Authorization": f"Bearer {cashier_token}"},
    )
    assert denied.status_code == 403
    device_denied = client.get(f"/api/v1/reservations/tables/{table['id']}/history", headers=device())
    assert device_denied.status_code == 403


def test_reservation_changes_are_published(client, monkeypatch: pytest.MonkeyPatch) -> None:
    token, table = setup(client)
    customer = _customer(client, token)
    seen: list[dict] = []
    monkeypatch.setattr("app.websockets.table_sync.publish", lambda _store, event: seen.append(event))
    created = _book(client, token, table, customer_id=customer["id"])
    assert created.status_code == 201, created.text
    assert any(event["type"] == "RESERVATION_CHANGED" and event["status"] == "confirmed" for event in seen)


def test_an_offline_order_cannot_replace_the_seated_party(client) -> None:
    token, table = setup(client)
    customer = _customer(client, token)
    seated = _ready(client, token, table, customer)
    pushed = push(
        client,
        "open_order",
        {
            "id": str(uuid.uuid4()),
            "store_id": STORE_ID,
            "table_id": table["id"],
            "covers": 2,
            "opened_by_id": CASHIER_ID,
            "service_type": "DINE_IN",
            "opened_at": datetime.now(UTC).isoformat(),
            "items": [],
        },
    )
    assert pushed.status_code == 422, pushed.text
    assert pushed.json()["error"]["code"] == "sync_rejected"
    order = client.get(f"/api/v1/orders/{seated['order_id']}", headers=device())
    assert order.json()["customer_id"] == customer["id"]
    assert order.json()["status"] == "OPEN"


def test_hours_notice_and_date_boundaries(client) -> None:
    token, table = setup(client)
    customer = _customer(client, token)
    early = _book(client, token, table, customer_id=customer["id"], starts_at=_at(8))
    assert early.status_code == 422
    assert early.json()["error"]["code"] == "reservation_rules"
    late = _book(client, token, table, customer_id=customer["id"], starts_at="2026-11-02T23:30:00+04:00")
    assert late.status_code == 422
    boundary = _book(client, token, table, customer_id=customer["id"], starts_at="2026-11-02T00:30:00+04:00")
    assert boundary.status_code == 422
    override = _book(
        client,
        token,
        table,
        customer_id=customer["id"],
        starts_at=_at(8),
        override_reason="Private breakfast",
    )
    assert override.status_code == 201, override.text
    open_ok = _book(client, token, table, customer_id=customer["id"], starts_at=_at(10))
    assert open_ok.status_code == 409 or open_ok.status_code == 201


def test_only_restaurant_and_cafe_can_reserve(client, session: Session) -> None:
    token, table = setup(client)
    customer = _customer(client, token)
    row = session.scalar(select(BusinessSettings))
    assert row is not None
    row.business_profile = "quick_service"
    session.commit()
    clear_settings_cache()
    denied = _book(client, token, table, customer_id=customer["id"])
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "reservations_unavailable"


def test_invalid_status_changes_are_rejected(client) -> None:
    token, table = setup(client)
    customer = _customer(client, token)
    created = _book(client, token, table, customer_id=customer["id"], starts_at=_at(16))
    rejected = client.post(
        f"/api/v1/reservations/{created.json()['id']}/seat",
        headers=bearer(token),
    )
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "invalid_transition"
    seated = _ready(client, token, table, _customer(client, token, name="Other", phone="+971500000009"))
    cancelled = client.post(
        f"/api/v1/reservations/{seated['reservation_id']}/cancel",
        headers=bearer(token),
        json={"reason": "customer_request"},
    )
    assert cancelled.status_code == 409
