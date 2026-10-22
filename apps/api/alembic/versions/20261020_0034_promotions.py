"""Promotions, their redemptions, and line discounts on sale items.

Revision ID: 20261020_0034
Revises: 20261020_0033
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261020_0034"
down_revision: str | None = "20261020_0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "promotions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.String(255), nullable=False, server_default=""),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("product_ids", sa.JSON(), nullable=False),
        sa.Column("category_ids", sa.JSON(), nullable=False),
        sa.Column("store_ids", sa.JSON(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true(), index=True),
        sa.Column("coupon_code", sa.String(32), nullable=True, unique=True),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("min_spend_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("min_spend_cents >= 0", name="promotion_min_spend_nonnegative"),
    )
    op.create_table(
        "promotion_redemptions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("promotion_id", sa.Uuid(as_uuid=True), sa.ForeignKey("promotions.id"), nullable=False, index=True),
        sa.Column("sale_id", sa.Uuid(as_uuid=True), sa.ForeignKey("sales.id"), nullable=False, index=True),
        sa.Column("store_id", sa.Uuid(as_uuid=True), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("discount_cents", sa.Integer(), nullable=False),
        sa.Column("coupon_code", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column("sale_items", sa.Column("discount_cents", sa.Integer(), nullable=False, server_default="0"))
    with op.batch_alter_table("sale_items") as batch:
        batch.add_column(sa.Column("promotion_id", sa.Uuid(as_uuid=True), nullable=True))
        batch.create_foreign_key("fk_sale_items_promotion_id_promotions", "promotions", ["promotion_id"], ["id"])
        batch.create_index("ix_sale_items_promotion_id", ["promotion_id"])


def downgrade() -> None:
    with op.batch_alter_table("sale_items") as batch:
        batch.drop_index("ix_sale_items_promotion_id")
        batch.drop_constraint("fk_sale_items_promotion_id_promotions", type_="foreignkey")
        batch.drop_column("promotion_id")
    op.drop_column("sale_items", "discount_cents")
    op.drop_table("promotion_redemptions")
    op.drop_table("promotions")
