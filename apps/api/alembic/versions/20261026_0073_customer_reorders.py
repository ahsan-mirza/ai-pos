"""Customer reorder plans and the reminders they produce.

Revision ID: 20261026_0073
Revises: 20261025_0072
Create Date: 2026-10-26

A plan belongs to one customer. An occurrence is one scheduled date for that plan.
The unique key stops a second worker, or a retry, from opening the same reminder twice.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261026_0073"
down_revision: str | None = "20261025_0072"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POLICY = (
    "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid "
    "OR current_setting('app.bypass_rls', true) = 'on') "
    "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid "
    "OR current_setting('app.bypass_rls', true) = 'on')"
)


def _rls(table: str) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'CREATE POLICY tenant_isolation ON "{table}" {POLICY}'))


def upgrade() -> None:
    op.create_table(
        "customer_reorder_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("frequency", sa.String(16), nullable=False),
        sa.Column("weekdays", sa.JSON(), nullable=True),
        sa.Column("month_day", sa.Integer(), nullable=True),
        sa.Column("start_on", sa.Date(), nullable=False),
        sa.Column("end_on", sa.Date(), nullable=True),
        sa.Column("next_on", sa.Date(), nullable=True),
        sa.Column("preferred_time", sa.String(5), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("lead_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fulfillment", sa.String(16), nullable=False, server_default="DELIVERY"),
        sa.Column("delivery_address", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("salesperson_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("store_id", sa.Uuid(), sa.ForeignKey("stores.id"), nullable=True),
        sa.Column("notify_customer", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_customer_reorder_plans"),
    )
    op.create_index("ix_customer_reorder_plans_tenant_id", "customer_reorder_plans", ["tenant_id"])
    op.create_index("ix_customer_reorder_plans_customer_id", "customer_reorder_plans", ["customer_id"])
    op.create_index("ix_customer_reorder_plans_status", "customer_reorder_plans", ["status"])
    op.create_index("ix_reorder_plans_due", "customer_reorder_plans", ["tenant_id", "status", "next_on"])
    op.create_index("ix_reorder_plans_customer", "customer_reorder_plans", ["tenant_id", "customer_id"])
    _rls("customer_reorder_plans")

    op.create_table(
        "customer_reorder_plan_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column(
            "plan_id",
            sa.Uuid(),
            sa.ForeignKey("customer_reorder_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("product_id", sa.Uuid(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("note", sa.String(160), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id", name="pk_customer_reorder_plan_items"),
    )
    op.create_index("ix_customer_reorder_plan_items_tenant_id", "customer_reorder_plan_items", ["tenant_id"])
    op.create_index("ix_customer_reorder_plan_items_plan_id", "customer_reorder_plan_items", ["plan_id"])
    op.create_index("ix_customer_reorder_plan_items_product_id", "customer_reorder_plan_items", ["product_id"])
    op.create_index("ix_reorder_items_plan", "customer_reorder_plan_items", ["tenant_id", "plan_id"])
    _rls("customer_reorder_plan_items")

    op.create_table(
        "customer_reorder_occurrences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), sa.ForeignKey("customer_reorder_plans.id"), nullable=False),
        sa.Column("scheduled_on", sa.Date(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("sales_order_id", sa.Uuid(), sa.ForeignKey("sales_orders.id"), nullable=True),
        sa.Column("notification_status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("notification_error", sa.String(255), nullable=True),
        sa.Column("stock_note", sa.String(500), nullable=False, server_default=""),
        sa.Column("snooze_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("skip_reason", sa.String(160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_customer_reorder_occurrences"),
        sa.UniqueConstraint("tenant_id", "plan_id", "scheduled_on", name="uq_reorder_occurrences_plan_day"),
    )
    op.create_index("ix_customer_reorder_occurrences_tenant_id", "customer_reorder_occurrences", ["tenant_id"])
    op.create_index("ix_customer_reorder_occurrences_plan_id", "customer_reorder_occurrences", ["plan_id"])
    op.create_index("ix_customer_reorder_occurrences_status", "customer_reorder_occurrences", ["status"])
    op.create_index(
        "ix_reorder_occurrences_due", "customer_reorder_occurrences", ["tenant_id", "status", "scheduled_on"]
    )
    op.create_index("ix_reorder_occurrences_order", "customer_reorder_occurrences", ["tenant_id", "sales_order_id"])
    _rls("customer_reorder_occurrences")


def downgrade() -> None:
    op.drop_table("customer_reorder_occurrences")
    op.drop_table("customer_reorder_plan_items")
    op.drop_table("customer_reorder_plans")
