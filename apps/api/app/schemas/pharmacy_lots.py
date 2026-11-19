"""Pharmacy lot lifecycle payloads. These are stock-batch facts, not product master fields."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QuarantineIn(ApiModel):
    reason: str = Field(min_length=3, max_length=2000)


class QuarantineOut(ApiModel):
    batch_item_id: UUID
    lot_status: str
    quarantine_reason: str


class SupplierReturnLineIn(ApiModel):
    batch_item_id: UUID
    quantity: int = Field(ge=1, le=1_000_000)


class SupplierReturnIn(ApiModel):
    reference: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=3, max_length=2000)
    lines: list[SupplierReturnLineIn] = Field(min_length=1, max_length=100)

    @field_validator("reference", "reason")
    @classmethod
    def strip(cls, value: str) -> str:
        return value.strip()


class SupplierReturnLineOut(ApiModel):
    batch_item_id: UUID
    product_id: UUID
    quantity: int
    quantity_remaining: int
    lot_status: str | None


class SupplierReturnOut(ApiModel):
    id: UUID
    reference: str
    reason: str
    lines: list[SupplierReturnLineOut]


class RecallLotIn(ApiModel):
    product_id: UUID
    manufacturer_lot: str = Field(min_length=1, max_length=64)

    @field_validator("manufacturer_lot")
    @classmethod
    def strip_lot(cls, value: str) -> str:
        return value.strip()


class RecallIn(ApiModel):
    reference: str = Field(min_length=1, max_length=64)
    source_text: str = Field(min_length=1, max_length=4000)
    severity: str = Field(min_length=1, max_length=32)
    reason: str = Field(min_length=3, max_length=4000)
    lots: list[RecallLotIn] = Field(min_length=1, max_length=100)

    @field_validator("reference", "source_text", "severity", "reason")
    @classmethod
    def strip(cls, value: str) -> str:
        return value.strip()


class RecallOut(ApiModel):
    id: UUID
    reference: str
    status: str
    severity: str
    layers_recalled: int


class RecallStatusIn(ApiModel):
    status: str


class RecallSaleOut(ApiModel):
    sale_id: UUID
    invoice_number: str | None
    sale_item_id: UUID
    batch_item_id: UUID
    quantity: int
    quantity_returned: int


class RecallSalesOut(ApiModel):
    total: int
    sales: list[RecallSaleOut]


class ConfirmedReason(ApiModel):
    reason: str = Field(min_length=3, max_length=2000)
    confirm: bool

    @field_validator("reason")
    @classmethod
    def strip(cls, value: str) -> str:
        return value.strip()


class PharmacistGrantIn(ConfirmedReason):
    user_id: UUID


class PharmacistOut(ApiModel):
    user_id: UUID
    status: str
    granted_at: str
    active: bool


class GovernanceItemOut(ApiModel):
    user_id: UUID
    user_name: str
    status: str
    requested_by_id: UUID
    requested_by_name: str
    can_decide: bool


class AuthorizationHistoryOut(ApiModel):
    """A closed appointment. The active list does not include these rows, and this view cannot reopen them."""

    id: UUID
    user_id: UUID
    user_name: str
    status: str
    requested_at: str
    requested_by_name: str
    approved_at: str | None = None
    approved_by_name: str = ""
    revoked_at: str | None = None
    revoked_by_name: str = ""
    revocation_reason: str | None = None
    rejected_at: str | None = None
    rejection_reason: str | None = None


class GovernanceOut(ApiModel):
    established: bool
    viewer_is_officer: bool
    can_nominate: bool
    officers: list[GovernanceItemOut]
    appointments: list[GovernanceItemOut]
    appointment_history: list[AuthorizationHistoryOut] = []


class PharmacistSelfOut(ApiModel):
    authorized: bool


class LotDecisionOut(ApiModel):
    batch_item_id: UUID
    lot_status: str
    released_at: str | None


class LotEventOut(ApiModel):
    action: str
    from_status: str | None
    to_status: str | None
    reason: str | None
    user_name: str | None
    created_at: str
