"""Restaurant core: menu modifiers, open orders (tabs), the dining-room floor plan, and service charge / tips on
sales, plus the restaurant permissions for the system roles.

Revision ID: 20261021_0050
Revises: 20261021_0049
Create Date: 2026-10-21
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261021_0050"
down_revision: str | None = "20261021_0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUPER_ADMIN_ROLE_ID = uuid.UUID("00000000-0000-4000-8000-0000000000a1")
STORE_MANAGER_ROLE_ID = uuid.UUID("00000000-0000-4000-8000-0000000000a2")
CASHIER_ROLE_ID = uuid.UUID("00000000-0000-4000-8000-0000000000a3")
GRANTS = {
    SUPER_ADMIN_ROLE_ID: ("pos:orders", "pos:void_sent_item", "kds:operate"),
    STORE_MANAGER_ROLE_ID: ("pos:orders", "pos:void_sent_item", "kds:operate"),
    CASHIER_ROLE_ID: ("pos:orders",),
}


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


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
        "modifier_groups",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("min_select", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_select", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
        sa.CheckConstraint("min_select >= 0", name="ck_modifier_groups_min_nonnegative"),
        sa.CheckConstraint("max_select >= 1", name="ck_modifier_groups_max_positive"),
        sa.CheckConstraint("max_select >= min_select", name="ck_modifier_groups_max_covers_min"),
    )
    op.create_table(
        "modifier_options",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "group_id", sa.Uuid(as_uuid=True), sa.ForeignKey("modifier_groups.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("price_delta_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        *_timestamps(),
    )
    op.create_index("ix_modifier_options_group_id", "modifier_options", ["group_id"])
    op.create_table(
        "product_modifier_groups",
        sa.Column(
            "product_id", sa.Uuid(as_uuid=True), sa.ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "group_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("modifier_groups.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_product_modifier_groups_group_id", "product_modifier_groups", ["group_id"])
    op.add_column("sale_items", sa.Column("modifiers", sa.JSON(), nullable=True))

    op.create_table(
        "dining_areas",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.Uuid(as_uuid=True), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
    )
    op.create_index("ix_dining_areas_store_id", "dining_areas", ["store_id"])
    op.create_table(
        "dining_tables",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "area_id", sa.Uuid(as_uuid=True), sa.ForeignKey("dining_areas.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("label", sa.String(16), nullable=False),
        sa.Column("seats", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("shape", sa.String(8), nullable=False, server_default="square"),
        sa.Column("x", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("y", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("w", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("h", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
        sa.UniqueConstraint("area_id", "label", name="uq_dining_tables_area_label"),
        sa.CheckConstraint("seats >= 1", name="ck_dining_tables_seats_positive"),
    )
    op.create_index("ix_dining_tables_area_id", "dining_tables", ["area_id"])

    op.create_table(
        "open_orders",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.Uuid(as_uuid=True), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("service_type", sa.String(10), nullable=False, server_default="DINE_IN"),
        sa.Column("status", sa.String(10), nullable=False, server_default="OPEN"),
        sa.Column(
            "table_id", sa.Uuid(as_uuid=True), sa.ForeignKey("dining_tables.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("covers", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("customer_id", sa.Uuid(as_uuid=True), sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("name", sa.String(80), nullable=True),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("opened_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("bill_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("channel_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("external_ref", sa.String(64), nullable=True),
        sa.Column("channel_status", sa.String(12), nullable=True),
        sa.Column("prep_minutes", sa.Integer(), nullable=True),
        sa.Column("channel_payload", sa.JSON(), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("covers >= 0", name="ck_open_orders_covers_nonnegative"),
    )
    op.create_index("ix_open_orders_store_status", "open_orders", ["store_id", "status"])
    op.create_index("ix_open_orders_table_id", "open_orders", ["table_id"])
    op.create_index("ix_open_orders_channel_id", "open_orders", ["channel_id"])
    op.create_index("ix_open_orders_updated_at", "open_orders", ["updated_at"])
    op.create_table(
        "open_order_items",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "order_id", sa.Uuid(as_uuid=True), sa.ForeignKey("open_orders.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("product_id", sa.Uuid(as_uuid=True), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price_cents", sa.Integer(), nullable=False),
        sa.Column("modifiers", sa.JSON(), nullable=True),
        sa.Column("seat", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(160), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("added_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("void_reason", sa.String(160), nullable=True),
        sa.Column("voided_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("paid_sale_id", sa.Uuid(as_uuid=True), sa.ForeignKey("sales.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity >= 1", name="ck_open_order_items_quantity_positive"),
    )
    op.create_index("ix_open_order_items_order_id", "open_order_items", ["order_id"])
    op.create_index("ix_open_order_items_paid_sale_id", "open_order_items", ["paid_sale_id"])

    op.add_column("sales", sa.Column("order_id", sa.Uuid(as_uuid=True), nullable=True))
    op.add_column("sales", sa.Column("service_charge_cents", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("sales", sa.Column("service_charge_tax_cents", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("sales", sa.Column("tip_cents", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("sales", sa.Column("tip_user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True))
    op.create_index("ix_sales_order_id", "sales", ["order_id"])

    _grant(op.get_bind())


def downgrade() -> None:
    op.drop_index("ix_sales_order_id", table_name="sales")
    for column in ("tip_user_id", "tip_cents", "service_charge_tax_cents", "service_charge_cents", "order_id"):
        op.drop_column("sales", column)
    op.drop_table("open_order_items")
    op.drop_table("open_orders")
    op.drop_table("dining_tables")
    op.drop_table("dining_areas")
    op.drop_column("sale_items", "modifiers")
    op.drop_table("product_modifier_groups")
    op.drop_table("modifier_options")
    op.drop_table("modifier_groups")
    role_permissions = sa.table("role_permissions", sa.column("permission", sa.String(64)))
    op.execute(
        role_permissions.delete().where(
            role_permissions.c.permission.in_(("pos:orders", "pos:void_sent_item", "kds:operate"))
        )
    )
