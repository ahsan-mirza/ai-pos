"""POS demo enrollment tickets, device-token exchange, and demo register unlock."""

import os
import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.database import build_engine
from app.core.permissions import Permission
from app.core.rate_limit import reset as reset_rates
from app.core.security import decode_access_token
from app.main import create_app
from app.models import Base
from app.models.device import DemoPosTicket, Device
from app.models.store import Store
from app.models.user import User
from app.services import payment_service
from app.services.demo_access import set_demo_access
from app.services.demo_catalog import EXPLORER_USERNAME, demo_tenants, seed_production_demos
from app.services.demo_pos import exchange_pos_ticket
from app.services.demo_reset import deactivate_demo_account, reactivate_demo_account, reset_demo_tenant
from app.services.rbac_service import ensure_super_admin, ensure_system_roles
from app.services.settings_service import clear_settings_cache, load_settings
from app.tenancy import provisioning, registry
from app.tenancy.context import use_tenant
from app.tenancy.models import ControlBase, Tenant

CODES = ("restaurant", "supermarket", "electronics", "fashion", "pharmacy")


class _Gateway(Exception):
    pass


def _boom(*_args, **_kwargs):
    raise _Gateway("A payment gateway was called.")


@pytest.fixture(scope="module")
def door(tmp_path_factory):
    root = tmp_path_factory.mktemp("demo-pos")
    previous = {
        "DATABASE_URL": os.environ.get("DATABASE_URL"),
        "CONTROL_DATABASE_URL": os.environ.get("CONTROL_DATABASE_URL"),
    }
    shared = f"sqlite:///{(root / 'shared.db').as_posix()}"
    control = f"sqlite:///{(root / 'control.db').as_posix()}"
    os.environ["DATABASE_URL"] = shared
    os.environ["CONTROL_DATABASE_URL"] = control
    get_settings.cache_clear()
    registry.invalidate()
    registry._control_factory.cache_clear()
    clear_settings_cache()
    settings = get_settings()
    settings.demo_pos_enroll_ip_limit = 500
    settings.demo_pos_enroll_code_limit = 500
    settings.demo_pos_exchange_ip_limit = 500
    settings.demo_pos_exchange_code_limit = 500
    ControlBase.metadata.create_all(build_engine(control))
    original_migrate = provisioning.migrate
    original_consume = payment_service.consume_for_sale
    provisioning.migrate = lambda url: Base.metadata.create_all(build_engine(url))
    payment_service.consume_for_sale = _boom
    try:
        seed_production_demos(settings)
        for spec in demo_tenants():
            set_demo_access(settings, spec["code"], enabled=True)
        with registry.control_session(settings) as db:
            db.add(
                Tenant(
                    slug="alpha",
                    name="Alpha Mobiles",
                    status="active",
                    profile="electronics_wholesale",
                    data_plane="shared",
                    database_url_encrypted=registry.encrypt_database_url(shared, settings),
                    is_demo=False,
                )
            )
            db.commit()
        found = registry.lookup("alpha", settings)
        assert found.tenant is not None
        with use_tenant(found.tenant), sessionmaker(bind=build_engine(shared), expire_on_commit=False)() as db:
            ensure_system_roles(db)
            ensure_super_admin(
                db,
                settings,
                username="alpha-admin",
                email="admin@alpha.example",
                full_name="Alpha Admin",
                password="alpha-password-1",
                pin=None,
            )
            load_settings(db, lock=True)
            db.commit()
    finally:
        payment_service.consume_for_sale = original_consume
        provisioning.migrate = original_migrate
    reset_rates()
    with TestClient(create_app()) as client:
        yield client
    if previous["DATABASE_URL"] is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = previous["DATABASE_URL"]
    if previous["CONTROL_DATABASE_URL"] is None:
        os.environ.pop("CONTROL_DATABASE_URL", None)
    else:
        os.environ["CONTROL_DATABASE_URL"] = previous["CONTROL_DATABASE_URL"]
    get_settings.cache_clear()
    registry.invalidate()
    registry._control_factory.cache_clear()
    clear_settings_cache()


def _enroll(client: TestClient, code: str, **headers: str):
    return client.post("/api/v1/demo-access/pos/enroll", json={"business_code": code}, headers=headers)


