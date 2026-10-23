"""Commercial catalog: packages, cycles, add-ons, subscriptions and checkout invoices.

Revision ID: control_0008
Revises: control_0007
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "control_0008"
down_revision: str | None = "control_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("practice_mode", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "billing_plans",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("included_registers", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("included_modules", sa.JSON(), nullable=False),
        sa.Column("monthly_fils", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trial_days", sa.Integer(), nullable=False, server_default="14"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "billing_cycles",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("months", sa.Integer(), nullable=False),
        sa.Column("discount_bps", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "billing_addons",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("monthly_fils", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("one_time_fils", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("refundable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "billing_fees",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("amount_fils", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, unique=True),
        sa.Column("plan_id", sa.Uuid(as_uuid=True), sa.ForeignKey("billing_plans.id"), nullable=False),
        sa.Column("cycle_id", sa.Uuid(as_uuid=True), sa.ForeignKey("billing_cycles.id"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="trialing"),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stripe_customer_id", sa.String(64), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "subscription_items",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("subscription_id", sa.Uuid(as_uuid=True), sa.ForeignKey("subscriptions.id"), nullable=False),
        sa.Column("addon_code", sa.String(32), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index("ix_subscription_items_subscription_id", "subscription_items", ["subscription_id"])
    op.create_table(
        "billing_invoices",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("subscription_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="AED"),
        sa.Column("plan_code", sa.String(32), nullable=False),
        sa.Column("cycle_code", sa.String(32), nullable=False),
        sa.Column("recurring_fils", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("one_time_fils", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_fils", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("purge", sa.String(16), nullable=False, server_default="keep"),
        sa.Column("opening_stock", sa.String(16), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("confirm_name", sa.String(120), nullable=False),
        sa.Column("stripe_session_id", sa.String(80), nullable=True, unique=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_billing_invoices_tenant_id", "billing_invoices", ["tenant_id"])
    op.create_index("ix_billing_invoices_status", "billing_invoices", ["status"])
    op.create_table(
        "billing_invoice_lines",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("invoice_id", sa.Uuid(as_uuid=True), sa.ForeignKey("billing_invoices.id"), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("unit_fils", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("amount_fils", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recurring", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("refundable", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_billing_invoice_lines_invoice_id", "billing_invoice_lines", ["invoice_id"])


def downgrade() -> None:
    op.drop_index("ix_billing_invoice_lines_invoice_id", table_name="billing_invoice_lines")
    op.drop_table("billing_invoice_lines")
    op.drop_index("ix_billing_invoices_status", table_name="billing_invoices")
    op.drop_index("ix_billing_invoices_tenant_id", table_name="billing_invoices")
    op.drop_table("billing_invoices")
    op.drop_index("ix_subscription_items_subscription_id", table_name="subscription_items")
    op.drop_table("subscription_items")
    op.drop_table("subscriptions")
    op.drop_table("billing_fees")
    op.drop_table("billing_addons")
    op.drop_table("billing_cycles")
    op.drop_table("billing_plans")
    op.drop_column("tenants", "practice_mode")
