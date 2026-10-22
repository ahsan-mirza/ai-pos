"""Purchase import wizard and FIFO batch inventory: suppliers, mapping templates, purchase batches, batch items,
batch allocations, and batch links on sale items and serial numbers.

Revision ID: 20261019_0011
Revises: 20261019_0010
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0011"
down_revision: str | None = "20261019_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "suppliers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("contact_name", sa.String(length=120), nullable=True),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_suppliers"),
        sa.UniqueConstraint("name", name="uq_suppliers_name"),
        sa.UniqueConstraint("code", name="uq_suppliers_code"),
    )
    op.create_table(
        "import_mapping_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=True),
        sa.Column("mapping", sa.JSON(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["suppliers.id"],
            name="fk_import_mapping_templates_supplier_id_suppliers",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], name="fk_import_mapping_templates_created_by_id_users"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_import_mapping_templates"),
        sa.UniqueConstraint("supplier_id", "name", name="uq_import_mapping_templates_supplier_name"),
    )
    op.create_index("ix_import_mapping_templates_supplier_id", "import_mapping_templates", ["supplier_id"])
    op.create_table(
        "purchase_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("batch_number", sa.String(length=32), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=True),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("import_source", sa.String(length=16), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=True),
        sa.Column("file_url", sa.String(length=255), nullable=True),
        sa.Column("mapping_template_used", sa.JSON(), nullable=True),
        sa.Column("total_cost_amount", sa.Integer(), nullable=False),
        sa.Column("total_items_count", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("reversal_reason", sa.Text(), nullable=True),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reversed_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("total_cost_amount >= 0", name="ck_purchase_batches_total_cost_nonnegative"),
        sa.CheckConstraint("total_items_count >= 0", name="ck_purchase_batches_total_items_nonnegative"),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], name="fk_purchase_batches_supplier_id_suppliers"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], name="fk_purchase_batches_store_id_stores"),
        sa.ForeignKeyConstraint(["reversed_by_id"], ["users.id"], name="fk_purchase_batches_reversed_by_id_users"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name="fk_purchase_batches_created_by_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_purchase_batches"),
        sa.UniqueConstraint("batch_number", name="uq_purchase_batches_batch_number"),
    )
    op.create_index("ix_purchase_batches_supplier_id", "purchase_batches", ["supplier_id"])
    op.create_index("ix_purchase_batches_store_id", "purchase_batches", ["store_id"])
    op.create_index("ix_purchase_batches_status", "purchase_batches", ["status"])
    op.create_index("ix_purchase_batches_created_at", "purchase_batches", ["created_at"])
    op.create_index("ix_purchase_batches_store_created", "purchase_batches", ["store_id", "created_at"])
    op.create_table(
        "batch_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("quantity_imported", sa.Integer(), nullable=False),
        sa.Column("quantity_remaining", sa.Integer(), nullable=False),
        sa.Column("purchase_cost_per_unit", sa.Integer(), nullable=False),
        sa.Column("selling_price_per_unit", sa.Integer(), nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("imported_serials", sa.JSON(), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity_imported >= 0", name="ck_batch_items_imported_nonnegative"),
        sa.CheckConstraint("quantity_remaining >= 0", name="ck_batch_items_remaining_nonnegative"),
        sa.CheckConstraint("quantity_remaining <= quantity_imported", name="ck_batch_items_remaining_within_imported"),
        sa.CheckConstraint("purchase_cost_per_unit >= 0", name="ck_batch_items_cost_nonnegative"),
        sa.CheckConstraint("selling_price_per_unit >= 0", name="ck_batch_items_price_nonnegative"),
        sa.ForeignKeyConstraint(
            ["batch_id"], ["purchase_batches.id"], name="fk_batch_items_batch_id_purchase_batches", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_batch_items_product_id_products"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], name="fk_batch_items_store_id_stores"),
        sa.PrimaryKeyConstraint("id", name="pk_batch_items"),
    )
    op.create_index("ix_batch_items_batch_id", "batch_items", ["batch_id"])
    op.create_index("ix_batch_items_product_id", "batch_items", ["product_id"])
    op.create_index("ix_batch_items_store_id", "batch_items", ["store_id"])
    op.create_index(
        "ix_batch_items_fifo", "batch_items", ["product_id", "store_id", "quantity_remaining", "created_at"]
    )
    op.create_table(
        "batch_allocations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("batch_item_id", sa.Uuid(), nullable=False),
        sa.Column("stock_movement_id", sa.Uuid(), nullable=False),
        sa.Column("sale_item_id", sa.Uuid(), nullable=True),
        sa.Column("movement_type", sa.String(length=24), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("quantity_returned", sa.Integer(), nullable=False),
        sa.Column("unit_cost_cents", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity >= 1", name="ck_batch_allocations_quantity_positive"),
        sa.CheckConstraint("quantity_returned >= 0", name="ck_batch_allocations_returned_nonnegative"),
        sa.CheckConstraint("quantity_returned <= quantity", name="ck_batch_allocations_returned_within_quantity"),
        sa.ForeignKeyConstraint(
            ["batch_item_id"],
            ["batch_items.id"],
            name="fk_batch_allocations_batch_item_id_batch_items",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["stock_movement_id"],
            ["stock_movements.id"],
            name="fk_batch_allocations_stock_movement_id_stock_movements",
        ),
        sa.ForeignKeyConstraint(
            ["sale_item_id"], ["sale_items.id"], name="fk_batch_allocations_sale_item_id_sale_items"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_batch_allocations"),
    )
    op.create_index("ix_batch_allocations_batch_item_id", "batch_allocations", ["batch_item_id"])
    op.create_index("ix_batch_allocations_stock_movement_id", "batch_allocations", ["stock_movement_id"])
    op.create_index("ix_batch_allocations_sale_item_id", "batch_allocations", ["sale_item_id"])
    with op.batch_alter_table("sale_items") as batch:
        batch.add_column(sa.Column("batch_item_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_sale_items_batch_item_id_batch_items",
            "batch_items",
            ["batch_item_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_sale_items_batch_item_id", ["batch_item_id"])
    with op.batch_alter_table("serial_numbers") as batch:
        batch.add_column(sa.Column("batch_item_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_serial_numbers_batch_item_id_batch_items",
            "batch_items",
            ["batch_item_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_serial_numbers_batch_item_id", ["batch_item_id"])


def downgrade() -> None:
    with op.batch_alter_table("serial_numbers") as batch:
        batch.drop_index("ix_serial_numbers_batch_item_id")
        batch.drop_constraint("fk_serial_numbers_batch_item_id_batch_items", type_="foreignkey")
        batch.drop_column("batch_item_id")
    with op.batch_alter_table("sale_items") as batch:
        batch.drop_index("ix_sale_items_batch_item_id")
        batch.drop_constraint("fk_sale_items_batch_item_id_batch_items", type_="foreignkey")
        batch.drop_column("batch_item_id")
    op.drop_table("batch_allocations")
    op.drop_table("batch_items")
    op.drop_table("purchase_batches")
    op.drop_table("import_mapping_templates")
    op.drop_table("suppliers")
