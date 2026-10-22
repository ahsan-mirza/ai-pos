"""Supplier ordering terms (MOQ, pack size, order days) and the note they leave on suggestions.

Revision ID: 20261019_0030
Revises: 20261019_0029
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0030"
down_revision: str | None = "20261019_0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("suppliers", sa.Column("moq", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("suppliers", sa.Column("pack_size", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("suppliers", sa.Column("order_days", sa.JSON(), nullable=True))
    op.add_column("replenishment_suggestions", sa.Column("terms_note", sa.String(160), nullable=True))


def downgrade() -> None:
    op.drop_column("replenishment_suggestions", "terms_note")
    op.drop_column("suppliers", "order_days")
    op.drop_column("suppliers", "pack_size")
    op.drop_column("suppliers", "moq")