def _exchange(client: TestClient, ticket: str, **headers: str):
    return client.post(
        "/api/v1/demo-access/pos/exchange",
        json={"enrollment_ticket": ticket, "machine_name": "FRONT-PC"},
        headers=headers,
    )


def _closed(response) -> None:
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "demo_unavailable"
    assert "password" not in response.text.lower()
    assert "database" not in response.text.lower()


def _tenant(slug: str):
    registry.invalidate(slug)
    found = registry.lookup(slug, get_settings())
    assert found.tenant is not None
    return found.tenant


def _operational(slug: str):
    ref = _tenant(slug)
    session = sessionmaker(bind=build_engine(get_settings().database_url), expire_on_commit=False)()
    return ref, session


def test_each_business_enrolls_and_exchanges_a_device_token(door: TestClient) -> None:
    portal = door.post("/api/v1/demo-access/exchange", json={"business_code": "restaurant"})
    assert portal.status_code == 200, portal.text
    assert portal.json()["scope"] == "portal"
    for code in CODES:
        created = _enroll(door, code, **{"X-Tenant-Domain": "alpha"})
        assert created.status_code == 200, created.text
        body = created.json()
        assert body["business_code"] == code
        assert body["expires_in"] == get_settings().demo_pos_ticket_ttl_seconds
        assert set(body) == {"enrollment_ticket", "expires_in", "business_code"}
        assert "device_token" not in created.text
        ticket = body["enrollment_ticket"]
        assert ticket.startswith(f"{code}.")
        exchanged = _exchange(door, ticket, **{"X-Tenant-Domain": "alpha"})
        assert exchanged.status_code == 200, exchanged.text
        token = exchanged.json()
        assert token["tenant_slug"] == f"demo-{code}"
        assert token["device_token"].startswith("aipos_")
        assert "database_url" not in exchanged.text
        assert token["register_name"] == "Demo Register"
        again = _exchange(door, ticket)
        _closed(again)


def test_invalid_codes_and_client_tenant_fields_are_rejected(door: TestClient) -> None:
    _closed(_enroll(door, "warehouse"))
    extra = door.post(
        "/api/v1/demo-access/pos/enroll",
        json={"business_code": "restaurant", "tenant_id": str(uuid.uuid4())},
    )
    assert extra.status_code == 422
    _closed(_exchange(door, "not-a-ticket"))
    _closed(_exchange(door, "supermarket." + "x" * 20))


def test_disabled_expired_inactive_and_non_demo_are_unavailable(door: TestClient) -> None:
    settings = get_settings()
    set_demo_access(settings, "fashion", enabled=False)
    try:
        _closed(_enroll(door, "fashion"))
    finally:
        set_demo_access(settings, "fashion", enabled=True)
    with registry.control_session(settings) as db:
        row = db.scalar(select(Tenant).where(Tenant.slug == "demo-electronics"))
        assert row is not None
        original_expiry = row.demo_expires_at
        original_status = row.status
        original_demo = row.is_demo
        row.demo_expires_at = datetime.now(UTC) - timedelta(days=1)
        db.commit()
    registry.invalidate("demo-electronics")
    try:
        _closed(_enroll(door, "electronics"))
    finally:
        with registry.control_session(settings) as db:
            row = db.scalar(select(Tenant).where(Tenant.slug == "demo-electronics"))
            assert row is not None
            row.demo_expires_at = original_expiry
            row.status = original_status
            row.is_demo = original_demo
            db.commit()
        registry.invalidate("demo-electronics")
    with registry.control_session(settings) as db:
        row = db.scalar(select(Tenant).where(Tenant.slug == "demo-supermarket"))
        assert row is not None
        row.status = "suspended"
        db.commit()
    registry.invalidate("demo-supermarket")
    try:
        _closed(_enroll(door, "supermarket"))
    finally:
        with registry.control_session(settings) as db:
            row = db.scalar(select(Tenant).where(Tenant.slug == "demo-supermarket"))
            assert row is not None
            row.status = "active"
            db.commit()
        registry.invalidate("demo-supermarket")
    with registry.control_session(settings) as db:
        row = db.scalar(select(Tenant).where(Tenant.slug == "demo-restaurant"))
        assert row is not None
        row.is_demo = False
        db.commit()
    registry.invalidate("demo-restaurant")
    try:
        _closed(_enroll(door, "restaurant"))
    finally:
        with registry.control_session(settings) as db:
            row = db.scalar(select(Tenant).where(Tenant.slug == "demo-restaurant"))
            assert row is not None
            row.is_demo = True
            db.commit()
        registry.invalidate("demo-restaurant")


