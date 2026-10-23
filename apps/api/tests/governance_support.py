"""A two-store platform (control database plus a database per store) for governance and console tests."""

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.database import build_engine
from app.main import create_app
from app.models import Base
from app.services.rbac_service import ensure_super_admin, ensure_system_roles
from app.services.settings_service import clear_settings_cache, load_settings
from app.tenancy import registry
from app.tenancy.models import ControlBase, Tenant

PASSWORDS = {"alpha": "alpha-password-1", "bravo": "bravo-password-1"}
OPERATOR_PASSWORD = "Operator-password-1"


@dataclass
class Platform:
    client: TestClient
    root: Path

    def url(self, slug: str) -> str:
        return f"sqlite:///{(self.root / f'{slug}.db').as_posix()}"

    def session(self, slug: str):
        return sessionmaker(bind=build_engine(self.url(slug)), expire_on_commit=False)()

    def control(self):
        return registry.control_session(get_settings())

    def operator(self, email: str = "it@qios.ae", role: str = "ADMIN") -> dict[str, str]:
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
            headers={"X-Tenant-Domain": f"{slug}.qios.ae"},
            json={"username": f"{slug}-admin", "password": PASSWORDS[slug]},
        )
        assert response.status_code == 200, response.text
        return {"X-Tenant-Domain": f"{slug}.qios.ae", "Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture()
def platform(tmp_path):
    control_url = f"sqlite:///{(tmp_path / 'control.db').as_posix()}"
    os.environ["CONTROL_DATABASE_URL"] = control_url
    os.environ.setdefault("CONSOLE_JWT_SECRET", "console-test-secret-0123456789-abcdef")
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
            row = load_settings(db, lock=True)
            row.business_profile = "electronics_wholesale"
            row.onboarded_at = datetime.now(UTC)
            db.commit()
        engine.dispose()
        control.add(
            Tenant(
                slug=slug,
                name=f"{slug.title()} Mobiles",
                status="active",
                profile="electronics_wholesale",
                database_url_encrypted=registry.encrypt_database_url(url, settings),
            )
        )
    control.commit()
    control.close()
    clear_settings_cache()
    yield Platform(client=TestClient(create_app()), root=tmp_path)
    del os.environ["CONTROL_DATABASE_URL"]
    get_settings.cache_clear()
    registry.invalidate()
    registry._control_factory.cache_clear()
    clear_settings_cache()
