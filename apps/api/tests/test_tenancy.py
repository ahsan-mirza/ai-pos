"""Database-per-tenant routing: each subdomain reaches only its own database."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.database import build_engine
from app.main import create_app
from app.models import Base
from app.services.rbac_service import ensure_super_admin, ensure_system_roles
from app.tenancy import registry
from app.tenancy.models import ControlBase, Tenant

PASSWORDS = {"alpha": "alpha-password-1", "bravo": "bravo-password-1"}


@pytest.fixture()
def tenants(tmp_path):
    control_url = f"sqlite:///{(tmp_path / 'control.db').as_posix()}"
    os.environ["CONTROL_DATABASE_URL"] = control_url
    get_settings.cache_clear()
    registry.invalidate()
    registry._control_factory.cache_clear()
    settings = get_settings()
    ControlBase.metadata.create_all(build_engine(control_url))
    control = registry.control_session(settings)
    for slug, password in PASSWORDS.items():
        url = f"sqlite:///{(tmp_path / f'{slug}.db').as_posix()}"
        engine = build_engine(url)
        Base.metadata.create_all(engine)
        with sessionmaker(bind=engine, expire_on_commit=False)() as db:
            ensure_system_roles(db)
            ensure_super_admin(
                db,
                settings,
                username=f"{slug}-admin",
                email=f"admin@{slug}.example",
                full_name=f"{slug.title()} Admin",
                password=password,
                pin=None,
            )
            db.commit()
        control.add(
            Tenant(
                slug=slug,
                name=f"{slug.title()} Mobiles",
                status="active",
                database_url_encrypted=registry.encrypt_database_url(url, settings),
            )
        )
    control.add(
        Tenant(
            slug="closed",
            name="Closed Shop",
            status="suspended",
            database_url_encrypted=registry.encrypt_database_url(f"sqlite:///{(tmp_path / 'alpha.db').as_posix()}"),
        )
    )
    control.commit()
    control.close()
    yield TestClient(create_app())
    del os.environ["CONTROL_DATABASE_URL"]
    get_settings.cache_clear()
    registry.invalidate()
    registry._control_factory.cache_clear()


def _login(client: TestClient, slug: str, username: str, password: str, **headers: str):
    return client.post(
        "/api/v1/auth/login-password",
        headers={"X-Tenant-Domain": f"{slug}.qios.ae", **headers},
        json={"username": username, "password": password},
    )


def test_tenant_comes_from_header_or_subdomain(tenants: TestClient) -> None:
    by_header = tenants.get("/api/v1/tenant", headers={"X-Tenant-Domain": "alpha.qios.ae"})
    assert by_header.status_code == 200
    assert by_header.json() == {
        "slug": "alpha",
        "name": "Alpha Mobiles",
        "url": "https://alpha.qios.ae",
        "multi_tenant": True,
    }
    by_host = tenants.get("/api/v1/tenant", headers={"Host": "bravo.localhost:5173"})
    assert by_host.json()["slug"] == "bravo"
    assert tenants.get("/health").status_code == 200


def test_unknown_missing_invalid_and_suspended_tenants_are_refused(tenants: TestClient) -> None:
    unknown = tenants.get("/api/v1/tenant", headers={"X-Tenant-Domain": "nobody.qios.ae"})
    assert (unknown.status_code, unknown.json()["error"]["code"]) == (404, "tenant_not_found")
    missing = tenants.get("/api/v1/tenant", headers={"Host": "localhost:8000"})
    assert (missing.status_code, missing.json()["error"]["code"]) == (400, "tenant_required")
    invalid = tenants.get("/api/v1/tenant", headers={"X-Tenant-Domain": "evil.example.com"})
    assert invalid.json()["error"]["code"] == "tenant_invalid"
    closed = tenants.get("/api/v1/tenant", headers={"X-Tenant-Domain": "closed"})
    assert (closed.status_code, closed.json()["error"]["code"]) == (403, "tenant_suspended")


def test_each_tenant_only_sees_its_own_database(tenants: TestClient) -> None:
    alpha = _login(tenants, "alpha", "alpha-admin", PASSWORDS["alpha"])
    assert alpha.status_code == 200, alpha.text
    token = alpha.json()["access_token"]
    assert _login(tenants, "bravo", "alpha-admin", PASSWORDS["alpha"]).status_code == 401

    me_alpha = tenants.get(
        "/api/v1/auth/me", headers={"X-Tenant-Domain": "alpha.qios.ae", "Authorization": f"Bearer {token}"}
    )
    assert me_alpha.status_code == 200
    me_bravo = tenants.get(
        "/api/v1/auth/me", headers={"X-Tenant-Domain": "bravo.qios.ae", "Authorization": f"Bearer {token}"}
    )
    assert me_bravo.status_code == 401


def test_tenant_portals_pass_cors(tenants: TestClient) -> None:
    preflight = tenants.options(
        "/api/v1/tenant",
        headers={
            "Origin": "https://alpha.qios.ae",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-tenant-domain",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "https://alpha.qios.ae"
    refused = tenants.get(
        "/api/v1/tenant", headers={"Origin": "https://alpha.qios.ae", "X-Tenant-Domain": "nobody.qios.ae"}
    )
    assert refused.status_code == 404
    assert refused.headers.get("access-control-allow-origin") == "https://alpha.qios.ae"


@pytest.mark.parametrize(
    ("value", "slug"),
    [
        ("client1", "client1"),
        ("client1.qios.ae", "client1"),
        ("https://Client1.qios.ae/login", "client1"),
        ("client1.localhost:5173", "client1"),
        ("qios.ae", None),
        ("a.b.qios.ae", None),
        ("www.qios.ae", None),
        ("client1.example.com", None),
    ],
)
def test_slug_from_domain(value: str, slug: str | None) -> None:
    assert registry.slug_from_domain(value, get_settings()) == slug
