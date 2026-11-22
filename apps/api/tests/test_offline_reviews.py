"""Lost-terminal and conflict requests. In-memory SQLite. Neither decision posts stock or money."""

import uuid

from sqlalchemy import func, select
from tests.conftest import ADMIN_PASSWORD

from app.core.security import hash_password
from app.models.inventory import StockMovement
from app.models.store import Store
from app.models.user import User


def _admin(client) -> dict[str, str]:
    response = client.post("/api/v1/auth/login-password", json={"username": "admin", "password": ADMIN_PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _reviewer(client, session) -> dict[str, str]:
    admin = session.scalar(select(User).where(User.username == "admin"))
    session.add(
        User(
            username="reviewer",
            email="reviewer@example.com",
            full_name="Reviewer",
            hashed_password=hash_password("reviewer-password-123"),
            is_active=True,
            store_id=None,
            role_id=admin.role_id,
            has_pos_access=False,
            has_portal_access=True,
            failed_login_attempts=0,
            token_version=0,
        )
    )
    session.commit()
    response = client.post(
        "/api/v1/auth/login-password",
        json={"username": "reviewer", "password": "reviewer-password-123"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _store(session) -> str:
    store_id = uuid.uuid4()
    session.add(Store(id=store_id, code="O84", name="Review", currency="USD"))
    session.commit()
    return str(store_id)


def test_lost_terminal_approval_does_not_write_off_stock(client, session) -> None:
    store_id = _store(session)
    admin = _admin(client)
    reviewer = _reviewer(client, session)
    payload = {
        "store_id": store_id,
        "device_id": str(uuid.uuid4()),
        "allocation_id": str(uuid.uuid4()),
        "last_sequence": 2,
        "quantity": 40,
        "reason": "Terminal did not return.",
        "evidence": "Last sync sequence 2.",
        "idempotency_key": "lost-1",
    }
    created = client.post("/api/v1/inventory/lost-terminal-requests", headers=admin, json=payload)
    assert created.status_code == 201, created.text
    again = client.post("/api/v1/inventory/lost-terminal-requests", headers=admin, json=payload)
    assert again.json()["id"] == created.json()["id"]
    refused = client.post(
        f"/api/v1/inventory/lost-terminal-requests/{created.json()['id']}/decision",
        headers=admin,
        json={"decision": "approved", "reason": "Same person."},
    )
    assert refused.status_code == 403
    decided = client.post(
        f"/api/v1/inventory/lost-terminal-requests/{created.json()['id']}/decision",
        headers=reviewer,
        json={"decision": "approved", "reason": "Recorded. Stock is not posted."},
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "approved"
    assert decided.json()["posting_status"] == "awaiting_approval"
    assert session.scalar(select(func.count()).select_from(StockMovement)) == 0


def test_conflict_adjustment_keeps_posting_disabled(client, session) -> None:
    store_id = _store(session)
    admin = _admin(client)
    reviewer = _reviewer(client, session)
    payload = {
        "store_id": store_id,
        "idempotency_key": "sale-key-1",
        "original_hash": "a" * 64,
        "proposed_hash": "b" * 64,
        "currency": "USD",
        "amount_cents": 500,
        "reason": "The second payload disagrees.",
        "evidence": "Both hashes retained.",
        "request_key": "adjust-1",
    }
    created = client.post("/api/v1/sync/conflict-adjustments", headers=admin, json=payload)
    assert created.status_code == 201, created.text
    again = client.post("/api/v1/sync/conflict-adjustments", headers=admin, json=payload)
    assert again.json()["id"] == created.json()["id"]
    decided = client.post(
        f"/api/v1/sync/conflict-adjustments/{created.json()['id']}/decision",
        headers=reviewer,
        json={"decision": "rejected", "reason": "No posting rule is approved."},
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "rejected"
    assert decided.json()["posting_status"] == "awaiting_approval"
    assert decided.json()["original_hash"] == "a" * 64


def test_cashier_cannot_request_a_write_off(client, session) -> None:
    from app.core.permissions import CASHIER_ROLE_ID
    from app.models.role import RolePermission

    store_id = _store(session)
    session.add(RolePermission(role_id=uuid.UUID(CASHIER_ROLE_ID), permission="portal:access"))
    session.commit()
    session.add(
        User(
            username="desk",
            email="desk@example.com",
            full_name="Desk",
            hashed_password=hash_password("desk-password-123"),
            is_active=True,
            store_id=None,
            role_id=uuid.UUID(CASHIER_ROLE_ID),
            has_pos_access=False,
            has_portal_access=True,
            failed_login_attempts=0,
            token_version=0,
        )
    )
    session.commit()
    response = client.post(
        "/api/v1/auth/login-password",
        json={"username": "desk", "password": "desk-password-123"},
    )
    assert response.status_code == 200, response.text
    refused = client.post(
        "/api/v1/inventory/lost-terminal-requests",
        headers={"Authorization": f"Bearer {response.json()['access_token']}"},
        json={
            "store_id": store_id,
            "device_id": str(uuid.uuid4()),
            "last_sequence": 0,
            "quantity": 1,
            "reason": "No.",
            "idempotency_key": "lost-cashier",
        },
    )
    assert refused.status_code == 403
