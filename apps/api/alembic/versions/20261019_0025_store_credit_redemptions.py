"""Store-credit vouchers spent as a sale tender.

Revision ID: 20261019_0025
Revises: 20261019_0024
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0025"
down_revision: str | None = "20261019_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "store_credit_redemptions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "store_credit_id", sa.Uuid(as_uuid=True), sa.ForeignKey("store_credits.id"), nullable=False, index=True
        ),
        sa.Column("sale_id", sa.Uuid(as_uuid=True), sa.ForeignKey("sales.id"), nullable=False, index=True),
        sa.Column("store_id", sa.Uuid(as_uuid=True), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_cents >= 1", name="amount_positive"),
        sa.UniqueConstraint("store_credit_id", "sale_id", name="uq_store_credit_redemption_sale"),
    )


def downgrade() -> None:
    op.drop_table("store_credit_redemptions")
