"""Margin policies and below-floor exceptions recorded on sale lines.

Revision ID: 20261019_0018
Revises: 20261019_0017
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0018"
down_revision: str | None = "20261019_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "margin_policies",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("scope", sa.String(12), nullable=False),
        sa.Column("category_id", sa.Uuid(as_uuid=True), sa.ForeignKey("categories.id"), nullable=True, index=True),
        sa.Column("product_id", sa.Uuid(as_uuid=True), sa.ForeignKey("products.id"), nullable=True, index=True),
        sa.Column("min_margin_bps", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("scope", "category_id", "product_id", name="uq_margin_policy_target"),
        sa.CheckConstraint("min_margin_bps >= 0 AND min_margin_bps <= 100000", name="margin_bps_range"),
    )
    op.add_column("sale_items", sa.Column("floor_cents", sa.Integer(), nullable=True))
    op.add_column(
        "sale_items",
        sa.Column("below_floor_approved_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sale_items", "below_floor_approved_by_id")
    op.drop_column("sale_items", "floor_cents")
    op.drop_table("margin_policies")
