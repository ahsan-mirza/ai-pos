import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import CASHIER_ROLE_ID
from app.models import AuditLog
from test_returns import CASHIER_ID, STORE_ID, STORE_MANAGER_ROLE, admin_token, bearer, device, seed_catalog
from test_settings import portal_user


def logs(session: Session, **where: object) -> list[AuditLog]:
    session.expire_all()
    statement = select(AuditLog).order_by(AuditLog.occurred_at)
    for column, value in where.items():
        statement = statement.where(getattr(AuditLog, column) == value)
    return list(session.scalars(statement).all())


def test_password_login_is_logged_with_device_and_ip(client, session: Session) -> None:
    admin_token(client)
    [entry] = logs(session, action_type="LOGIN_PASSWORD")
    assert entry.user_name == "Root Admin"
    assert entry.user_role == "Super Admin"
    assert entry.client_device in {"web", "api"}
    assert entry.ip_address


def test_mutations_record_json_diffs(client, session: Session) -> None:
    token = admin_token(client)
    created = client.post(
        "/api/v1/categories", headers={**bearer(token), "X-Client-Device": "web"}, json={"name": "Audio"}
    )
    assert created.status_code == 201, created.text
    category_id = uuid.UUID(created.json()["id"])

    [create] = logs(session, target_entity="Category", action_type="CREATE")
    assert create.target_entity_id == category_id
    assert create.old_values is None
    assert create.new_values["name"] == "Audio"
    assert create.client_device == "web"
    assert create.request_path == "/api/v1/categories"

    renamed = client.patch(f"/api/v1/categories/{category_id}", headers=bearer(token), json={"name": "Audio Gear"})
    assert renamed.status_code == 200, renamed.text
    [update] = logs(session, target_entity="Category", action_type="UPDATE")
    assert update.old_values["name"] == "Audio" and update.new_values["name"] == "Audio Gear"
    assert "created_at" not in update.new_values

    assert client.delete(f"/api/v1/categories/{category_id}", headers=bearer(token)).status_code == 204
    [delete] = logs(session, target_entity="Category", action_type="DELETE")
    assert delete.old_values["name"] == "Audio Gear" and delete.new_values is None


