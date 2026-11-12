"""Salary versions, payroll lifecycle, encrypted IBANs, and WPS export metadata.

Revision ID: 20261112_0108
Revises: 20261112_0107
Create Date: 2026-11-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261112_0108"
down_revision: str | None = "20261112_0107"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    # The migration smoke test stamps a stub database that has not created payroll tables.
    if "employee_profiles" not in _tables() or "payroll_runs" not in _tables():
        return
    _profile_columns()
    _run_columns()
    _line_columns()
    _drop_period_unique()
    _open_period_indexes()
    _salary_versions()
    _approvals()
    _payments()
    _exports()


def _profile_columns() -> None:
    op.add_column("employee_profiles", sa.Column("employment_type", sa.String(24), nullable=False, server_default=""))
    op.add_column("employee_profiles", sa.Column("bank_name", sa.String(80), nullable=False, server_default=""))
    op.add_column("employee_profiles", sa.Column("account_holder", sa.String(80), nullable=False, server_default=""))
    op.add_column("employee_profiles", sa.Column("iban_encrypted", sa.Text(), nullable=False, server_default=""))
    op.add_column("employee_profiles", sa.Column("iban_last4", sa.String(4), nullable=False, server_default=""))
    op.add_column(
        "employee_profiles", sa.Column("food_allowance_cents", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "employee_profiles", sa.Column("variable_allowance_cents", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "employee_profiles", sa.Column("recurring_deduction_cents", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("employee_profiles", sa.Column("components", sa.JSON(), nullable=True))
    op.add_column(
        "employee_profiles", sa.Column("overtime_eligible", sa.Boolean(), nullable=False, server_default=sa.true())
    )
    op.add_column(
        "employee_profiles", sa.Column("commission_eligible", sa.Boolean(), nullable=False, server_default=sa.true())
    )
    op.add_column(
        "employee_profiles", sa.Column("salary_frequency", sa.String(12), nullable=False, server_default="MONTHLY")
    )
    op.add_column(
        "employee_profiles", sa.Column("profile_status", sa.String(12), nullable=False, server_default="ACTIVE")
    )
    op.add_column("employee_profiles", sa.Column("effective_from", sa.Date(), nullable=True))
    op.alter_column("employee_profiles", "iban", existing_type=sa.String(23), type_=sa.Text(), existing_nullable=False)


def _run_columns() -> None:
    op.add_column(
        "payroll_runs", sa.Column("store_id", sa.Uuid(as_uuid=True), sa.ForeignKey("stores.id"), nullable=True)
    )
    op.alter_column("payroll_runs", "status", existing_type=sa.String(10), type_=sa.String(24), existing_nullable=False)
    op.add_column("payroll_runs", sa.Column("payment_status", sa.String(20), nullable=False, server_default="NONE"))
    op.add_column("payroll_runs", sa.Column("exceptions", sa.JSON(), nullable=True))
    op.add_column("payroll_runs", sa.Column("rejection_note", sa.String(255), nullable=False, server_default=""))
    op.add_column(
        "payroll_runs", sa.Column("submitted_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True)
    )
    op.add_column("payroll_runs", sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("payroll_runs", sa.Column("wps_generated_at", sa.DateTime(timezone=True), nullable=True))


def _line_columns() -> None:
    op.add_column("payroll_lines", sa.Column("variable_cents", sa.Integer(), nullable=False, server_default="0"))
    op.add_column(
        "payroll_lines", sa.Column("recurring_deduction_cents", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("payroll_lines", sa.Column("gross_cents", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("payroll_lines", sa.Column("calculation_status", sa.String(16), nullable=False, server_default="OK"))
    op.add_column("payroll_lines", sa.Column("breakdown", sa.JSON(), nullable=True))


def _drop_period_unique() -> None:
    inspector = sa.inspect(op.get_bind())
    for constraint in inspector.get_unique_constraints("payroll_runs"):
        cols = tuple(constraint.get("column_names") or ())
        name = constraint.get("name")
        if name and cols in {("year", "month"), ("tenant_id", "year", "month")}:
            op.drop_constraint(name, "payroll_runs", type_="unique")


def _open_period_indexes() -> None:
    op.create_index(
        "uq_payroll_runs_all_branches",
        "payroll_runs",
        ["tenant_id", "year", "month"],
        unique=True,
        sqlite_where=sa.and_(sa.column("status") != "CANCELLED", sa.column("store_id").is_(None)),
        postgresql_where=sa.and_(sa.column("status") != "CANCELLED", sa.column("store_id").is_(None)),
    )
    op.create_index(
        "uq_payroll_runs_one_branch",
        "payroll_runs",
        ["tenant_id", "year", "month", "store_id"],
        unique=True,
        sqlite_where=sa.and_(sa.column("status") != "CANCELLED", sa.column("store_id").is_not(None)),
        postgresql_where=sa.and_(sa.column("status") != "CANCELLED", sa.column("store_id").is_not(None)),
    )


def _salary_versions() -> None:
    op.create_table(
        "employee_salary_versions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "profile_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("employee_profiles.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("status", sa.String(12), nullable=False, server_default="ACTIVE"),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("tenant_id", "profile_id", "effective_from", name="uq_salary_version_effective"),
    )


def _approvals() -> None:
    op.create_table(
        "payroll_approvals",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "run_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("payroll_runs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("action", sa.String(24), nullable=False),
        sa.Column("actor_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("note", sa.String(255), nullable=False, server_default=""),
        *_timestamps(),
    )


def _payments() -> None:
    op.create_table(
        "payroll_payments",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "run_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("payroll_runs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("reference", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("note", sa.String(255), nullable=False, server_default=""),
        sa.Column("recorded_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("tenant_id", "run_id", "reference", name="uq_payroll_payment_reference"),
    )


def _exports() -> None:
    op.create_table(
        "payroll_wps_exports",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "run_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("payroll_runs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("filename", sa.String(80), nullable=False),
        sa.Column("employee_count", sa.Integer(), nullable=False),
        sa.Column("total_cents", sa.Integer(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        *_timestamps(),
    )


def downgrade() -> None:
    if "employee_profiles" not in _tables():
        return
    op.drop_table("payroll_wps_exports")
    op.drop_table("payroll_payments")
    op.drop_table("payroll_approvals")
    op.drop_table("employee_salary_versions")
    op.drop_index("uq_payroll_runs_one_branch", table_name="payroll_runs")
    op.drop_index("uq_payroll_runs_all_branches", table_name="payroll_runs")
    op.create_unique_constraint("uq_payroll_runs_period", "payroll_runs", ["tenant_id", "year", "month"])
    op.drop_column("payroll_lines", "breakdown")
    op.drop_column("payroll_lines", "calculation_status")
    op.drop_column("payroll_lines", "gross_cents")
    op.drop_column("payroll_lines", "recurring_deduction_cents")
    op.drop_column("payroll_lines", "variable_cents")
    op.drop_column("payroll_runs", "wps_generated_at")
    op.drop_column("payroll_runs", "submitted_at")
    op.drop_column("payroll_runs", "submitted_by_id")
    op.drop_column("payroll_runs", "rejection_note")
    op.drop_column("payroll_runs", "exceptions")
    op.drop_column("payroll_runs", "payment_status")
    op.alter_column("payroll_runs", "status", existing_type=sa.String(24), type_=sa.String(10), existing_nullable=False)
    op.drop_column("payroll_runs", "store_id")
    op.alter_column("employee_profiles", "iban", existing_type=sa.Text(), type_=sa.String(23), existing_nullable=False)
    op.drop_column("employee_profiles", "effective_from")
    op.drop_column("employee_profiles", "profile_status")
    op.drop_column("employee_profiles", "salary_frequency")
    op.drop_column("employee_profiles", "commission_eligible")
    op.drop_column("employee_profiles", "overtime_eligible")
    op.drop_column("employee_profiles", "components")
    op.drop_column("employee_profiles", "recurring_deduction_cents")
    op.drop_column("employee_profiles", "variable_allowance_cents")
    op.drop_column("employee_profiles", "food_allowance_cents")
    op.drop_column("employee_profiles", "iban_last4")
    op.drop_column("employee_profiles", "iban_encrypted")
    op.drop_column("employee_profiles", "account_holder")
    op.drop_column("employee_profiles", "bank_name")
    op.drop_column("employee_profiles", "employment_type")
