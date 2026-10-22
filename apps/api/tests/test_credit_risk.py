import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from app.models.customer import CustomerLedgerEntry
from app.models.sale import Sale
from app.services.credit_risk_service import Features, score
from test_credit_hold import on_account
from wholesale_support import admin, create_customer, event, push, seed

GOOD = Features(
    balance_cents=10_000,
    limit_cents=100_000,
    overdue_cents=0,
    max_days_overdue=0,
    avg_days_late=0.0,
    settled_invoices=12,
    bounced_cheques=0,
    reminders_90d=0,
    credit_hold=False,
    account_age_days=400,
    monthly_purchases_cents=60_000_00,
    payment_terms="NET_30",
)


def test_reliable_payer_grades_a_with_a_generous_limit() -> None:
    risk = score(GOOD)
    assert (risk.score, risk.grade, risk.factors) == (0, "A", ())
    assert risk.suggested_limit_cents == 90_000_00


def test_every_point_has_a_reason_and_bad_accounts_grade_e() -> None:
    bad = replace(
        GOOD,
        balance_cents=120_000,
        overdue_cents=90_000,
        max_days_overdue=95,
        avg_days_late=40,
        bounced_cheques=1,
        reminders_90d=2,
        credit_hold=True,
    )
    risk = score(bad)
    assert risk.grade == "E" and risk.score == 100
    assert risk.suggested_limit_cents == 0
    keys = [factor.key for factor in risk.factors]
    assert keys[0] == "overdue_days"
    assert {"utilisation", "late_payment", "bounced_cheques", "reminders", "credit_hold"} <= set(keys)
    assert all(factor.detail for factor in risk.factors)


def test_grades_follow_score_bands() -> None:
    assert score(replace(GOOD, max_days_overdue=10, overdue_cents=1_000)).grade == "B"
    assert score(replace(GOOD, avg_days_late=None, account_age_days=10)).grade == "A"
    assert score(replace(GOOD, max_days_overdue=45, overdue_cents=10_000, avg_days_late=12)).grade == "C"


def test_ledger_replay_measures_late_payment(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    customer = create_customer(client, headers, credit_limit_cents=10_000)
    first = on_account(customer["id"], 3000)
    assert push(client, [event("risk-first", "sale", first)]).status_code == 200
    # The invoice fell due 20 days ago and is only paid now: 20 days late.
    session.get(Sale, uuid.UUID(first["id"])).due_date = datetime.now(UTC) - timedelta(days=20)
    for entry in session.query(CustomerLedgerEntry).filter(CustomerLedgerEntry.sale_id == uuid.UUID(first["id"])):
        entry.created_at = datetime.now(UTC) - timedelta(days=50)
    session.commit()
    paid = client.post(
        f"/api/v1/customers/{customer['id']}/payments", headers=headers, json={"amount_cents": 3000, "method": "cash"}
    )
    assert paid.status_code == 201, paid.text
    second = on_account(customer["id"], 9000)
    assert push(client, [event("risk-second", "sale", second)]).status_code == 200

    risk = client.get(f"/api/v1/customers/{customer['id']}/risk", headers=headers)
    assert risk.status_code == 200, risk.text
    body = risk.json()
    factors = {factor["key"]: factor for factor in body["factors"]}
    assert factors["late_payment"]["points"] == 12 and "20 days" in factors["late_payment"]["detail"]
    assert factors["utilisation"]["points"] == 12
    assert body["grade"] in {"B", "C"} and body["score"] == sum(f["points"] for f in body["factors"])

    listing = client.get("/api/v1/customers", headers=headers).json()
    row = next(item for item in listing if item["id"] == customer["id"])
    assert row["risk_grade"] == body["grade"]
    portfolio = client.get("/api/v1/customers/risk", headers=headers).json()
    assert portfolio[0]["customer_id"] == customer["id"]


def test_assistant_explains_credit_risk_and_reorders(client) -> None:
    seed(client)
    headers, _ = admin(client)
    customer = create_customer(client, headers, credit_limit_cents=5_000)
    assert push(client, [event("risk-assistant", "sale", on_account(customer["id"], 4500))]).status_code == 200

    reply = client.post("/api/v1/assistant/ask", headers=headers, json={"question": "Who is our riskiest customer?"})
    assert reply.status_code == 200, reply.text
    body = reply.json()
    assert body["results"][0]["tool"] == "credit_risk"
    assert "Ali Traders" in body["answer"] and "grade" in body["answer"]

    reorder = client.post("/api/v1/assistant/ask", headers=headers, json={"question": "What should I reorder?"})
    assert reorder.json()["results"][0]["tool"] == "reorder_forecast"


def test_risk_is_part_of_the_b2b_credit_module(client) -> None:
    seed(client)
    headers, _ = admin(client)
    switched = client.put("/api/v1/settings/profile", headers=headers, json={"business_profile": "cafe"})
    assert switched.status_code == 200
    assert client.get("/api/v1/customers/risk", headers=headers).status_code == 403
