"""Meal combos: slots of real menu items on a combo product, components on sold and ordered lines.

Revision ID: 20261021_0056
Revises: 20261021_0055
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261021_0056"
down_revision: str | None = "20261021_0055"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "combo_slots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("product_id", sa.Uuid(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("min_select", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_select", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("min_select >= 0", name="ck_combo_slots_min_nonnegative"),
        sa.CheckConstraint("max_select >= 1", name="ck_combo_slots_max_positive"),
        sa.CheckConstraint("max_select >= min_select", name="ck_combo_slots_max_covers_min"),
    )
    op.create_index("ix_combo_slots_product_id", "combo_slots", ["product_id"])
    op.create_table(
        "combo_slot_options",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("slot_id", sa.Uuid(), sa.ForeignKey("combo_slots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.Uuid(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("surcharge_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("surcharge_cents >= 0", name="ck_combo_slot_options_surcharge_nonnegative"),
        sa.UniqueConstraint("slot_id", "product_id", name="uq_combo_slot_options_slot_product"),
    )
    op.create_index("ix_combo_slot_options_slot_id", "combo_slot_options", ["slot_id"])
    op.create_index("ix_combo_slot_options_product_id", "combo_slot_options", ["product_id"])
    op.add_column("sale_items", sa.Column("components", sa.JSON(), nullable=True))
    op.add_column("open_order_items", sa.Column("components", sa.JSON(), nullable=True))
    op.add_column("kitchen_ticket_items", sa.Column("combo_name", sa.String(160), nullable=True))
    op.add_column(
        "modifier_groups", sa.Column("is_sample", sa.Boolean(), nullable=False, server_default=sa.false())
    )


def downgrade() -> None:
    op.drop_column("modifier_groups", "is_sample")
    op.drop_column("kitchen_ticket_items", "combo_name")
    op.drop_column("open_order_items", "components")
    op.drop_column("sale_items", "components")
    op.drop_index("ix_combo_slot_options_product_id", table_name="combo_slot_options")
    op.drop_index("ix_combo_slot_options_slot_id", table_name="combo_slot_options")
    op.drop_table("combo_slot_options")
    op.drop_index("ix_combo_slots_product_id", table_name="combo_slots")
    op.drop_table("combo_slots")
