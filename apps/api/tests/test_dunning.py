import uuid
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.jobs.runner import run_job
from app.models.messaging import OutboundMessage
from app.models.sale import Sale
from wholesale_support import CABLE, admin, event, line, push, sale, seed


def test_statements_and_weekly_overdue_reminders(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    customer = client.post(
        "/api/v1/customers",
        headers=headers,
        json={
            "name": "Ali",
            "company_name": "Ali Traders LLC",
            "customer_type": "WHOLESALE",
            "price_tier": "TIER_1",
            "credit_limit_cents": 1_000_000,
            "payment_terms": "NET_30",
            "email": "ali@example.com",
            "email_opt_in": True,
        },
    ).json()
    body = sale(
        [line(CABLE, 2, 1500)],
        customer_id=customer["id"],
        sale_type="WHOLESALE",
        payment_method="on_account",
        tenders=[{"method": "on_account", "amount_cents": 3000}],
    )
    assert push(client, [event("dunning-sale", "sale", body)]).status_code == 200

    pdf = client.get(f"/api/v1/customers/{customer['id']}/statement.pdf", headers=headers)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")

    sent = client.post("/api/v1/customers/statements/send", headers=headers, json={}).json()
    assert sent == {"queued": 1, "skipped": 0}
    statement = session.query(OutboundMessage).filter(OutboundMessage.template_key == "statement").one()
    assert statement.attachment_kind == "statement" and statement.channel == "email"

    settings = get_settings()
    assert run_job(session, settings, "dispatch_messages") == "ok"
    session.refresh(statement)
    assert statement.status == "SENT"
    assert run_job(session, settings, "overdue_reminders") == "ok"
    assert session.query(OutboundMessage).filter(OutboundMessage.template_key == "overdue_reminder").count() == 0

    row = session.get(Sale, uuid.UUID(body["id"]))
    row.due_date = datetime.now(UTC) - timedelta(days=12)
    session.commit()
    assert run_job(session, settings, "overdue_reminders") == "ok"
    assert run_job(session, settings, "overdue_reminders") == "ok"
    reminders = session.query(OutboundMessage).filter(OutboundMessage.template_key == "overdue_reminder").all()
    assert len(reminders) == 1
    assert "12 days" in reminders[0].body
