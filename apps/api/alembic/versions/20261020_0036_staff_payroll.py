"""Commission rules, employee payroll profiles, payroll runs, and WPS employer settings.

Revision ID: 20261020_0036
Revises: 20261020_0035
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261020_0036"
down_revision: str | None = "20261020_0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.add_column("business_settings", sa.Column("payroll", sa.JSON(), nullable=True))
    op.create_table(
        "commission_rules",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("basis", sa.String(12), nullable=False),
        sa.Column("rate_bps", sa.Integer(), nullable=False),
        sa.Column("category_ids", sa.JSON(), nullable=False),
        sa.Column("role_ids", sa.JSON(), nullable=False),
        sa.Column("threshold_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
        sa.CheckConstraint("rate_bps >= 0 AND rate_bps <= 10000", name="commission_rate_range"),
    )
    op.create_table(
        "employee_profiles",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("employee_code", sa.String(20), nullable=False),
        sa.Column("labour_id", sa.String(14), nullable=False),
        sa.Column("bank_routing_code", sa.String(9), nullable=False),
        sa.Column("iban", sa.String(23), nullable=False),
        sa.Column("basic_salary_cents", sa.Integer(), nullable=False),
        sa.Column("housing_allowance_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("transport_allowance_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("other_allowance_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("overtime_rate_pct", sa.Integer(), nullable=False, server_default="125"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
    )
    op.create_table(
        "payroll_runs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="DRAFT"),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("finalized_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("year", "month", name="uq_payroll_runs_period"),
    )
    op.create_table(
        "payroll_lines",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id", sa.Uuid(as_uuid=True), sa.ForeignKey("payroll_runs.id", ondelete="CASCADE"), nullable=False, index=True
        ),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("employee_code", sa.String(20), nullable=False),
        sa.Column("basic_cents", sa.Integer(), nullable=False),
        sa.Column("allowances_cents", sa.Integer(), nullable=False),
        sa.Column("overtime_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("overtime_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("commission_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bonus_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deductions_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unpaid_leave_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("note", sa.String(255), nullable=False, server_default=""),
        sa.Column("net_cents", sa.Integer(), nullable=False),
        sa.UniqueConstraint("run_id", "user_id", name="uq_payroll_lines_run_user"),
    )


def downgrade() -> None:
    op.drop_table("payroll_lines")
    op.drop_table("payroll_runs")
    op.drop_table("employee_profiles")
    op.drop_table("commission_rules")
    op.drop_column("business_settings", "payroll")
