from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    and_,
    column,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique


class CommissionRule(TenantScoped, TimestampMixin, Base):
    """Pays rate_bps of a sale line's net sales or gross profit to the cashier who rang it up. A line earns under its
    most specific matching rule (a category rule beats an all-products rule). threshold_cents is per person per
    period: commission starts once their basis under this rule passes it."""

    __tablename__ = "commission_rules"
    __table_args__ = (CheckConstraint("rate_bps >= 0 AND rate_bps <= 10000", name="commission_rate_range"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(80))
    # NET_SALES or GROSS_PROFIT
    basis: Mapped[str] = mapped_column(String(12))
    rate_bps: Mapped[int] = mapped_column(Integer)
    category_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    role_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    threshold_cents: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class EmployeeProfile(TenantScoped, TimestampMixin, Base):
    """Current payroll profile for a staff user. Amounts are monthly, in the business currency.

    Salary changes are also stored as effective-dated rows on employee_salary_versions. This row is the
    latest version the screens edit. Approved payroll lines keep their own snapshot.
    """

    __tablename__ = "employee_profiles"
    __table_args__ = (tenant_unique("user_id", name="uq_employee_profiles_user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    # Assigned when the profile is first saved. Later edits keep the same code.
    employee_code: Mapped[str] = mapped_column(String(20))
    job_title: Mapped[str] = mapped_column(String(80), default="")
    nationality: Mapped[str] = mapped_column(String(60), default="")
    phone: Mapped[str] = mapped_column(String(20), default="")
    emirates_id: Mapped[str] = mapped_column(String(15), default="")
    passport_number: Mapped[str] = mapped_column(String(20), default="")
    joined_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    employment_type: Mapped[str] = mapped_column(String(24), default="")
    # MOHRE personal number (14 digits) used as the WPS employee ID.
    labour_id: Mapped[str] = mapped_column(String(14), default="")
    bank_name: Mapped[str] = mapped_column(String(80), default="")
    account_holder: Mapped[str] = mapped_column(String(80), default="")
    # Routing code of the employee's bank (9 digits). The IBAN is encrypted in iban_encrypted.
    bank_routing_code: Mapped[str] = mapped_column(String(9), default="")
    # Legacy plaintext IBAN. Cleared once iban_encrypted is written. Reads still accept a leftover value.
    iban: Mapped[str] = mapped_column(Text, default="")
    iban_encrypted: Mapped[str] = mapped_column(Text, default="")
    iban_last4: Mapped[str] = mapped_column(String(4), default="")
    basic_salary_cents: Mapped[int] = mapped_column(Integer)
    housing_allowance_cents: Mapped[int] = mapped_column(Integer, default=0)
    transport_allowance_cents: Mapped[int] = mapped_column(Integer, default=0)
    food_allowance_cents: Mapped[int] = mapped_column(Integer, default=0)
    other_allowance_cents: Mapped[int] = mapped_column(Integer, default=0)
    variable_allowance_cents: Mapped[int] = mapped_column(Integer, default=0)
    recurring_deduction_cents: Mapped[int] = mapped_column(Integer, default=0)
    # Extra allowances and deductions that are not one of the columns above. Standard codes are mirrored there.
    components: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Overtime pay as a percentage of the hourly basic rate (UAE minimum is 125%).
    overtime_rate_pct: Mapped[int] = mapped_column(Integer, default=125)
    overtime_eligible: Mapped[bool] = mapped_column(Boolean, default=True)
    commission_eligible: Mapped[bool] = mapped_column(Boolean, default=True)
    salary_frequency: Mapped[str] = mapped_column(String(12), default="MONTHLY")
    # DRAFT profiles are not payable. ACTIVE profiles are.
    profile_status: Mapped[str] = mapped_column(String(12), default="ACTIVE")
    # Null means the salary applies from the start of employment, so older months can still be paid.
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class EmployeeSalaryVersion(TenantScoped, TimestampMixin, Base):
    """One effective-dated salary. A later version closes the previous one. Approved payroll does not read this live."""

    __tablename__ = "employee_salary_versions"
    __table_args__ = (tenant_unique("profile_id", "effective_from", name="uq_salary_version_effective"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employee_profiles.id", ondelete="CASCADE"), index=True
    )
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    # DRAFT, ACTIVE, or SUPERSEDED.
    status: Mapped[str] = mapped_column(String(12), default="ACTIVE")
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


class PayrollRun(TenantScoped, TimestampMixin, Base):
    """One month's payroll for the business, or for one branch when store_id is set.

    DRAFT can be recalculated. UNDER_REVIEW is waiting for approval. FINALIZED is the approved snapshot and
    does not change. CANCELLED frees the month so another run can be prepared. Payment progress lives on
    payment_status, because a WPS file is not proof that salaries were paid.
    """

    __tablename__ = "payroll_runs"
    __table_args__ = (
        # NULL store_id is the all-branch run. A unique index would treat each NULL as different, so it is partial.
        Index(
            "uq_payroll_runs_all_branches",
            "tenant_id",
            "year",
            "month",
            unique=True,
            sqlite_where=and_(column("status") != "CANCELLED", column("store_id").is_(None)),
            postgresql_where=and_(column("status") != "CANCELLED", column("store_id").is_(None)),
        ),
        Index(
            "uq_payroll_runs_one_branch",
            "tenant_id",
            "year",
            "month",
            "store_id",
            unique=True,
            sqlite_where=and_(column("status") != "CANCELLED", column("store_id").is_not(None)),
            postgresql_where=and_(column("status") != "CANCELLED", column("store_id").is_not(None)),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    # Null store_id means every branch. A branch run does not block a different branch, or an all-branch run.
    store_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    # NONE, GENERATED, SUBMITTED, PROCESSING, PARTIALLY_PAID, PAID, REJECTED, FAILED.
    payment_status: Mapped[str] = mapped_column(String(20), default="NONE")
    currency: Mapped[str] = mapped_column(String(3))
    exceptions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    rejection_note: Mapped[str] = mapped_column(String(255), default="")
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    submitted_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finalized_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    wps_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lines: Mapped[list[PayrollLine]] = relationship(
        "PayrollLine", cascade="all, delete-orphan", lazy="selectin", order_by="PayrollLine.employee_code"
    )


class PayrollLine(TenantScoped, Base):
    __tablename__ = "payroll_lines"
    __table_args__ = (tenant_unique("run_id", "user_id", name="uq_payroll_lines_run_user"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("payroll_runs.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    employee_code: Mapped[str] = mapped_column(String(20))
    basic_cents: Mapped[int] = mapped_column(Integer)
    allowances_cents: Mapped[int] = mapped_column(Integer)
    overtime_minutes: Mapped[int] = mapped_column(Integer, default=0)
    overtime_cents: Mapped[int] = mapped_column(Integer, default=0)
    commission_cents: Mapped[int] = mapped_column(Integer, default=0)
    bonus_cents: Mapped[int] = mapped_column(Integer, default=0)
    # Variable allowance, kept apart so the WPS variable column can include it. Also inside allowances_cents.
    variable_cents: Mapped[int] = mapped_column(Integer, default=0)
    recurring_deduction_cents: Mapped[int] = mapped_column(Integer, default=0)
    deductions_cents: Mapped[int] = mapped_column(Integer, default=0)
    unpaid_leave_days: Mapped[int] = mapped_column(Integer, default=0)
    gross_cents: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(String(255), default="")
    calculation_status: Mapped[str] = mapped_column(String(16), default="OK")
    # Component names, amounts, and the sources used. This is the auditable snapshot.
    breakdown: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    net_cents: Mapped[int] = mapped_column(Integer)


class PayrollApproval(TenantScoped, TimestampMixin, Base):
    """Who calculated, submitted, approved, returned, or cancelled a run."""

    __tablename__ = "payroll_approvals"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("payroll_runs.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(24))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    note: Mapped[str] = mapped_column(String(255), default="")


class PayrollPayment(TenantScoped, TimestampMixin, Base):
    """A recorded salary payment. Generating a WPS file does not create one of these."""

    __tablename__ = "payroll_payments"
    __table_args__ = (tenant_unique("run_id", "reference", name="uq_payroll_payment_reference"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("payroll_runs.id", ondelete="CASCADE"), index=True
    )
    amount_cents: Mapped[int] = mapped_column(Integer)
    reference: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(String(255), default="")
    recorded_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


class PayrollWpsExport(TenantScoped, TimestampMixin, Base):
    """Metadata for a generated SIF. The file itself is rebuilt from the payroll snapshot and is not stored."""

    __tablename__ = "payroll_wps_exports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("payroll_runs.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(40))
    filename: Mapped[str] = mapped_column(String(80))
    employee_count: Mapped[int] = mapped_column(Integer)
    total_cents: Mapped[int] = mapped_column(Integer)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
