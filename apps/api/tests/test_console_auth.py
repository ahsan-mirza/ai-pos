import time

from sqlalchemy import select
from tests.governance_support import OPERATOR_PASSWORD, platform  # noqa: F401

from app.console.auth import create_operator
from app.console.security import totp, verify_totp
from app.core.config import get_settings
from app.tenancy.models import Operator, OperatorAuditLog


def test_totp_follows_rfc_6238() -> None:
    # RFC 6238 appendix B test key ("12345678901234567890"), SHA-1, 8 digits truncated to our 6.
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    assert totp(secret, 59) == "287082"
    assert verify_totp(secret, "287082", 59 + 30)
    assert not verify_totp(secret, "287082", 59 + 90)
    assert not verify_totp(secret, "12ab56", time.time())


def test_operators_sign_in_with_password_and_code(platform) -> None:  # noqa: F811
    _, secret = create_operator(
        get_settings(), email="Sara@QIOS.ae", full_name="Sara", role="SUPPORT", password=OPERATOR_PASSWORD
    )
    url = "/api/v1/super-admin/auth/login"
    wrong_code = platform.client.post(
        url, json={"email": "sara@qios.ae", "password": OPERATOR_PASSWORD, "code": "000000"}
    )
    assert wrong_code.status_code == 401
    wrong_password = platform.client.post(url, json={"email": "sara@qios.ae", "password": "nope", "code": totp(secret)})
    assert wrong_password.status_code == 401
    session = platform.client.post(
        url, json={"email": "sara@qios.ae", "password": OPERATOR_PASSWORD, "code": totp(secret)}
    )
    assert session.status_code == 200, session.text
    body = session.json()
    assert body["operator"]["role"] == "SUPPORT" and body["expires_in"] == 3600
    console = {"Authorization": f"Bearer {body['access_token']}"}
    assert platform.client.get("/api/v1/super-admin/me", headers=console).json()["email"] == "sara@qios.ae"

    with platform.control() as db:
        actions = [row.action for row in db.scalars(select(OperatorAuditLog).order_by(OperatorAuditLog.created_at))]
        assert actions.count("console.login_failed") == 2 and "console.login" in actions
        db.scalar(select(Operator).where(Operator.email == "sara@qios.ae")).is_active = False
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
    _, secret = create_operator(
        get_settings(), email="lock@qios.ae", full_name="Lock", role="SUPPORT", password=OPERATOR_PASSWORD
    )
    url = "/api/v1/super-admin/auth/login"
    for _ in range(get_settings().login_max_attempts):
        platform.client.post(url, json={"email": "lock@qios.ae", "password": "wrong-password", "code": totp(secret)})
    locked = platform.client.post(
        url, json={"email": "lock@qios.ae", "password": OPERATOR_PASSWORD, "code": totp(secret)}
    )
    assert locked.status_code == 423
