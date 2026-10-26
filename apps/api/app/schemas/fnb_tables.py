"""Waiter and table-tablet payloads. A table session is the open order already shared by every register."""

from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.menu import ModifierGroupOut
from app.schemas.orders import OrderOut
from app.schemas.payloads import ApiModel, ModifierChoice

Course = Literal["Starters", "Mains", "Beverages", "Desserts"]


class SessionStart(ApiModel):
    phone: str | None = Field(default=None, max_length=40)
    covers: int = Field(default=1, ge=1, le=200)

    @field_validator("phone")
    @classmethod
    def normalize_guest_phone(cls, value: str | None) -> str | None:
        from app.services.phone_numbers import normalize_phone

        return normalize_phone(value)
    user_id: UUID | None = None


class RoundItem(ApiModel):
    product_id: UUID
    quantity: int = Field(ge=1, le=99)
    note: str | None = Field(default=None, max_length=160)
    modifiers: list[ModifierChoice] = Field(default_factory=list, max_length=30)


class AddRound(ApiModel):
    user_id: UUID | None = None
    # The tablet mints this so a retried tap does not fire the same dishes twice.
    client_round_id: UUID | None = None
    items: list[RoundItem] = Field(min_length=1, max_length=40)


class ActiveSessionOut(ApiModel):
    status: Literal["OCCUPIED", "FREE"]
    table_id: UUID
    table_label: str
    order: OrderOut | None
    customer_name: str | None
    phone: str | None
    loyalty_points: int


class TableMenuItem(ApiModel):
    id: UUID
    name: str
    course: Course
    price_cents: int
    currency: str
    # Cover photo for the guest menu. Empty when the dish has no image yet.
    image_url: str | None = None
    groups: list[ModifierGroupOut]


class WaiterCallOut(ApiModel):
    table_id: UUID
    table_label: str
    message: str


class TableMenuOut(ApiModel):
    items: list[TableMenuItem]
