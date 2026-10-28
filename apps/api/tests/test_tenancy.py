"""Tenant routing: each subdomain reaches only its own rows in the shared database."""

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
from app.tenancy.context import TenantRef, use_tenant
from app.tenancy.models import ControlBase, Tenant

PASSWORDS = {"alpha": "alpha-password-1", "bravo": "bravo-password-1"}


@pytest.fixture()
def tenants(tmp_path):
    previous_database = os.environ.get("DATABASE_URL")
    shared_url = f"sqlite:///{(tmp_path / 'shared.db').as_posix()}"
    control_url = f"sqlite:///{(tmp_path / 'control.db').as_posix()}"
    os.environ["DATABASE_URL"] = shared_url
    os.environ["CONTROL_DATABASE_URL"] = control_url
    get_settings.cache_clear()
    registry.invalidate()
    registry._control_factory.cache_clear()
    settings = get_settings()
    ControlBase.metadata.create_all(build_engine(control_url))
    engine = build_engine(shared_url)
    Base.metadata.create_all(engine)
    control = registry.control_session(settings)
    for slug, password in PASSWORDS.items():
        tenant = Tenant(
            slug=slug,
            name=f"{slug.title()} Mobiles",
            status="active",
            data_plane="shared",
            database_url_encrypted=registry.encrypt_database_url(shared_url, settings),
        )
        control.add(tenant)
        control.flush()
        ref = TenantRef(id=str(tenant.id), slug=slug, name=tenant.name, database_url=shared_url, data_plane="shared")
        with use_tenant(ref), sessionmaker(bind=engine, expire_on_commit=False)() as db:
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
            slug="closed",
            name="Closed Shop",
            status="suspended",
            data_plane="shared",
            database_url_encrypted=registry.encrypt_database_url(shared_url, settings),
        )
    )
    control.commit()
    control.close()
    engine.dispose()
    yield TestClient(create_app())
    del os.environ["CONTROL_DATABASE_URL"]
    if previous_database is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = previous_database
    get_settings.cache_clear()
    registry.invalidate()
    registry._control_factory.cache_clear()


def _login(client: TestClient, slug: str, username: str, password: str, **headers: str):
    return client.post(
        "/api/v1/auth/login-password",
        headers={"X-Tenant-Domain": f"{slug}.axizpos.com", **headers},
        json={"username": username, "password": password},
    )


def test_tenant_comes_from_header_or_subdomain(tenants: TestClient) -> None:
    by_header = tenants.get("/api/v1/tenant", headers={"X-Tenant-Domain": "alpha.axizpos.com"})
    assert by_header.status_code == 200
    assert by_header.json() == {
        "slug": "alpha",
        "name": "Alpha Mobiles",
        "url": "https://alpha.axizpos.com",
        "multi_tenant": True,
    }
    by_host = tenants.get("/api/v1/tenant", headers={"Host": "bravo.localhost:5173"})
    assert by_host.json()["slug"] == "bravo"
    assert tenants.get("/health").status_code == 200


def test_unknown_missing_invalid_and_suspended_tenants_are_refused(tenants: TestClient) -> None:
    unknown = tenants.get("/api/v1/tenant", headers={"X-Tenant-Domain": "nobody.axizpos.com"})
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
        "/api/v1/auth/me", headers={"X-Tenant-Domain": "alpha.axizpos.com", "Authorization": f"Bearer {token}"}
    )
    assert me_alpha.status_code == 200
    me_bravo = tenants.get(
        "/api/v1/auth/me", headers={"X-Tenant-Domain": "bravo.axizpos.com", "Authorization": f"Bearer {token}"}
    )
    assert me_bravo.status_code == 401


def test_tenant_portals_pass_cors(tenants: TestClient) -> None:
    preflight = tenants.options(
        "/api/v1/tenant",
        headers={
            "Origin": "https://alpha.axizpos.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-tenant-domain",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "https://alpha.axizpos.com"
    refused = tenants.get(
        "/api/v1/tenant", headers={"Origin": "https://alpha.axizpos.com", "X-Tenant-Domain": "nobody.axizpos.com"}
    )
    assert refused.status_code == 404
    assert refused.headers.get("access-control-allow-origin") == "https://alpha.axizpos.com"


@pytest.mark.parametrize(
    ("value", "slug"),
    [
        ("client1", "client1"),
        ("client1.axizpos.com", "client1"),
        ("https://Client1.axizpos.com/login", "client1"),
        ("client1.localhost:5173", "client1"),
        ("axizpos.com", None),
        ("a.b.axizpos.com", None),
        ("www.axizpos.com", None),
        ("client1.example.com", None),
    ],
)
def test_slug_from_domain(value: str, slug: str | None) -> None:
    assert registry.slug_from_domain(value, get_settings()) == slug


def test_store_code_whitespace_resolves_to_the_same_tenant() -> None:
    settings = get_settings()
    assert registry.normalize_store_code(" bar isto ") == "baristo"
    assert registry.normalize_store_code("BAR\tISTO\n") == "baristo"
    assert registry.normalize_store_code("\u00a0bar\u2003isto\u2028") == "baristo"
    assert registry.normalize_store_code("   \t") == ""
    assert registry.normalize_store_code("Bar-Isto!") == "bar-isto!"
    assert registry.slug_from_domain(" bar isto ", settings) == "baristo"
    assert registry.slug_from_domain("BAR ISTO.axizpos.com", settings) == "baristo"
    assert registry.valid_slug("baristo")
    assert not registry.valid_slug("bar isto")
    assert not registry.valid_slug("")


def test_public_ip_portal_is_allowed_over_http() -> None:
    import re

    settings = get_settings().model_copy(
        update={
            "tenant_base_domains": "203.0.113.10",
            "control_database_url": "postgresql+psycopg://ai_pos:secret@127.0.0.1:5432/control",
        }
    )
    pattern = re.compile(settings.tenant_origin_regex or "")
    assert pattern.fullmatch("http://203.0.113.10")
    assert pattern.fullmatch("https://203.0.113.10")
    assert pattern.fullmatch("http://203.0.113.10:80")
    assert pattern.fullmatch("http://client1.203.0.113.10") is None
    assert registry.slug_from_domain("203.0.113.10", settings) is None
    assert registry.slug_from_domain("client1", settings) == "client1"
    assert registry.slug_from_domain("client1.203.0.113.10", settings) == "client1"
    assert registry.tenant_domain_for("client1", settings) == "client1"
