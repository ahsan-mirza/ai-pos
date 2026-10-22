"""Kitchen display: stations routed by category, and the tickets fired to them from sent orders and counter sales.

Revision ID: 20261021_0051
Revises: 20261021_0050
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261021_0051"
down_revision: str | None = "20261021_0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "kitchen_stations",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.Uuid(as_uuid=True), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("category_ids", sa.JSON(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("print_tickets", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_kitchen_stations_store_id", "kitchen_stations", ["store_id"])
    op.create_table(
        "kitchen_tickets",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.Uuid(as_uuid=True), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column(
            "station_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("kitchen_stations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "order_id", sa.Uuid(as_uuid=True), sa.ForeignKey("open_orders.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column("sale_id", sa.Uuid(as_uuid=True), sa.ForeignKey("sales.id", ondelete="CASCADE"), nullable=True),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("service_type", sa.String(10), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="NEW"),
        sa.Column("fired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bumped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_kitchen_tickets_station_status", "kitchen_tickets", ["station_id", "status"])
    op.create_index("ix_kitchen_tickets_order_id", "kitchen_tickets", ["order_id"])
    op.create_index("ix_kitchen_tickets_sale_id", "kitchen_tickets", ["sale_id"])
    op.create_index("ix_kitchen_tickets_updated_at", "kitchen_tickets", ["updated_at"])
    op.create_table(
        "kitchen_ticket_items",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "ticket_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("kitchen_tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "order_item_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("open_order_items.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("product_name", sa.String(160), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("modifiers", sa.JSON(), nullable=True),
        sa.Column("seat", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(160), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_kitchen_ticket_items_ticket_id", "kitchen_ticket_items", ["ticket_id"])
    op.create_index("ix_kitchen_ticket_items_order_item_id", "kitchen_ticket_items", ["order_item_id"])


def downgrade() -> None:
    op.drop_table("kitchen_ticket_items")
    op.drop_table("kitchen_tickets")
    op.drop_table("kitchen_stations")
