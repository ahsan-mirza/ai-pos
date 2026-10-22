from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session
from tests.test_menu import enable
from tests.test_orders import line, open_order, settle
from tests.test_returns import CASHIER_ID, STORE_ID, admin_id, admin_token, bearer, push, seed_catalog

from app.models import RegisterShift, Sale
from app.services import shift_service

MODULES = ("menu_modifiers", "open_orders", "tables", "tips_service_charge")


def test_tips_pool_by_server_and_shift_report(client, session: Session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    enable(client, token, *MODULES)
    area = client.post("/api/v1/dining/areas", headers=bearer(token), json={"store_id": STORE_ID, "name": "Main"})
    area_id = area.json()["areas"][0]["id"]
    tables = client.post("/api/v1/dining/tables", headers=bearer(token), json={"area_id": area_id, "label": "1"})
    table = tables.json()["areas"][0]["tables"][0]
    order = open_order(client, table, line(), line(2))
    first, second = (item["id"] for item in order["items"])

    by_cashier = settle(order, [first], tip=300, service=150)
    server = admin_id(client)
    for_server = {**settle(order, [second], tip=500), "tip_user_id": server}
    assert push(client, "sale", by_cashier).status_code == 200
    assert push(client, "sale", for_server).status_code == 200

    # Synced sales are dated when the register rang them up (the test pushes date them 2026-10-19).
    today = datetime.now(UTC).date().isoformat()
    report = client.get("/api/v1/reports/tips", headers=bearer(token), params={"from": "2026-10-01", "to": today})
    assert report.status_code == 200, report.text
    body = report.json()
    assert (body["tips_cents"], body["service_charge_cents"], body["sales_count"]) == (800, 150, 2)
    assert [(row["user_id"], row["tips_cents"]) for row in body["by_server"]] == [(server, 500), (CASHIER_ID, 300)]

    shift = RegisterShift(
        id=UUID("00000000-0000-4000-8000-00000000f001"),
        store_id=UUID(STORE_ID),
        opened_by_id=UUID(CASHIER_ID),
        opened_at=datetime.now(UTC),
        currency="USD",
        opening_float_cents=0,
        status="OPEN",
    )
    session.add(shift)
    session.flush()
    for sale_id in (by_cashier["id"], for_server["id"]):
        session.get(Sale, UUID(sale_id)).shift_id = shift.id
    session.flush()
    summary = shift_service.build_report(session, shift)
    assert (summary.tips_cents, summary.service_charge_cents, summary.on_account_cents) == (800, 150, 0)
    assert [row.tips_cents for row in summary.tips_by_server] == [500, 300]


def test_tip_report_needs_the_module(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    today = datetime.now(UTC).date().isoformat()
    blocked = client.get("/api/v1/reports/tips", headers=bearer(token), params={"from": today, "to": today})
    assert blocked.status_code == 403
