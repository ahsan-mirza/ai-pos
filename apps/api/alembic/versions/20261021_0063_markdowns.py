"""Markdown events, retail price history, and the was-price on products.

Revision ID: 20261021_0063
Revises: 20261021_0062
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261021_0063"
down_revision: str | None = "20261021_0062"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "markdown_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("percent_bps", sa.Integer(), nullable=True),
        sa.Column("price_cents", sa.Integer(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("final_sale", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(16), nullable=False, server_default="SCHEDULED"),
        sa.Column("applied_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('SCHEDULED', 'ACTIVE', 'ENDED', 'CANCELLED')", name="markdown_status"),
        sa.CheckConstraint("(percent_bps IS NOT NULL) <> (price_cents IS NOT NULL)", name="markdown_one_price_rule"),
        sa.CheckConstraint("ends_at > starts_at", name="markdown_window"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_markdown_events_status", "markdown_events", ["status"])
    op.create_table(
        "price_changes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("old_price_cents", sa.Integer(), nullable=False),
        sa.Column("new_price_cents", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(16), nullable=False),
        sa.Column("markdown_event_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("reason IN ('MANUAL', 'MARKDOWN', 'IMPORT', 'BULK')", name="price_change_reason"),
        sa.ForeignKeyConstraint(["markdown_event_id"], ["markdown_events.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_price_changes_product_id", "price_changes", ["product_id"])
    op.create_index("ix_price_changes_markdown_event_id", "price_changes", ["markdown_event_id"])
    op.add_column("products", sa.Column("compare_at_cents", sa.Integer(), nullable=True))
    op.add_column("products", sa.Column("markdown_event_id", sa.Uuid(), nullable=True))
    op.create_index("ix_products_markdown_event_id", "products", ["markdown_event_id"])
    op.create_foreign_key(
        "fk_products_markdown_event", "products", "markdown_events", ["markdown_event_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint("fk_products_markdown_event", "products", type_="foreignkey")
    op.drop_index("ix_products_markdown_event_id", table_name="products")
    op.drop_column("products", "markdown_event_id")
    op.drop_column("products", "compare_at_cents")
    op.drop_index("ix_price_changes_markdown_event_id", table_name="price_changes")
    op.drop_index("ix_price_changes_product_id", table_name="price_changes")
    op.drop_table("price_changes")
    op.drop_index("ix_markdown_events_status", table_name="markdown_events")
    op.drop_table("markdown_events")