def test_inactive_store_and_missing_pos_permission_are_unavailable(door: TestClient) -> None:
    ref, db = _operational("demo-fashion")
    try:
        with use_tenant(ref):
            store = db.scalar(select(Store).where(Store.is_active.is_(True)))
            assert store is not None
            store.is_active = False
            db.commit()
        _closed(_enroll(door, "fashion"))
        with use_tenant(ref):
            store = db.scalar(select(Store))
            assert store is not None
            store.is_active = True
            user = db.scalar(select(User).where(User.username == EXPLORER_USERNAME))
            assert user is not None
            user.has_pos_access = False
            db.commit()
        _closed(_enroll(door, "fashion"))
        with use_tenant(ref):
            user = db.scalar(select(User).where(User.username == EXPLORER_USERNAME))
            assert user is not None
            user.has_pos_access = True
            db.commit()
    finally:
        db.close()


def test_expired_reused_wrong_scope_and_revoked_terminal(door: TestClient) -> None:
    created = _enroll(door, "restaurant")
    assert created.status_code == 200, created.text
    ticket = created.json()["enrollment_ticket"]
    ref, db = _operational("demo-restaurant")
    try:
        with use_tenant(ref):
            row = db.scalar(select(DemoPosTicket).order_by(DemoPosTicket.created_at.desc()))
            assert row is not None
            row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
            db.commit()
        _closed(_exchange(door, ticket))
        fresh = _enroll(door, "restaurant")
        assert fresh.status_code == 200, fresh.text
        ticket = fresh.json()["enrollment_ticket"]
        with use_tenant(ref):
            pending = select(DemoPosTicket).where(DemoPosTicket.used_at.is_(None))
            row = db.scalar(pending.order_by(DemoPosTicket.created_at.desc()))
            assert row is not None
            row.application_scope = "portal"
            db.commit()
        _closed(_exchange(door, ticket))
        fresh = _enroll(door, "restaurant")
        ticket = fresh.json()["enrollment_ticket"]
        with use_tenant(ref):
            pending = select(DemoPosTicket).where(DemoPosTicket.used_at.is_(None))
            row = db.scalar(pending.order_by(DemoPosTicket.created_at.desc()))
            assert row is not None
            device = db.get(Device, row.device_id)
            assert device is not None
            device.revoked_at = datetime.now(UTC)
            db.commit()
        _closed(_exchange(door, ticket))
    finally:
        db.close()


def test_a_ticket_cannot_be_exchanged_for_another_business(door: TestClient) -> None:
    created = _enroll(door, "electronics")
    assert created.status_code == 200, created.text
    ticket = created.json()["enrollment_ticket"]
    secret = ticket.split(".", 1)[1]
    _closed(_exchange(door, f"fashion.{secret}"))
    exchanged = _exchange(door, ticket)
    assert exchanged.status_code == 200, exchanged.text
    assert exchanged.json()["tenant_slug"] == "demo-electronics"


def test_one_ticket_cannot_be_consumed_twice_at_once(door: TestClient) -> None:
    created = _enroll(door, "supermarket")
    assert created.status_code == 200, created.text
    ticket = created.json()["enrollment_ticket"]
    settings = get_settings()
    outcomes: list[int] = []

    def once() -> None:
        try:
            exchange_pos_ticket(settings, ticket, "FRONT-PC", client_host="concurrent")
            outcomes.append(200)
        except Exception as exc:  # noqa: BLE001 - the loser is an API refusal or a database lock
            outcomes.append(getattr(exc, "status_code", 500))

    first = threading.Thread(target=once)
    second = threading.Thread(target=once)
    first.start()
    second.start()
    first.join()
    second.join()
    assert outcomes.count(200) == 1
    assert 404 in outcomes or 500 in outcomes
    _closed(_exchange(door, ticket))


