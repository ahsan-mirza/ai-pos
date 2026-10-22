"""Console sign-in: password plus a TOTP code (RFC 6238), and short-lived tokens with their own secret and audience
so a store's token can never open the console (and a console token never opens a store)."""

import base64
import hashlib
import hmac
import secrets
import struct
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import quote

import jwt
from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.tenancy import registry
from app.tenancy.models import Operator, OperatorAuditLog

AUDIENCE = "qios-console"
ISSUER = "qios-console"
TOTP_STEP_SECONDS = 30
TOTP_DIGITS = 6


# --- TOTP ---------------------------------------------------------------------------------------------------


def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _key(secret: str) -> bytes:
    padded = secret.upper() + "=" * (-len(secret) % 8)
    return base64.b32decode(padded)


def totp(secret: str, at: float | None = None) -> str:
    counter = int((time.time() if at is None else at) // TOTP_STEP_SECONDS)
    digest = hmac.new(_key(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**TOTP_DIGITS).zfill(TOTP_DIGITS)


def verify_totp(secret: str, code: str, at: float | None = None) -> bool:
    """Accepts the current step and one either side, for clock drift."""
    cleaned = code.strip().replace(" ", "")
    if not cleaned.isdigit() or len(cleaned) != TOTP_DIGITS:
        return False
    now = time.time() if at is None else at
    return any(hmac.compare_digest(totp(secret, now + drift * TOTP_STEP_SECONDS), cleaned) for drift in (-1, 0, 1))


def provisioning_uri(secret: str, email: str) -> str:
    return f"otpauth://totp/QIOS%20Console:{quote(email)}?secret={secret}&issuer=QIOS%20Console&digits=6&period=30"


# --- Tokens -------------------------------------------------------------------------------------------------


def _secret(settings: Settings) -> str:
    if not settings.console_jwt_secret or not settings.tenancy_enabled:
        raise ApiError(503, "console_disabled", "The console is not configured on this server.")
    return settings.console_jwt_secret


def issue_token(operator: Operator, settings: Settings) -> tuple[str, int]:
    lifetime = timedelta(minutes=settings.console_token_minutes)
    now = datetime.now(UTC)
    claims = {
        "sub": str(operator.id),
        "aud": AUDIENCE,
        "iss": ISSUER,
        "role": operator.role,
        "ver": operator.token_version,
        "iat": now,
        "exp": now + lifetime,
    }
    token = jwt.encode(claims, _secret(settings), algorithm="HS256")
    return (token.decode("utf-8") if isinstance(token, bytes) else token), int(lifetime.total_seconds())


@dataclass(frozen=True)
class OperatorPrincipal:
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    ip: str | None

    @property
    def is_admin(self) -> bool:
        return self.role == "ADMIN"


def current_operator(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> OperatorPrincipal:
    secret = _secret(settings)
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise ApiError(401, "unauthorized", "Sign in to the console.")
    try:
        claims = jwt.decode(
            token.strip(),
            secret,
            algorithms=["HS256"],
            audience=AUDIENCE,
            issuer=ISSUER,
            options={"require": ["sub", "exp", "aud", "iss", "ver"]},
        )
        operator_id = uuid.UUID(str(claims["sub"]))
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise ApiError(401, "invalid_token", "The console session is invalid or expired.") from exc
    with registry.control_session(settings) as db:
        operator = db.get(Operator, operator_id)
        if operator is None or not operator.is_active or operator.token_version != claims.get("ver"):
            raise ApiError(401, "invalid_token", "The console session is no longer valid.")
        return OperatorPrincipal(
            id=operator.id,
            email=operator.email,
            full_name=operator.full_name,
            role=operator.role,
            ip=request.client.host if request.client else None,
        )


def require_admin(operator: Annotated[OperatorPrincipal, Depends(current_operator)]) -> OperatorPrincipal:
    if not operator.is_admin:
        raise ApiError(403, "forbidden", "Only a console admin can do this.")
    return operator


CurrentOperator = Annotated[OperatorPrincipal, Depends(current_operator)]
ConsoleAdmin = Annotated[OperatorPrincipal, Depends(require_admin)]


def audit_operator(
    db: Session,
    operator: OperatorPrincipal | None,
    action: str,
    *,
    tenant_id: uuid.UUID | None = None,
    before: dict | None = None,
    after: dict | None = None,
    reason: str | None = None,
    ip: str | None = None,
) -> None:
    """Queues the entry on the caller's control session; it is written with the change it describes."""
    db.add(
        OperatorAuditLog(
            id=uuid.uuid4(),
            operator_id=operator.id if operator else None,
            tenant_id=tenant_id,
            action=action,
            before=before,
            after=after,
            reason=reason,
            ip=ip or (operator.ip if operator else None),
            created_at=datetime.now(UTC),
        )
    )
