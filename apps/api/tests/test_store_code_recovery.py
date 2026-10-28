"""Store codes are the tenant slugs a person can sign in with, and only after an emailed code."""

import os
import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.console import mail
from app.core import cache
from app.core.config import get_settings
from app.core.database import build_engine
from app.core.security import hash_password
from app.main import create_app
from app.models import Base
from app.models.store import Store
from app.models.user import User
from app.services.messaging_providers import ProviderError
from app.services.rbac_service import ensure_super_admin, ensure_system_roles
from app.tenancy import registry
from app.tenancy.context import TenantRef, use_tenant
from app.tenancy.models import ControlBase, RecoveryChallenge, Tenant

SHARED_EMAIL = "owner@example.com"


def _mailbox(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "mail.example.com")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_starttls", True)
    monkeypatch.setattr(settings, "smtp_from", "pos@example.com")


@pytest.fixture()
def stores(tmp_path):
    previous_database = os.environ.get("DATABASE_URL")
    shared_url = f"sqlite:///{(tmp_path / 'shared.db').as_posix()}"
    control_url = f"sqlite:///{(tmp_path / 'control.db').as_posix()}"
    os.environ["DATABASE_URL"] = shared_url
    os.environ["CONTROL_DATABASE_URL"] = control_url
    get_settings.cache_clear()
    registry.invalidate()
    registry._control_factory.cache_clear()
    registry._factories.clear()
    settings = get_settings()
    ControlBase.metadata.create_all(build_engine(control_url))
    engine = build_engine(shared_url)
    Base.metadata.create_all(engine)
    control = registry.control_session(settings)
    specs = (
        ("alpha", "Alpha Mobiles", "active", SHARED_EMAIL),
        ("bravo", "Bravo Wholesale", "active", SHARED_EMAIL),
        ("closed", "Closed Shop", "suspended", SHARED_EMAIL),
    )
    for slug, name, status, email in specs:
        tenant = Tenant(
            slug=slug,
            name=name,
            status=status,
            data_plane="shared",
            database_url_encrypted=registry.encrypt_database_url(shared_url, settings),
        )
        control.add(tenant)
        control.flush()
        ref = TenantRef(id=str(tenant.id), slug=slug, name=name, database_url=shared_url, data_plane="shared")
        with use_tenant(ref), sessionmaker(bind=engine, expire_on_commit=False)() as db:
            ensure_system_roles(db)
            user, _ = ensure_super_admin(
                db,
                settings,
                username=f"{slug}-admin",
                email=email,
                full_name=f"{name} Owner",
                password="owner-password-1",
                pin=None,
            )
            if slug == "alpha":
                branch = Store(code="DT", name="Downtown", currency="AED", is_active=True)
                db.add(branch)
                db.flush()
                user.store_id = branch.id
            if slug == "bravo":
                db.add(
                    User(
                        username="sleeper",
                        email="inactive@example.com",
                        full_name="Inactive",
                        hashed_password=hash_password("owner-password-1"),
                        is_active=False,
                        role_id=user.role_id,
                        has_portal_access=True,
                        token_version=0,
                        failed_login_attempts=0,
                    )
                )
            db.commit()
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
    registry._factories.clear()


def _request(stores: TestClient, email: str = SHARED_EMAIL):
    return stores.post("/api/v1/auth/recover-store-code", json={"email": email})


