"""Pharmacist appointment, lot release, and quarantine clearance."""

import uuid
from datetime import timedelta

from sqlalchemy import func, select
from tests.test_auth import STORE_MANAGER_ROLE
from tests.test_capabilities import change_profile
from tests.test_inventory import WH, admin, bearer
from tests.test_pharmacy_catalog import OTHER_TENANT, PROFILES, _create, _medicine, _pharmacy
from tests.test_pharmacy_fefo import _on_hand as _hand
from tests.test_pharmacy_fefo import _sell
from tests.test_pharmacy_lots import LOT, _layers, _on_hand, _order_and_receive

from app.models.audit_log import AuditLog
from app.models.batch import BatchItem
from app.models.pharmacy_lots import BatchItemEvent, PharmacistAuthorization
from app.services.batch_ledger import today
from app.tenancy.scoping import INCLUDE_ALL


def _product(client, headers) -> str:
    created = _create(client, headers, "Release amoxicillin", _medicine(), sku="AMOX-REL", barcode="6291111111401")
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _manager(client, headers, username: str = "pharma.mgr") -> dict[str, str]:
    created = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": username,
            "email": f"{username}@example.com",
            "full_name": "Appointed Pharmacist",
            "role_id": STORE_MANAGER_ROLE,
            "store_id": WH,
            "password": "manager-password-1",
            "pin": "8642",
            "has_portal_access": True,
            "has_pos_access": True,
        },
    )
    assert created.status_code == 201, created.text
    signed = client.post(
        "/api/v1/auth/login-password",
        json={"username": username, "password": "manager-password-1"},
    )
    assert signed.status_code == 200, signed.text
    return bearer(signed.json()["access_token"]), created.json()["id"]


def _grant(client, headers, user_id: str, confirm: bool = True):
    return client.post(
        "/api/v1/pharmacy/pharmacists",
        headers=headers,
        json={"user_id": user_id, "reason": "Appointed for lot release", "confirm": confirm},
    )


def _officers(client, headers):
    """Two role managers nominate and confirm two governance officers. Neither signer becomes an officer."""
    role = client.post(
        "/api/v1/roles",
        headers=headers,
        json={
            "name": "Role clerk",
            "description": "Confirms the first governance officers",
            "permissions": ["roles:manage", "portal:access"],
        },
    )
    assert role.status_code == 201, role.text
    signer = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": "role.clerk",
            "email": "role.clerk@example.com",
            "full_name": "Role Clerk",
            "role_id": role.json()["id"],
            "store_id": WH,
            "password": "manager-password-1",
            "pin": "8642",
            "has_portal_access": True,
            "has_pos_access": True,
        },
    )
    assert signer.status_code == 201, signer.text
    signed = client.post(
        "/api/v1/auth/login-password",
        json={"username": "role.clerk", "password": "manager-password-1"},
    )
    assert signed.status_code == 200, signed.text
    signer_headers = bearer(signed.json()["access_token"])
    officer_a_headers, officer_a = _manager(client, headers, "officer.a")
    officer_b_headers, officer_b = _manager(client, headers, "officer.b")
    for officer_id, signer in ((officer_a, signer_headers), (officer_b, signer_headers)):
        nominated = client.post(
            "/api/v1/pharmacy/governance-officers",
            headers=headers,
            json={"user_id": officer_id, "reason": "Governance officer", "confirm": True},
        )
        assert nominated.status_code == 201, nominated.text
        confirmed = client.post(
            f"/api/v1/pharmacy/governance-officers/{officer_id}/confirm",
            headers=signer,
            json={"reason": "Second role manager confirms", "confirm": True},
        )
        assert confirmed.status_code == 200, confirmed.text
    return officer_a_headers, officer_b_headers, officer_a, officer_b


