import uuid
from datetime import UTC, datetime, timedelta

from app.core.deps import Principal
from app.models.approval import ApprovalRequest
from app.models.sale import Sale
from app.models.user import User
from app.services import manager_service
from wholesale_support import CABLE, CASHIER_ID, STORE, admin, device, event, line, push, sale, seed


def _ask(client, kind: str = "PRICE_OVERRIDE") -> dict:
    response = client.post(
        "/api/v1/approvals",
        headers=device(),
        json={
            "kind": kind,
            "requested_by_id": CASHIER_ID,
            "title": "Price override: USB-C Cable",
            "details": ["15.00 to 12.00 per piece", "10 pcs: 120.00 (list 150.00)"],
            "amount_cents": 12_000,
            "store_id": STORE,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _cashier_token(client) -> str:
    return client.post("/api/v1/auth/login-pin", json={"username": "cashier", "pin": "1357"}, headers=device()).json()[
        "access_token"
    ]


def test_register_asks_manager_approves_and_sale_carries_the_approver(client) -> None:
    seed(client)
    headers, admin_id = admin(client)
    request = _ask(client)
    assert request["status"] == "PENDING" and request["store_code"] == "DT-01"

    inbox = client.get("/api/v1/approvals", headers=headers).json()
    assert [row["id"] for row in inbox] == [request["id"]]
    assert inbox[0]["requested_by_name"]

    no_note = client.post(f"/api/v1/approvals/{request['id']}/approve", headers=headers, json={"note": ""})
    assert no_note.status_code == 422
    approved = client.post(
        f"/api/v1/approvals/{request['id']}/approve", headers=headers, json={"note": "Regular trade customer"}
    )
    assert approved.status_code == 200, approved.text

    polled = client.get(f"/api/v1/approvals/{request['id']}", headers=device()).json()
    assert polled["status"] == "APPROVED"
    assert polled["approver"]["id"] == admin_id
    assert "pos:price_override" in polled["approver"]["permissions"]
    assert polled["note"] == "Regular trade customer"

    again = client.post(f"/api/v1/approvals/{request['id']}/decline", headers=headers, json={})
    assert again.status_code == 409

    body = sale([line(CABLE, 10, 1200, listed=1500, override_by=polled["approver"]["id"])])
    assert push(client, [event("remote-approved-sale", "sale", body)]).status_code == 200
    assert client.get("/api/v1/approvals", headers=headers).json() == []


def test_cashier_cannot_answer_and_expired_requests_close(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    request = _ask(client)
    cashier = _cashier_token(client)
    denied = client.post(
        f"/api/v1/approvals/{request['id']}/approve",
        headers={"Authorization": f"Bearer {cashier}"},
        json={"note": "self approve"},
    )
    assert denied.status_code == 403

    stored = session.get(ApprovalRequest, uuid.UUID(request["id"]))
    stored.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    session.commit()
    assert client.get(f"/api/v1/approvals/{request['id']}", headers=device()).json()["status"] == "EXPIRED"
    late = client.post(f"/api/v1/approvals/{request['id']}/approve", headers=headers, json={"note": "Too late"})
    assert late.status_code == 409

    cancelled = _ask(client, "CREDIT_LIMIT")
    assert client.post(f"/api/v1/approvals/{cancelled['id']}/cancel", headers=device()).json()["status"] == "CANCELLED"
    assert client.get("/api/v1/approvals", headers=headers).json() == []


def test_manager_dashboard_shows_today_by_branch_and_attention(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    assert push(client, [event("dash-sale-1", "sale", sale([line(CABLE, 4, 1500)]))]).status_code == 200
    assert push(client, [event("dash-sale-2", "sale", sale([line(CABLE, 2, 1500)]))]).status_code == 200
    _ask(client)
    # Sales from the sync helper are stamped 2026-10-19 08:00 UTC; look at that day from Dubai (UTC+4).
    user = session.query(User).filter(User.username == "admin").one()
    principal = Principal(kind="user", scope="portal", user=user, permissions=frozenset(user.permissions))
    board = manager_service.dashboard(session, principal, 240, now=datetime(2026, 10, 19, 15, 0, tzinfo=UTC))
    assert board.sales == 2
    assert board.net_cents == 9_000
    assert board.branches[0].store_code == "DT-01"
    assert board.branches[0].average_basket_cents == 4_500
    assert sum(board.hourly_cents) == 9_000
    assert board.hourly_cents[12] == 9_000
    assert board.top_products[0].quantity == 6
    assert board.attention.approvals == 1
    assert session.query(Sale).count() == 2

    live = client.get("/api/v1/manager/dashboard", headers=headers)
    assert live.status_code == 200, live.text
    assert live.json()["attention"]["approvals"] == 1
    assert client.get("/api/v1/manager/timesheets", headers=headers).status_code == 200
    assert client.get("/api/v1/manager/credit-holds", headers=headers).json() == []
