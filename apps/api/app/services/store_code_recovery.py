"""Emails a one-time code, then returns the store codes that email may sign in with.

The sign-in store code is the tenant slug. A user is included only when an active user row
in an active tenant has that email and can open the portal or the register. Owner email on
the tenant record is not a membership.
"""

import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.console import mail
from app.console.entitlements import tenant_session
from app.core.config import Settings
from app.core.errors import ApiError
from app.models.store import Store
from app.models.user import User
from app.services.email_brand import store_code_parts, store_code_result_parts
from app.services.messaging_providers import Outgoing, ProviderError
from app.tenancy import registry
from app.tenancy.models import OperatorAuditLog, RecoveryChallenge, Tenant

logger = logging.getLogger("ai_pos.store_code_recovery")

PURPOSE = "store_code"
CODE_MINUTES = 10
MAX_ATTEMPTS = 5
RESEND_SECONDS = 60
SENT = "If that email is registered, we sent a 6-digit code. It expires in 10 minutes."


def _refused() -> ApiError:
    return ApiError(400, "invalid_code", "That code is wrong or has expired. Request a new one.")


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _digest(challenge_id: uuid.UUID, code: str) -> str:
    return hashlib.sha256(f"{challenge_id}:{code}".encode()).hexdigest()


def _dummy(email: str) -> None:
    hmac.compare_digest(hashlib.sha256(b"store-code").hexdigest(), hashlib.sha256(email.encode()).hexdigest())


class RecoveredStore:
    def __init__(self, code: str, name: str, branch: str | None) -> None:
        self.code = code
        self.name = name
        self.branch = branch

    @property
    def label(self) -> str:
        return self.name if self.branch is None else f"{self.name} ({self.branch})"


def memberships(settings: Settings, email: str) -> list[RecoveredStore]:
    """Active sign-in codes for this email. Suspended tenants and inactive users are omitted."""
    if not settings.tenancy_enabled:
        _dummy(email)
        return []
    found: list[RecoveredStore] = []
    with registry.control_session(settings) as control:
        tenants = list(control.scalars(select(Tenant).where(Tenant.status == "active").order_by(Tenant.slug)))
        for tenant in tenants:
            try:
                match = _member(settings, tenant, email)
            except Exception:
                logger.warning("store code lookup skipped a tenant")
                continue
            if match is not None:
                found.append(match)
    if not found:
        _dummy(email)
    return found


def _member(settings: Settings, tenant: Tenant, email: str) -> RecoveredStore | None:
    with tenant_session(tenant, settings) as db:
        user = db.scalar(select(User).where(User.email == email, User.is_active.is_(True)))
        if user is None or not (user.has_portal_access or user.has_pos_access):
            return None
        if user.hashed_password is None and user.hashed_pin is None:
            return None
        branch = _branch(db, user)
        return RecoveredStore(code=tenant.slug, name=tenant.name, branch=branch)


def _branch(db: Session, user: User) -> str | None:
    if user.store_id is None:
        return None
    store = db.get(Store, user.store_id)
    if store is None or not store.is_active:
        return None
    return store.name


def request_code(settings: Settings, email: str, ip: str | None) -> str:
    if mail.platform_link(settings) is None:
        logger.warning("store code recovery skipped: mailbox is not configured")
        return SENT
    matches = memberships(settings, email)
    if not matches:
        return SENT
    code = f"{secrets.randbelow(1_000_000):06d}"
    with registry.control_session(settings) as db:
        row = db.scalar(
            select(RecoveryChallenge)
            .where(RecoveryChallenge.purpose == PURPOSE, RecoveryChallenge.email == email)
            .with_for_update()
        )
        sent_at = _aware(row.sent_at) if row is not None else None
        if row is not None and sent_at is not None and _now() - sent_at < timedelta(seconds=RESEND_SECONDS):
            return SENT
        if row is None:
            row = RecoveryChallenge(
                purpose=PURPOSE,
                email=email,
                code_hash="",
                expires_at=_now(),
                sent_at=_now(),
                attempts=0,
            )
            db.add(row)
            db.flush()
        row.code_hash = _digest(row.id, code)
        row.expires_at = _now() + timedelta(minutes=CODE_MINUTES)
        row.sent_at = _now()
        row.attempts = 0
        row.consumed_at = None
        db.add(
            OperatorAuditLog(
                action="account.store_code_requested",
                after={"issued": True},
                ip=ip,
            )
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return SENT
        challenge_id = row.id
    plain, html_body = store_code_parts(code=code, minutes=CODE_MINUTES, support_email=settings.support_email)
    try:
        mail.send(
            settings,
            Outgoing(to=email, subject="Your AxizPOS store code verification", body=plain, html=html_body),
        )
    except ProviderError as error:
        _clear(settings, challenge_id)
        logger.warning("store code recovery email failed")
        raise ApiError(502, "mail_failed", "We could not send the email. Try again in a few minutes.") from error
    logger.info("store code recovery issued")
    return SENT


def _clear(settings: Settings, challenge_id: uuid.UUID) -> None:
    with registry.control_session(settings) as db:
        row = db.get(RecoveryChallenge, challenge_id)
        if row is None:
            return
        row.code_hash = ""
        row.expires_at = _now()
        db.commit()


def verify(settings: Settings, email: str, code: str, ip: str | None) -> tuple[list[RecoveredStore], str]:
    with registry.control_session(settings) as db:
        row = db.scalar(
            select(RecoveryChallenge)
            .where(RecoveryChallenge.purpose == PURPOSE, RecoveryChallenge.email == email)
            .with_for_update()
        )
        if row is None or row.consumed_at is not None or not row.code_hash:
            _dummy(email)
            raise _refused()
        expires = _aware(row.expires_at)
        if expires is None or expires <= _now() or row.attempts >= MAX_ATTEMPTS:
            raise _refused()
        if not hmac.compare_digest(row.code_hash, _digest(row.id, code.strip())):
            row.attempts += 1
            db.commit()
            raise _refused()
        row.consumed_at = _now()
        row.code_hash = ""
        db.add(
            OperatorAuditLog(
                action="account.store_code_recovered",
                after={"verified": True},
                ip=ip,
            )
        )
        db.commit()
    stores = memberships(settings, email)
    mailed = _send_results(settings, email, stores)
    logger.info("store code recovery verified count=%s", len(stores))
    if not stores:
        return stores, "No store code is linked to this email."
    if mailed:
        return stores, "These store codes are registered to this email. A copy was sent to the same address."
    return stores, "These store codes are registered to this email. We could not send a second copy."


def _send_results(settings: Settings, email: str, stores: list[RecoveredStore]) -> bool:
    if not stores or mail.platform_link(settings) is None:
        return False
    plain, html_body = store_code_result_parts(
        stores=[(item.code, item.label) for item in stores],
        support_email=settings.support_email,
    )
    try:
        mail.send(
            settings,
            Outgoing(to=email, subject="Your AxizPOS store codes", body=plain, html=html_body),
        )
    except ProviderError:
        logger.warning("store code result email failed")
        return False
    return True
