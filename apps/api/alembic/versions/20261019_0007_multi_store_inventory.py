"""Categories, sub-categories, branch details, branch-isolated stock, movements, purchasing, transfers.

Products become a global catalog: products.store_id and products.stock_quantity move into inventory_levels
(one opening AUDIT_ADJUSTMENT per non-zero level) and are dropped.

Revision ID: 20261019_0007
Revises: 20261019_0006
Create Date: 2026-10-19
"""

import re
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0007"
down_revision: str | None = "20261019_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _code(name: str, taken: set[str]) -> str:
    base = "-".join(re.findall(r"[A-Za-z0-9]+", name.upper()))[:28] or "CAT"
    code, suffix = base, 2
    while code in taken:
        code = f"{base[:26]}-{suffix}"
        suffix += 1
    taken.add(code)
    return code


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.add_column("stores", sa.Column("address", sa.String(length=255), nullable=True))
    op.add_column("stores", sa.Column("phone", sa.String(length=40), nullable=True))
    op.add_column("stores", sa.Column("is_warehouse", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("stores", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))

    categories = op.create_table(
        "categories",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("name", name="uq_categories_name"),
        sa.UniqueConstraint("code", name="uq_categories_code"),
    )
    op.create_table(
        "sub_categories",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("category_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name="fk_sub_categories_category_id_categories",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("category_id", "name", name="uq_sub_categories_category_name"),
        sa.UniqueConstraint("category_id", "code", name="uq_sub_categories_category_code"),
    )
    op.create_index("ix_sub_categories_category_id", "sub_categories", ["category_id"])

    op.add_column("products", sa.Column("category_id", sa.Uuid(as_uuid=True), nullable=True))
    op.add_column("products", sa.Column("sub_category_id", sa.Uuid(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_products_category_id_categories", "products", "categories", ["category_id"], ["id"])
    op.create_foreign_key(
        "fk_products_sub_category_id_sub_categories", "products", "sub_categories", ["sub_category_id"], ["id"]
    )
    op.create_index("ix_products_category_id", "products", ["category_id"])
    op.create_index("ix_products_sub_category_id", "products", ["sub_category_id"])

    levels = op.create_table(
        "inventory_levels",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("product_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("store_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("quantity_on_hand", sa.Integer(), nullable=False),
        sa.Column("quantity_reserved", sa.Integer(), nullable=False),
        sa.Column("min_reorder_level", sa.Integer(), nullable=False),
        sa.Column("max_stock_level", sa.Integer(), nullable=True),
        sa.Column("aisle_shelf_location", sa.String(length=64), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_inventory_levels_product_id_products"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], name="fk_inventory_levels_store_id_stores"),
        sa.UniqueConstraint("product_id", "store_id", name="uq_inventory_levels_product_store"),
        sa.CheckConstraint("quantity_on_hand >= 0", name="ck_inventory_levels_on_hand_nonnegative"),
        sa.CheckConstraint("quantity_reserved >= 0", name="ck_inventory_levels_reserved_nonnegative"),
        sa.CheckConstraint("min_reorder_level >= 0", name="ck_inventory_levels_min_reorder_nonnegative"),
    )
    op.create_index("ix_inventory_levels_product_id", "inventory_levels", ["product_id"])
    op.create_index("ix_inventory_levels_store_id", "inventory_levels", ["store_id"])

    movements = op.create_table(
        "stock_movements",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("product_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("store_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("serial_number_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("movement_type", sa.String(length=24), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("quantity_after", sa.Integer(), nullable=False),
        sa.Column("reference_type", sa.String(length=32), nullable=False),
        sa.Column("reference_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("note", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_stock_movements_product_id_products"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], name="fk_stock_movements_store_id_stores"),
        sa.ForeignKeyConstraint(
            ["serial_number_id"],
            ["serial_numbers.id"],
            name="fk_stock_movements_serial_number_id_serial_numbers",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_stock_movements_user_id_users"),
        sa.CheckConstraint("quantity <> 0", name="ck_stock_movements_quantity_nonzero"),
    )
    for column in ("product_id", "store_id", "serial_number_id", "movement_type", "reference_id", "created_at"):
        op.create_index(f"ix_stock_movements_{column}", "stock_movements", [column])
    op.create_index(
        "ix_stock_movements_product_store_created", "stock_movements", ["product_id", "store_id", "created_at"]
    )

    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("number", sa.String(length=32), nullable=False),
        sa.Column("supplier_name", sa.String(length=120), nullable=False),
        sa.Column("destination_store_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("expected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ordered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["destination_store_id"], ["stores.id"], name="fk_purchase_orders_destination_store_id_stores"
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name="fk_purchase_orders_created_by_id_users"),
        sa.UniqueConstraint("number", name="uq_purchase_orders_number"),
    )
    op.create_index("ix_purchase_orders_destination_store_id", "purchase_orders", ["destination_store_id"])
    op.create_index("ix_purchase_orders_status", "purchase_orders", ["status"])
    op.create_table(
        "purchase_order_lines",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("purchase_order_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("quantity_ordered", sa.Integer(), nullable=False),
        sa.Column("quantity_received", sa.Integer(), nullable=False),
        sa.Column("unit_cost_cents", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["purchase_order_id"],
            ["purchase_orders.id"],
            name="fk_purchase_order_lines_purchase_order_id_purchase_orders",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_purchase_order_lines_product_id_products"),
        sa.CheckConstraint("quantity_ordered >= 1", name="ck_purchase_order_lines_ordered_positive"),
        sa.CheckConstraint("quantity_received >= 0", name="ck_purchase_order_lines_received_nonnegative"),
        sa.CheckConstraint(
            "quantity_received <= quantity_ordered", name="ck_purchase_order_lines_received_within_ordered"
        ),
        sa.CheckConstraint("unit_cost_cents >= 0", name="ck_purchase_order_lines_cost_nonnegative"),
    )
    op.create_index("ix_purchase_order_lines_purchase_order_id", "purchase_order_lines", ["purchase_order_id"])
    op.create_index("ix_purchase_order_lines_product_id", "purchase_order_lines", ["product_id"])
    op.create_table(
        "goods_receipts",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("number", sa.String(length=32), nullable=False),
        sa.Column("purchase_order_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("store_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("received_by_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("note", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["purchase_order_id"], ["purchase_orders.id"], name="fk_goods_receipts_purchase_order_id_purchase_orders"
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], name="fk_goods_receipts_store_id_stores"),
        sa.ForeignKeyConstraint(["received_by_id"], ["users.id"], name="fk_goods_receipts_received_by_id_users"),
        sa.UniqueConstraint("number", name="uq_goods_receipts_number"),
    )
    op.create_index("ix_goods_receipts_purchase_order_id", "goods_receipts", ["purchase_order_id"])
    op.create_index("ix_goods_receipts_store_id", "goods_receipts", ["store_id"])
    op.create_table(
        "goods_receipt_lines",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("goods_receipt_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("purchase_order_line_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["goods_receipt_id"],
            ["goods_receipts.id"],
            name="fk_goods_receipt_lines_goods_receipt_id_goods_receipts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["purchase_order_line_id"],
            ["purchase_order_lines.id"],
            name="fk_goods_receipt_lines_po_line_id",
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_goods_receipt_lines_product_id_products"),
        sa.CheckConstraint("quantity >= 1", name="ck_goods_receipt_lines_quantity_positive"),
    )
    op.create_index("ix_goods_receipt_lines_goods_receipt_id", "goods_receipt_lines", ["goods_receipt_id"])
    op.create_index("ix_goods_receipt_lines_purchase_order_line_id", "goods_receipt_lines", ["purchase_order_line_id"])

    op.create_table(
        "stock_transfers",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("number", sa.String(length=32), nullable=False),
        sa.Column("source_store_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("destination_store_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("note", sa.String(length=255), nullable=False),
        sa.Column("requested_by_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("shipped_by_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("received_by_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["source_store_id"], ["stores.id"], name="fk_stock_transfers_source_store_id_stores"),
        sa.ForeignKeyConstraint(
            ["destination_store_id"], ["stores.id"], name="fk_stock_transfers_destination_store_id_stores"
        ),
        sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"], name="fk_stock_transfers_requested_by_id_users"),
        sa.ForeignKeyConstraint(["shipped_by_id"], ["users.id"], name="fk_stock_transfers_shipped_by_id_users"),
        sa.ForeignKeyConstraint(["received_by_id"], ["users.id"], name="fk_stock_transfers_received_by_id_users"),
        sa.UniqueConstraint("number", name="uq_stock_transfers_number"),
        sa.CheckConstraint("source_store_id <> destination_store_id", name="ck_stock_transfers_distinct_stores"),
    )
    op.create_index("ix_stock_transfers_source_store_id", "stock_transfers", ["source_store_id"])
    op.create_index("ix_stock_transfers_destination_store_id", "stock_transfers", ["destination_store_id"])
    op.create_index("ix_stock_transfers_status", "stock_transfers", ["status"])
    op.create_table(
        "stock_transfer_lines",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("transfer_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["transfer_id"],
            ["stock_transfers.id"],
            name="fk_stock_transfer_lines_transfer_id_stock_transfers",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_stock_transfer_lines_product_id_products"),
        sa.CheckConstraint("quantity >= 1", name="ck_stock_transfer_lines_quantity_positive"),
    )
    op.create_index("ix_stock_transfer_lines_transfer_id", "stock_transfer_lines", ["transfer_id"])
    op.create_index("ix_stock_transfer_lines_product_id", "stock_transfer_lines", ["product_id"])
    op.create_table(
        "stock_transfer_serials",
        sa.Column("transfer_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("serial_number_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("transfer_line_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["transfer_id"],
            ["stock_transfers.id"],
            name="fk_stock_transfer_serials_transfer_id_stock_transfers",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["serial_number_id"],
            ["serial_numbers.id"],
            name="fk_stock_transfer_serials_serial_number_id_serial_numbers",
        ),
        sa.ForeignKeyConstraint(
            ["transfer_line_id"],
            ["stock_transfer_lines.id"],
            name="fk_stock_transfer_serials_transfer_line_id_stock_transfer_lines",
        ),
        sa.PrimaryKeyConstraint("transfer_id", "serial_number_id", name="pk_stock_transfer_serials"),
    )

    # --- Data: categories from product text, branch levels from product stock and in-stock serials ---
    bind = op.get_bind()
    now = datetime.now(UTC)
    names = [row[0] for row in bind.execute(sa.text("SELECT DISTINCT category FROM products ORDER BY category"))]
    taken: set[str] = set()
    category_ids: dict[str, uuid.UUID] = {}
    for name in names:
        category_ids[name] = uuid.uuid4()
        op.bulk_insert(
            categories,
            [
                {
                    "id": category_ids[name],
                    "name": name,
                    "code": _code(name, taken),
                    "description": "",
                    "created_at": now,
                    "updated_at": now,
                }
            ],
        )
        bind.execute(
            sa.text("UPDATE products SET category_id = :id WHERE category = :name"),
            {"id": category_ids[name], "name": name},
        )

    on_hand: dict[tuple[uuid.UUID, uuid.UUID], int] = {}
    for product_id, store_id, stock, serialized in bind.execute(
        sa.text("SELECT id, store_id, stock_quantity, is_serialized FROM products")
    ):
        on_hand[(product_id, store_id)] = 0 if serialized else int(stock)
    for product_id, store_id, count in bind.execute(
        sa.text(
            "SELECT s.product_id, s.store_id, COUNT(*) FROM serial_numbers s "
            "JOIN products p ON p.id = s.product_id "
            "WHERE s.status = 'in_stock' AND p.is_serialized GROUP BY s.product_id, s.store_id"
        )
    ):
        on_hand[(product_id, store_id)] = int(count)

    level_rows = []
    movement_rows = []
    for (product_id, store_id), quantity in on_hand.items():
        level_rows.append(
            {
                "id": uuid.uuid4(),
                "product_id": product_id,
                "store_id": store_id,
                "quantity_on_hand": quantity,
                "quantity_reserved": 0,
                "min_reorder_level": 0,
                "max_stock_level": None,
                "aisle_shelf_location": None,
                "created_at": now,
                "updated_at": now,
            }
        )
        if quantity:
            movement_rows.append(
                {
                    "id": uuid.uuid4(),
                    "product_id": product_id,
                    "store_id": store_id,
                    "serial_number_id": None,
                    "movement_type": "AUDIT_ADJUSTMENT",
                    "quantity": quantity,
                    "quantity_after": quantity,
                    "reference_type": "opening_balance",
                    "reference_id": None,
                    "user_id": None,
                    "note": "Opening balance migrated from products.stock_quantity",
                    "created_at": now,
                }
            )
    if level_rows:
        op.bulk_insert(levels, level_rows)
    if movement_rows:
        op.bulk_insert(movements, movement_rows)

    op.drop_constraint("ck_products_stock_nonnegative", "products", type_="check")
    op.drop_index("ix_products_store_id", table_name="products")
    op.drop_constraint("fk_products_store_id_stores", "products", type_="foreignkey")
    op.drop_column("products", "store_id")
    op.drop_column("products", "stock_quantity")


def downgrade() -> None:
    op.add_column("products", sa.Column("store_id", sa.Uuid(as_uuid=True), nullable=True))
    op.add_column("products", sa.Column("stock_quantity", sa.Integer(), nullable=False, server_default="0"))
    op.execute(
        """
        UPDATE products p SET
            stock_quantity = COALESCE(
                (SELECT SUM(quantity_on_hand) FROM inventory_levels l WHERE l.product_id = p.id), 0
            ),
            store_id = COALESCE(
                (SELECT l.store_id FROM inventory_levels l WHERE l.product_id = p.id
                 ORDER BY l.quantity_on_hand DESC LIMIT 1),
                (SELECT id FROM stores ORDER BY created_at LIMIT 1)
            )
        """
    )
    op.alter_column("products", "store_id", nullable=False)
    op.create_foreign_key("fk_products_store_id_stores", "products", "stores", ["store_id"], ["id"])
    op.create_index("ix_products_store_id", "products", ["store_id"])
    op.create_check_constraint("ck_products_stock_nonnegative", "products", "stock_quantity >= 0")

    for table in (
        "stock_transfer_serials",
        "stock_transfer_lines",
        "stock_transfers",
        "goods_receipt_lines",
        "goods_receipts",
        "purchase_order_lines",
        "purchase_orders",
        "stock_movements",
        "inventory_levels",
    ):
        op.drop_table(table)
    op.drop_index("ix_products_sub_category_id", table_name="products")
    op.drop_index("ix_products_category_id", table_name="products")
    op.drop_constraint("fk_products_sub_category_id_sub_categories", "products", type_="foreignkey")
    op.drop_constraint("fk_products_category_id_categories", "products", type_="foreignkey")
    op.drop_column("products", "sub_category_id")
    op.drop_column("products", "category_id")
    op.drop_table("sub_categories")
    op.drop_table("categories")
    for column in ("is_active", "is_warehouse", "phone", "address"):
        op.drop_column("stores", column)
