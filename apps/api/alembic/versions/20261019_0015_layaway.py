"""Layaway: quotes gain a kind, and deposits against a layaway get their own ledger.

Revision ID: 20261019_0015
Revises: 20261019_0014
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0015"
down_revision: str | None = "20261019_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sales", sa.Column("quote_kind", sa.String(12), nullable=True))
    op.execute("UPDATE sales SET quote_kind = 'QUOTE' WHERE is_quote_proforma")
    op.create_table(
        "quote_payments",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("quote_id", sa.Uuid(as_uuid=True), sa.ForeignKey("sales.id"), nullable=False, index=True),
        sa.Column("store_id", sa.Uuid(as_uuid=True), sa.ForeignKey("stores.id"), nullable=False, index=True),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("reference", sa.String(120), nullable=False, server_default=""),
        sa.Column("received_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("shift_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(12), nullable=False, server_default="ACTIVE"),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_cents > 0", name="quote_payment_positive"),
    )


def downgrade() -> None:
    op.drop_table("quote_payments")
    op.drop_column("sales", "quote_kind")
