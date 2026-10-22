"""Loyalty points: ledger, customer balance, and programme settings.

Revision ID: 20261019_0023
Revises: 20261019_0022
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0023"
down_revision: str | None = "20261019_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("loyalty_points", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("business_settings", sa.Column("loyalty", sa.JSON(), nullable=True))
    op.create_table(
        "loyalty_entries",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("customer_id", sa.Uuid(as_uuid=True), sa.ForeignKey("customers.id"), nullable=False, index=True),
        sa.Column("entry_type", sa.String(12), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("sale_id", sa.Uuid(as_uuid=True), sa.ForeignKey("sales.id"), nullable=True),
        sa.Column("return_id", sa.Uuid(as_uuid=True), sa.ForeignKey("returns.id"), nullable=True),
        sa.Column("note", sa.String(255), nullable=False, server_default=""),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.CheckConstraint("points <> 0", name="loyalty_points_nonzero"),
    )


def downgrade() -> None:
    op.drop_table("loyalty_entries")
    op.drop_column("business_settings", "loyalty")
    op.drop_column("customers", "loyalty_points")
