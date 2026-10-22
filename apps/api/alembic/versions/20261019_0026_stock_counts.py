"""Stock count sessions with blind counting and posted variances.

Revision ID: 20261019_0026
Revises: 20261019_0025
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0026"
down_revision: str | None = "20261019_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _user_fk(name: str) -> sa.Column:
    return sa.Column(name, sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True)


def upgrade() -> None:
    op.create_table(
        "stock_counts",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("number", sa.String(40), nullable=False, unique=True),
        sa.Column("store_id", sa.Uuid(as_uuid=True), sa.ForeignKey("stores.id"), nullable=False, index=True),
        sa.Column("category_id", sa.Uuid(as_uuid=True), sa.ForeignKey("categories.id"), nullable=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="OPEN", index=True),
        sa.Column("blind", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("note", sa.String(255), nullable=False, server_default=""),
        _user_fk("created_by_id"),
        _user_fk("submitted_by_id"),
        _user_fk("posted_by_id"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "stock_count_lines",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("count_id", sa.Uuid(as_uuid=True), sa.ForeignKey("stock_counts.id"), nullable=False, index=True),
        sa.Column("product_id", sa.Uuid(as_uuid=True), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("expected_qty", sa.Integer(), nullable=True),
        sa.Column("counted_qty", sa.Integer(), nullable=True),
        sa.Column("scanned_serials", sa.JSON(), nullable=False),
        sa.Column("serial_result", sa.JSON(), nullable=True),
        _user_fk("counted_by_id"),
        sa.Column("counted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("count_id", "product_id", name="uq_stock_count_lines_count_product"),
        sa.CheckConstraint("counted_qty IS NULL OR counted_qty >= 0", name="counted_nonnegative"),
    )


def downgrade() -> None:
    op.drop_table("stock_count_lines")
    op.drop_table("stock_counts")
