import uuid
from datetime import UTC, datetime

from wholesale_support import CABLE, CASHIER_ID, STORE, admin, event, line, push, sale, seed


def shift_body(shift_id: str, **extra) -> dict:
    body = {
        "id": shift_id,
        "store_id": STORE,
        "opened_by_id": CASHIER_ID,
        "opened_at": datetime.now(UTC).isoformat(),
        "opening_float_cents": 20_000,
        "currency": "USD",
        "status": "OPEN",
    }
    body.update(extra)
    return body


def movement(shift_id: str, kind: str, amount: int, reason: str = "Petty cash") -> dict:
    return {
        "id": str(uuid.uuid4()),
        "shift_id": shift_id,
        "store_id": STORE,
        "user_id": CASHIER_ID,
        "kind": kind,
        "amount_cents": amount,
        "currency": "USD",
        "reason": reason,
        "occurred_at": datetime.now(UTC).isoformat(),
    }


def test_shift_close_reconciles_cash_and_issues_z(client) -> None:
    seed(client)
    headers, _ = admin(client)
    shift_id = str(uuid.uuid4())
    cash_sale = sale(
        [line(CABLE, 2, 1500)], shift_id=shift_id, tenders=[{"method": "cash", "amount_cents": 3000, "reference": ""}]
    )
    card_sale = sale(
        [line(CABLE, 1, 1500)],
        shift_id=shift_id,
        payment_method="card",
        tenders=[{"method": "card", "amount_cents": 1500, "reference": ""}],
    )
    events = [
        event("shift-open-key", "register_shift", shift_body(shift_id)),
        event("shift-sale-cash", "sale", cash_sale),
        event("shift-sale-card", "sale", card_sale),
        event("shift-payout", "cash_movement", movement(shift_id, "PAY_OUT", 500)),
        event("shift-drop", "cash_movement", movement(shift_id, "CASH_DROP", 10_000, "Safe drop")),
        event("shift-nosale", "cash_movement", movement(shift_id, "NO_SALE", 0, "")),
    ]
    response = push(client, events)
    assert response.status_code == 200, response.text
    assert {item["status"] for item in response.json()["results"]} == {"applied"}

    live = client.get(f"/api/v1/shifts/{shift_id}", headers=headers).json()
    assert live["status"] == "OPEN"
    assert live["expected_cash_cents"] == 20_000 + 3000 - 500 - 10_000
    assert live["report"]["tenders"] == {"cash": 3000, "card": 1500}

    closed = shift_body(
        shift_id,
        status="CLOSED",
        closed_by_id=CASHIER_ID,
        closed_at=datetime.now(UTC).isoformat(),
        counted_cash_cents=12_400,
    )
    assert push(client, [event("shift-close-key", "register_shift", closed)]).status_code == 200
    final = client.get(f"/api/v1/shifts/{shift_id}", headers=headers).json()
    assert final["status"] == "CLOSED"
    assert final["variance_cents"] == 12_400 - 12_500
    assert final["z_number"] == "DT-01-Z-000001"
    assert final["report"]["no_sale_count"] == 1

    late = push(client, [event("shift-late-move", "cash_movement", movement(shift_id, "PAY_IN", 100))])
    assert late.status_code == 422
    assert "already closed" in late.json()["error"]["message"]
    assert len(client.get("/api/v1/shifts?status=CLOSED", headers=headers).json()) == 1