def test_verified_email_receives_only_its_active_store_codes(stores: TestClient, monkeypatch):
    _mailbox(monkeypatch)
    sent: list[str] = []

    def capture(message, **kwargs):
        sent.append(message.body)
        return "id"

    monkeypatch.setattr(mail, "transmit_smtp", capture)
    requested = _request(stores)
    assert requested.status_code == 200
    assert "alpha" not in requested.text
    assert "bravo" not in requested.text
    code = re.search(r"\b(\d{6})\b", sent[0]).group(1)
    wrong = "000000" if code != "000000" else "111111"
    refused = stores.post(
        "/api/v1/auth/recover-store-code/verify",
        json={"email": SHARED_EMAIL, "code": wrong},
    )
    assert refused.status_code == 400
    assert "alpha" not in refused.text

    verified = stores.post(
        "/api/v1/auth/recover-store-code/verify",
        json={"email": SHARED_EMAIL, "code": code},
    )
    assert verified.status_code == 200, verified.text
    body = verified.json()
    assert [item["code"] for item in body["stores"]] == ["alpha", "bravo"]
    assert body["stores"][0]["branch"] == "Downtown"
    assert body["stores"][1]["branch"] is None
    assert "closed" not in verified.text
    assert "alpha" in sent[-1] and "bravo" in sent[-1]
    assert "closed" not in sent[-1]

    replay = stores.post(
        "/api/v1/auth/recover-store-code/verify",
        json={"email": SHARED_EMAIL, "code": code},
    )
    assert replay.status_code == 400


def test_unknown_and_inactive_emails_are_not_told_apart(stores: TestClient, monkeypatch):
    _mailbox(monkeypatch)
    sent: list[str] = []
    monkeypatch.setattr(mail, "transmit_smtp", lambda *args, **kwargs: sent.append("x") or "id")
    unknown = _request(stores, "nobody@example.com")
    inactive = _request(stores, "inactive@example.com")
    assert unknown.status_code == inactive.status_code == 200
    assert unknown.json() == inactive.json()
    assert sent == []
    missing = stores.post(
        "/api/v1/auth/recover-store-code/verify",
        json={"email": "nobody@example.com", "code": "123456"},
    )
    assert missing.status_code == 400


def test_expired_code_is_refused(stores: TestClient, monkeypatch):
    _mailbox(monkeypatch)
    sent: list[str] = []
    monkeypatch.setattr(mail, "transmit_smtp", lambda message, **kwargs: sent.append(message.body) or "id")
    assert _request(stores).status_code == 200
    with registry.control_session(get_settings()) as db:
        row = db.scalar(select(RecoveryChallenge).where(RecoveryChallenge.email == SHARED_EMAIL))
        row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()
    code = re.search(r"\b(\d{6})\b", sent[0]).group(1)
    response = stores.post(
        "/api/v1/auth/recover-store-code/verify",
        json={"email": SHARED_EMAIL, "code": code},
    )
    assert response.status_code == 400


def test_mail_failure_does_not_leave_a_code(stores: TestClient, monkeypatch):
    _mailbox(monkeypatch)

    def fail(*args, **kwargs):
        raise ProviderError("mailbox down")

    monkeypatch.setattr(mail, "transmit_smtp", fail)
    response = _request(stores)
    assert response.status_code == 502
    follow = stores.post(
        "/api/v1/auth/recover-store-code/verify",
        json={"email": SHARED_EMAIL, "code": "123456"},
    )
    assert follow.status_code == 400


def test_store_code_recovery_is_rate_limited_and_redis_failure_refuses(stores: TestClient, monkeypatch):
    monkeypatch.setattr(mail, "platform_link", lambda settings: None)
    last = None
    for _ in range(6):
        last = _request(stores, "nobody@example.com")
    assert last is not None and last.status_code == 429

    class Down:
        def incr(self, *args, **kwargs):
            raise RedisError("down")

    monkeypatch.setattr(cache, "_client_for", lambda: Down())
    assert _request(stores).status_code == 503


def test_single_tenant_mode_does_not_invent_a_store_code(client, monkeypatch):
    _mailbox(monkeypatch)
    sent: list[str] = []
    monkeypatch.setattr(mail, "transmit_smtp", lambda *args, **kwargs: sent.append("x") or "id")
    response = client.post("/api/v1/auth/recover-store-code", json={"email": "admin@example.com"})
    assert response.status_code == 200
    assert sent == []
    assert "store code" not in response.text.lower() or "sent a 6-digit" in response.text.lower()
