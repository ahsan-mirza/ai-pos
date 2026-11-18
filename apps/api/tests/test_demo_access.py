"""Public demo exchange through the real middleware and the existing portal token."""

import os
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.database import build_engine
from app.core.security import decode_access_token
from app.main import create_app
from app.models import Base
from app.models.audit_log import AuditLog
from app.models.role import Role
from app.models.user import User
from app.services import payment_service
from app.services.demo_access import set_demo_access
from app.services.demo_catalog import EXPLORER_USERNAME, demo_tenants, seed_production_demos
from app.services.demo_reset import deactivate_demo_account, reactivate_demo_account, reset_demo_tenant
from app.services.rbac_service import ensure_super_admin, ensure_system_roles
from app.services.settings_service import clear_settings_cache, load_settings
from app.tenancy import provisioning, registry
from app.tenancy.context import use_tenant
from app.tenancy.models import ControlBase, Tenant

NAMES = {
    "restaurant": "Harbor & Rye",
    "supermarket": "Noon Market",
    "electronics": "Axis Electronics",
    "fashion": "Linen & Co",
}


class _Gateway(Exception):
    pass


def _boom(*_args, **_kwargs):
    raise _Gateway("A payment gateway was called.")


@pytest.fixture(scope="module")
def door(tmp_path_factory):
    root = tmp_path_factory.mktemp("demo-access")
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
        engine = build_engine(shared)
        with use_tenant(found.tenant), sessionmaker(bind=engine, expire_on_commit=False)() as db:
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


def _exchange(client: TestClient, code: str, **headers: str):
    return client.post("/api/v1/demo-access/exchange", json={"business_code": code}, headers=headers)


def _tenant_id(slug: str) -> str:
    registry.invalidate(slug)
    found = registry.lookup(slug, get_settings())
    assert found.tenant is not None
    return found.tenant.id


def _closed(response) -> None:
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "demo_unavailable"
    text = response.text.lower()
    assert "resetting" not in text
    assert "reset_failed" not in text
    assert "expired" not in text
    assert "explorer" not in text
    assert "password" not in text


def _issued(client: TestClient, code: str, **headers: str) -> dict:
    response = _exchange(client, code, **headers)
    assert response.status_code == 200, response.text
    body = response.json()
    slug = f"demo-{code}"
    assert body["token_type"] == "bearer"
    assert body["demo"] is True
    assert body["business_code"] == code
    assert body["business_name"] == NAMES[code]
    assert body["scope"] == "portal"
    assert body["expires_in"] == get_settings().access_token_expire_minutes * 60
    assert body["user"]["username"] == EXPLORER_USERNAME
    assert body["user"]["role"]["name"] == "Demo Explorer"
    assert "users:create" not in body["user"]["permissions"]
    assert "hashed_password" not in response.text
    claims = decode_access_token(body["access_token"], settings=get_settings())
    assert claims["demo"] is True
    assert claims["scope"] == "portal"
    assert claims["tid"] == _tenant_id(slug)
    assert claims["sub"] == body["user"]["id"]
    assert "ver" in claims
    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {body['access_token']}", "X-Tenant-Domain": f"{slug}.axizpos.com"},
    )
    assert me.status_code == 200, me.text
    assert me.json()["username"] == EXPLORER_USERNAME
    assert me.json()["role"]["name"] == "Demo Explorer"
    return body


@contextmanager
def _flag(slug: str, **values):
    previous: dict = {}
    with registry.control_session(get_settings()) as db:
        row = db.scalar(select(Tenant).where(Tenant.slug == slug))
        assert row is not None
        for key, value in values.items():
            previous[key] = getattr(row, key)
            setattr(row, key, value)
        db.commit()
    try:
        yield
    finally:
        with registry.control_session(get_settings()) as db:
            row = db.scalar(select(Tenant).where(Tenant.slug == slug))
            assert row is not None
            for key, value in previous.items():
                setattr(row, key, value)
            db.commit()


def _user(slug: str) -> tuple:
    registry.invalidate(slug)
    found = registry.lookup(slug, get_settings())
    assert found.tenant is not None
    db = sessionmaker(bind=build_engine(found.tenant.database_url), expire_on_commit=False)()
    return db, found.tenant


def test_each_business_code_issues_its_own_explorer(door: TestClient):
    seen = set()
    for code in ("restaurant", "supermarket", "electronics", "fashion"):
        body = _issued(door, code)
        seen.add(body["user"]["id"])
        claims = decode_access_token(body["access_token"], settings=get_settings())
        assert claims["tid"] == _tenant_id(f"demo-{code}")
    assert len(seen) == 4


