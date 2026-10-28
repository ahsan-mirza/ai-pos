import re
from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.permissions import ALL_PERMISSIONS

USERNAME = re.compile(r"[a-z0-9][a-z0-9._-]{2,31}")
EMAIL = re.compile(r"[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}")
PIN = re.compile(r"\d{4,6}")


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _username(value: str) -> str:
    normalized = value.strip().lower()
    if USERNAME.fullmatch(normalized) is None:
        raise ValueError("username must be 3-32 characters: lowercase letters, digits, dot, dash, underscore.")
    return normalized


def _email(value: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) > 254 or EMAIL.fullmatch(normalized) is None:
        raise ValueError("email is invalid.")
    return normalized


def _pin(value: str) -> str:
    if PIN.fullmatch(value) is None:
        raise ValueError("PIN must be 4 to 6 digits.")
    return value


def _permissions(values: list[str]) -> list[str]:
    unknown = sorted(set(values) - ALL_PERMISSIONS)
    if unknown:
        raise ValueError(f"Unknown permissions: {', '.join(unknown)}")
    return sorted(set(values))


class ForgotPasswordRequest(ApiModel):
    email: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return _email(value)


class ForgotPasswordResponse(ApiModel):
    message: str


class RecoveredStoreOut(ApiModel):
    """`code` is the store code typed at sign-in. `branch` is set when the user is assigned to one branch."""

    code: str
    name: str
    branch: str | None = None


class StoreCodeVerifyResponse(ApiModel):
    message: str
    stores: list[RecoveredStoreOut]


class VerifyResetCodeRequest(ApiModel):
    email: str
    code: str = Field(pattern=r"^\d{6}$")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return _email(value)


class ResetPasswordRequest(ApiModel):
    email: str
    code: str = Field(pattern=r"^\d{6}$")
    password: str = Field(min_length=10, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return _email(value)


class PasswordLoginRequest(ApiModel):
    """`username` is the portal username or the account email."""

    username: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class PinLoginRequest(ApiModel):
    username: str = Field(min_length=1, max_length=64)
    pin: str = Field(min_length=4, max_length=6)


class RegisterStaffOut(ApiModel):
    """A staff member a register can name as the sales associate ("Served by")."""

    id: UUID
    full_name: str
    role_name: str


class RoleSummary(ApiModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    id: UUID
    name: str
    # Largest discount (basis points) the role gives without a manager; None uses the business default.
    max_discount_bps: int | None = None


class UserOut(ApiModel):
    id: UUID
    username: str
    email: str
    full_name: str
    is_active: bool
    store_id: UUID | None
    role: RoleSummary
    permissions: list[str]
    has_pos_access: bool
    has_portal_access: bool
    can_sell_open_price: bool
    has_password: bool
    has_pin: bool
    locked_until: datetime | None
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime
    # Active purchased add-ons this user may use. Empty when the store has not bought any.
    addon_modules: list[str] = Field(default_factory=list)
    # Public media URL for this user's photo. Null when they have not uploaded one.
    avatar_url: str | None = None


class TokenResponse(ApiModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    scope: Literal["portal", "pos"]
    expires_in: int
    user: UserOut


class UserCreate(ApiModel):
    username: str
    email: str
    full_name: str = Field(min_length=1, max_length=120)
    role_id: UUID
    store_id: UUID | None = None
    password: str | None = Field(default=None, min_length=10, max_length=128)
    pin: str | None = None
    has_pos_access: bool = False
    has_portal_access: bool = False
    can_sell_open_price: bool = False
    is_active: bool = True

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return _username(value)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return _email(value)

    @field_validator("pin")
    @classmethod
    def pin_digits(cls, value: str | None) -> str | None:
        return None if value is None else _pin(value)

    @model_validator(mode="after")
    def credentials_for_access(self) -> Self:
        if self.has_portal_access and self.password is None:
            raise ValueError("A password is required for web portal access.")
        if self.has_pos_access and self.pin is None:
            raise ValueError("A PIN is required for POS access.")
        return self


class UserUpdate(ApiModel):
    email: str | None = None
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    role_id: UUID | None = None
    store_id: UUID | None = None
    clear_store: bool = False
    has_pos_access: bool | None = None
    has_portal_access: bool | None = None
    can_sell_open_price: bool | None = None
    is_active: bool | None = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        return None if value is None else _email(value)

    @model_validator(mode="after")
    def store_choice(self) -> Self:
        if self.clear_store and self.store_id is not None:
            raise ValueError("Use either store_id or clear_store, not both.")
        return self


class AccountProfileUpdate(ApiModel):
    """A person editing their own account. Role, store, and status are not on this request."""

    full_name: str = Field(min_length=2, max_length=120)

    @field_validator("full_name")
    @classmethod
    def _name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("Enter your name.")
        return cleaned


class AccountPasswordChange(ApiModel):
    current_password: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=10, max_length=128)


class PasswordReset(ApiModel):
    password: str = Field(min_length=10, max_length=128)


class PinReset(ApiModel):
    pin: str

    @field_validator("pin")
    @classmethod
    def pin_digits(cls, value: str) -> str:
        return _pin(value)


class PermissionOut(ApiModel):
    key: str
    label: str


class PermissionGroupOut(ApiModel):
    group: str
    permissions: list[PermissionOut]


class RoleOut(ApiModel):
    id: UUID
    name: str
    description: str
    is_system: bool
    permissions: list[str]
    user_count: int
    created_at: datetime
    updated_at: datetime
    # Largest discount holders give without a manager (basis points); None uses the business default.
    max_discount_bps: int | None = None


class RoleCreate(ApiModel):
    name: str = Field(min_length=2, max_length=64)
    description: str = Field(default="", max_length=255)
    permissions: list[str] = Field(default_factory=list, max_length=64)
    max_discount_bps: int | None = Field(default=None, ge=0, le=10_000)

    @field_validator("permissions")
    @classmethod
    def known_permissions(cls, value: list[str]) -> list[str]:
        return _permissions(value)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 2:
            raise ValueError("name must be at least 2 characters.")
        return stripped


class RoleUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=2, max_length=64)
    description: str | None = Field(default=None, max_length=255)
    permissions: list[str] | None = Field(default=None, max_length=64)
    # Sent explicitly (null clears it back to the business default).
    max_discount_bps: int | None = Field(default=None, ge=0, le=10_000)

    @field_validator("permissions")
    @classmethod
    def known_permissions(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _permissions(value)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if len(stripped) < 2:
            raise ValueError("name must be at least 2 characters.")
        return stripped
