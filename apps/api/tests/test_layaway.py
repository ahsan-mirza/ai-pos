import uuid

from test_quotes import quote_body, reserved
from wholesale_support import CABLE, CASHIER_ID, admin, create_customer, device, event, line, push, sale, seed


def test_layaway_deposits_apply_at_pickup(client) -> None:
    seed(client)
    headers, _ = admin(client)
    customer = create_customer(client, headers, customer_type="RETAIL", price_tier="RETAIL", credit_limit_cents=0)
    body = quote_body(
        [line(CABLE, 4, 1500)],
        sale_type="RETAIL",
        customer_id=customer["id"],
        quote_kind="LAYAWAY",
        valid_days=30,
        deposit={"id": str(uuid.uuid4()), "amount_cents": 2000, "method": "cash"},
    )
    created = client.post("/api/v1/quotes", headers=device(), json=body)
    assert created.status_code == 201, created.text
    assert (created.json()["quote_kind"], created.json()["deposits_cents"]) == ("LAYAWAY", 2000)
    assert reserved(client, CABLE) == 4

    too_much = client.post(
        f"/api/v1/quotes/{body['id']}/payments",
        headers=device(),
        json={"id": str(uuid.uuid4()), "amount_cents": 5000, "method": "card", "cashier_id": CASHIER_ID},
    )
    assert too_much.status_code == 422
    second = client.post(
        f"/api/v1/quotes/{body['id']}/payments",
        headers=device(),
        json={"id": str(uuid.uuid4()), "amount_cents": 1000, "method": "card", "cashier_id": CASHIER_ID},
    )
    assert second.status_code == 200, second.text
    assert second.json()["deposits_cents"] == 3000
    assert len(second.json()["payments"]) == 2

    short = client.post(
        f"/api/v1/quotes/{body['id']}/convert",
        headers=headers,
        json={"payment_method": "cash", "tenders": [{"method": "cash", "amount_cents": 1000}]},
    )
    assert short.status_code == 422
    picked_up = client.post(
        f"/api/v1/quotes/{body['id']}/convert",
        headers=headers,
        json={"payment_method": "cash", "tenders": [{"method": "cash", "amount_cents": 3000}]},
    )
    assert picked_up.status_code == 200, picked_up.text
    result = picked_up.json()
    assert {row["status"] for row in result["payments"]} == {"APPLIED"}
    sold = client.get(f"/api/v1/sales/{result['converted_sale_id']}", headers=device()).json()
    assert sorted((tender["method"], tender["amount_cents"]) for tender in sold["tenders"]) == [
        ("cash", 3000),
        ("deposit", 3000),
    ]
    assert sold["payment_status"] == "PAID"


def test_open_layaways_get_a_weekly_reminder(client, session) -> None:
    from app.core.config import get_settings
    from app.jobs.runner import run_job
    from app.models.messaging import OutboundMessage

    seed(client)
    headers, _ = admin(client)
    customer = client.post(
        "/api/v1/customers", headers=headers, json={"name": "Sara", "phone": "+971501234567", "sms_opt_in": True}
    ).json()
    body = quote_body(
        [line(CABLE, 2, 1500)],
        sale_type="RETAIL",
        customer_id=customer["id"],
        quote_kind="LAYAWAY",
        deposit={"id": str(uuid.uuid4()), "amount_cents": 1000, "method": "cash"},
    )
    assert client.post("/api/v1/quotes", headers=device(), json=body).status_code == 201
    assert run_job(session, get_settings(), "layaway_reminders") == "ok"
    assert run_job(session, get_settings(), "layaway_reminders") == "ok"
    reminders = session.query(OutboundMessage).filter(OutboundMessage.template_key == "layaway_reminder").all()
    assert len(reminders) == 1 and "20.00" in reminders[0].body


def test_cancelled_layaway_owes_deposits_back(client) -> None:
    seed(client)
    headers, _ = admin(client)
    customer = create_customer(client, headers, customer_type="RETAIL", price_tier="RETAIL", credit_limit_cents=0)
    body = quote_body(
        [line(CABLE, 1, 1500)],
        sale_type="RETAIL",
        customer_id=customer["id"],
        quote_kind="LAYAWAY",
        deposit={"id": str(uuid.uuid4()), "amount_cents": 500, "method": "cash"},
    )
    assert client.post("/api/v1/quotes", headers=device(), json=body).status_code == 201
    cancelled = client.post(f"/api/v1/quotes/{body['id']}/cancel", headers=headers).json()
    assert (cancelled["refund_due_cents"], cancelled["deposits_cents"]) == (500, 0)


def test_registers_cannot_invent_deposit_tenders(client) -> None:
    seed(client)
    body = sale([line(CABLE, 1, 1500)], payment_method="deposit", tenders=[{"method": "deposit", "amount_cents": 1500}])
    response = push(client, [event("fake-deposit", "sale", body)])
    assert response.status_code == 422
    assert "layaway" in response.json()["error"]["message"]