def test_unknown_code_and_closed_demos_are_generic(door: TestClient):
    unknown = _exchange(door, "warehouse")
    _closed(unknown)
    with _flag("demo-supermarket", demo_access_enabled=False):
        _closed(_exchange(door, "supermarket"))
    with _flag("demo-electronics", demo_status="disabled"):
        _closed(_exchange(door, "electronics"))
    with _flag("demo-fashion", demo_expires_at=datetime.now(UTC) - timedelta(days=1)):
        _closed(_exchange(door, "fashion"))
    with _flag("demo-restaurant", demo_status="resetting"):
        _closed(_exchange(door, "restaurant"))
    with _flag("demo-supermarket", demo_status="reset_failed"):
        _closed(_exchange(door, "supermarket"))
    assert _exchange(door, "restaurant").status_code == 200


def test_explorer_must_be_the_active_system_role(door: TestClient):
    db, ref = _user("demo-fashion")
    original_role = None
    try:
        with use_tenant(ref):
            explorer = db.scalar(select(User).where(User.username == EXPLORER_USERNAME))
            assert explorer is not None
            original_role = explorer.role_id
            explorer.username = "explorer-hidden"
            db.commit()
        _closed(_exchange(door, "fashion"))
        with use_tenant(ref):
            hidden = db.scalar(select(User).where(User.username == "explorer-hidden"))
            assert hidden is not None
            hidden.username = EXPLORER_USERNAME
            hidden.is_active = False
            db.commit()
        _closed(_exchange(door, "fashion"))
        with use_tenant(ref):
            inactive = db.scalar(select(User).where(User.username == EXPLORER_USERNAME))
            assert inactive is not None
            inactive.is_active = True
            admin_role = db.scalar(select(Role).where(Role.name == "Super Admin", Role.is_system.is_(True)))
            assert admin_role is not None
            inactive.role_id = admin_role.id
            db.commit()
        _closed(_exchange(door, "fashion"))
    finally:
        with use_tenant(ref):
            user = db.scalar(select(User).where(User.username.in_([EXPLORER_USERNAME, "explorer-hidden"])))
            if user is not None and original_role is not None:
                user.username = EXPLORER_USERNAME
                user.is_active = True
                user.role_id = original_role
                db.commit()
        db.close()
    assert _exchange(door, "fashion").status_code == 200


def test_header_and_host_cannot_select_another_tenant(door: TestClient):
    spoofed = door.get("/api/v1/tenant", headers={"X-Tenant-Domain": "demo-supermarket.axizpos.com"})
    assert spoofed.status_code == 200, spoofed.text
    assert spoofed.json()["slug"] == "demo-supermarket"
    body = _issued(door, "restaurant", **{"X-Tenant-Domain": "demo-supermarket.axizpos.com"})
    claims = decode_access_token(body["access_token"], settings=get_settings())
    assert claims["tid"] == _tenant_id("demo-restaurant")
    assert claims["tid"] != _tenant_id("demo-supermarket")
    hosted = _issued(door, "fashion", Host="demo-electronics.axizpos.com")
    hosted_claims = decode_access_token(hosted["access_token"], settings=get_settings())
    assert hosted_claims["tid"] == _tenant_id("demo-fashion")
    assert hosted_claims["tid"] != _tenant_id("demo-electronics")
    extra = door.post(
        "/api/v1/demo-access/exchange",
        json={"business_code": "restaurant", "tenant_id": str(uuid.uuid4())},
    )
    assert extra.status_code == 422
    assert "access_token" not in extra.text


def test_rate_limit_stops_a_client(door: TestClient, monkeypatch: pytest.MonkeyPatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "demo_exchange_ip_limit", 2, raising=False)
    assert _exchange(door, "electronics").status_code == 200
    assert _exchange(door, "electronics").status_code == 200
    blocked = _exchange(door, "electronics")
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert "access_token" not in blocked.text


def test_audit_and_logs_omit_the_token(door: TestClient, caplog: pytest.LogCaptureFixture):
    caplog.set_level("INFO", logger="ai_pos.demo_access")
    body = _issued(door, "supermarket")
    assert body["access_token"] not in caplog.text
    assert "hashed_password" not in caplog.text
    db, ref = _user("demo-supermarket")
    try:
        with use_tenant(ref):
            rows = list(db.scalars(select(AuditLog).where(AuditLog.action == "demo.exchange")))
            issued = next(row for row in rows if row.details.get("category") == "issued")
            login = db.scalar(select(AuditLog).where(AuditLog.action == "auth.login_demo"))
            assert login is not None
            assert issued.details["business_code"] == "supermarket"
            assert issued.details["result"] == "success"
            assert body["access_token"] not in str(issued.details)
            assert "hashed_password" not in str(issued.details)
    finally:
        db.close()
    with _flag("demo-electronics", demo_access_enabled=False):
        _closed(_exchange(door, "electronics"))
    db, ref = _user("demo-electronics")
    try:
        with use_tenant(ref):
            refused = db.scalar(
                select(AuditLog).where(AuditLog.action == "demo.exchange").order_by(AuditLog.created_at.desc())
            )
            assert refused is not None
            assert refused.details["category"] == "access_disabled"
            assert refused.details["result"] == "refused"
    finally:
        db.close()


