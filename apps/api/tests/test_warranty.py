import uuid
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.jobs.runner import run_job
from app.models.messaging import OutboundMessage
from app.models.warranty import WarrantyRegistration
from wholesale_support import PHONE, STORE, admin, device, event, line, push, sale, seed


def repair(identifier: str, status: str = "intake", **extra) -> dict:
    body = {
        "id": str(uuid.uuid4()),
        "store_id": STORE,
        "customer_name": "Sara",
        "customer_phone": "+971501234567",
        "device_model": "Pixel 9",
        "identifier_kind": "imei",
        "identifier_value": identifier,
        "issue": "Cracked screen",
        "status": status,
        "estimated_cost_cents": 25_000,
        "currency": "USD",
    }
    body.update(extra)
    return body


def test_sold_units_get_cover_plans_extend_it_and_repairs_see_it(client, session) -> None:
    values = seed(client, phone_units=2)
    headers, _ = admin(client)
    assert (
        client.post(
            "/api/v1/warranties/policies", headers=headers, json={"name": "Standard", "scope": "DEFAULT", "months": 12}
        ).status_code
        == 201
    )
    plans = client.post(
        "/api/v1/warranties/plans",
        headers=headers,
        json={"name": "Care+ 1 year", "extra_months": 12, "price_cents": 9900},
    ).json()
    plan = plans[0]
    customer = client.post(
        "/api/v1/customers", headers=headers, json={"name": "Sara", "phone": "+971501234567", "sms_opt_in": True}
    ).json()

    body = sale(
        [line(PHONE, 1, 79900, serial=values[0]), line(plan["product_id"], 1, 9900)],
        customer_id=customer["id"],
        sale_type="RETAIL",
    )
    assert push(client, [event("warranty-sale-key", "sale", body)]).status_code == 200, "sale"

    found = client.get("/api/v1/warranties/lookup", headers=device(), params={"serial": values[0]}).json()
    assert found["plan_name"] == "Care+ 1 year"
    assert found["coverage"] == "IN_WARRANTY"
    months = (datetime.fromisoformat(found["expires_at"]) - datetime.fromisoformat(found["starts_at"])).days
    assert 725 <= months <= 732

    receipt = client.get(f"/api/v1/returns/receipts/{body['id']}", headers=device()).json()
    phone_line = next(item for item in receipt["items"] if item["is_serialized"])
    assert phone_line["warranty_expires_at"] is not None

    ticket = repair(values[0])
    assert push(client, [event("warranty-repair", "repair_ticket", ticket)]).status_code == 200
    ready = {**ticket, "status": "ready"}
    assert push(client, [event("warranty-repair-ready", "repair_ticket", ready)]).status_code == 200
    queued = session.query(OutboundMessage).filter(OutboundMessage.template_key == "repair_ready").one()
    assert queued.channel == "sms" and "Pixel 9" in queued.body
    registration = session.query(WarrantyRegistration).one()
    assert (registration.status, registration.claims) == ("CLAIMED", 1)

    registration.status = "ACTIVE"
    registration.expires_at = datetime.now(UTC) + timedelta(days=10)
    session.commit()
    assert run_job(session, get_settings(), "warranty_reminders") == "ok"
    assert session.query(OutboundMessage).filter(OutboundMessage.template_key == "warranty_expiry").count() == 1

    listing = client.get("/api/v1/warranties", headers=headers, params={"expiring_days": 30}).json()
    assert listing["expiring_count"] == 1 and listing["extended_count"] == 1
