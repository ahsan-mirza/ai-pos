import uuid

from app.core.config import get_settings
from app.jobs.runner import run_job
from app.models.customer import Customer
from app.services import messaging_service
from wholesale_support import admin, create_customer, seed


def test_messages_respect_consent_and_dispatch_through_the_log_provider(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    silent = create_customer(client, headers)
    keen = client.post(
        "/api/v1/customers",
        headers=headers,
        json={"name": "Sara", "phone": "+971501234567", "whatsapp_opt_in": True},
    ).json()
    assert keen["whatsapp_opt_in"] is True

    for customer_id in (silent["id"], keen["id"]):
        customer = session.get(Customer, uuid.UUID(customer_id))
        messaging_service.enqueue(
            session,
            template_key="statement",
            customer=customer,
            context={"business": "AI POS", "balance": "AED 10.00", "overdue": "AED 0.00"},
            dedupe_key=f"statement:{customer_id}",
        )
    again = messaging_service.enqueue(
        session,
        template_key="statement",
        customer=session.get(Customer, uuid.UUID(keen["id"])),
        context={},
        dedupe_key=f"statement:{keen['id']}",
    )
    assert again is None
    session.commit()

    assert run_job(session, get_settings(), "dispatch_messages") == "ok"
    outbox = client.get("/api/v1/messaging/outbox", headers=headers).json()
    by_status = {row["status"]: row for row in outbox}
    assert set(by_status) == {"SENT", "SKIPPED"}
    assert by_status["SENT"]["channel"] == "whatsapp"
    assert "Sara" in by_status["SENT"]["body"] and "AED 10.00" in by_status["SENT"]["body"]

    jobs = {row["name"]: row for row in client.get("/api/v1/jobs", headers=headers).json()}
    assert jobs["dispatch_messages"]["run_count"] == 1
    assert jobs["dispatch_messages"]["last_status"] == "ok"


def test_messaging_settings_and_templates(client) -> None:
    seed(client)
    headers, _ = admin(client)
    settings = client.get("/api/v1/messaging/settings", headers=headers).json()
    assert settings["providers"]["email"] == "log"
    bad = client.put("/api/v1/messaging/settings", headers=headers, json={"providers": {"sms": "smtp"}})
    assert bad.status_code == 422
    updated = client.put(
        "/api/v1/messaging/settings",
        headers=headers,
        json={"providers": {"email": "smtp"}, "events": {"receipt": True}},
    ).json()
    assert updated["providers"]["email"] == "smtp" and updated["events"]["receipt"] is True

    unknown = client.put(
        "/api/v1/messaging/templates/statement", headers=headers, json={"body": "Hi {{nickname}}", "subject": ""}
    )
    assert unknown.status_code == 422
    saved = client.put(
        "/api/v1/messaging/templates/statement",
        headers=headers,
        json={"body": "Hello {{customer}}, you owe {{balance}}.", "subject": "Statement"},
    )
    assert saved.status_code == 200 and saved.json()["body"].startswith("Hello")

    failed = client.post("/api/v1/messaging/test", headers=headers, json={"channel": "email", "to": "a@b.co"}).json()
    assert failed["status"] == "FAILED" and "SMTP_HOST" in failed["last_error"]
