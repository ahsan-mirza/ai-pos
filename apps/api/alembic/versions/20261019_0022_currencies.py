"""Accepted foreign currencies, exchange rates, and foreign-cash details on sale tenders.

Revision ID: 20261019_0022
Revises: 20261019_0021
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0022"
down_revision: str | None = "20261019_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "accepted_currencies",
        sa.Column("code", sa.String(3), primary_key=True),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "exchange_rates",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("currency", sa.String(3), sa.ForeignKey("accepted_currencies.code"), nullable=False, index=True),
        sa.Column("base_currency", sa.String(3), nullable=False),
        sa.Column("rate_micros", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.String(24), nullable=False),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.CheckConstraint("rate_micros > 0", name="rate_positive"),
    )
    op.add_column("sale_tenders", sa.Column("currency", sa.String(3), nullable=True))
    op.add_column("sale_tenders", sa.Column("foreign_amount_cents", sa.Integer(), nullable=True))
    op.add_column("sale_tenders", sa.Column("rate_micros", sa.BigInteger(), nullable=True))
    op.add_column("sale_tenders", sa.Column("change_cents", sa.Integer(), nullable=True))


def downgrade() -> None:
    for column in ("change_cents", "rate_micros", "foreign_amount_cents", "currency"):
        op.drop_column("sale_tenders", column)
    op.drop_table("exchange_rates")
    op.drop_table("accepted_currencies")
