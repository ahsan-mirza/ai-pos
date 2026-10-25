import time

from sqlalchemy import select
from tests.governance_support import OPERATOR_PASSWORD, platform  # noqa: F401

from app.console.auth import create_operator, ensure_console_admin, validate_operator_password
from app.console.security import totp, verify_totp
from app.core.config import get_settings
from app.tenancy.models import Operator, OperatorAuditLog


def test_operator_passwords_need_length_case_number_and_symbol() -> None:
    validate_operator_password("GoodPass1!")
    for password in ("Short1!", "lowercase-1", "NoNumber!", "NoSymbol1"):
        try:
            validate_operator_password(password)
        except ValueError:
            continue
        raise AssertionError(password)


def test_totp_follows_rfc_6238() -> None:
    # RFC 6238 appendix B test key ("12345678901234567890"), SHA-1, 8 digits truncated to our 6.
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    assert totp(secret, 59, step=30) == "287082"
    assert verify_totp(secret, "287082", 59 + 30, step=30)
    assert not verify_totp(secret, "287082", 59 + 90, step=30)
    assert not verify_totp(secret, "12ab56", time.time())


def test_operators_sign_in_with_email_and_password(platform) -> None:  # noqa: F811
    create_operator(
        get_settings(), email="Sara@axizpos.com", full_name="Sara", role="SUPPORT", password=OPERATOR_PASSWORD
    )
    url = "/api/v1/super-admin/auth/login"
    wrong_password = platform.client.post(url, json={"email": "sara@axizpos.com", "password": "nope"})
    assert wrong_password.status_code == 401
    session = platform.client.post(url, json={"email": "sara@axizpos.com", "password": OPERATOR_PASSWORD})
    assert session.status_code == 200, session.text
    body = session.json()
    assert body["operator"]["role"] == "SUPPORT" and body["expires_in"] == 3600
    console = {"Authorization": f"Bearer {body['access_token']}"}
    assert platform.client.get("/api/v1/super-admin/me", headers=console).json()["email"] == "sara@axizpos.com"

    with platform.control() as db:
        actions = [row.action for row in db.scalars(select(OperatorAuditLog).order_by(OperatorAuditLog.created_at))]
        assert actions.count("console.login_failed") == 1 and "console.login" in actions
        db.scalar(select(Operator).where(Operator.email == "sara@axizpos.com")).is_active = False
        db.commit()
    assert platform.client.get("/api/v1/super-admin/me", headers=console).status_code == 401


def test_store_and_console_tokens_never_cross(platform) -> None:  # noqa: F811
    console = platform.operator()
    store = platform.headers("alpha")
    assert (
        platform.client.get("/api/v1/super-admin/me", headers={"Authorization": store["Authorization"]}).status_code
        == 401
    )
    assert platform.client.get("/api/v1/super-admin/me").status_code == 401
    crossed = platform.client.get(
        "/api/v1/tenant/modules", headers={**store, "Authorization": console["Authorization"]}
    )
    assert crossed.status_code == 401


def test_accounts_lock_after_repeated_failures(platform) -> None:  # noqa: F811
    create_operator(
        get_settings(), email="lock@axizpos.com", full_name="Lock", role="SUPPORT", password=OPERATOR_PASSWORD
    )
    url = "/api/v1/super-admin/auth/login"
    for _ in range(get_settings().login_max_attempts):
        platform.client.post(url, json={"email": "lock@axizpos.com", "password": "wrong-password"})
    locked = platform.client.post(url, json={"email": "lock@axizpos.com", "password": OPERATOR_PASSWORD})
    assert locked.status_code == 423


def test_ensure_console_admin_creates_keeps_and_replaces_the_password(platform) -> None:  # noqa: F811
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import func

    from app.core.security import hash_password, verify_password

    settings = get_settings()
    previous = (settings.console_admin_email, settings.console_admin_name, settings.console_admin_password)
    email = "console-owner@example.com"
    password = "Console-admin-1"
    settings.console_admin_email = email
    settings.console_admin_name = "Console Owner"
    settings.console_admin_password = password
    try:
        assert ensure_console_admin(get_settings().model_copy(update={"console_admin_email": None})) is None
        created = ensure_console_admin(settings)
        assert created is not None and created.email == email and created.role == "ADMIN"
        again = ensure_console_admin(settings)
        assert again is not None and again.id == created.id
        with platform.control() as db:
            row = db.scalar(select(Operator).where(Operator.email == email))
            assert row is not None
            version = row.token_version
            row.password_hash = hash_password("Other-admin-1")
            row.role = "SUPPORT"
            row.is_active = False
            row.failed_attempts = 4
            row.locked_until = datetime.now(UTC) + timedelta(hours=1)
            db.commit()
        replaced = ensure_console_admin(settings)
        assert replaced is not None and replaced.role == "ADMIN" and replaced.is_active
        with platform.control() as db:
            rows = list(db.scalars(select(Operator).where(func.lower(Operator.email) == email)))
            assert len(rows) == 1
            row = rows[0]
            assert verify_password(password, row.password_hash)
            assert row.role == "ADMIN" and row.is_active
            assert row.failed_attempts == 0 and row.locked_until is None
            assert row.token_version == version + 1
        login = platform.client.post(
            "/api/v1/super-admin/auth/login",
            json={"email": email, "password": password},
        )
        assert login.status_code == 200, login.text
        assert login.json()["operator"]["role"] == "ADMIN"
        with platform.control() as db:
            kept = db.scalar(select(Operator.token_version).where(Operator.email == email))
        ensure_console_admin(settings)
        with platform.control() as db:
            assert db.scalar(select(Operator.token_version).where(Operator.email == email)) == kept
    finally:
        settings.console_admin_email, settings.console_admin_name, settings.console_admin_password = previous
