"""Link a later kitchen round to the original sent line.

Revision ID: 20261126_0141
Revises: 20261125_0140
Create Date: 2026-11-26

The extra quantity is its own order line and its own ticket. This column
names the original line so a register can show one net quantity and can
cancel only the extra. Existing rows stay original lines.
Not applied to a protected database.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261126_0141"
down_revision: str | None = "20261125_0140"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("open_order_items", sa.Column("source_item_id", sa.Uuid(), nullable=True))
    op.create_index("ix_open_order_items_source_item_id", "open_order_items", ["source_item_id"])
    op.create_foreign_key(
        "fk_open_order_items_source_item_id",
        "open_order_items",
        "open_order_items",
        ["source_item_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_open_order_items_source_item_id", "open_order_items", type_="foreignkey")
    op.drop_index("ix_open_order_items_source_item_id", table_name="open_order_items")
    op.drop_column("open_order_items", "source_item_id")