def test_demo_session_skips_the_pin_and_stays_pos_scoped(door: TestClient, caplog) -> None:
    created = _enroll(door, "restaurant")
    ticket = created.json()["enrollment_ticket"]
    exchanged = _exchange(door, ticket)
    assert exchanged.status_code == 200, exchanged.text
    body = exchanged.json()
    assert ticket not in caplog.text
    assert body["device_token"] not in caplog.text
    headers = {"X-Tenant-Domain": body["tenant_domain"], "X-Terminal-Token": body["device_token"]}
    pin = door.post("/api/v1/auth/login-pin", json={"username": EXPLORER_USERNAME, "pin": "0000"}, headers=headers)
    assert pin.status_code == 401
    session = door.post("/api/v1/demo-access/pos/session", headers=headers)
    assert session.status_code == 200, session.text
    issued = session.json()
    assert issued["scope"] == "pos"
    assert Permission.DEVICES_MANAGE.value not in issued["user"]["permissions"]
    assert Permission.USERS_CREATE.value not in issued["user"]["permissions"]
    claims = decode_access_token(issued["access_token"], settings=get_settings())
    assert claims["scope"] == "pos"
    assert claims["demo"] is True
    portal = door.post("/api/v1/demo-access/exchange", json={"business_code": "restaurant"})
    portal_headers = {
        "Authorization": f"Bearer {portal.json()['access_token']}",
        "X-Tenant-Domain": body["tenant_domain"],
    }
    denied = door.post("/api/v1/demo-access/pos/session", headers=portal_headers)
    assert denied.status_code == 401
    feed = door.get("/api/v1/insights/feed", headers={**headers, "Authorization": f"Bearer {issued['access_token']}"})
    assert feed.status_code == 403
    assert feed.json()["error"]["message"] == "This token cannot be used for this action."
    other = door.post(
        "/api/v1/demo-access/pos/session",
        headers={"X-Tenant-Domain": "demo-supermarket", "X-Terminal-Token": body["device_token"]},
    )
    assert other.status_code == 401
    plain = dict(headers)
    ref, db = _operational("demo-restaurant")
    try:
        with use_tenant(ref):
            device = db.get(Device, uuid.UUID(body["register_id"]))
            assert device is not None and device.is_demo is True
            device.is_demo = False
            db.commit()
    finally:
        db.close()
    blocked = door.post("/api/v1/demo-access/pos/session", headers=plain)
    assert blocked.status_code == 403


def test_deactivate_and_reset_revoke_demo_register_credentials(door: TestClient) -> None:
    created = _enroll(door, "fashion")
    assert created.status_code == 200, created.text
    ticket = created.json()["enrollment_ticket"]
    deactivate_demo_account(get_settings(), "fashion")
    try:
        _closed(_exchange(door, ticket))
        _closed(_enroll(door, "fashion"))
    finally:
        reactivate_demo_account(get_settings(), "fashion")
        set_demo_access(get_settings(), "fashion", enabled=True)
    created = _enroll(door, "fashion")
    assert created.status_code == 200, created.text
    ticket = created.json()["enrollment_ticket"]
    exchanged = _exchange(door, ticket)
    assert exchanged.status_code == 200, exchanged.text
    token = exchanged.json()["device_token"]
    reset_demo_tenant(get_settings(), "fashion")
    set_demo_access(get_settings(), "fashion", enabled=True)
    refused = door.post(
        "/api/v1/demo-access/pos/session",
        headers={"X-Tenant-Domain": exchanged.json()["tenant_domain"], "X-Terminal-Token": token},
    )
    assert refused.status_code in {401, 403}
    _closed(_exchange(door, ticket))


def test_enrollment_is_rate_limited(door: TestClient) -> None:
    settings = get_settings()
    previous = settings.demo_pos_enroll_ip_limit
    settings.demo_pos_enroll_ip_limit = 2
    reset_rates()
    try:
        assert _enroll(door, "restaurant").status_code == 200
        assert _enroll(door, "supermarket").status_code == 200
        limited = _enroll(door, "electronics")
        assert limited.status_code == 429
        assert "enrollment_ticket" not in limited.text
    finally:
        settings.demo_pos_enroll_ip_limit = previous
        reset_rates()
