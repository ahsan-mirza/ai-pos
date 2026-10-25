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


def test_admin_creates_a_support_operator_who_can_sign_in(platform) -> None:  # noqa: F811
    admin = platform.operator()
    created = platform.client.post(
        "/api/v1/super-admin/operators",
        headers=admin,
        json={
            "full_name": "Nora",
            "email": "Nora@axizpos.com",
            "role": "SUPPORT",
            "password": "Support-password-1",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["email"] == "nora@axizpos.com" and body["role"] == "SUPPORT"
    assert "password" not in body and "password_hash" not in body
    listed = platform.client.get("/api/v1/super-admin/operators", headers=admin)
    assert listed.status_code == 200
    assert any(row["email"] == "nora@axizpos.com" for row in listed.json())
    session = platform.client.post(
        "/api/v1/super-admin/auth/login",
        json={"email": "nora@axizpos.com", "password": "Support-password-1"},
    )
    assert session.status_code == 200, session.text
    assert session.json()["operator"]["role"] == "SUPPORT"
    duplicate = platform.client.post(
        "/api/v1/super-admin/operators",
        headers=admin,
        json={
            "full_name": "Nora",
            "email": "nora@axizpos.com",
            "role": "SUPPORT",
            "password": "Support-password-1",
        },
    )
    assert duplicate.status_code == 409
    with platform.control() as db:
        created_logs = db.scalars(
            select(OperatorAuditLog).where(OperatorAuditLog.action == "console.operator_created")
        )
        created_log = next((log for log in created_logs if (log.after or {}).get("email") == "nora@axizpos.com"), None)
        assert created_log is not None and created_log.operator_id is not None


def test_support_cannot_list_or_create_operators(platform) -> None:  # noqa: F811
    support = platform.operator(email="desk@axizpos.com", role="SUPPORT")
    assert platform.client.get("/api/v1/super-admin/operators", headers=support).status_code == 403
    created = platform.client.post(
        "/api/v1/super-admin/operators",
        headers=support,
        json={
            "full_name": "Nora",
            "email": "nora@axizpos.com",
            "role": "SUPPORT",
            "password": "Support-password-1",
        },
    )
    assert created.status_code == 403


def test_admin_password_reset_retires_the_old_password_and_session(platform) -> None:  # noqa: F811
    admin = platform.operator()
    created = platform.client.post(
        "/api/v1/super-admin/operators",
        headers=admin,
        json={
            "full_name": "Nora",
            "email": "nora@axizpos.com",
            "role": "SUPPORT",
            "password": "Support-password-1",
        },
    )
    assert created.status_code == 201, created.text
    operator_id = created.json()["id"]
    signed_in = platform.client.post(
        "/api/v1/super-admin/auth/login",
        json={"email": "nora@axizpos.com", "password": "Support-password-1"},
    )
    old_token = {"Authorization": f"Bearer {signed_in.json()['access_token']}"}
    reset = platform.client.patch(
        f"/api/v1/super-admin/operators/{operator_id}",
        headers=admin,
        json={"password": "Support-password-2"},
    )
    assert reset.status_code == 200, reset.text
    assert platform.client.get("/api/v1/super-admin/me", headers=old_token).status_code == 401
    old_password = platform.client.post(
        "/api/v1/super-admin/auth/login",
        json={"email": "nora@axizpos.com", "password": "Support-password-1"},
    )
    assert old_password.status_code == 401
    new_password = platform.client.post(
        "/api/v1/super-admin/auth/login",
        json={"email": "nora@axizpos.com", "password": "Support-password-2"},
    )
    assert new_password.status_code == 200, new_password.text
    with platform.control() as db:
        reset_log = db.scalar(
            select(OperatorAuditLog).where(OperatorAuditLog.action == "console.operator_password_reset")
        )
        assert reset_log is not None and reset_log.operator_id is not None


def test_the_last_admin_cannot_be_demoted(platform) -> None:  # noqa: F811
    admin = platform.operator()
    me = platform.client.get("/api/v1/super-admin/me", headers=admin).json()
    refused = platform.client.patch(
        f"/api/v1/super-admin/operators/{me['id']}",
        headers=admin,
        json={"role": "SUPPORT"},
    )
    assert refused.status_code == 409
    second = platform.client.post(
        "/api/v1/super-admin/operators",
        headers=admin,
        json={
            "full_name": "Second Admin",
            "email": "second@axizpos.com",
            "role": "ADMIN",
            "password": "Support-password-1",
        },
    )
    assert second.status_code == 201, second.text
    demoted = platform.client.patch(
        f"/api/v1/super-admin/operators/{me['id']}",
        headers=admin,
        json={"role": "SUPPORT"},
    )
    assert demoted.status_code == 200, demoted.text
    assert demoted.json()["role"] == "SUPPORT"
    other = platform.client.post(
        "/api/v1/super-admin/auth/login",
        json={"email": "second@axizpos.com", "password": "Support-password-1"},
    )
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    still_last = platform.client.patch(
        f"/api/v1/super-admin/operators/{second.json()['id']}",
        headers=other_headers,
        json={"role": "SUPPORT"},
    )
    assert still_last.status_code == 409
