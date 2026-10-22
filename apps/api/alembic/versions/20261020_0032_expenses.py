"""Expenses and the petty cash ledger.

Revision ID: 20261020_0032
Revises: 20261020_0031
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261020_0032"
down_revision: str | None = "20261020_0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "expenses",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("number", sa.String(40), nullable=False, unique=True),
        sa.Column("store_id", sa.Uuid(as_uuid=True), sa.ForeignKey("stores.id"), nullable=False, index=True),
        sa.Column("category", sa.String(12), nullable=False, index=True),
        sa.Column("description", sa.String(200), nullable=False),
        sa.Column("payee", sa.String(120), nullable=False, server_default=""),
        sa.Column("payee_trn", sa.String(15), nullable=True),
        sa.Column("spent_on", sa.Date(), nullable=False, index=True),
        sa.Column("net_cents", sa.Integer(), nullable=False),
        sa.Column("tax_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("has_tax_invoice", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("paid_from", sa.String(12), nullable=False),
        sa.Column("reference", sa.String(64), nullable=False, server_default=""),
        sa.Column("status", sa.String(8), nullable=False, server_default="RECORDED", index=True),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("voided_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("void_reason", sa.String(255), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("total_cents > 0", name="expense_total_positive"),
        sa.CheckConstraint("tax_cents >= 0 AND tax_cents < total_cents", name="expense_tax_within_total"),
    )
    op.create_table(
        "petty_cash_entries",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.Uuid(as_uuid=True), sa.ForeignKey("stores.id"), nullable=False, index=True),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("expense_id", sa.Uuid(as_uuid=True), sa.ForeignKey("expenses.id"), nullable=True),
        sa.Column("source", sa.String(8), nullable=True),
        sa.Column("note", sa.String(255), nullable=False, server_default=""),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.CheckConstraint("amount_cents <> 0", name="petty_cash_nonzero"),
    )


def downgrade() -> None:
    op.drop_table("petty_cash_entries")
    op.drop_table("expenses")