def _appoint(client, headers, pharmacist_id: str):
    """Two role managers establish two officers. Those officers request and approve the pharmacist."""
    officer_a_headers, officer_b_headers, _officer_a, _officer_b = _officers(client, headers)
    requested = client.post(
        "/api/v1/pharmacy/pharmacists",
        headers=officer_a_headers,
        json={"user_id": pharmacist_id, "reason": "Appointed for lot release", "confirm": True},
    )
    assert requested.status_code == 201, requested.text
    assert requested.json()["status"] == "PENDING"
    approved = client.post(
        f"/api/v1/pharmacy/pharmacists/{pharmacist_id}/approve",
        headers=officer_b_headers,
        json={"reason": "Independent approval", "confirm": True},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["active"] is True
    return officer_a_headers, officer_b_headers


def _release(client, headers, item_id, reason: str = "Checked and ready", confirm: bool = True):
    return client.post(
        f"/api/v1/pharmacy/lots/{item_id}/release",
        headers=headers,
        json={"reason": reason, "confirm": confirm},
    )


def test_only_an_appointed_pharmacist_can_release(client, session) -> None:
    seed_headers = admin(client)
    from tests.test_inventory import seed

    seed(client)
    headers = _pharmacy(client)
    product_id = _product(client, headers)
    _, received = _order_and_receive(client, headers, product_id, 4)
    assert received.status_code == 200, received.text
    item = _layers(session, product_id)[0]
    me = client.get("/api/v1/auth/me", headers=headers).json()

    denied = _release(client, headers, item.id)
    assert denied.status_code == 403, denied.text
    assert denied.json()["error"]["code"] == "pharmacist_required"
    session.expire_all()
    assert item.lot_status == "UNRELEASED"

    self_grant = _grant(client, headers, me["id"])
    assert self_grant.status_code == 403
    assert self_grant.json()["error"]["code"] == "self_authorization"

    unconfirmed = _grant(client, headers, me["id"], confirm=False)
    assert unconfirmed.status_code == 422
    assert unconfirmed.json()["error"]["code"] == "confirmation_required"

    manager_headers, manager_id = _manager(client, headers)
    manager_me = client.get("/api/v1/auth/me", headers=manager_headers)
    assert "pharmacy:authorize_pharmacist" not in manager_me.json()["permissions"]
    still = _release(client, manager_headers, item.id)
    assert still.status_code == 403
    assert still.json()["error"]["code"] == "pharmacist_required"

    officer_headers, _second_officer = _appoint(client, headers, manager_id)
    who = client.get("/api/v1/pharmacy/pharmacist-authorization", headers=manager_headers)
    assert who.status_code == 200
    assert who.json() == {"authorized": True}
    hidden = client.get("/api/v1/pharmacy/pharmacist-authorization", headers=headers)
    assert hidden.json() == {"authorized": False}

    missing_confirm = _release(client, manager_headers, item.id, confirm=False)
    assert missing_confirm.status_code == 422
    assert missing_confirm.json()["error"]["code"] == "confirmation_required"
    session.expire_all()
    assert item.lot_status == "UNRELEASED"
    released_events = session.scalar(
        select(func.count()).select_from(BatchItemEvent).where(BatchItemEvent.action == "RELEASED")
    )
    assert released_events == 0

    released = _release(client, manager_headers, item.id)
    assert released.status_code == 200, released.text
    assert released.json()["lot_status"] == "RELEASED"
    session.expire_all()
    assert item.lot_status == "RELEASED"
    assert item.released_by_id == uuid.UUID(manager_id)
    assert item.quantity_remaining == 4
    assert _on_hand(session, product_id) == 4
    event = session.scalar(select(BatchItemEvent).where(BatchItemEvent.action == "RELEASED"))
    assert event is not None
    assert event.from_status == "UNRELEASED"
    assert event.to_status == "RELEASED"
    assert event.reason == "Checked and ready"
    assert event.user_id == uuid.UUID(manager_id)
    audit = session.scalar(select(AuditLog).where(AuditLog.action == "pharmacy.lot_released"))
    assert audit is not None

    again = _release(client, manager_headers, item.id)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "already_released"

    sold, _ = _sell(client, WH, [(product_id, 1)])
    assert sold.status_code == 200, sold.text
    assert _hand(session, product_id) == 3

    revoked = client.post(
        f"/api/v1/pharmacy/pharmacists/{manager_id}/revoke",
        headers=officer_headers,
        json={"reason": "Appointment ended", "confirm": True},
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["active"] is False
    session.expire_all()
    assert session.scalar(
        select(func.count()).select_from(PharmacistAuthorization).where(PharmacistAuthorization.revoked_at.is_(None))
    ) == 0
    assert seed_headers


def test_release_rejects_ineligible_lots(client, session) -> None:
    from tests.test_inventory import seed

    seed(client)
    headers = _pharmacy(client)
    _, manager_id = _manager(client, headers, "pharma.rel")
    _appoint(client, headers, manager_id)
    manager = bearer(
        client.post(
            "/api/v1/auth/login-password",
            json={"username": "pharma.rel", "password": "manager-password-1"},
        ).json()["access_token"]
    )
    product_id = _product(client, headers)
    _, received = _order_and_receive(client, headers, product_id, 3)
    assert received.status_code == 200, received.text
    item = _layers(session, product_id)[0]

    item.expiry_date = today() - timedelta(days=1)
    session.commit()
    expired = _release(client, manager, item.id)
    assert expired.status_code == 422
    assert expired.json()["error"]["code"] == "lot_expired"

    item.expiry_date = None
    session.commit()
    missing_expiry = _release(client, manager, item.id)
    assert missing_expiry.json()["error"]["code"] == "expiry_required"

    item.expiry_date = today() + timedelta(days=30)
    item.manufacturer_lot = None
    session.commit()
    missing_lot = _release(client, manager, item.id)
    assert missing_lot.json()["error"]["code"] == "lot_required"

    item.manufacturer_lot = LOT
    item.quantity_remaining = 0
    session.commit()
    empty = _release(client, manager, item.id)
    assert empty.json()["error"]["code"] == "lot_empty"

    item.quantity_remaining = 3
    item.lot_status = "DAMAGED"
    session.commit()
    damaged = _release(client, manager, item.id)
    assert damaged.json()["error"]["code"] == "lot_damaged"

    item.lot_status = "SUPPLIER_RETURN"
    session.commit()
    returned = _release(client, manager, item.id)
    assert returned.json()["error"]["code"] == "lot_supplier_return"

    item.lot_status = "QUARANTINED"
    session.commit()
    held = _release(client, manager, item.id)
    assert held.json()["error"]["code"] == "invalid_transition"
    session.expire_all()
    assert item.lot_status == "QUARANTINED"
    released_events = session.scalar(
        select(func.count()).select_from(BatchItemEvent).where(BatchItemEvent.action == "RELEASED")
    )
    assert released_events == 0


def test_recalled_lot_cannot_be_released_or_cleared(client, session) -> None:
    from tests.test_inventory import seed

    seed(client)
    headers = _pharmacy(client)
    _, manager_id = _manager(client, headers, "pharma.rcl")
    _appoint(client, headers, manager_id)
    manager = bearer(
        client.post(
            "/api/v1/auth/login-password",
            json={"username": "pharma.rcl", "password": "manager-password-1"},
        ).json()["access_token"]
    )
    product_id = _product(client, headers)
    assert _order_and_receive(client, headers, product_id, 2)[1].status_code == 200
    opened = client.post(
        "/api/v1/pharmacy/recalls",
        headers=headers,
        json={
            "reference": "RCL-REL",
            "source_text": "Supplier letter",
            "severity": "high",
            "reason": "Do not release",
            "lots": [{"product_id": product_id, "manufacturer_lot": LOT}],
        },
    )
    assert opened.status_code == 201, opened.text
    item = _layers(session, product_id)[0]
    assert item.lot_status == "RECALLED"
    denied = _release(client, manager, item.id)
    assert denied.status_code == 422
    assert denied.json()["error"]["code"] == "lot_recalled"
    cleared = client.post(
        f"/api/v1/pharmacy/lots/{item.id}/clear-quarantine",
        headers=manager,
        json={"reason": "Trying to clear a recall", "confirm": True},
    )
    assert cleared.status_code == 422
    assert cleared.json()["error"]["code"] == "lot_recalled"
    session.expire_all()
    assert item.lot_status == "RECALLED"


def test_pharmacist_clears_an_eligible_quarantine(client, session) -> None:
    from tests.test_inventory import seed

    seed(client)
    headers = _pharmacy(client)
    _, manager_id = _manager(client, headers, "pharma.clr")
    _appoint(client, headers, manager_id)
    manager = bearer(
        client.post(
            "/api/v1/auth/login-password",
            json={"username": "pharma.clr", "password": "manager-password-1"},
        ).json()["access_token"]
    )
    product_id = _product(client, headers)
    assert _order_and_receive(client, headers, product_id, 2)[1].status_code == 200
    item = _layers(session, product_id)[0]
    blocked = client.post(
        f"/api/v1/pharmacy/lots/{item.id}/clear-quarantine",
        headers=headers,
        json={"reason": "Admin is not appointed", "confirm": True},
    )
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "pharmacist_required"
    quarantined = client.post(
        f"/api/v1/pharmacy/lots/{item.id}/quarantine",
        headers=headers,
        json={"reason": "Quality hold"},
    )
    assert quarantined.status_code == 200, quarantined.text
    item.expiry_date = today() - timedelta(days=1)
    session.commit()
    expired = client.post(
        f"/api/v1/pharmacy/lots/{item.id}/clear-quarantine",
        headers=manager,
        json={"reason": "Expired stock", "confirm": True},
    )
    assert expired.json()["error"]["code"] == "lot_expired"
    item.expiry_date = today() + timedelta(days=40)
    item.lot_status = "DAMAGED"
    session.commit()
    damaged = client.post(
        f"/api/v1/pharmacy/lots/{item.id}/clear-quarantine",
        headers=manager,
        json={"reason": "Damaged stock", "confirm": True},
    )
    assert damaged.json()["error"]["code"] == "lot_damaged"
    item.lot_status = "SUPPLIER_RETURN"
    session.commit()
    returned = client.post(
        f"/api/v1/pharmacy/lots/{item.id}/clear-quarantine",
        headers=manager,
        json={"reason": "Returned stock", "confirm": True},
    )
    assert returned.json()["error"]["code"] == "lot_supplier_return"
    item.lot_status = "QUARANTINED"
    item.manufacturer_lot = None
    session.commit()
    missing = client.post(
        f"/api/v1/pharmacy/lots/{item.id}/clear-quarantine",
        headers=manager,
        json={"reason": "No lot number", "confirm": True},
    )
    assert missing.json()["error"]["code"] == "lot_required"
    item.manufacturer_lot = LOT
    session.commit()
    cleared = client.post(
        f"/api/v1/pharmacy/lots/{item.id}/clear-quarantine",
        headers=manager,
        json={"reason": "Quality hold lifted", "confirm": True},
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["lot_status"] == "RELEASED"
    session.expire_all()
    assert item.lot_status == "RELEASED"
    assert item.quantity_remaining == 2
    event = session.scalar(
        select(BatchItemEvent).where(
            BatchItemEvent.from_status == "QUARANTINED",
            BatchItemEvent.to_status == "RELEASED",
        )
    )
    assert event is not None
    assert event.reason == "Quality hold lifted"
    history = client.get(f"/api/v1/pharmacy/lots/{item.id}/events", headers=manager)
    assert history.status_code == 200
    assert any(row["to_status"] == "RELEASED" for row in history.json())


def test_another_tenant_and_other_profiles_cannot_release(client, session) -> None:
    from tests.test_inventory import seed

    seed(client)
    headers = _pharmacy(client)
    product_id = _product(client, headers)
    assert _order_and_receive(client, headers, product_id, 1)[1].status_code == 200
    item = _layers(session, product_id)[0]
    manager_headers, manager_id = _manager(client, headers, "pharma.iso")
    _appoint(client, headers, manager_id)
    session.info[INCLUDE_ALL] = True
    foreign = BatchItem(
        tenant_id=OTHER_TENANT,
        batch_id=item.batch_id,
        product_id=item.product_id,
        store_id=item.store_id,
        quantity_imported=1,
        quantity_remaining=1,
        purchase_cost_per_unit=100,
        selling_price_per_unit=1500,
        expiry_date=item.expiry_date,
        manufacturer_lot="FOREIGN",
        lot_status="UNRELEASED",
        imported_serials=[],
    )
    session.add(foreign)
    session.commit()
    session.info.pop(INCLUDE_ALL, None)
    missing = _release(client, manager_headers, foreign.id)
    assert missing.status_code == 404
    session.info[INCLUDE_ALL] = True
    assert session.get(BatchItem, foreign.id).lot_status == "UNRELEASED"
    session.info.pop(INCLUDE_ALL, None)

    for profile in PROFILES:
        switched = change_profile(client, headers, profile)
        assert switched.status_code == 200, switched.text
        response = _release(client, manager_headers, item.id)
        assert response.status_code == 403, (profile, response.text)
    session.expire_all()
    assert item.lot_status == "UNRELEASED"
