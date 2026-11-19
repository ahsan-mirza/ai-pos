"""Governance of pharmacist appointment. A role does not appoint anyone."""

import uuid

from sqlalchemy import select
from tests.test_inventory import seed
from tests.test_pharmacy_catalog import OTHER_TENANT, _pharmacy
from tests.test_pharmacy_lots import _layers, _order_and_receive
from tests.test_pharmacy_release import _appoint, _grant, _manager, _officers, _product, _release

from app.core.permissions import GOVERNED_PERMISSIONS, SUPER_ADMIN_PERMISSIONS
from app.models.role import Role, RolePermission
from app.models.user import User
from app.services.rbac_service import ensure_system_roles
from app.tenancy.context import TenantRef, use_tenant
from app.tenancy.scoping import DEFAULT_TENANT_ID, INCLUDE_ALL


def _scope():
    return use_tenant(TenantRef(id=str(DEFAULT_TENANT_ID), slug="default", name="Default", database_url="sqlite://"))


def test_super_admin_sync_does_not_grant_appointment_authority(client, session) -> None:
    seed(client)
    headers = _pharmacy(client)
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    assert "pharmacy:authorize_pharmacist" not in me.json()["permissions"]
    created = client.post(
        "/api/v1/roles",
        headers=headers,
        json={
            "name": "Appointment role",
            "description": "Should be rejected",
            "permissions": ["portal:access", "pharmacy:authorize_pharmacist"],
        },
    )
    assert created.status_code == 422
    assert created.json()["error"]["code"] == "governed_permission"
    with _scope():
        role = session.scalar(select(Role).where(Role.name == "Super Admin"))
        role.permission_rows.append(RolePermission(permission="pharmacy:authorize_pharmacist"))
        session.flush()
        ensure_system_roles(session)
        session.commit()
        assert "pharmacy:authorize_pharmacist" not in set(role.permissions)
        assert set(role.permissions) == SUPER_ADMIN_PERMISSIONS
        assert GOVERNED_PERMISSIONS.isdisjoint(role.permissions)
    again = client.get("/api/v1/auth/me", headers=headers)
    assert "pharmacy:authorize_pharmacist" not in again.json()["permissions"]


