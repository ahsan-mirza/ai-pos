"""QR payment intents.

Revision ID: 20261019_0021
Revises: 20261019_0020
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0021"
down_revision: str | None = "20261019_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payment_intents",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.Uuid(as_uuid=True), sa.ForeignKey("stores.id"), nullable=False, index=True),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("reference", sa.String(40), nullable=False),
        sa.Column("qr_payload", sa.Text(), nullable=False),
        sa.Column("provider_ref", sa.String(120), nullable=True),
        sa.Column("status", sa.String(12), nullable=False, server_default="PENDING", index=True),
        sa.Column("sale_id", sa.Uuid(as_uuid=True), sa.ForeignKey("sales.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("amount_cents > 0", name="intent_amount_positive"),
    )


def downgrade() -> None:
    op.drop_table("payment_intents")
