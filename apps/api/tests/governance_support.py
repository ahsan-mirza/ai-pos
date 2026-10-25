"""A two-store platform on one shared SQLite file, plus the control database."""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.console.site import invalidate_contact_cache
from app.core.config import get_settings
from app.core.database import build_engine
from app.main import create_app
from app.models import Base
from app.services.rbac_service import ensure_super_admin, ensure_system_roles
from app.services.settings_service import clear_settings_cache, load_settings
from app.tenancy import registry
from app.tenancy.context import TenantRef, use_tenant
from app.tenancy.models import ControlBase, Tenant

PASSWORDS = {"alpha": "alpha-password-1", "bravo": "bravo-password-1"}
OPERATOR_PASSWORD = "Operator-password-1"


@dataclass
class Platform:
    client: TestClient
    root: Path

    def url(self, slug: str) -> str:
        del slug
        return f"sqlite:///{(self.root / 'shared.db').as_posix()}"

    @contextmanager
    def session(self, slug: str) -> Iterator[Session]:
        found = registry.lookup(slug, get_settings())
        if found.tenant is None:
            raise RuntimeError(f"Tenant {slug} is not registered.")
        db = sessionmaker(bind=build_engine(found.tenant.database_url), expire_on_commit=False)()
        try:
            with use_tenant(found.tenant):
                yield db
        finally:
            db.close()

    def control(self):
        return registry.control_session(get_settings())

    def operator(self, email: str = "it@axizpos.com", role: str = "ADMIN") -> dict[str, str]:
        """Creates a console operator and signs in; returns its Authorization header."""
        from app.console.auth import create_operator

        create_operator(get_settings(), email=email, full_name="IT Support", role=role, password=OPERATOR_PASSWORD)
        response = self.client.post(
            "/api/v1/super-admin/auth/login",
            json={"email": email, "password": OPERATOR_PASSWORD},
        )
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def tenant_id(self, slug: str) -> str:
        from sqlalchemy import select

        with self.control() as db:
            return str(db.scalar(select(Tenant.id).where(Tenant.slug == slug)))

    def headers(self, slug: str) -> dict[str, str]:
        response = self.client.post(
            "/api/v1/auth/login-password",
            headers={"X-Tenant-Domain": f"{slug}.axizpos.com"},
            json={"username": f"{slug}-admin", "password": PASSWORDS[slug]},
        )
        assert response.status_code == 200, response.text
        return {"X-Tenant-Domain": f"{slug}.axizpos.com", "Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture()
def platform(tmp_path):
    previous_database = os.environ.get("DATABASE_URL")
    shared_url = f"sqlite:///{(tmp_path / 'shared.db').as_posix()}"
    control_url = f"sqlite:///{(tmp_path / 'control.db').as_posix()}"
    os.environ["DATABASE_URL"] = shared_url
    os.environ["CONTROL_DATABASE_URL"] = control_url
    os.environ.setdefault("CONSOLE_JWT_SECRET", "console-test-secret-0123456789-abcdef")
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
            profile="electronics_wholesale",
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
            row = load_settings(db, lock=True)
            row.business_profile = "electronics_wholesale"
            row.onboarded_at = datetime.now(UTC)
            db.commit()
    control.commit()
    control.close()
    engine.dispose()
    clear_settings_cache()
    invalidate_contact_cache()
    yield Platform(client=TestClient(create_app()), root=tmp_path)
    del os.environ["CONTROL_DATABASE_URL"]
    if previous_database is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = previous_database
    get_settings.cache_clear()
    registry.invalidate()
    registry._control_factory.cache_clear()
    clear_settings_cache()
    invalidate_contact_cache()
