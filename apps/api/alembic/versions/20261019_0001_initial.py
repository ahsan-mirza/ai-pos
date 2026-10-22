"""Initial POS schema.

Revision ID: 20261019_0001
Revises:
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stores",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("code", name="uq_stores_code"),
    )
    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("barcode", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("is_serialized", sa.Boolean(), nullable=False),
        sa.Column("stock_quantity", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("price_cents >= 0", name="ck_products_price_nonnegative"),
        sa.CheckConstraint("stock_quantity >= 0", name="ck_products_stock_nonnegative"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], name="fk_products_store_id_stores"),
        sa.UniqueConstraint("sku", name="uq_products_sku"),
        sa.UniqueConstraint("barcode", name="uq_products_barcode"),
    )
    op.create_index("ix_products_store_id", "products", ["store_id"])
    op.create_index("ix_products_category", "products", ["category"])
    op.create_table(
        "serial_numbers",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("product_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("store_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("value_hash", sa.String(length=64), nullable=False),
        sa.Column("value_encrypted", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_serial_numbers_product_id_products"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], name="fk_serial_numbers_store_id_stores"),
        sa.UniqueConstraint("value_hash", name="uq_serial_numbers_value_hash"),
    )
    op.create_index("ix_serial_numbers_product_id", "serial_numbers", ["product_id"])
    op.create_index("ix_serial_numbers_store_id", "serial_numbers", ["store_id"])
    op.create_index("ix_serial_numbers_status", "serial_numbers", ["status"])
    op.create_table(
        "sales",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("cashier_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("payment_method", sa.String(length=32), nullable=False),
        sa.Column("subtotal_cents", sa.Integer(), nullable=False),
        sa.Column("tax_cents", sa.Integer(), nullable=False),
        sa.Column("total_cents", sa.Integer(), nullable=False),
        sa.Column("client_sale_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("subtotal_cents >= 0", name="ck_sales_subtotal_nonnegative"),
        sa.CheckConstraint("tax_cents >= 0", name="ck_sales_tax_nonnegative"),
        sa.CheckConstraint("total_cents >= 0", name="ck_sales_total_nonnegative"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], name="fk_sales_store_id_stores"),
        sa.UniqueConstraint("client_sale_id", name="uq_sales_client_sale_id"),
    )
    op.create_index("ix_sales_store_id", "sales", ["store_id"])
    op.create_index("ix_sales_status", "sales", ["status"])
    op.create_index("ix_sales_currency", "sales", ["currency"])
    op.create_index("ix_sales_created_at", "sales", ["created_at"])
    op.create_table(
        "sale_items",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("sale_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("serial_number_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price_cents", sa.Integer(), nullable=False),
        sa.Column("tax_cents", sa.Integer(), nullable=False),
        sa.Column("line_total_cents", sa.Integer(), nullable=False),
        sa.CheckConstraint("quantity >= 1", name="ck_sale_items_quantity_positive"),
        sa.CheckConstraint("unit_price_cents >= 0", name="ck_sale_items_unit_price_nonnegative"),
        sa.CheckConstraint("tax_cents >= 0", name="ck_sale_items_tax_nonnegative"),
        sa.CheckConstraint("line_total_cents >= 0", name="ck_sale_items_line_total_nonnegative"),
        sa.ForeignKeyConstraint(["sale_id"], ["sales.id"], name="fk_sale_items_sale_id_sales"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_sale_items_product_id_products"),
        sa.ForeignKeyConstraint(
            ["serial_number_id"],
            ["serial_numbers.id"],
            name="fk_sale_items_serial_number_id_serial_numbers",
        ),
    )
    op.create_index("ix_sale_items_sale_id", "sale_items", ["sale_id"])
    op.create_index("ix_sale_items_product_id", "sale_items", ["product_id"])
    op.create_table(
        "repair_tickets",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("customer_name", sa.String(length=120), nullable=False),
        sa.Column("customer_phone", sa.String(length=40), nullable=False),
        sa.Column("device_model", sa.String(length=120), nullable=False),
        sa.Column("identifier_kind", sa.String(length=16), nullable=False),
        sa.Column("identifier_hash", sa.String(length=64), nullable=False),
        sa.Column("identifier_encrypted", sa.Text(), nullable=False),
        sa.Column("issue", sa.String(length=2000), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("estimated_cost_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("estimated_cost_cents >= 0", name="ck_repair_tickets_estimate_nonnegative"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], name="fk_repair_tickets_store_id_stores"),
    )
    op.create_index("ix_repair_tickets_store_id", "repair_tickets", ["store_id"])
    op.create_index("ix_repair_tickets_status", "repair_tickets", ["status"])
    op.create_table(
        "sync_events",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_sync_events_idempotency_key"),
    )
    op.create_index("ix_sync_events_device_id", "sync_events", ["device_id"])


def downgrade() -> None:
    op.drop_table("sync_events")
    op.drop_table("repair_tickets")
    op.drop_table("sale_items")
    op.drop_table("sales")
    op.drop_table("serial_numbers")
    op.drop_table("products")
    op.drop_table("stores")