def test_reset_and_deactivation_reject_the_old_token(door: TestClient):
    restaurant = _issued(door, "restaurant")
    supermarket = _issued(door, "supermarket")
    reset_demo_tenant(get_settings(), "restaurant")
    stale = door.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": f"Bearer {restaurant['access_token']}",
            "X-Tenant-Domain": "demo-restaurant.axizpos.com",
        },
    )
    assert stale.status_code == 401
    fresh = _issued(door, "restaurant")
    assert fresh["access_token"] != restaurant["access_token"]
    still = decode_access_token(supermarket["access_token"], settings=get_settings())
    assert still["tid"] == _tenant_id("demo-supermarket")
    me = door.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": f"Bearer {supermarket['access_token']}",
            "X-Tenant-Domain": "demo-supermarket.axizpos.com",
        },
    )
    assert me.status_code == 200
    fashion = _issued(door, "fashion")
    try:
        deactivate_demo_account(get_settings(), "fashion")
        revoked = door.get(
            "/api/v1/auth/me",
            headers={
                "Authorization": f"Bearer {fashion['access_token']}",
                "X-Tenant-Domain": "demo-fashion.axizpos.com",
            },
        )
        assert revoked.status_code == 401
        _closed(_exchange(door, "fashion"))
    finally:
        reactivate_demo_account(get_settings(), "fashion")
        set_demo_access(get_settings(), "fashion", enabled=True)
    assert _exchange(door, "fashion").status_code == 200


def test_token_version_is_checked_on_the_protected_route(door: TestClient):
    body = _issued(door, "electronics")
    db, ref = _user("demo-electronics")
    try:
        with use_tenant(ref):
            explorer = db.scalar(select(User).where(User.username == EXPLORER_USERNAME))
            assert explorer is not None
            explorer.token_version = int(explorer.token_version or 0) + 1
            db.commit()
    finally:
        db.close()
    rejected = door.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": f"Bearer {body['access_token']}",
            "X-Tenant-Domain": "demo-electronics.axizpos.com",
        },
    )
    assert rejected.status_code == 401
    replacement = _issued(door, "electronics")
    assert replacement["access_token"] != body["access_token"]


def test_normal_login_still_requires_the_tenant_and_a_password(door: TestClient):
    missing = door.post(
        "/api/v1/auth/login-password",
        headers={"Host": "axizpos.com"},
        json={"username": "alpha-admin", "password": "alpha-password-1"},
    )
    assert missing.status_code == 400
    assert missing.json()["error"]["code"] == "tenant_required"
    signed = door.post(
        "/api/v1/auth/login-password",
        headers={"X-Tenant-Domain": "alpha.axizpos.com"},
        json={"username": "alpha-admin", "password": "alpha-password-1"},
    )
    assert signed.status_code == 200, signed.text
    assert signed.json()["user"]["username"] == "alpha-admin"
    assert signed.json()["user"]["role"]["name"] == "Super Admin"
    claims = decode_access_token(signed.json()["access_token"], settings=get_settings())
    assert claims.get("demo") is not True
    assert claims["tid"] == _tenant_id("alpha")
    own = door.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": f"Bearer {signed.json()['access_token']}",
            "X-Tenant-Domain": "alpha.axizpos.com",
        },
    )
    assert own.status_code == 200
    crossed = door.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": f"Bearer {signed.json()['access_token']}",
            "X-Tenant-Domain": "demo-restaurant.axizpos.com",
        },
    )
    assert crossed.status_code == 401
    demo_login = door.post(
        "/api/v1/auth/login-password",
        headers={"X-Tenant-Domain": "demo-restaurant.axizpos.com"},
        json={"username": EXPLORER_USERNAME, "password": "not-the-demo-password"},
    )
    assert demo_login.status_code == 401
    public = _issued(door, "restaurant")
    assert public["user"]["role"]["name"] != "Super Admin"
    assert public["user"]["username"] != "alpha-admin"
