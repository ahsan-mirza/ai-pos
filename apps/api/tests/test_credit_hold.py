import uuid
from datetime import UTC, datetime, timedelta

from app.models.audit_log import AuditLog
from app.models.sale import Sale
from wholesale_support import CABLE, admin, create_customer, event, line, push, sale, seed


def on_account(customer_id: str, cents: int = 3000) -> dict:
    return sale(
        [line(CABLE, cents // 1500, 1500)],
        customer_id=customer_id,
        sale_type="WHOLESALE",
        payment_method="on_account",
        tenders=[{"method": "on_account", "amount_cents": cents}],
    )


def test_overdue_invoice_puts_the_account_on_hold_until_paid(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    customer = create_customer(client, headers, credit_limit_cents=1_000_000)
    first = on_account(customer["id"])
    assert push(client, [event("hold-first-sale", "sale", first)]).status_code == 200
    row = session.get(Sale, uuid.UUID(first["id"]))
    row.due_date = datetime.now(UTC) - timedelta(days=45)
    session.commit()

    second = on_account(customer["id"])
    assert push(client, [event("hold-second-sale", "sale", second)]).status_code == 200
    held = client.get(f"/api/v1/customers/{customer['id']}", headers=headers).json()
    assert held["credit_hold"] is True and "overdue" in held["credit_hold_reason"]
    flagged = session.query(AuditLog).filter(AuditLog.action == "sale.credit_hold_bypassed").count()
    assert flagged == 1

    paid = client.post(
        f"/api/v1/customers/{customer['id']}/payments", headers=headers, json={"amount_cents": 6000, "method": "cash"}
    )
    assert paid.status_code == 201
    third = on_account(customer["id"])
    assert push(client, [event("hold-third-sale", "sale", third)]).status_code == 200
    lifted = client.get(f"/api/v1/customers/{customer['id']}", headers=headers).json()
    assert lifted["credit_hold"] is False


def test_manager_hold_stays_until_lifted(client) -> None:
    seed(client)
    headers, _ = admin(client)
    customer = create_customer(client, headers)
    placed = client.post(
        f"/api/v1/customers/{customer['id']}/credit-hold",
        headers=headers,
        json={"hold": True, "reason": "Disputed invoices"},
    ).json()
    assert (placed["credit_hold"], placed["credit_hold_reason"]) == (True, "Disputed invoices")
    assert push(client, [event("manual-hold-sale", "sale", on_account(customer["id"]))]).status_code == 200
    still = client.get(f"/api/v1/customers/{customer['id']}", headers=headers).json()
    assert still["credit_hold"] is True
    lifted = client.post(
        f"/api/v1/customers/{customer['id']}/credit-hold", headers=headers, json={"hold": False}
    ).json()
    assert lifted["credit_hold"] is False
