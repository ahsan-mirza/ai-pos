from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.payloads import ApiModel

CommissionBasis = Literal["NET_SALES", "GROSS_PROFIT"]


class CommissionRuleWrite(ApiModel):
    name: str = Field(min_length=2, max_length=80)
    basis: CommissionBasis
    rate_bps: int = Field(ge=0, le=10_000)
    category_ids: list[UUID] = Field(default_factory=list, max_length=100)
    role_ids: list[UUID] = Field(default_factory=list, max_length=50)
    threshold_cents: int = Field(default=0, ge=0, le=10_000_000_000)
    is_active: bool = True


class CommissionRuleOut(CommissionRuleWrite):
    id: UUID
    category_ids: list[UUID]
    role_ids: list[UUID]


class CommissionByRule(ApiModel):
    rule_id: UUID
    rule_name: str
    basis_cents: int
    commission_cents: int


class StaffCommission(ApiModel):
    user_id: UUID
    name: str
    role_name: str
    lines: int
    commission_cents: int
    by_rule: list[CommissionByRule]


class CommissionReport(ApiModel):
    period_from: date
    period_to: date
    currency: str
    total_cents: int
    staff: list[StaffCommission]


class PayrollSettings(ApiModel):
    employer_id: str = Field(pattern=r"^\d{13}$")
    bank_routing_code: str = Field(pattern=r"^\d{9}$")


class EmployeeProfileWrite(ApiModel):
    employee_code: str = Field(min_length=1, max_length=20)
    labour_id: str = Field(pattern=r"^\d{14}$")
    bank_routing_code: str = Field(pattern=r"^\d{9}$")
    iban: str = Field(min_length=23, max_length=23)
    basic_salary_cents: int = Field(ge=0, le=100_000_000)
    housing_allowance_cents: int = Field(default=0, ge=0, le=100_000_000)
    transport_allowance_cents: int = Field(default=0, ge=0, le=100_000_000)
    other_allowance_cents: int = Field(default=0, ge=0, le=100_000_000)
    overtime_rate_pct: int = Field(default=125, ge=100, le=300)
    is_active: bool = True

    @field_validator("iban")
    @classmethod
    def uae_iban(cls, value: str) -> str:
        cleaned = value.replace(" ", "").upper()
        if not (cleaned.startswith("AE") and cleaned[2:].isdigit() and len(cleaned) == 23):
            raise ValueError("Enter a UAE IBAN: AE followed by 21 digits.")
        return cleaned


class EmployeeOut(ApiModel):
    user_id: UUID
    name: str
    role_name: str
    store_id: UUID | None
    profile: EmployeeProfileWrite | None


class PayrollLineWrite(ApiModel):
    bonus_cents: int = Field(default=0, ge=0, le=100_000_000)
    deductions_cents: int = Field(default=0, ge=0, le=100_000_000)
    unpaid_leave_days: int = Field(default=0, ge=0, le=31)
    note: str = Field(default="", max_length=255)


class PayrollLineOut(ApiModel):
    id: UUID
    user_id: UUID
    name: str
    employee_code: str
    basic_cents: int
    allowances_cents: int
    overtime_minutes: int
    overtime_cents: int
    commission_cents: int
    bonus_cents: int
    deductions_cents: int
    unpaid_leave_days: int
    leave_deduction_cents: int
    note: str
    net_cents: int


class PayrollRunOut(ApiModel):
    id: UUID
    year: int
    month: int
    status: Literal["DRAFT", "FINALIZED"]
    currency: str
    finalized_at: datetime | None
    total_net_cents: int
    lines: list[PayrollLineOut]


class PayrollRunCreate(ApiModel):
    year: int = Field(ge=2020, le=2100)
    month: int = Field(ge=1, le=12)
