"""Authenticated HTTP checks for EC terminals. Two stores are created by signup, not by a shared tenant id."""

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.console import hardware
from app.console.billing import ensure_catalog
from app.console.entitlements import tenant_session
from app.console.security import OperatorPrincipal
from app.core.config import get_settings
from app.core.database import build_engine
from app.core.permissions import CASHIER_ROLE_ID, STORE_MANAGER_ROLE_ID
from app.core.security import hash_password
from app.models.device import Device
from app.models.store import Store
from app.models.user import User
from app.schemas.hardware import FulfillmentIn, HardwareItemIn, HardwarePick
from app.services.settings_service import load_settings
from app.tenancy import provisioning, registry
from app.tenancy.models import (
    BillingInvoice,
    BillingPlan,
    ControlBase,
    HardwareAssignment,
    HardwareOrderLine,
    Operator,
    Subscription,
    Tenant,
)
from test_signup import _create_all, _post, _status, _store, _tenant_headers, _verified


@pytest.fixture()
def signup(tmp_path, monkeypatch):
    previous_database = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = f"sqlite:///{(tmp_path / 'shared.db').as_posix()}"
    os.environ["CONTROL_DATABASE_URL"] = f"sqlite:///{(tmp_path / 'control.db').as_posix()}"
    os.environ["TENANT_DATABASE_URL_TEMPLATE"] = f"sqlite:///{tmp_path.as_posix()}/{{database}}.db"
    os.environ["SIGNUP_MAX_PER_HOUR"] = "8"
    get_settings.cache_clear()
    registry.invalidate()
    registry._control_factory.cache_clear()
    engine = build_engine(os.environ["CONTROL_DATABASE_URL"])
    ControlBase.metadata.create_all(engine)
    engine.dispose()
    monkeypatch.setattr(provisioning, "migrate", _create_all)
    from app.main import create_app

    yield TestClient(create_app())
    for name in ("CONTROL_DATABASE_URL", "TENANT_DATABASE_URL_TEMPLATE", "SIGNUP_MAX_PER_HOUR"):
        del os.environ[name]
    if previous_database is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = previous_database
    get_settings.cache_clear()
    registry.invalidate()
    registry._control_factory.cache_clear()


def _owner(client: TestClient, slug: str, email: str, phone: str) -> dict[str, str]:
    started = _verified(client, email=email, phone=phone)
    business = _post(client, started, "business", {"profile": "retail_fashion", "sub_type": "fashion_boutique"})
    assert business.status_code == 200
    assert _post(client, started, "store", _store(slug)).status_code == 200
    state = _status(client, started)
    assert state["status"] == "READY", state
    handed = client.post(
        "/api/v1/auth/handoff", headers=_tenant_headers(slug), json={"token": state["handoff_token"]}
    )
    assert handed.status_code == 200, handed.text
    return _tenant_headers(slug, handed.json()["access_token"])


def _grant_card_package(slug: str) -> None:
    settings = get_settings()
    with registry.control_session(settings) as db:
        ensure_catalog(db)
        db.commit()
        tenant = db.scalar(select(Tenant).where(Tenant.slug == slug))
        plan = db.scalar(select(BillingPlan).where(BillingPlan.code == "GROWTH"))
        assert tenant is not None and plan is not None
        row = db.scalar(select(Subscription).where(Subscription.tenant_id == tenant.id))
        assert row is not None
        row.plan_id = plan.id
        row.status = "active"
        row.current_period_end = datetime.now(UTC) + timedelta(days=30)
        db.commit()


