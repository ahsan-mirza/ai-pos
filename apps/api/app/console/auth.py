"""Operator sign-in and creation. Accounts lock after repeated failures, like store accounts."""

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.console.security import OperatorPrincipal, audit_operator, issue_token, new_totp_secret, verify_totp
from app.core.config import Settings
from app.core.errors import ApiError
from app.core.security import decrypt_value, encrypt_value, hash_password, verify_password
from app.schemas.console import ConsoleLogin, ConsoleSession, OperatorOut
from app.tenancy import registry
from app.tenancy.models import OPERATOR_ROLES, Operator


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    return value if value is None or value.tzinfo is not None else value.replace(tzinfo=UTC)


def operator_out(row: Operator) -> OperatorOut:
    return OperatorOut(
        id=row.id,
        email=row.email,
        full_name=row.full_name,
        role=row.role,  # type: ignore[arg-type]
        is_active=row.is_active,
        last_login_at=row.last_login_at,
    )


def login(settings: Settings, data: ConsoleLogin, ip: str | None) -> ConsoleSession:
    refused = ApiError(401, "invalid_credentials", "Email, password or code is wrong.")
    with registry.control_session(settings) as db:
        operator = db.scalar(select(Operator).where(func.lower(Operator.email) == data.email.strip().lower()))
        password_ok = verify_password(data.password, operator.password_hash if operator else None)
        if operator is None or not operator.is_active:
            raise refused
        locked = _aware(operator.locked_until)
        if locked is not None and locked > _now():
            raise ApiError(423, "account_locked", "Too many failed attempts. Try again later.")
        code_ok = verify_totp(decrypt_value(operator.totp_secret_enc, settings), data.code)
        if not (password_ok and code_ok):
            operator.failed_attempts += 1
            if operator.failed_attempts >= settings.login_max_attempts:
                operator.locked_until = _now() + timedelta(minutes=settings.login_lockout_minutes)
                operator.failed_attempts = 0
            audit_operator(db, None, "console.login_failed", after={"email": operator.email}, ip=ip)
            db.commit()
            raise refused
        operator.failed_attempts = 0
        operator.locked_until = None
        operator.last_login_at = _now()
        principal = OperatorPrincipal(operator.id, operator.email, operator.full_name, operator.role, ip)
        audit_operator(db, principal, "console.login")
        token, expires_in = issue_token(operator, settings)
        db.commit()
        return ConsoleSession(access_token=token, expires_in=expires_in, operator=operator_out(operator))


def create_operator(
    settings: Settings, *, email: str, full_name: str, role: str, password: str
) -> tuple[OperatorOut, str]:
    """Returns the operator and the TOTP secret to enrol in an authenticator app (shown once)."""
    if role not in OPERATOR_ROLES:
        raise ValueError(f"Role must be one of {', '.join(OPERATOR_ROLES)}.")
    if len(password) < 12:
        raise ValueError("Operator passwords are at least 12 characters.")
    secret = new_totp_secret()
    with registry.control_session(settings) as db:
        if db.scalar(select(Operator.id).where(func.lower(Operator.email) == email.strip().lower())) is not None:
            raise ValueError(f"An operator with {email} already exists.")
        row = Operator(
            id=uuid.uuid4(),
            email=email.strip().lower(),
            full_name=full_name.strip(),
            password_hash=hash_password(password),
            totp_secret_enc=encrypt_value(secret, settings),
            role=role,
            is_active=True,
            token_version=1,
            created_at=_now(),
            updated_at=_now(),
        )
        db.add(row)
        audit_operator(db, None, "console.operator_created", after={"email": row.email, "role": role})
        db.commit()
        return operator_out(row), secret


def random_password() -> str:
    return secrets.token_urlsafe(18)
