"""One-time codes for signup, password reset, and store-code recovery.

Callers keep the hash on their own row. This module issues the code, seals it, checks it,
and sends it. Email uses the platform mailbox. sms, whatsapp, and log use the same
messaging providers as the rest of the product.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from typing import Literal

from app.console import mail
from app.core.config import Settings
from app.services import email_brand
from app.services.messaging_providers import Outgoing, ProviderError, deliver

logger = logging.getLogger("ai_pos.otp")

Purpose = Literal["signup", "password_reset", "store_code"]

_SUBJECTS: dict[str, str] = {
    "signup": "Verify your AxizPOS email",
    "password_reset": "Reset your AxizPOS password",
    "store_code": "Your AxizPOS store code verification",
}
_TEXT_PROVIDERS = {"sms": "http_sms", "whatsapp": "whatsapp_cloud", "log": "log"}


def new_code() -> str:
    """A 6-digit code, including leading zeros."""
    return f"{secrets.randbelow(1_000_000):06d}"


def seal(subject: str, code: str) -> str:
    """Hash of subject and code. The subject is the row id that owns this code."""
    return hashlib.sha256(f"{subject}:{code}".encode()).hexdigest()


def matches(stored: str | None, subject: str, code: str) -> bool:
    """True when the stored hash is the seal of this subject and code."""
    if stored is None or len(stored) != 64:
        return False
    digits = "".join(character for character in code if character.isdigit())
    if len(digits) != 6:
        return False
    return hmac.compare_digest(stored, seal(subject, digits))


def send(
    settings: Settings,
    *,
    to: str,
    purpose: Purpose,
    code: str,
    minutes: int,
    name: str = "",
    channel: str = "email",
) -> None:
    """Sends one code. Raises ProviderError when the channel cannot deliver it."""
    if purpose not in _SUBJECTS:
        raise ProviderError(f"Unknown OTP purpose {purpose}.", permanent=True)
    if channel == "email":
        plain, html_body = _email_parts(purpose, code, minutes, name, settings.support_email)
        mail.send(settings, Outgoing(to=to, subject=_SUBJECTS[purpose], body=plain, html=html_body))
        logger.info("otp emailed purpose=%s", purpose)
        return
    provider = _TEXT_PROVIDERS.get(channel)
    if provider is None:
        raise ProviderError(f"OTP cannot be sent by {channel}.", permanent=True)
    body = f"Your AxizPOS verification code is {code}. It expires in {minutes} minutes."
    deliver(
        settings,
        provider,
        Outgoing(to=to, subject="Your AxizPOS verification code", body=body),
    )
    logger.info("otp sent purpose=%s channel=%s", purpose, channel)


def _email_parts(purpose: str, code: str, minutes: int, name: str, support_email: str) -> tuple[str, str]:
    if purpose == "password_reset":
        return email_brand.password_reset_parts(
            code=code, minutes=minutes, name=name, support_email=support_email
        )
    if purpose == "store_code":
        return email_brand.store_code_parts(code=code, minutes=minutes, support_email=support_email)
    return email_brand.verification_parts(code=code, minutes=minutes, support_email=support_email)
