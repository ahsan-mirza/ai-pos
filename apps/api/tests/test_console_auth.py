import time

from sqlalchemy import select
from tests.governance_support import OPERATOR_PASSWORD, platform  # noqa: F401

from app.console.auth import create_operator, validate_operator_password
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
