"""Emails a 6-digit code so a portal user can set a new password."""

import hashlib
import hmac
import logging
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.console import mail
from app.core.config import Settings
from app.core.errors import ApiError
from app.core.security import hash_password
from app.models.user import User
from app.services.messaging_providers import Outgoing, ProviderError

logger = logging.getLogger("ai_pos.password_reset")

CODE_MINUTES = 10
MAX_ATTEMPTS = 5
RESEND_SECONDS = 60
SENT = "If that email belongs to a portal user, we sent a 6-digit code. It expires in 10 minutes."


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _digest(user: User, code: str) -> str:
    return hashlib.sha256(f"{user.id}:{code}".encode()).hexdigest()


def _find(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.strip().lower(), User.is_active.is_(True)))


def request_code(db: Session, settings: Settings, email: str) -> str:
    if mail.platform_link(settings) is None:
        logger.warning("password reset skipped: platform mailbox is not configured")
        return SENT
    user = _find(db, email)
    if user is None or not user.has_portal_access or user.hashed_password is None:
        return SENT
    sent_at = _aware(user.reset_code_sent_at)
    if sent_at is not None and _now() - sent_at < timedelta(seconds=RESEND_SECONDS):
        return SENT
    code = f"{secrets.randbelow(1_000_000):06d}"
    user.reset_code_hash = _digest(user, code)
    user.reset_code_expires_at = _now() + timedelta(minutes=CODE_MINUTES)
    user.reset_code_sent_at = _now()
    user.reset_code_attempts = 0
    db.commit()
    body = (
        f"Your AI POS password reset code is {code}.\n\n"
        f"It expires in {CODE_MINUTES} minutes. If you did not ask for this, you can ignore the email."
    )
    try:
        mail.send(settings, Outgoing(to=user.email, subject="Your AI POS password reset code", body=body))
    except ProviderError as error:
        user.reset_code_hash = None
        user.reset_code_expires_at = None
        user.reset_code_sent_at = None
        db.commit()
        logger.warning("password reset email failed: %s", error)
        raise ApiError(502, "mail_failed", "We could not send the email. Try again in a few minutes.") from error
    return SENT


def _match(db: Session, email: str, code: str) -> User:
    user = _find(db, email)
    refused = ApiError(400, "invalid_code", "That code is wrong or has expired. Request a new one.")
    if user is None or not user.reset_code_hash:
        raise refused
    expires = _aware(user.reset_code_expires_at)
    if expires is None or expires <= _now() or user.reset_code_attempts >= MAX_ATTEMPTS:
        raise refused
    if not hmac.compare_digest(user.reset_code_hash, _digest(user, code.strip())):
        user.reset_code_attempts += 1
        db.commit()
        raise refused
    return user


def check_code(db: Session, email: str, code: str) -> None:
    """Confirms the emailed code without using it up, so the password step can follow."""
    _match(db, email, code)


def reset_password(db: Session, email: str, code: str, password: str) -> None:
    user = _match(db, email, code)
    user.hashed_password = hash_password(password)
    user.token_version += 1
    user.failed_login_attempts = 0
    user.locked_until = None
    user.reset_code_hash = None
    user.reset_code_expires_at = None
    user.reset_code_sent_at = None
    user.reset_code_attempts = 0
    db.commit()
