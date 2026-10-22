"""Self-service signup on the bare domain: account and one-time code, business type, store and subdomain.

Runs against the control database only. Provisioning the store itself lives in app.tenancy.provisioning."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import capabilities as capability_catalog
from app.core.config import Settings
from app.core.errors import ApiError
from app.core.security import hash_password
from app.schemas.signup import (
    ProvisionStep,
    SignupBusiness,
    SignupStart,
    SignupStarted,
    SignupState,
    SignupStore,
    SlugCheck,
)
from app.services import messaging_providers
from app.tenancy import registry
from app.tenancy.models import SignupRequest, Tenant

RESEND_SECONDS = 30
MAX_OTP_ATTEMPTS = 5
HANDOFF_MINUTES = 5
CHANNEL_PROVIDERS = {"log": "log", "whatsapp": "whatsapp_cloud", "sms": "http_sms", "email": "smtp"}
SUPPORTED_COUNTRIES = {"AE": "AED", "SA": "SAR", "QA": "QAR", "KW": "KWD", "BH": "BHD", "OM": "OMR"}
STEPS: tuple[tuple[str, str], ...] = (
    ("database", "Creating your store's own database"),
    ("migrations", "Building the database tables"),
    ("register", "Reserving your store address"),
    ("owner", "Creating your owner account"),
    ("settings", "Applying your business type, currency and tax settings"),
    ("samples", "Adding sample products to practise with"),
    ("ready", "Opening your store"),
)
FOOD_SAMPLES_LABEL = "Setting up a sample menu, meals, tables and kitchen to practise with"


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _require_enabled(settings: Settings) -> None:
    if not settings.tenancy_enabled or not settings.signup_enabled:
        raise ApiError(404, "signup_disabled", "Self-service signup is not available on this server.")


def _load(settings: Settings, request_id: uuid.UUID, token: str | None) -> tuple[Session, SignupRequest]:
    db = registry.control_session(settings)
    row = db.get(SignupRequest, request_id)
    if row is None or not token or not hmac.compare_digest(row.access_hash, _digest(token)):
        db.close()
        raise ApiError(404, "not_found", "Signup was not found. Start again.")
    return db, row


def _send_code(settings: Settings, row: SignupRequest) -> str:
    code = settings.signup_otp_code or f"{secrets.randbelow(1_000_000):06d}"
    row.otp_hash = _digest(f"{row.id}:{code}")
    row.otp_expires_at = _now() + timedelta(minutes=settings.signup_otp_minutes)
    row.otp_sent_at = _now()
    row.otp_attempts = 0
    if settings.signup_otp_code:
        return code
    channel = settings.signup_otp_channel
    to = row.email if channel == "email" else row.phone
    body = f"Your AI POS verification code is {code}. It expires in {settings.signup_otp_minutes} minutes."
    try:
        messaging_providers.deliver(
            settings,
            CHANNEL_PROVIDERS[channel],
            messaging_providers.Outgoing(to=to, subject="Your AI POS verification code", body=body),
        )
    except messaging_providers.ProviderError as error:
        raise ApiError(502, "otp_not_sent", f"We could not send the code: {error}") from error
    return code


def _masked(row: SignupRequest, channel: str) -> str:
    if channel == "email":
        name, _, domain = row.email.partition("@")
        return f"{name[:2]}•••@{domain}"
    return f"{row.phone[:4]}•••{row.phone[-3:]}"


def start(settings: Settings, data: SignupStart) -> SignupStarted:
    _require_enabled(settings)
    with registry.control_session(settings) as db:
        since = _now() - timedelta(hours=1)
        recent = db.scalar(
            select(func.count())
            .select_from(SignupRequest)
            .where(
                SignupRequest.created_at >= since,
                (SignupRequest.email == data.email) | (SignupRequest.phone == data.phone),
            )
        )
        if int(recent or 0) >= settings.signup_max_per_hour:
            raise ApiError(429, "too_many_signups", "Too many signup attempts. Try again in an hour.")
        token = secrets.token_urlsafe(32)
        row = SignupRequest(
            email=data.email,
            phone=data.phone,
            full_name=data.full_name.strip(),
            password_hash=hash_password(data.password),
            access_hash=_digest(token),
            status="PENDING_OTP",
            steps=[],
        )
        db.add(row)
        db.flush()
        code = _send_code(settings, row)
        db.commit()
        channel = settings.signup_otp_channel
        return SignupStarted(
            id=row.id,
            token=token,
            channel=channel,
            sent_to=_masked(row, channel),
            resend_after_seconds=RESEND_SECONDS,
            dev_code=code if channel == "log" and settings.app_env != "production" else None,
        )


def resend(settings: Settings, request_id: uuid.UUID, token: str | None) -> SignupStarted:
    _require_enabled(settings)
    db, row = _load(settings, request_id, token)
    with db:
        if row.status != "PENDING_OTP":
            raise ApiError(409, "already_verified", "This signup is already verified.")
        sent = _aware(row.otp_sent_at)
        if sent is not None and (_now() - sent).total_seconds() < RESEND_SECONDS:
            raise ApiError(429, "resend_too_soon", f"Wait {RESEND_SECONDS} seconds before asking for a new code.")
        code = _send_code(settings, row)
        db.commit()
        channel = settings.signup_otp_channel
        return SignupStarted(
            id=row.id,
            token=token or "",
            channel=channel,
            sent_to=_masked(row, channel),
            resend_after_seconds=RESEND_SECONDS,
            dev_code=code if channel == "log" and settings.app_env != "production" else None,
        )


def verify(settings: Settings, request_id: uuid.UUID, token: str | None, code: str) -> SignupState:
    _require_enabled(settings)
    db, row = _load(settings, request_id, token)
    with db:
        if row.status != "PENDING_OTP":
            return state(settings, row)
        expires = _aware(row.otp_expires_at)
        if row.otp_hash is None or expires is None or expires < _now():
            raise ApiError(410, "code_expired", "The code has expired. Ask for a new one.")
        if row.otp_attempts >= MAX_OTP_ATTEMPTS:
            raise ApiError(429, "too_many_attempts", "Too many wrong codes. Ask for a new one.")
        if not hmac.compare_digest(row.otp_hash, _digest(f"{row.id}:{code}")):
            row.otp_attempts += 1
            db.commit()
            left = MAX_OTP_ATTEMPTS - row.otp_attempts
            raise ApiError(422, "wrong_code", f"That code is not right. {left} attempt{'s' if left != 1 else ''} left.")
        row.status = "VERIFIED"
        row.verified_at = _now()
        row.otp_hash = None
        db.commit()
        return state(settings, row)


def suggest_slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:32].strip("-")
    return base or "store"


def _slug_reason(db: Session, slug: str, own_id: uuid.UUID | None = None) -> str | None:
    if not registry.valid_slug(slug):
        return "Use 1-32 lowercase letters, numbers or dashes; some names (www, api, admin) are reserved."
    if db.scalar(select(Tenant.id).where(Tenant.slug == slug)) is not None:
        return "That address is taken."
    claimed = db.scalar(
        select(SignupRequest.id).where(
            SignupRequest.slug == slug,
            SignupRequest.status.in_(("PROVISIONING", "READY")),
            SignupRequest.id != (own_id or uuid.uuid4()),
        )
    )
    return "That address is being set up for another store." if claimed is not None else None


def check_slug(settings: Settings, slug: str) -> SlugCheck:
    _require_enabled(settings)
    cleaned = slug.strip().lower()
    with registry.control_session(settings) as db:
        reason = _slug_reason(db, cleaned)
        suggestion = None
        if reason is not None:
            stem = suggest_slug(cleaned)[:28].strip("-") or "store"
            for index in range(2, 50):
                candidate = f"{stem}-{index}"
                if _slug_reason(db, candidate) is None:
                    suggestion = candidate
                    break
        return SlugCheck(slug=cleaned, available=reason is None, reason=reason, suggestion=suggestion)


def choose_business(settings: Settings, request_id: uuid.UUID, token: str | None, data: SignupBusiness) -> SignupState:
    _require_enabled(settings)
    db, row = _load(settings, request_id, token)
    with db:
        if row.status not in ("VERIFIED", "WAITLIST"):
            raise ApiError(409, "wrong_step", "Verify your mobile number first.")
        if data.profile not in capability_catalog.PROFILES:
            raise ApiError(422, "unknown_profile", "Choose one of the business types shown.")
        row.profile = data.profile
        live = capability_catalog.SUB_TYPES.get(data.profile)
        if live is None:
            row.sub_type = None
            row.status = "WAITLIST"
        else:
            if data.sub_type not in live:
                raise ApiError(422, "unknown_sub_type", f"Choose one of: {', '.join(live)}.")
            row.sub_type = data.sub_type
            row.status = "VERIFIED"
        db.commit()
        return state(settings, row)


def choose_store(settings: Settings, request_id: uuid.UUID, token: str | None, data: SignupStore) -> SignupState:
    """Locks in the store and subdomain and marks the signup for provisioning; the caller starts the job."""
    _require_enabled(settings)
    db, row = _load(settings, request_id, token)
    with db:
        if row.status != "VERIFIED" or row.sub_type is None:
            raise ApiError(409, "wrong_step", "Choose your business type first.")
        if data.country not in SUPPORTED_COUNTRIES:
            raise ApiError(422, "unsupported_country", "Choose a GCC country.")
        slug = data.slug.strip().lower()
        reason = _slug_reason(db, slug, row.id)
        if reason is not None:
            raise ApiError(409, "slug_unavailable", reason)
        row.store_name = data.store_name.strip()
        row.slug = slug
        row.currency = data.currency
        row.country = data.country
        row.trn = data.trn
        row.status = "PROVISIONING"
        row.error = None
        food = row.profile in capability_catalog.FOOD_AND_BEVERAGE
        row.steps = [
            {"key": key, "label": FOOD_SAMPLES_LABEL if food and key == "samples" else label, "state": "pending"}
            for key, label in STEPS
        ]
        db.commit()
        return state(settings, row)


def retry(settings: Settings, request_id: uuid.UUID, token: str | None) -> SignupState:
    _require_enabled(settings)
    db, row = _load(settings, request_id, token)
    with db:
        if row.status != "FAILED":
            raise ApiError(409, "wrong_step", "Only a failed setup can be retried.")
        row.status = "PROVISIONING"
        row.error = None
        row.steps = [{**step, "state": "pending" if step["state"] != "done" else "done"} for step in (row.steps or [])]
        db.commit()
        return state(settings, row)


def handoff_token(settings: Settings, row: SignupRequest) -> str | None:
    if row.status != "READY" or row.handoff_jti is None or row.handoff_used_at is not None or row.tenant_id is None:
        return None
    now = _now()
    claims = {
        "aud": "handoff",
        "tid": str(row.tenant_id),
        "sub": row.owner_username,
        "jti": row.handoff_jti,
        "iat": now,
        "exp": now + timedelta(minutes=HANDOFF_MINUTES),
    }
    token = jwt.encode(claims, settings.jwt_secret, algorithm="HS256")
    return token if isinstance(token, str) else token.decode("utf-8")


def state(settings: Settings, row: SignupRequest) -> SignupState:
    return SignupState(
        id=row.id,
        status=row.status,  # type: ignore[arg-type]
        email=row.email,
        phone=row.phone,
        profile=row.profile,
        sub_type=row.sub_type,
        store_name=row.store_name,
        slug=row.slug,
        steps=[ProvisionStep(**step) for step in (row.steps or [])],
        error=row.error,
        portal_url=registry.tenant_public_url(row.slug, settings) if row.slug and row.status == "READY" else None,
        owner_username=row.owner_username,
        handoff_token=handoff_token(settings, row),
    )


def current(settings: Settings, request_id: uuid.UUID, token: str | None) -> SignupState:
    _require_enabled(settings)
    db, row = _load(settings, request_id, token)
    with db:
        return state(settings, row)


def redeem_handoff(settings: Settings, token: str, tenant_id: str) -> str:
    """Validates a handoff token for this store and marks it used; returns the owner's username."""
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], audience="handoff")
    except jwt.PyJWTError as error:
        raise ApiError(401, "invalid_handoff", "This sign-in link has expired. Sign in with your password.") from error
    if claims.get("tid") != tenant_id:
        raise ApiError(401, "invalid_handoff", "This sign-in link is for another store.")
    with registry.control_session(settings) as db:
        row = db.scalar(select(SignupRequest).where(SignupRequest.handoff_jti == str(claims.get("jti"))))
        if row is None or row.handoff_used_at is not None:
            raise ApiError(401, "invalid_handoff", "This sign-in link was already used. Sign in with your password.")
        row.handoff_used_at = _now()
        db.commit()
        return str(claims.get("sub"))
