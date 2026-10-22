"""Sales orders: wholesale orders with reservations, pick lists, delivery notes with proof of delivery, and a link
from each delivery's invoice (sale) back to the order; grants sales:orders to the system manager roles.

Revision ID: 20261021_0058
Revises: 20261021_0057
Create Date: 2026-10-21
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261021_0058"
down_revision: str | None = "20261021_0057"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUPER_ADMIN_ROLE_ID = uuid.UUID("00000000-0000-4000-8000-0000000000a1")
STORE_MANAGER_ROLE_ID = uuid.UUID("00000000-0000-4000-8000-0000000000a2")
GRANTS = {SUPER_ADMIN_ROLE_ID: ("sales:orders",), STORE_MANAGER_ROLE_ID: ("sales:orders",)}


def _grant(bind: sa.engine.Connection) -> None:
    roles = sa.table("roles", sa.column("id", sa.Uuid(as_uuid=True)))
    role_permissions = sa.table(
        "role_permissions", sa.column("role_id", sa.Uuid(as_uuid=True)), sa.column("permission", sa.String(64))
    )
    for role_id, permissions in GRANTS.items():
        if bind.execute(sa.select(roles.c.id).where(roles.c.id == role_id)).first() is None:
            continue
        held = {
            row[0]
            for row in bind.execute(
                sa.select(role_permissions.c.permission).where(role_permissions.c.role_id == role_id)
            )
        }
        missing = [{"role_id": role_id, "permission": item} for item in permissions if item not in held]
        if missing:
            op.bulk_insert(role_permissions, missing)


def upgrade() -> None:
    op.create_table(
        "sales_orders",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("number", sa.String(40), nullable=False, unique=True),
        sa.Column("store_id", sa.Uuid(as_uuid=True), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("customer_id", sa.Uuid(as_uuid=True), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("sale_type", sa.String(10), nullable=False, server_default="WHOLESALE"),
        sa.Column("price_tier", sa.String(16), nullable=False, server_default="RETAIL"),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("source", sa.String(12), nullable=False, server_default="manual"),
        sa.Column("quote_id", sa.Uuid(as_uuid=True), sa.ForeignKey("sales.id"), nullable=True),
        sa.Column("channel_ref", sa.String(64), nullable=True),
        sa.Column("customer_reference", sa.String(64), nullable=True),
        sa.Column("requested_date", sa.Date(), nullable=True),
        sa.Column("delivery_address", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("subtotal_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tax_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sales_orders_store_id", "sales_orders", ["store_id"])
    op.create_index("ix_sales_orders_customer_id", "sales_orders", ["customer_id"])
    op.create_index("ix_sales_orders_status", "sales_orders", ["status"])
    op.create_index("ix_sales_orders_channel_ref", "sales_orders", ["channel_ref"])

    op.create_table(
        "sales_order_lines",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "order_id", sa.Uuid(as_uuid=True), sa.ForeignKey("sales_orders.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("product_id", sa.Uuid(as_uuid=True), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("description", sa.String(160), nullable=True),
        sa.Column("quantity_ordered", sa.Integer(), nullable=False),
        sa.Column("quantity_reserved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quantity_delivered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quantity_cancelled", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unit_price_cents", sa.Integer(), nullable=False),
        sa.Column("list_price_cents", sa.Integer(), nullable=False),
        sa.Column("price_override_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("tax_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("line_total_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("quantity_ordered >= 1", name="ck_sales_order_lines_ordered_positive"),
        sa.CheckConstraint(
            "quantity_delivered + quantity_cancelled <= quantity_ordered",
            name="ck_sales_order_lines_fulfilled_within_ordered",
        ),
        sa.CheckConstraint("quantity_reserved >= 0", name="ck_sales_order_lines_reserved_nonnegative"),
    )
    op.create_index("ix_sales_order_lines_order_id", "sales_order_lines", ["order_id"])
    op.create_index("ix_sales_order_lines_product_id", "sales_order_lines", ["product_id"])

    op.create_table(
        "pick_lists",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("number", sa.String(40), nullable=False, unique=True),
        sa.Column(
            "order_id", sa.Uuid(as_uuid=True), sa.ForeignKey("sales_orders.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("store_id", sa.Uuid(as_uuid=True), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="OPEN"),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_pick_lists_order_id", "pick_lists", ["order_id"])
    op.create_table(
        "pick_list_lines",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "pick_list_id", sa.Uuid(as_uuid=True), sa.ForeignKey("pick_lists.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("order_line_id", sa.Uuid(as_uuid=True), sa.ForeignKey("sales_order_lines.id"), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("bin_location", sa.String(64), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_pick_list_lines_pick_list_id", "pick_list_lines", ["pick_list_id"])

    op.create_table(
        "delivery_notes",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("number", sa.String(40), nullable=False, unique=True),
        sa.Column(
            "order_id", sa.Uuid(as_uuid=True), sa.ForeignKey("sales_orders.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("store_id", sa.Uuid(as_uuid=True), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="DISPATCHED"),
        sa.Column("sale_id", sa.Uuid(as_uuid=True), sa.ForeignKey("sales.id"), nullable=True),
        sa.Column("driver_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("vehicle", sa.String(40), nullable=True),
        sa.Column("dispatched_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("receiver_name", sa.String(120), nullable=True),
        sa.Column("signature", sa.Text(), nullable=True),
        sa.Column("pod_note", sa.String(255), nullable=True),
    )
    op.create_index("ix_delivery_notes_order_id", "delivery_notes", ["order_id"])
    op.create_index("ix_delivery_notes_status", "delivery_notes", ["status"])
    op.create_table(
        "delivery_note_lines",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "delivery_note_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("delivery_notes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("order_line_id", sa.Uuid(as_uuid=True), sa.ForeignKey("sales_order_lines.id"), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("serial_suffixes", sa.JSON(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_delivery_note_lines_delivery_note_id", "delivery_note_lines", ["delivery_note_id"])

    op.add_column("sales", sa.Column("sales_order_id", sa.Uuid(as_uuid=True), nullable=True))
    op.create_index("ix_sales_sales_order_id", "sales", ["sales_order_id"])
    op.add_column("sale_items", sa.Column("sales_order_line_id", sa.Uuid(as_uuid=True), nullable=True))
    op.create_index("ix_sale_items_sales_order_line_id", "sale_items", ["sales_order_line_id"])

    _grant(op.get_bind())


def downgrade() -> None:
    op.drop_index("ix_sale_items_sales_order_line_id", table_name="sale_items")
    op.drop_column("sale_items", "sales_order_line_id")
    op.drop_index("ix_sales_sales_order_id", table_name="sales")
    op.drop_column("sales", "sales_order_id")
    op.drop_table("delivery_note_lines")
    op.drop_table("delivery_notes")
    op.drop_table("pick_list_lines")
    op.drop_table("pick_lists")
    op.drop_table("sales_order_lines")
    op.drop_table("sales_orders")
    role_permissions = sa.table("role_permissions", sa.column("permission", sa.String(64)))
    op.execute(role_permissions.delete().where(role_permissions.c.permission == "sales:orders"))
