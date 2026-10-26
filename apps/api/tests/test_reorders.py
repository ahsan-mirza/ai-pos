"""Customer reorder plans stay per customer, and a reminder never confirms a sale by itself."""

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select

from app.core import capabilities as catalog
from app.core.capabilities import Capability
from app.core.config import get_settings
from app.jobs.runner import run_job
from app.models.inventory import InventoryLevel
from app.models.messaging import OutboundMessage
from app.models.reorder import CustomerReorderOccurrence
from app.models.sales_order import SalesOrder
from app.services.reorder_service import following, generate_due
from wholesale_support import CABLE, STORE, admin, create_customer, device, event, push, seed, set_cable_tiers

SOAP = "00000000-0000-4000-8000-000000000018"


def _wholesale(client, headers) -> None:
    chosen = [item.value for item in catalog.WHOLESALE_RETAIL]
    saved = client.put(
        "/api/v1/settings/profile",
        headers=headers,
        json={"business_profile": "wholesale_retail", "capabilities": chosen},
    )
    assert saved.status_code == 200, saved.text


def _product(client) -> None:
    response = push(
        client,
        [
            event(
                "reorder-soap",
                "product",
                {
                    "id": SOAP,
                    "store_id": STORE,
                    "sku": "SOAP-1",
                    "barcode": "100000000018",
                    "name": "Laundry soap",
                    "category": "Household",
                    "price_cents": 500,
                    "currency": "USD",
                    "is_serialized": False,
                    "stock_quantity": 40,
                },
            )
        ],
    )
    assert response.status_code == 200, response.text


