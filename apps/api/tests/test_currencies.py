import uuid
from datetime import UTC, datetime

from app.core.config import get_settings
from app.services import fx_service
from test_shifts import shift_body
from wholesale_support import CABLE, CASHIER_ID, admin, device, event, line, push, sale, seed


def test_foreign_cash_tenders_and_drawer_split(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    added = client.post("/api/v1/currencies", headers=headers, json={"code": "eur", "rate_micros": 1_100_000})
    assert added.status_code == 201, added.text
    assert added.json()[0]["code"] == "EUR" and added.json()[0]["rate_micros"] == 1_100_000
    assert client.get("/api/v1/currencies", headers=device()).json()[0]["base_currency"] == "USD"

    shift_id = str(uuid.uuid4())
    assert (
        push(
            client, [event("fx-shift-open", "register_shift", shift_body(shift_id, opening_float_cents=10_000))]
        ).status_code
        == 200
    )

    def euro_sale(received: int, change: int, rate: int = 1_100_000) -> dict:
        return sale(
            [line(CABLE, 2, 1500)],
            shift_id=shift_id,
            tenders=[
                {
                    "method": "cash",
                    "amount_cents": 3000,
                    "currency": "EUR",
                    "foreign_amount_cents": received,
                    "rate_micros": rate,
                    "change_cents": change,
                }
            ],
        )

    wrong = push(client, [event("fx-sale-wrong", "sale", euro_sale(2000, 0))])
    assert wrong.status_code == 422 and "does not match" in wrong.json()["error"]["message"]
    stale = push(client, [event("fx-sale-stale", "sale", euro_sale(3000, 300, rate=1_000_000))])
    assert stale.status_code == 422 and "rate" in stale.json()["error"]["message"]

    ok = push(client, [event("fx-sale-good", "sale", euro_sale(3000, 300))])
    assert ok.status_code == 200, ok.text

    live = client.get(f"/api/v1/shifts/{shift_id}", headers=headers).json()
    assert live["report"]["foreign_cash"] == {"EUR": 3000}
    assert live["expected_cash_cents"] == 10_000 - 300

    closed = shift_body(
        shift_id,
        status="CLOSED",
        closed_by_id=CASHIER_ID,
        closed_at=datetime.now(UTC).isoformat(),
        counted_cash_cents=9_700,
        counted_foreign={"EUR": 2_950},
    )
    assert push(client, [event("fx-shift-close", "register_shift", closed)]).status_code == 200
    final = client.get(f"/api/v1/shifts/{shift_id}", headers=headers).json()
    assert final["variance_cents"] == 0
    assert final["report"]["foreign_counted"] == {"EUR": 2950}


def test_rate_sync_uses_the_provider(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    client.post("/api/v1/currencies", headers=headers, json={"code": "GBP"})
    updated = fx_service.sync_rates(session, get_settings(), fetch=lambda base: {"GBP": 0.8})
    assert updated == 1
    rows = client.get("/api/v1/currencies", headers=headers).json()
    assert rows[0]["rate_micros"] == 1_250_000 and rows[0]["source"] == "sync"
