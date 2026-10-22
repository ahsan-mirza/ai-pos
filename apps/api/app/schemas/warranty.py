from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from app.schemas.payloads import ApiModel

PolicyScope = Literal["DEFAULT", "CATEGORY", "PRODUCT"]
RegistrationStatus = Literal["ACTIVE", "CLAIMED", "VOID"]
Coverage = Literal["IN_WARRANTY", "EXPIRED", "NOT_FOUND", "VOID"]


class PolicyWrite(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    scope: PolicyScope
    category_id: UUID | None = None
    product_id: UUID | None = None
    months: int = Field(ge=0, le=120)
    terms: str = Field(default="", max_length=2000)
    is_active: bool = True

    @model_validator(mode="after")
    def target(self) -> Self:
        if self.scope == "CATEGORY" and self.category_id is None:
            raise ValueError("Choose the category this cover applies to.")
        if self.scope == "PRODUCT" and self.product_id is None:
            raise ValueError("Choose the product this cover applies to.")
        return self


class PolicyOut(ApiModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    name: str
    scope: PolicyScope
    category_id: UUID | None
    product_id: UUID | None
    months: int
    terms: str
    is_active: bool


class PlanWrite(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    extra_months: int = Field(ge=1, le=60)
    price_cents: int = Field(ge=0, le=100_000_000)
    terms: str = Field(default="", max_length=2000)


class PlanOut(ApiModel):
    id: UUID
    name: str
    extra_months: int
    product_id: UUID
    sku: str
    price_cents: int
    terms: str
    is_active: bool


class RegistrationOut(ApiModel):
    id: UUID
    sale_id: UUID
    invoice: str
    # SALE cover on a unit sold here, or REPAIR: our guarantee on an invoiced repair.
    kind: Literal["SALE", "REPAIR"] = "SALE"
    product_name: str
    serial: str | None
    customer_id: UUID | None
    customer_name: str | None
    plan_name: str | None
    starts_at: datetime
    expires_at: datetime
    status: RegistrationStatus
    coverage: Coverage
    claims: int


class RegistrationList(ApiModel):
    active_count: int
    expiring_count: int
    extended_count: int
    registrations: list[RegistrationOut]
