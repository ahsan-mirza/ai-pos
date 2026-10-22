"""Repairs 2.0: state machine, deposits in the drawer and on the invoice, parts held in stock, the customer
approval link, and the warranty an invoiced repair carries."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from tests.test_open_price import labour_product
from tests.test_repairs import booked
from tests.test_shifts import shift_body
from tests.test_warranty import repair

from app.models.inventory import InventoryLevel
from app.models.repair_ticket import RepairTicket
from app.models.sale import Sale
from app.models.sale_tender import SaleTender
from wholesale_support import CABLE, STORE, event, imeis, push

TINY_PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


def test_illegal_moves_are_refused_and_a_no_charge_ticket_can_be_collected(client) -> None:
    ticket, headers = booked(client)
    base = f"/api/v1/repairs/{ticket['id']}"
    blocked = client.post(f"{base}/status", headers=headers, json={"status": "waiting_parts"})
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["error"]["code"] == "invalid_transition"
    collected = client.post(f"{base}/pickup", headers=headers, json={"note": "No charge, handed back"})
    assert collected.status_code == 200, collected.text
    assert collected.json()["status"] == "closed"


def test_cash_deposit_is_in_the_drawer_and_credited_on_the_invoice(client, session) -> None:
    ticket, headers = booked(client)
    base = f"/api/v1/repairs/{ticket['id']}"
    shift_id = str(uuid.uuid4())
    assert push(client, [event("repair-shift", "register_shift", shift_body(shift_id))]).status_code == 200
    deposited = client.post(
        f"{base}/deposits",
        headers=headers,
        json={"amount_cents": 2_500, "method": "cash", "shift_id": shift_id},
    )
    assert deposited.status_code == 201, deposited.text
    assert deposited.json()["deposit_held_cents"] == 2_500
    shift = client.get(f"/api/v1/shifts/{shift_id}", headers=headers).json()
    assert shift["expected_cash_cents"] == 20_000 + 2_500
    assert shift["report"]["deposit_cents"] == 2_500

    part = client.post(f"{base}/lines", headers=headers, json={"kind": "PART", "product_id": CABLE, "quantity": 2})
    assert part.status_code == 201, part.text
    labour = client.post(
        f"{base}/lines",
        headers=headers,
        json={"kind": "LABOUR", "description": "Port clean", "unit_price_cents": 8000},
    )
    assert labour.status_code == 201, labour.text
    invoiced = client.post(f"{base}/invoice", headers=headers, json={"payment_method": "card"})
    assert invoiced.status_code == 200, invoiced.text
    body = invoiced.json()
    assert body["status"] == "closed"
    assert "deposit" in body["events"][-1]["note"]
    assert body["repair_warranty"]["status"] == "ACTIVE"

    session.expire_all()
    sale = session.get(Sale, uuid.UUID(body["sale_id"]))
    assert sale is not None
    tenders = {
        row.method: row.amount_cents for row in session.scalars(select(SaleTender).where(SaleTender.sale_id == sale.id))
    }
    assert tenders["deposit"] == 2_500
    assert tenders["card"] == sale.total_cents - 2_500

    covered = client.get(f"/api/v1/warranties/lookup?serial={ticket['identifier_value']}", headers=headers)
    assert covered.status_code == 200, covered.text
    assert covered.json()["kind"] == "REPAIR"

    deposit_id = deposited.json()["deposits"][0]["id"]
    already = client.post(f"{base}/deposits/{deposit_id}/refund", headers=headers)
    assert already.status_code == 409


def test_parts_are_reserved_until_the_line_is_removed(client, session) -> None:
    ticket, headers = booked(client)
    base = f"/api/v1/repairs/{ticket['id']}"
    added = client.post(f"{base}/lines", headers=headers, json={"kind": "PART", "product_id": CABLE, "quantity": 1000})
    assert added.status_code == 201, added.text
    line = added.json()["lines"][0]
    assert line["reserved_quantity"] == 500
    assert added.json()["parts_short"] is True
    reserved = select(InventoryLevel.quantity_reserved).where(
        InventoryLevel.product_id == uuid.UUID(CABLE), InventoryLevel.store_id == uuid.UUID(STORE)
    )
    session.expire_all()
    assert session.scalar(reserved) == 500
    removed = client.delete(f"{base}/lines/{line['id']}", headers=headers)
    assert removed.status_code == 200, removed.text
    session.expire_all()
    assert session.scalar(reserved) == 0


def test_approval_link_is_single_use_and_expires(client, session) -> None:
    ticket, headers = booked(client)
    base = f"/api/v1/repairs/{ticket['id']}"
    sent = client.post(f"{base}/approval/request", headers=headers, json={"amount_cents": 15000, "note": "New screen"})
    assert sent.status_code == 200, sent.text
    url = sent.json()["approval_url"]
    assert url and "/repair/approve/" in url
    token = url.rsplit("/", 1)[-1]
    page = client.get(f"/repair/approve/{token}")
    assert page.status_code == 200
    assert "150.00" in page.text and "New screen" in page.text

    other, _ = booked_extra(client)
    other_sent = client.post(
        f"/api/v1/repairs/{other['id']}/approval/request", headers=headers, json={"amount_cents": 1000}
    )
    assert other_sent.status_code == 200, other_sent.text
    stale = other_sent.json()["approval_url"].rsplit("/", 1)[-1]
    row = session.get(RepairTicket, uuid.UUID(other["id"]))
    assert row is not None
    row.approval_expires_at = datetime.now(UTC) - timedelta(minutes=5)
    session.commit()
    expired = client.post(f"/repair/approve/{stale}", data={"outcome": "approve"})
    assert expired.status_code == 410

    decided = client.post(f"/repair/approve/{token}", data={"outcome": "approve"})
    assert decided.status_code == 200
    assert "Approved" in decided.text
    again = client.post(f"/repair/approve/{token}", data={"outcome": "decline"})
    assert again.status_code == 404
    detail = client.get(base, headers=headers).json()
    assert detail["status"] == "in_repair"
    assert detail["approval_status"] == "APPROVED"
    assert detail["tracking_url"]
    track = detail["tracking_url"].rsplit("/", 1)[-1]
    tracked = client.get(f"/track/{track}")
    assert tracked.status_code == 200
    assert "Being repaired" in tracked.text


def test_intake_passcode_photo_and_job_card(client) -> None:
    from wholesale_support import admin, seed

    seed(client)
    seed_ticket = repair(
        imeis(1, "35391805314")[0], passcode="2580", accessories="Case", intake_checklist={"powers_on": True}
    )
    pushed = push(
        client,
        [event("labour-2", "product", labour_product()), event("repair-pass", "repair_ticket", seed_ticket)],
    )
    assert pushed.status_code == 200, pushed.text
    headers, _ = admin(client)
    base = f"/api/v1/repairs/{seed_ticket['id']}"
    detail = client.get(base, headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["has_passcode"] is True
    assert detail.json()["accessories"] == "Case"
    revealed = client.get(f"{base}/passcode", headers=headers)
    assert revealed.status_code == 200
    assert revealed.json()["passcode"] == "2580"
    uploaded = client.post(
        f"{base}/attachments/json",
        headers=headers,
        json={"content_type": "image/png", "data_base64": TINY_PNG, "file_name": "front.png", "kind": "INTAKE"},
    )
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["attachments"][0]["file_name"] == "front.png"
    card = client.get(f"{base}/job-card", headers=headers)
    assert card.status_code == 200, card.text
    assert card.json()["pdf_base64"].startswith("JVBERi")
    board = client.get("/api/v1/repairs/board", headers=headers)
    assert board.status_code == 200, board.text
    assert any(column["status"] == "intake" and column["cards"] for column in board.json()["columns"])


def booked_extra(client) -> tuple[dict, dict[str, str]]:
    """A second ticket in a test that already seeded the store."""
    from wholesale_support import admin

    ticket = repair(imeis(1, "35391805315")[0])
    assert push(client, [event(f"repair-{ticket['id'][:8]}", "repair_ticket", ticket)]).status_code == 200
    headers, _ = admin(client)
    return ticket, headers