def test_two_stores_cannot_share_a_terminal_and_a_live_charge_stays_refused(signup: TestClient) -> None:
    alpha = _owner(signup, "alpha", "owner@alpha.ae", "+971501110301")
    bravo = _owner(signup, "bravo", "owner@bravo.ae", "+971501110302")
    _grant_card_package("alpha")
    settings = get_settings()
    with registry.control_session(settings) as db:
        ensure_catalog(db)
        db.commit()
        operator_row = Operator(
            email="ec-ops@example.com", full_name="EC Ops", password_hash="x", totp_secret_enc="x", role="ADMIN"
        )
        db.add(operator_row)
        db.commit()
        operator = OperatorPrincipal(
            id=operator_row.id,
            email=operator_row.email,
            full_name=operator_row.full_name,
            role=operator_row.role,
            ip=None,
        )
        tenant = db.scalar(select(Tenant).where(Tenant.slug == "alpha"))
        assert tenant is not None
        category = hardware.list_categories(db)[0]
        item = hardware.create_item(
            db,
            operator,
            HardwareItemIn(
                sku="ECHTTP",
                name="Counter terminal",
                category_id=category.id,
                purchase_available=True,
                lease_available=False,
                purchase_fils=150_000,
                installation_fils=5_000,
                device_type="WIRED",
                warranty_months=12,
                reason="Publish a test terminal",
            ),
        )
        invoice = BillingInvoice(tenant_id=tenant.id, plan_code="LITE", cycle_code="MONTHLY", confirm_name="Terminal")
        db.add(invoice)
        db.commit()
        order = hardware.open_order(
            db,
            tenant_id=tenant.id,
            invoice_id=invoice.id,
            picks=[HardwarePick(item_id=item.id, quantity=1, mode="purchase", store_label="Counter")],
            stores=None,
        )
        assert order is not None
        db.commit()
        hardware.mark_paid(db, invoice.id)
        db.commit()
        line = db.scalar(select(HardwareOrderLine).where(HardwareOrderLine.order_id == order.id))
        assert line is not None
        hardware.fulfill(
            db,
            operator,
            order.id,
            FulfillmentIn(line_id=line.id, fulfilled_qty=1, serials=["HTTP-SN"], reason="Delivered for the HTTP test"),
        )
        assignment = db.scalar(select(HardwareAssignment).where(HardwareAssignment.order_line_id == line.id))
        assert assignment is not None
        assignment_id = assignment.id
        with tenant_session(tenant, settings) as store_db:
            store = store_db.scalar(select(Store).limit(1))
            assert store is not None
            store_id = store.id
            device = Device(
                tenant_id=tenant.id,
                store_id=store.id,
                code="T1",
                name="Till 1",
                key_hash="a" * 64,
                key_hint="aaaa",
            )
            store_db.add(device)
            cashier = User(
                username="alpha-cashier",
                email="cashier@alpha.ae",
                full_name="Alpha Cashier",
                hashed_password=hash_password("Cashier-password-1"),
                is_active=True,
                role_id=uuid.UUID(CASHIER_ROLE_ID),
                has_pos_access=True,
                has_portal_access=False,
                token_version=0,
            )
            manager = User(
                username="alpha-manager",
                email="manager@alpha.ae",
                full_name="Alpha Manager",
                hashed_password=hash_password("Manager-password-1"),
                is_active=True,
                role_id=uuid.UUID(STORE_MANAGER_ROLE_ID),
                has_pos_access=True,
                has_portal_access=True,
                token_version=0,
            )
            store_db.add(cashier)
            store_db.add(manager)
            settings_row = load_settings(store_db, lock=True)
            settings_row.capabilities = list(settings_row.capabilities or []) + ["card_terminals"]
            store_db.commit()
            register_id = device.id

    anonymous = signup.get("/api/v1/billing/ec-devices", headers=_tenant_headers("alpha"))
    assert anonymous.status_code == 401

    tampered = signup.post(
        "/api/v1/billing/ec-quote",
        headers=alpha,
        json={
            "hardware": [{"item_id": str(item.id), "quantity": 1, "mode": "purchase", "store_id": str(store_id)}],
            "purchase_fils": 1,
            "tenant_id": str(uuid.uuid4()),
        },
    )
    assert tampered.status_code == 422
    assert tampered.json()["error"]["field_errors"]["purchase_fils"] == "Purchase fils cannot be changed here."
    quoted = signup.post(
        "/api/v1/billing/ec-quote",
        headers=alpha,
        json={"hardware": [{"item_id": str(item.id), "quantity": 1, "mode": "purchase", "store_id": str(store_id)}]},
    )
    assert quoted.status_code == 200, quoted.text
    assert quoted.json()["recurring_fils"] == 0
    assert quoted.json()["total_fils"] == 155_000

    listed = signup.get("/api/v1/billing/ec-devices", headers=alpha)
    assert listed.status_code == 200, listed.text
    assert any(row["assignment_id"] == str(assignment_id) for row in listed.json())
    assert signup.get("/api/v1/billing/ec-devices", headers=bravo).json() == []

    hidden = signup.get(f"/api/v1/billing/ec-devices/{assignment_id}/readiness", headers=bravo)
    assert hidden.status_code == 404
    stolen = signup.post(
        f"/api/v1/billing/ec-devices/{assignment_id}/register",
        headers=bravo,
        json={"serial": "HTTP-SN"},
    )
    assert stolen.status_code == 404

    wrong = signup.post(
        f"/api/v1/billing/ec-devices/{assignment_id}/register",
        headers=alpha,
        json={"serial": "OTHER-SN"},
    )
    assert wrong.status_code == 409
    assert wrong.json()["error"]["code"] == "serial_mismatch"
    registered = signup.post(
        f"/api/v1/billing/ec-devices/{assignment_id}/register",
        headers=alpha,
        json={"serial": "HTTP-SN", "label": "Counter"},
    )
    assert registered.status_code == 200, registered.text
    assert registered.json()["registered"] is True
    assert registered.json()["connected"] is False
    assert registered.json()["payment_ready"] is False

    cashier_login = signup.post(
        "/api/v1/auth/login-password",
        headers=_tenant_headers("alpha"),
        json={"username": "alpha-cashier", "password": "Cashier-password-1"},
    )
    assert cashier_login.status_code == 403
    assert cashier_login.json()["error"]["code"] == "portal_access_denied"
    manager_login = signup.post(
        "/api/v1/auth/login-password",
        headers=_tenant_headers("alpha"),
        json={"username": "alpha-manager", "password": "Manager-password-1"},
    )
    assert manager_login.status_code == 200, manager_login.text
    manager = _tenant_headers("alpha", manager_login.json()["access_token"])
    forbidden = signup.put(
        f"/api/v1/billing/ec-devices/{assignment_id}/assignment",
        headers=manager,
        json={"store_id": str(store_id), "register_id": str(register_id)},
    )
    assert forbidden.status_code == 403
    assert signup.get("/api/v1/billing/ec-devices", headers=manager).status_code == 403
    forged = dict(alpha)
    forged["X-Tenant-Domain"] = "bravo.axizpos.com"
    crossed = signup.get("/api/v1/billing/ec-devices", headers=forged)
    assert crossed.status_code == 401
    assert crossed.json()["error"]["code"] == "invalid_token"
    os.environ["CONSOLE_JWT_SECRET"] = "test-only-console-secret-not-for-production"
    get_settings.cache_clear()
    console = signup.post(
        "/api/v1/super-admin/billing/transfers/00000000-0000-4000-8000-000000000099/approve",
        headers=alpha,
    )
    os.environ.pop("CONSOLE_JWT_SECRET", None)
    get_settings.cache_clear()
    assert console.status_code == 401
    assert console.json()["error"]["code"] == "invalid_token"

    foreign_store = signup.get("/api/v1/stores", headers=bravo).json()[0]["id"]
    foreign = signup.put(
        f"/api/v1/billing/ec-devices/{assignment_id}/assignment",
        headers=alpha,
        json={"store_id": foreign_store, "register_id": str(register_id)},
    )
    assert foreign.status_code == 422
    assert foreign.json()["error"]["code"] == "unknown_store"

    assigned = signup.put(
        f"/api/v1/billing/ec-devices/{assignment_id}/assignment",
        headers=alpha,
        json={"store_id": str(store_id), "register_id": str(register_id)},
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["register_id"] == str(register_id)
    cleared = signup.delete(f"/api/v1/billing/ec-devices/{assignment_id}/assignment", headers=alpha)
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["register_id"] is None
    assert any(event.get("action") == "unassign" for event in cleared.json()["history"])

    ready = signup.get(f"/api/v1/billing/ec-devices/{assignment_id}/readiness", headers=alpha)
    assert ready.status_code == 200, ready.text
    assert ready.json()["production_ready"] is False
    assert "INTEGRATION_NOT_CERTIFIED" in ready.json()["blockers"]

    refused = signup.post("/api/v1/payments/terminal-payments", headers=alpha)
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "terminal_not_configured"
