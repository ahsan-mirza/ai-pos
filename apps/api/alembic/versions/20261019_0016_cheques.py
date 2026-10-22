"""Post-dated cheques with status history; customers gain an automatic credit hold.

Revision ID: 20261019_0016
Revises: 20261019_0015
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0016"
down_revision: str | None = "20261019_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cheques",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.Uuid(as_uuid=True), sa.ForeignKey("stores.id"), nullable=False, index=True),
        sa.Column("customer_id", sa.Uuid(as_uuid=True), sa.ForeignKey("customers.id"), nullable=True, index=True),
        sa.Column("cheque_number", sa.String(32), nullable=False),
        sa.Column("bank", sa.String(80), nullable=False),
        sa.Column("cheque_date", sa.Date(), nullable=False, index=True),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="RECEIVED", index=True),
        sa.Column("source", sa.String(8), nullable=False),
        sa.Column("sale_id", sa.Uuid(as_uuid=True), sa.ForeignKey("sales.id"), nullable=True),
        sa.Column(
            "ledger_entry_id", sa.Uuid(as_uuid=True), sa.ForeignKey("customer_ledger_entries.id"), nullable=True
        ),
        sa.Column("received_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("bounce_fee_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_cents > 0", name="cheque_amount_positive"),
    )
    op.create_table(
        "cheque_events",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("cheque_id", sa.Uuid(as_uuid=True), sa.ForeignKey("cheques.id"), nullable=False, index=True),
        sa.Column("from_status", sa.String(12), nullable=True),
        sa.Column("to_status", sa.String(12), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("note", sa.String(255), nullable=False, server_default=""),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column("customers", sa.Column("credit_hold", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("customers", sa.Column("credit_hold_reason", sa.String(255), nullable=True))
    op.add_column("customers", sa.Column("credit_hold_manual", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("customers", "credit_hold_manual")
    op.drop_column("customers", "credit_hold_reason")
    op.drop_column("customers", "credit_hold")
    op.drop_table("cheque_events")
    op.drop_table("cheques")