def test_appointment_requires_two_officers_and_blocks_reciprocal_approval(client, session) -> None:
    seed(client)
    headers = _pharmacy(client)
    manager_headers, manager_id = _manager(client, headers, "plain.manager")
    nominated = client.post(
        "/api/v1/pharmacy/governance-officers",
        headers=manager_headers,
        json={"user_id": manager_id, "reason": "Store manager tries", "confirm": True},
    )
    assert nominated.status_code == 403
    assert nominated.json()["error"]["code"] == "self_authorization"
    other_headers, other_id = _manager(client, headers, "plain.other")
    denied = client.post(
        "/api/v1/pharmacy/governance-officers",
        headers=manager_headers,
        json={"user_id": other_id, "reason": "No role authority", "confirm": True},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "role_manager_required"

    me = client.get("/api/v1/auth/me", headers=headers).json()
    own = client.post(
        "/api/v1/pharmacy/governance-officers",
        headers=headers,
        json={"user_id": me["id"], "reason": "Admin nominates self", "confirm": True},
    )
    assert own.status_code == 403
    assert own.json()["error"]["code"] == "self_authorization"
    opened = client.post(
        "/api/v1/pharmacy/governance-officers",
        headers=headers,
        json={"user_id": other_id, "reason": "First nomination", "confirm": True},
    )
    assert opened.status_code == 201, opened.text
    self_confirm = client.post(
        f"/api/v1/pharmacy/governance-officers/{other_id}/confirm",
        headers=headers,
        json={"reason": "Nominator confirms", "confirm": True},
    )
    assert self_confirm.status_code == 403
    assert self_confirm.json()["error"]["code"] == "separation_of_duties"
    officer_a_headers, officer_b_headers, officer_a, officer_b = _officers(client, headers)

    late = client.post(
        "/api/v1/pharmacy/governance-officers",
        headers=headers,
        json={"user_id": manager_id, "reason": "Admin after establishment", "confirm": True},
    )
    assert late.status_code == 403
    assert late.json()["error"]["code"] == "officer_required"

    requested = _grant(client, officer_a_headers, officer_b)
    assert requested.status_code == 201, requested.text
    reciprocal = client.post(
        f"/api/v1/pharmacy/pharmacists/{officer_b}/approve",
        headers=officer_b_headers,
        json={"reason": "Approving myself", "confirm": True},
    )
    assert reciprocal.status_code == 403
    assert reciprocal.json()["error"]["code"] == "separation_of_duties"
    own = client.get("/api/v1/pharmacy/pharmacist-authorization", headers=officer_b_headers)
    assert own.json()["authorized"] is False

    pending_release = _release(client, other_headers, uuid.uuid4())
    assert pending_release.status_code == 403
    assert pending_release.json()["error"]["code"] == "pharmacist_required"

    duplicate = _grant(client, officer_a_headers, officer_b)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "already_pending"

    _appoint_existing = client.post(
        "/api/v1/pharmacy/pharmacists",
        headers=officer_a_headers,
        json={"user_id": manager_id, "reason": "Appoint the manager", "confirm": True},
    )
    assert _appoint_existing.status_code == 201, _appoint_existing.text
    same_officer = client.post(
        f"/api/v1/pharmacy/pharmacists/{manager_id}/approve",
        headers=officer_a_headers,
        json={"reason": "Requester approves", "confirm": True},
    )
    assert same_officer.status_code == 403
    assert same_officer.json()["error"]["code"] == "separation_of_duties"
    approved = client.post(
        f"/api/v1/pharmacy/pharmacists/{manager_id}/approve",
        headers=officer_b_headers,
        json={"reason": "Independent approval", "confirm": True},
    )
    assert approved.status_code == 200, approved.text
    assert client.get("/api/v1/pharmacy/pharmacist-authorization", headers=manager_headers).json()["authorized"] is True
    revoked = client.post(
        f"/api/v1/pharmacy/pharmacists/{manager_id}/revoke",
        headers=officer_a_headers,
        json={"reason": "Appointment ended", "confirm": True},
    )
    assert revoked.status_code == 200, revoked.text
    manager_auth = client.get("/api/v1/pharmacy/pharmacist-authorization", headers=manager_headers)
    assert manager_auth.json()["authorized"] is False
    assert session.scalar(select(User).where(User.id == uuid.UUID(manager_id))) is not None
    history = client.get("/api/v1/pharmacy/governance", headers=officer_b_headers)
    assert history.status_code == 200, history.text
    body = history.json()
    assert all(item["status"] in {"PENDING", "ACTIVE"} for item in body["appointments"])
    closed = [item for item in body["appointment_history"] if item["user_id"] == manager_id]
    assert len(closed) == 1
    assert closed[0]["status"] == "REVOKED"
    assert closed[0]["revocation_reason"] == "Appointment ended"
    assert closed[0]["approved_at"]
    assert closed[0]["revoked_at"]
    renewed = _grant(client, officer_a_headers, manager_id)
    assert renewed.status_code == 201, renewed.text
    again = client.get("/api/v1/pharmacy/governance", headers=officer_b_headers).json()
    assert any(item["user_id"] == manager_id and item["status"] == "PENDING" for item in again["appointments"])
    assert any(item["user_id"] == manager_id and item["status"] == "REVOKED" for item in again["appointment_history"])


def test_revoked_pharmacist_cannot_release_or_clear(client, session) -> None:
    seed(client)
    headers = _pharmacy(client)
    _manager_headers, manager_id = _manager(client, headers, "pharma.gone")
    officer_headers, _second = _appoint(client, headers, manager_id)
    product_id = _product(client, headers)
    assert _order_and_receive(client, headers, product_id, 2)[1].status_code == 200
    item = _layers(session, product_id)[0]
    manager = _manager_headers
    revoked = client.post(
        f"/api/v1/pharmacy/pharmacists/{manager_id}/revoke",
        headers=officer_headers,
        json={"reason": "Removed before release", "confirm": True},
    )
    assert revoked.status_code == 200, revoked.text
    denied = _release(client, manager, item.id)
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "pharmacist_required"
    held = client.post(
        f"/api/v1/pharmacy/lots/{item.id}/quarantine",
        headers=headers,
        json={"reason": "Quality hold"},
    )
    assert held.status_code == 200, held.text
    cleared = client.post(
        f"/api/v1/pharmacy/lots/{item.id}/clear-quarantine",
        headers=manager,
        json={"reason": "Trying after revocation", "confirm": True},
    )
    assert cleared.status_code == 403
    assert cleared.json()["error"]["code"] == "pharmacist_required"
    session.expire_all()
    assert item.lot_status == "QUARANTINED"


def test_other_tenant_user_cannot_be_appointed(client, session) -> None:
    seed(client)
    headers = _pharmacy(client)
    session.info[INCLUDE_ALL] = True
    foreign = User(
        tenant_id=OTHER_TENANT,
        username="foreign.user",
        email="foreign.user@example.com",
        full_name="Foreign User",
        role_id=uuid.UUID("00000000-0000-4000-8000-0000000000a2"),
        is_active=True,
        has_portal_access=True,
    )
    session.add(foreign)
    session.commit()
    foreign_id = str(foreign.id)
    session.info.pop(INCLUDE_ALL, None)
    response = client.post(
        "/api/v1/pharmacy/governance-officers",
        headers=headers,
        json={"user_id": foreign_id, "reason": "Other tenant", "confirm": True},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
