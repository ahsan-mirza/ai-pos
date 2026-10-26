import re
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.payloads import ApiModel

# Same rule as portal users (UserCreate).
PASSWORD_MIN_LENGTH = 10

SignupStatus = Literal["PENDING_OTP", "VERIFIED", "WAITLIST", "PROVISIONING", "READY", "FAILED"]
StepState = Literal["pending", "running", "done", "failed"]
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class SignupStart(ApiModel):
    email: str = Field(max_length=254)
    phone: str = Field(min_length=8, max_length=32)
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=128)

    @field_validator("password")
    @classmethod
    def _password(cls, value: str) -> str:
        if not re.search(r"[A-Z]", value):
            raise ValueError("Password needs an uppercase letter.")
        if not re.search(r"\d", value):
            raise ValueError("Password needs a number.")
        if not re.search(r"[^A-Za-z0-9]", value):
            raise ValueError("Password needs a special character.")
        return value

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not EMAIL.fullmatch(cleaned):
            raise ValueError("Enter a valid email address.")
        return cleaned

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str) -> str:
        from app.services.phone_numbers import normalize_phone

        normalized = normalize_phone(value, required=True)
        if normalized is None:
            raise ValueError("Enter a phone number.")
        return normalized


class SignupResume(ApiModel):
    """Log in to a signup that was already started with this email."""

    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not EMAIL.fullmatch(cleaned):
            raise ValueError("Enter a valid email address.")
        return cleaned


class SignupStarted(ApiModel):
    id: UUID
    # Sent back on every later call (X-Signup-Token); only its hash is stored.
    token: str
    channel: str
    sent_to: str
    resend_after_seconds: int
    expires_in_seconds: int
    dev_code: str | None = None


class SignupVerify(ApiModel):
    code: str = Field(pattern=r"^\d{6}$")


class SignupBusiness(ApiModel):
    profile: str = Field(max_length=32)
    sub_type: str | None = Field(default=None, max_length=32)


class SignupStore(ApiModel):
    store_name: str = Field(min_length=2, max_length=120)
    slug: str = Field(min_length=1, max_length=32)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    country: str = Field(pattern=r"^[A-Z]{2}$")
    trn: str | None = Field(default=None, pattern=r"^\d{15}$")


class SlugCheck(ApiModel):
    slug: str
    available: bool
    reason: str | None
    suggestion: str | None


class ProvisionStep(ApiModel):
    key: str
    label: str
    state: StepState


class SignupState(ApiModel):
    id: UUID
    status: SignupStatus
    email: str
    phone: str
    profile: str | None
    sub_type: str | None
    store_name: str | None
    slug: str | None
    steps: list[ProvisionStep]
    error: str | None
    portal_url: str | None
    owner_username: str | None
    # A five-minute, single-use sign-in for the new store; present once the store is ready.
    handoff_token: str | None


class HandoffRequest(ApiModel):
    token: str = Field(min_length=20, max_length=2000)
