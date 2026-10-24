from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Uuid
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
    """Payroll details for a staff member. Amounts are monthly, in the business currency."""

    __tablename__ = "employee_profiles"
    __table_args__ = (
        tenant_unique("user_id", name="uq_employee_profiles_user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    employee_code: Mapped[str] = mapped_column(String(20))
    # MOHRE personal number (14 digits) used as the WPS employee ID.
    labour_id: Mapped[str] = mapped_column(String(14))
    # Routing code of the employee's bank (9 digits) and their IBAN.
    bank_routing_code: Mapped[str] = mapped_column(String(9))
    iban: Mapped[str] = mapped_column(String(23))
    basic_salary_cents: Mapped[int] = mapped_column(Integer)
    housing_allowance_cents: Mapped[int] = mapped_column(Integer, default=0)
    transport_allowance_cents: Mapped[int] = mapped_column(Integer, default=0)
    other_allowance_cents: Mapped[int] = mapped_column(Integer, default=0)
    # Overtime pay as a percentage of the hourly basic rate (UAE minimum is 125%).
    overtime_rate_pct: Mapped[int] = mapped_column(Integer, default=125)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PayrollRun(TenantScoped, TimestampMixin, Base):
    """One month's payroll. DRAFT lines can be adjusted; FINALIZED runs are locked and exported to WPS."""

    __tablename__ = "payroll_runs"
    __table_args__ = (tenant_unique("year", "month", name="uq_payroll_runs_period"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(10), default="DRAFT")
    currency: Mapped[str] = mapped_column(String(3))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    finalized_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
    deductions_cents: Mapped[int] = mapped_column(Integer, default=0)
    unpaid_leave_days: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(String(255), default="")
    net_cents: Mapped[int] = mapped_column(Integer)
