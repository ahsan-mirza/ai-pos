"""Demand history, seasonal events, replenishment runs and suggestions; supplier lead times; PO supplier link.

Revision ID: 20261019_0020
Revises: 20261019_0019
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0020"
down_revision: str | None = "20261019_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("suppliers", sa.Column("lead_time_days", sa.Integer(), nullable=False, server_default="7"))
    op.add_column(
        "purchase_orders", sa.Column("supplier_id", sa.Uuid(as_uuid=True), sa.ForeignKey("suppliers.id"), nullable=True)
    )
    op.create_index("ix_purchase_orders_supplier_id", "purchase_orders", ["supplier_id"])
    op.create_table(
        "demand_daily",
        sa.Column("product_id", sa.Uuid(as_uuid=True), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("store_id", sa.Uuid(as_uuid=True), sa.ForeignKey("stores.id"), nullable=False, index=True),
        sa.Column("day", sa.Date(), nullable=False, index=True),
        sa.Column("units", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("product_id", "store_id", "day", name="pk_demand_daily"),
    )
    op.create_table(
        "seasonal_events",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("uplift_bps", sa.Integer(), nullable=False, server_default="10000"),
        sa.Column("category_id", sa.Uuid(as_uuid=True), sa.ForeignKey("categories.id"), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("uplift_bps >= 0 AND uplift_bps <= 100000", name="uplift_range"),
    )
    op.create_table(
        "replenishment_runs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.Uuid(as_uuid=True), sa.ForeignKey("stores.id"), nullable=False, index=True),
        sa.Column("review_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
    )
    op.create_table(
        "replenishment_suggestions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("run_id", sa.Uuid(as_uuid=True), sa.ForeignKey("replenishment_runs.id"), nullable=False, index=True),
        sa.Column("product_id", sa.Uuid(as_uuid=True), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("store_id", sa.Uuid(as_uuid=True), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("source", sa.String(12), nullable=False),
        sa.Column("supplier_id", sa.Uuid(as_uuid=True), sa.ForeignKey("suppliers.id"), nullable=True),
        sa.Column("supplier_name", sa.String(120), nullable=True),
        sa.Column("from_store_id", sa.Uuid(as_uuid=True), sa.ForeignKey("stores.id"), nullable=True),
        sa.Column("on_hand", sa.Integer(), nullable=False),
        sa.Column("on_order", sa.Integer(), nullable=False),
        sa.Column("daily_rate_milli", sa.Integer(), nullable=False),
        sa.Column("lead_time_days", sa.Integer(), nullable=False),
        sa.Column("forecast_units", sa.Integer(), nullable=False),
        sa.Column("safety_stock", sa.Integer(), nullable=False),
        sa.Column("suggested_qty", sa.Integer(), nullable=False),
        sa.Column("unit_cost_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("seasonal_note", sa.String(160), nullable=True),
        sa.Column("status", sa.String(12), nullable=False, server_default="PENDING", index=True),
        sa.Column("purchase_order_id", sa.Uuid(as_uuid=True), sa.ForeignKey("purchase_orders.id"), nullable=True),
        sa.Column("transfer_id", sa.Uuid(as_uuid=True), sa.ForeignKey("stock_transfers.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("replenishment_suggestions")
    op.drop_table("replenishment_runs")
    op.drop_table("seasonal_events")
    op.drop_table("demand_daily")
    op.drop_index("ix_purchase_orders_supplier_id", table_name="purchase_orders")
    op.drop_column("purchase_orders", "supplier_id")
    op.drop_column("suppliers", "lead_time_days")