def test_secrets_are_redacted_and_role_changes_classified(client, session: Session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    portal_user(client, token, username="manager", role_id=STORE_MANAGER_ROLE, store_id=STORE_ID)
    [user_create] = logs(session, target_entity="User", action_type="CREATE")
    assert user_create.new_values["hashed_password"] == "[redacted]"

    manager_id = user_create.target_entity_id
    moved = client.patch(f"/api/v1/users/{manager_id}", headers=bearer(token), json={"role_id": CASHIER_ROLE_ID})
    assert moved.status_code == 200, moved.text
    [change] = logs(session, action_type="ROLE_CHANGE", target_entity="User")
    assert change.old_values["role_id"] == STORE_MANAGER_ROLE
    assert change.new_values["role_id"] == CASHIER_ROLE_ID

    role = client.post(
        "/api/v1/roles", headers=bearer(token), json={"name": "Auditors", "permissions": ["portal:access"]}
    ).json()
    granted = client.patch(
        f"/api/v1/roles/{role['id']}", headers=bearer(token), json={"permissions": ["portal:access", "audit:read"]}
    )
    assert granted.status_code == 200, granted.text
    [permissions] = logs(session, action_type="ROLE_CHANGE", target_entity="Role")
    assert permissions.old_values["permissions"] == ["portal:access"]
    assert permissions.new_values["permissions"] == ["audit:read", "portal:access"]


def test_entries_are_immutable(client, session: Session) -> None:
    admin_token(client)
    [entry] = logs(session, action_type="LOGIN_PASSWORD")
    entry.reason_notes = "tampered"
    with pytest.raises(PermissionError):
        session.flush()
    session.rollback()
    session.delete(session.get(AuditLog, entry.id))
    with pytest.raises(PermissionError):
        session.flush()
    session.rollback()


def test_users_in_the_trail_cannot_be_deleted(client, session: Session) -> None:
    token = admin_token(client)
    portal_user(client, token, username="auditor", role_id=STORE_MANAGER_ROLE, store_id=None)
    [created] = logs(session, target_entity="User", action_type="CREATE")
    blocked = client.delete(f"/api/v1/users/{created.target_entity_id}", headers=bearer(token))
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "user_has_audit_history"


def test_list_filters_summary_detail_and_export(client, session: Session) -> None:
    token = admin_token(client)
    client.post("/api/v1/categories", headers=bearer(token), json={"name": "Chargers"})

    page = client.get("/api/v1/audit-logs", headers=bearer(token))
    assert page.status_code == 200, page.text
    body = page.json()
    assert body["total"] == 2
    assert [row["action_type"] for row in body["rows"]] == ["CREATE", "LOGIN_PASSWORD"]
    assert body["rows"][0]["changed_fields"]

    only_logins = client.get("/api/v1/audit-logs?action_type=LOGIN_PASSWORD", headers=bearer(token)).json()
    assert only_logins["total"] == 1
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    empty = client.get("/api/v1/audit-logs", params={"from": future}, headers=bearer(token)).json()
    assert empty["total"] == 0

    detail = client.get(f"/api/v1/audit-logs/{body['rows'][0]['id']}", headers=bearer(token)).json()
    assert detail["new_values"]["name"] == "Chargers"

    summary = client.get("/api/v1/audit-logs/summary", headers=bearer(token)).json()
    assert summary["total_actions"] == 2
    assert summary["active_staff_sessions"] == 1
    assert summary["active_staff"][0]["user_name"] == "Root Admin"

    facets = client.get("/api/v1/audit-logs/facets", headers=bearer(token)).json()
    assert "Category" in facets["entities"]

    exported = client.get("/api/v1/audit-logs/export?format=csv", headers=bearer(token))
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert exported.text.splitlines()[0].startswith("occurred_at,user_name")
    [export] = logs(session, action_type="EXPORT_DATA")
    assert export.details["rows"] == 2 and export.details["format"] == "csv"

    pdf = client.get("/api/v1/audit-logs/export?format=pdf", headers=bearer(token))
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")


def test_audit_trail_needs_permission(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    manager = portal_user(client, token, username="manager", role_id=STORE_MANAGER_ROLE, store_id=STORE_ID)
    assert client.get("/api/v1/audit-logs", headers=bearer(manager)).status_code == 403
    assert client.get("/api/v1/audit-logs", headers=device()).status_code == 403


def desktop_event(**overrides: object) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "occurred_at": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
        "action_type": "DRAWER_OPEN",
        "action": "drawer.no_sale",
        "user_id": CASHIER_ID,
        "store_id": STORE_ID,
        "target_entity": "CashDrawer",
        "reason_notes": "Change for a customer",
        **overrides,
    }


def test_desktop_batches_are_idempotent(client, session: Session) -> None:
    seed_catalog(client)
    drawer = desktop_event()
    unexplained = desktop_event(action_type="CASH_DROP", action="drawer.cash_drop", reason_notes=" ")
    batch = {"device_id": "till-1", "events": [drawer, unexplained, desktop_event(user_id=str(uuid.uuid4()))]}

    assert client.post("/api/v1/audit-logs/sync", json=batch).status_code == 401
    first = client.post("/api/v1/audit-logs/sync", headers=device(), json=batch)
    assert first.status_code == 200, first.text
    result = first.json()
    assert result["accepted"] == [drawer["id"]]
    assert {item["reason"] for item in result["rejected"]} == {"CASH_DROP needs a reason.", "Unknown cashier."}

    again = client.post("/api/v1/audit-logs/sync", headers=device(), json={"device_id": "till-1", "events": [drawer]})
    assert again.json()["duplicates"] == [drawer["id"]]

    [entry] = logs(session, action_type="DRAWER_OPEN")
    assert entry.user_name == "Front Cashier"
    assert entry.client_device == "desktop"
    assert entry.details["device_id"] == "till-1"
    assert entry.occurred_at < entry.created_at
