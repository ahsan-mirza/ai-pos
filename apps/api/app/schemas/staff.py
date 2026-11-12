import re
from datetime import date, datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

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


def _iban_checksum(iban: str) -> bool:
    rearranged = iban[4:] + iban[:4]
    digits = "".join(str(int(char, 36)) for char in rearranged)
    remainder = 0
    for char in digits:
        remainder = (remainder * 10 + int(char)) % 97
    return remainder == 1


class PayrollSettings(ApiModel):
    employer_id: str = Field(pattern=r"^\d{13}$")
    bank_routing_code: str = Field(pattern=r"^\d{9}$")
    bank_name: str = Field(default="", max_length=80)
    employer_reference: str = Field(default="", max_length=40)
    # When set, the person who prepared the run cannot approve it.
    segregate_approval: bool = False

    @field_validator("bank_name", "employer_reference")
    @classmethod
    def tidy_employer(cls, value: str) -> str:
        return value.strip()


class SalaryComponent(ApiModel):
    name: str = Field(min_length=1, max_length=80)
    kind: Literal["ALLOWANCE", "DEDUCTION"]
    code: str = Field(min_length=1, max_length=32)
    amount_cents: int = Field(ge=0, le=100_000_000)
    taxable: bool = False
    active: bool = True

    @field_validator("name", "code")
    @classmethod
    def tidy_component(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Enter a name.")
        return cleaned


class EmployeeProfileWrite(ApiModel):
    labour_id: str = ""
    bank_routing_code: str = ""
    iban: str = ""
    bank_name: str = Field(default="", max_length=80)
    account_holder: str = Field(default="", max_length=80)
    job_title: str = Field(default="", max_length=80)
    nationality: str = Field(default="", max_length=60)
    phone: str = Field(default="", max_length=20)
    emirates_id: str = Field(default="", max_length=18)
    passport_number: str = Field(default="", max_length=20)
    joined_on: date | None = None
    date_of_birth: date | None = None
    employment_type: str = Field(default="", max_length=24)
    basic_salary_cents: int = Field(ge=0, le=100_000_000)
    housing_allowance_cents: int = Field(default=0, ge=0, le=100_000_000)
    transport_allowance_cents: int = Field(default=0, ge=0, le=100_000_000)
    food_allowance_cents: int = Field(default=0, ge=0, le=100_000_000)
    other_allowance_cents: int = Field(default=0, ge=0, le=100_000_000)
    variable_allowance_cents: int = Field(default=0, ge=0, le=100_000_000)
    recurring_deduction_cents: int = Field(default=0, ge=0, le=100_000_000)
    components: list[SalaryComponent] = Field(default_factory=list, max_length=24)
    overtime_rate_pct: int = Field(default=125, ge=100, le=300)
    overtime_eligible: bool = True
    commission_eligible: bool = True
    salary_frequency: Literal["MONTHLY"] = "MONTHLY"
    profile_status: Literal["DRAFT", "ACTIVE"] = "ACTIVE"
    effective_from: date | None = None
    is_active: bool = True

    @field_validator("iban")
    @classmethod
    def uae_iban(cls, value: str) -> str:
        cleaned = value.replace(" ", "").upper()
        if not cleaned:
            return ""
        if not (cleaned.startswith("AE") and cleaned[2:].isdigit() and len(cleaned) == 23):
            raise ValueError("Enter a UAE IBAN: AE followed by 21 digits.")
        if not _iban_checksum(cleaned):
            raise ValueError("That IBAN failed the checksum. Check the digits.")
        return cleaned

    @field_validator(
        "job_title", "nationality", "phone", "passport_number", "bank_name", "account_holder", "employment_type"
    )
    @classmethod
    def trimmed(cls, value: str) -> str:
        return value.strip()

    @field_validator("emirates_id")
    @classmethod
    def emirates(cls, value: str) -> str:
        digits = value.replace("-", "").replace(" ", "")
        if digits and (len(digits) != 15 or not digits.isdigit()):
            raise ValueError("An Emirates ID is 15 digits.")
        return digits

    @field_validator("passport_number")
    @classmethod
    def passport(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if cleaned and not cleaned.replace(" ", "").isalnum():
            raise ValueError("A passport number uses letters and digits.")
        return cleaned.replace(" ", "")

    @field_validator("labour_id", "bank_routing_code")
    @classmethod
    def digits_only(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def active_profile_is_complete(self) -> Self:
        if self.labour_id and not re.fullmatch(r"\d{14}", self.labour_id):
            raise ValueError("A MOHRE personal number is 14 digits.")
        if self.bank_routing_code and not re.fullmatch(r"\d{9}", self.bank_routing_code):
            raise ValueError("A bank routing code is 9 digits.")
        if self.profile_status != "ACTIVE":
            return self
        if not re.fullmatch(r"\d{14}", self.labour_id):
            raise ValueError("An active salary profile needs a 14-digit MOHRE personal number.")
        if not re.fullmatch(r"\d{9}", self.bank_routing_code):
            raise ValueError("An active salary profile needs a 9-digit bank routing code.")
        if not self.iban:
            raise ValueError("An active salary profile needs a UAE IBAN.")
        return self


class EmployeeProfileOut(ApiModel):
    """Bank fields may be masked. iban_masked says whether the full IBAN was withheld."""

    employee_code: str
    labour_id: str
    bank_routing_code: str
    iban: str
    iban_masked: bool = False
    bank_name: str = ""
    account_holder: str = ""
    job_title: str = ""
    nationality: str = ""
    phone: str = ""
    emirates_id: str = ""
    passport_number: str = ""
    joined_on: date | None = None
    date_of_birth: date | None = None
    employment_type: str = ""
    basic_salary_cents: int
    housing_allowance_cents: int = 0
    transport_allowance_cents: int = 0
    food_allowance_cents: int = 0
    other_allowance_cents: int = 0
    variable_allowance_cents: int = 0
    recurring_deduction_cents: int = 0
    components: list[SalaryComponent] = Field(default_factory=list)
    overtime_rate_pct: int = 125
    overtime_eligible: bool = True
    commission_eligible: bool = True
    salary_frequency: Literal["MONTHLY"] = "MONTHLY"
    profile_status: Literal["DRAFT", "ACTIVE"] = "ACTIVE"
    effective_from: date | None = None
    is_active: bool = True


class SalaryVersionOut(ApiModel):
    id: UUID
    effective_from: date
    effective_to: date | None
    status: str
    basic_salary_cents: int
    housing_allowance_cents: int = 0
    transport_allowance_cents: int = 0
    food_allowance_cents: int = 0
    other_allowance_cents: int = 0
    variable_allowance_cents: int = 0
    recurring_deduction_cents: int = 0
    overtime_rate_pct: int = 125
    overtime_eligible: bool = True
    commission_eligible: bool = True


class EmployeeOut(ApiModel):
    user_id: UUID
    name: str
    role_name: str
    store_id: UUID | None
    store_name: str = ""
    employment_status: Literal["ACTIVE", "INACTIVE"] = "ACTIVE"
    profile: EmployeeProfileOut | None
    salary_history: list[SalaryVersionOut] = Field(default_factory=list)


class PayrollLineWrite(ApiModel):
    bonus_cents: int = Field(default=0, ge=0, le=100_000_000)
    deductions_cents: int = Field(default=0, ge=0, le=100_000_000)
    unpaid_leave_days: int = Field(default=0, ge=0, le=31)
    note: str = Field(default="", max_length=255)


class PayComponent(ApiModel):
    name: str
    kind: Literal["EARNING", "DEDUCTION"]
    cents: int
    source: str


class PayrollExceptionOut(ApiModel):
    user_id: UUID | None = None
    name: str = ""
    severity: Literal["EXCLUDED", "WARNING"]
    code: str
    message: str


class PayrollLineOut(ApiModel):
    id: UUID
    user_id: UUID
    name: str
    employee_code: str
    store_id: UUID | None = None
    store_name: str = ""
    basic_cents: int
    allowances_cents: int
    overtime_minutes: int
    overtime_cents: int
    commission_cents: int
    bonus_cents: int
    deductions_cents: int
    recurring_deduction_cents: int = 0
    unpaid_leave_days: int
    leave_deduction_cents: int
    gross_cents: int = 0
    note: str
    net_cents: int
    calculation_status: str = "OK"
    components: list[PayComponent] = Field(default_factory=list)
    formula: str = ""


class PayrollRunOut(ApiModel):
    id: UUID
    year: int
    month: int
    status: Literal["DRAFT", "UNDER_REVIEW", "FINALIZED", "CANCELLED"]
    payment_status: Literal[
        "NONE", "GENERATED", "SUBMITTED", "PROCESSING", "PARTIALLY_PAID", "PAID", "REJECTED", "FAILED"
    ] = "NONE"
    store_id: UUID | None = None
    currency: str
    finalized_at: datetime | None
    total_gross_cents: int = 0
    total_deductions_cents: int = 0
    total_net_cents: int
    exceptions: list[PayrollExceptionOut] = Field(default_factory=list)
    lines: list[PayrollLineOut]


class PayrollRunCreate(ApiModel):
    year: int = Field(ge=2020, le=2100)
    month: int = Field(ge=1, le=12)
    store_id: UUID | None = None


class PayrollNote(ApiModel):
    note: str = Field(default="", max_length=255)


class WpsIssue(ApiModel):
    user_id: UUID | None = None
    employee_code: str = ""
    name: str = ""
    code: str
    message: str


class WpsValidation(ApiModel):
    ready: bool
    provider: str
    provider_note: str
    issues: list[WpsIssue]


class PayrollPaymentWrite(ApiModel):
    amount_cents: int = Field(gt=0, le=100_000_000)
    reference: str = Field(min_length=3, max_length=40)
    status: Literal["SUBMITTED", "PROCESSING", "PAID", "PARTIALLY_PAID", "REJECTED", "FAILED"]
    note: str = Field(default="", max_length=255)

    @field_validator("reference", "note")
    @classmethod
    def tidy_payment(cls, value: str) -> str:
        return value.strip()


class PayrollPaymentOut(ApiModel):
    id: UUID
    amount_cents: int
    reference: str
    status: str
    note: str
    created_at: datetime


class PayslipSummary(ApiModel):
    id: UUID
    run_id: UUID
    user_id: UUID
    year: int
    month: int
    currency: str
    net_cents: int
    payment_status: str
