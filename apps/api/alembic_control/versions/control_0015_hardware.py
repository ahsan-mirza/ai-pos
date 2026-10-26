"""Hardware catalogue, orders, and lease assignments.

Revision ID: control_0015
Revises: control_0014
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "control_0015"
down_revision: str | None = "control_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hardware_categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint("id", name="pk_hardware_categories"),
        sa.UniqueConstraint("name", name="uq_hardware_categories_name"),
    )
    op.create_table(
        "hardware_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sku", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("image_url", sa.String(length=300), nullable=True),
        sa.Column("manufacturer", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("model", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("lease_available", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("purchase_available", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("monthly_fils", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deposit_fils", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fee_fils", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("purchase_fils", sa.Integer(), nullable=True),
        sa.Column("delivery_fils", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="AED"),
        sa.Column("min_qty", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_qty", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("stock_qty", sa.Integer(), nullable=True),
        sa.Column("counts_as_register", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("compatibility", sa.Text(), nullable=False, server_default=""),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("internal_notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["hardware_categories.id"], name="fk_hw_items_category"),
        sa.PrimaryKeyConstraint("id", name="pk_hardware_items"),
        sa.UniqueConstraint("sku", name="uq_hardware_items_sku"),
    )
    op.create_index("ix_hardware_items_category_id", "hardware_items", ["category_id"])
    op.create_table(
        "hardware_orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reference", sa.String(length=20), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=True),
        sa.Column("payment_status", sa.String(length=24), nullable=False, server_default="awaiting_payment"),
        sa.Column("fulfillment_status", sa.String(length=24), nullable=False, server_default="awaiting_payment"),
        sa.Column("monthly_fils", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deposit_fils", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("one_time_fils", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="AED"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("assigned_operator_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["invoice_id"], ["billing_invoices.id"], name="fk_hw_orders_invoice"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_hardware_orders_tenant_id_tenants"),
        sa.PrimaryKeyConstraint("id", name="pk_hardware_orders"),
        sa.UniqueConstraint("reference", name="uq_hardware_orders_reference"),
    )
    op.create_index("ix_hardware_orders_tenant_id", "hardware_orders", ["tenant_id"])
    op.create_index("ix_hardware_orders_invoice_id", "hardware_orders", ["invoice_id"])
    op.create_index("ix_hardware_orders_payment_status", "hardware_orders", ["payment_status"])
    op.create_index("ix_hardware_orders_fulfillment_status", "hardware_orders", ["fulfillment_status"])
    op.create_table(
        "hardware_order_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("sku", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=True),
        sa.Column("store_label", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("monthly_fils", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deposit_fils", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fee_fils", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("purchase_fils", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("delivery_fils", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fulfilled_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("serials", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["hardware_items.id"], name="fk_hw_lines_item"),
        sa.ForeignKeyConstraint(["order_id"], ["hardware_orders.id"], name="fk_hw_lines_order"),
        sa.PrimaryKeyConstraint("id", name="pk_hardware_order_lines"),
    )
    op.create_index("ix_hardware_order_lines_order_id", "hardware_order_lines", ["order_id"])
    op.create_index("ix_hardware_order_lines_item_id", "hardware_order_lines", ["item_id"])
    op.create_index("ix_hardware_order_lines_store_id", "hardware_order_lines", ["store_id"])
    op.create_table(
        "hardware_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("order_line_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=True),
        sa.Column("store_label", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("serial", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("monthly_fils", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deposit_fils", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("returned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("condition_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("deposit_decision", sa.String(length=24), nullable=False, server_default="held"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["item_id"], ["hardware_items.id"], name="fk_hw_assign_item"),
        sa.ForeignKeyConstraint(["order_line_id"], ["hardware_order_lines.id"], name="fk_hw_assign_line"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_hw_assign_tenant"),
        sa.PrimaryKeyConstraint("id", name="pk_hardware_assignments"),
    )
    op.create_index("ix_hardware_assignments_tenant_id", "hardware_assignments", ["tenant_id"])
    op.create_index("ix_hardware_assignments_order_line_id", "hardware_assignments", ["order_line_id"])
    op.create_index("ix_hardware_assignments_status", "hardware_assignments", ["status"])


def downgrade() -> None:
    op.drop_index("ix_hardware_assignments_status", table_name="hardware_assignments")
    op.drop_index("ix_hardware_assignments_order_line_id", table_name="hardware_assignments")
    op.drop_index("ix_hardware_assignments_tenant_id", table_name="hardware_assignments")
    op.drop_table("hardware_assignments")
    op.drop_index("ix_hardware_order_lines_store_id", table_name="hardware_order_lines")
    op.drop_index("ix_hardware_order_lines_item_id", table_name="hardware_order_lines")
    op.drop_index("ix_hardware_order_lines_order_id", table_name="hardware_order_lines")
    op.drop_table("hardware_order_lines")
    op.drop_index("ix_hardware_orders_fulfillment_status", table_name="hardware_orders")
    op.drop_index("ix_hardware_orders_payment_status", table_name="hardware_orders")
    op.drop_index("ix_hardware_orders_invoice_id", table_name="hardware_orders")
    op.drop_index("ix_hardware_orders_tenant_id", table_name="hardware_orders")
    op.drop_table("hardware_orders")
    op.drop_index("ix_hardware_items_category_id", table_name="hardware_items")
    op.drop_table("hardware_items")
    op.drop_table("hardware_categories")