def _plan(headers_client, headers, customer_id: str, **extra) -> dict:
    client = headers_client
    body = {
        "customer_id": customer_id,
        "name": "Daily route",
        "frequency": "DAILY",
        "start_on": date.today().isoformat(),
        "timezone": "Asia/Dubai",
        "preferred_time": "09:00",
        "fulfillment": "DELIVERY",
        "items": [{"product_id": CABLE, "quantity": 5, "unit": "PIECE"}],
    }
    body.update(extra)
    response = client.post("/api/v1/reorders/plans", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_electronics_is_renamed_and_still_sells_wholesale() -> None:
    assert catalog.PROFILE_LABELS["electronics_wholesale"] == "Electronics"
    assert Capability.WHOLESALE_PRICING in catalog.ELECTRONICS_WHOLESALE
    assert Capability.B2B_CREDIT in catalog.ELECTRONICS_WHOLESALE
    assert Capability.SERIAL_TRACKING in catalog.ELECTRONICS_WHOLESALE
    assert Capability.CUSTOMER_REORDERS not in catalog.ELECTRONICS_WHOLESALE
    assert catalog.SUB_TYPES["electronics_wholesale"]["electronics_b2b"] == catalog.ELECTRONICS_WHOLESALE
    assert "wholesale_retail" in catalog.PROFILES
    assert Capability.CUSTOMER_REORDERS in catalog.PROFILES["wholesale_retail"]


def test_electronics_cannot_open_reorder_plans(client) -> None:
    headers, _ = admin(client)
    denied = client.get("/api/v1/reorders/plans", headers=headers)
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "capability_disabled"


def test_a_customers_daily_plan_does_not_apply_to_another_customer(client, session) -> None:
    seed(client)
    _product(client)
    headers, user_id = admin(client)
    _wholesale(client, headers)
    set_cable_tiers(client, headers)
    ali = create_customer(client, headers, name="Ali Traders")
    noor = create_customer(client, headers, name="Noor Stores", company_name="Noor Stores")
    daily = _plan(
        client,
        headers,
        ali["id"],
        items=[
            {"product_id": CABLE, "quantity": 5, "unit": "PIECE"},
            {"product_id": SOAP, "quantity": 2, "unit": "PIECE"},
        ],
    )
    weekly = _plan(
        client,
        headers,
        noor["id"],
        name="Monday drop",
        frequency="CUSTOM_DAYS",
        weekdays=[0],
        items=[{"product_id": CABLE, "quantity": 10, "unit": "PIECE"}],
    )
    assert daily["customer_id"] == ali["id"]
    assert [item["quantity"] for item in daily["items"]] == [5, 2]
    assert weekly["customer_id"] == noor["id"]
    assert weekly["items"][0]["quantity"] == 10

    opened = generate_due(session)
    assert opened.startswith("1 ") or opened.startswith("2 ")
    rows = session.scalars(select(CustomerReorderOccurrence)).all()
    by_plan = {str(row.plan_id): row for row in rows}
    assert str(daily["id"]) in by_plan
    ali_items = {item.product_id: item.quantity for item in by_plan[str(daily["id"])].plan.items}
    assert ali_items[uuid.UUID(CABLE)] == 5
    assert ali_items[uuid.UUID(SOAP)] == 2
    if str(weekly["id"]) in by_plan:
        assert [item.quantity for item in by_plan[str(weekly["id"])].plan.items] == [10]

    again = generate_due(session)
    assert again.startswith("0 ")
    assert session.scalar(select(func.count()).select_from(CustomerReorderOccurrence)) == len(rows)

    listed = client.get(f"/api/v1/reorders/occurrences?customer_id={ali['id']}", headers=headers)
    assert listed.status_code == 200, listed.text
    assert {row["customer_id"] for row in listed.json()} == {ali["id"]}
    assert listed.json()[0]["status"] == "PENDING"
    assert "SENT" not in listed.json()[0]["notification_status"]

    draft = client.post(f"/api/v1/reorders/occurrences/{listed.json()[0]['id']}/order", headers=headers, json={})
    assert draft.status_code == 200, draft.text
    body = draft.json()
    assert body["status"] == "DRAFT"
    assert body["source"] == "reorder"
    assert body["customer_id"] == ali["id"]
    cable = next(line for line in body["lines"] if line["product_id"] == CABLE)
    soap = next(line for line in body["lines"] if line["product_id"] == SOAP)
    assert cable["quantity_ordered"] == 5 and cable["unit_price_cents"] == 1200
    assert soap["quantity_ordered"] == 2
    repeat = client.post(f"/api/v1/reorders/occurrences/{listed.json()[0]['id']}/order", headers=headers, json={})
    assert repeat.status_code == 200, repeat.text
    assert repeat.json()["id"] == body["id"]
    assert session.scalar(select(func.count()).select_from(SalesOrder)) == 1
    assert user_id


def test_weekly_monthly_and_timezone_follow_the_plan(client, session) -> None:
    monday = date(2026, 10, 5)
    assert monday.weekday() == 0
    weekly = type("Plan", (), {"frequency": "WEEKLY", "weekdays": None, "month_day": None})()
    monthly = type("Plan", (), {"frequency": "MONTHLY", "weekdays": None, "month_day": 15})()
    custom = type("Plan", (), {"frequency": "CUSTOM_DAYS", "weekdays": [0], "month_day": None})()
    assert following(weekly, monday) == date(2026, 10, 12)
    assert following(monthly, date(2026, 1, 15)) == date(2026, 2, 15)
    assert following(custom, monday) == date(2026, 10, 12)

    seed(client)
    headers, _ = admin(client)
    _wholesale(client, headers)
    ali = create_customer(client, headers, name="Dubai Route")
    noor = create_customer(client, headers, name="LA Route", company_name="LA Route")
    dubai = _plan(client, headers, ali["id"], name="Dubai", start_on="2026-10-26", timezone="Asia/Dubai")
    _plan(client, headers, noor["id"], name="Los Angeles", start_on="2026-10-26", timezone="America/Los_Angeles")

    def clock(zone: str) -> date:
        return date(2026, 10, 26) if zone == "Asia/Dubai" else date(2026, 10, 25)

    assert generate_due(session, today_for=clock) == "1 reorder reminders"
    opened = session.scalars(select(CustomerReorderOccurrence)).all()
    assert [str(row.plan_id) for row in opened] == [dubai["id"]]
    assert opened[0].scheduled_on == date(2026, 10, 26)


def test_pause_resume_snooze_and_skip_do_not_invent_old_reminders(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    _wholesale(client, headers)
    ali = create_customer(client, headers)
    yesterday = date.today() - timedelta(days=3)
    plan = _plan(client, headers, ali["id"], start_on=yesterday.isoformat())
    client.post(f"/api/v1/reorders/plans/{plan['id']}/pause", headers=headers)
    assert generate_due(session) == "0 reorder reminders"
    assert session.scalar(select(func.count()).select_from(CustomerReorderOccurrence)) == 0
    resumed = client.post(f"/api/v1/reorders/plans/{plan['id']}/resume", headers=headers)
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["next_on"] >= date.today().isoformat()
    assert session.scalar(select(func.count()).select_from(CustomerReorderOccurrence)) == 0
    archived = client.post(f"/api/v1/reorders/plans/{plan['id']}/archive", headers=headers)
    assert archived.status_code == 200, archived.text

    fresh = _plan(client, headers, ali["id"], name="Second route")
    assert generate_due(session).startswith("1 ")
    occurrence = client.get("/api/v1/reorders/occurrences?status=PENDING", headers=headers).json()[0]
    snoozed = client.post(
        f"/api/v1/reorders/occurrences/{occurrence['id']}/snooze", headers=headers, json={"hours": 4}
    )
    assert snoozed.status_code == 200, snoozed.text
    assert snoozed.json()["status"] == "SNOOZED"
    skipped = client.post(
        f"/api/v1/reorders/occurrences/{fresh['id']}/skip",
        headers=headers,
        json={"reason": "Customer is away"},
    )
    assert skipped.status_code == 404
    skipped = client.post(
        f"/api/v1/reorders/occurrences/{occurrence['id']}/skip",
        headers=headers,
        json={"reason": "Customer is away"},
    )
    assert skipped.status_code == 200, skipped.text
    assert skipped.json()["status"] == "SKIPPED"
    assert generate_due(session) == "0 reorder reminders"
    assert session.scalar(select(func.count()).select_from(CustomerReorderOccurrence)) == 1


def test_short_stock_and_a_missing_product_are_reported(client, session) -> None:
    seed(client)
    _product(client)
    headers, _ = admin(client)
    _wholesale(client, headers)
    ali = create_customer(client, headers)
    plan = _plan(client, headers, ali["id"])
    level = session.scalar(select(InventoryLevel).where(InventoryLevel.product_id == uuid.UUID(CABLE)))
    assert level is not None
    level.quantity_on_hand = 1
    session.commit()
    generate_due(session)
    occurrence = session.scalar(select(CustomerReorderOccurrence))
    assert occurrence is not None
    assert "1 available" in occurrence.stock_note
    assert "5 expected" in occurrence.stock_note
    draft = client.post(f"/api/v1/reorders/occurrences/{occurrence.id}/order", headers=headers, json={})
    assert draft.status_code == 200, draft.text
    assert draft.json()["status"] == "DRAFT"

    gone = _plan(
        client,
        headers,
        ali["id"],
        name="Soap route",
        items=[{"product_id": SOAP, "quantity": 1, "unit": "PIECE"}],
    )
    from app.models.product import Product

    soap = session.get(Product, uuid.UUID(SOAP))
    assert soap is not None
    soap.is_ingredient = True
    session.commit()
    generate_due(session)
    soap_row = session.scalar(
        select(CustomerReorderOccurrence).where(CustomerReorderOccurrence.plan_id == uuid.UUID(gone["id"]))
    )
    assert soap_row is not None
    refused = client.post(f"/api/v1/reorders/occurrences/{soap_row.id}/order", headers=headers, json={})
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "product_unavailable"
    assert plan["id"]


def test_permissions_and_a_plan_block_turning_the_module_off(client) -> None:
    seed(client)
    headers, _ = admin(client)
    _wholesale(client, headers)
    ali = create_customer(client, headers)
    _plan(client, headers, ali["id"])
    cashier = client.post(
        "/api/v1/auth/login-pin", json={"username": "cashier", "pin": "1357"}, headers=device()
    )
    assert cashier.status_code == 200, cashier.text
    token = {"Authorization": f"Bearer {cashier.json()['access_token']}"}
    assert client.get("/api/v1/reorders/occurrences", headers=token).status_code == 200
    denied = client.post(
        "/api/v1/reorders/plans",
        headers=token,
        json={
            "customer_id": ali["id"],
            "name": "Nope",
            "frequency": "DAILY",
            "start_on": date.today().isoformat(),
            "items": [{"product_id": CABLE, "quantity": 1, "unit": "PIECE"}],
        },
    )
    assert denied.status_code == 403
    extra = client.post("/api/v1/reorders/plans", headers=headers, json={"tenant_id": str(uuid.uuid4())})
    assert extra.status_code == 422
    kept = [item.value for item in catalog.WHOLESALE_RETAIL if item is not Capability.CUSTOMER_REORDERS]
    blocked = client.put(
        "/api/v1/settings/profile",
        headers=headers,
        json={"business_profile": "wholesale_retail", "capabilities": kept},
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "module_in_use"


def test_notification_retry_does_not_claim_the_message_was_sent(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    _wholesale(client, headers)
    ali = create_customer(
        client,
        headers,
        phone="+971501112233",
        whatsapp_opt_in=True,
    )
    _plan(client, headers, ali["id"], notify_customer=True)
    generate_due(session)
    occurrence = session.scalar(select(CustomerReorderOccurrence))
    assert occurrence is not None
    assert occurrence.notification_status == "QUEUED"
    message = session.scalar(select(OutboundMessage).where(OutboundMessage.dedupe_key == f"reorder:{occurrence.id}"))
    assert message is not None and message.status == "QUEUED"
    message.status = "FAILED"
    message.last_error = "provider down"
    session.commit()
    retried = client.post(f"/api/v1/reorders/occurrences/{occurrence.id}/retry-notification", headers=headers)
    assert retried.status_code == 200, retried.text
    assert retried.json()["notification_status"] == "QUEUED"
    assert session.scalar(select(func.count()).select_from(OutboundMessage)) == 1


def test_the_scheduler_lease_survives_a_second_run(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    _wholesale(client, headers)
    ali = create_customer(client, headers)
    _plan(client, headers, ali["id"])
    assert run_job(session, get_settings(), "customer_reorders") == "ok"
    assert session.scalar(select(func.count()).select_from(CustomerReorderOccurrence)) == 1
    from app.models.scheduled_job import ScheduledJob

    job = session.scalar(select(ScheduledJob).where(ScheduledJob.name == "customer_reorders"))
    assert job is not None
    job.locked_until = datetime.now(UTC) + timedelta(minutes=5)
    session.commit()
    assert run_job(session, get_settings(), "customer_reorders") == "busy"
    assert session.scalar(select(func.count()).select_from(CustomerReorderOccurrence)) == 1
    job.locked_until = None
    session.commit()
    assert run_job(session, get_settings(), "customer_reorders") == "ok"
    assert session.scalar(select(func.count()).select_from(CustomerReorderOccurrence)) == 1


def test_a_carton_converts_to_base_units_on_the_draft(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    _wholesale(client, headers)
    set_cable_tiers(client, headers)
    ali = create_customer(client, headers)
    _plan(
        client,
        headers,
        ali["id"],
        items=[{"product_id": CABLE, "quantity": 2, "unit": "BOX_10"}],
    )
    generate_due(session)
    occurrence = session.scalar(select(CustomerReorderOccurrence))
    draft = client.post(f"/api/v1/reorders/occurrences/{occurrence.id}/order", headers=headers, json={})
    assert draft.status_code == 200, draft.text
    assert draft.json()["lines"][0]["quantity_ordered"] == 20
    assert draft.json()["status"] == "DRAFT"
