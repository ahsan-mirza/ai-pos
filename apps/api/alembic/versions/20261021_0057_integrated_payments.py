"""Integrated payments: card terminals and BNPL intents beside QR, with provider refunds.

Revision ID: 20261021_0057
Revises: 20261021_0056
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261021_0057"
down_revision: str | None = "20261021_0056"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payment_terminals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("store_id", sa.Uuid(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("terminal_ref", sa.String(64), nullable=False),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("device_id", sa.Uuid(), sa.ForeignKey("devices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_check_ok", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "terminal_ref", name="uq_payment_terminals_ref"),
    )
    op.create_index("ix_payment_terminals_store_id", "payment_terminals", ["store_id"])

    op.add_column("payment_intents", sa.Column("channel", sa.String(8), nullable=False, server_default="QR"))
    op.add_column(
        "payment_intents",
        sa.Column("terminal_id", sa.Uuid(), sa.ForeignKey("payment_terminals.id"), nullable=True),
    )
    op.add_column("payment_intents", sa.Column("customer_url", sa.Text(), nullable=True))
    op.add_column("payment_intents", sa.Column("customer_phone", sa.String(32), nullable=True))
    op.add_column("payment_intents", sa.Column("auth_code", sa.String(40), nullable=True))
    op.add_column("payment_intents", sa.Column("card_brand", sa.String(20), nullable=True))
    op.add_column("payment_intents", sa.Column("card_last4", sa.String(4), nullable=True))
    op.add_column("payment_intents", sa.Column("failure_reason", sa.String(200), nullable=True))
    op.add_column("payment_intents", sa.Column("refunded_cents", sa.Integer(), nullable=False, server_default="0"))
    op.create_check_constraint(
        "ck_payment_intents_intent_refund_range",
        "payment_intents",
        "refunded_cents >= 0 AND refunded_cents <= amount_cents",
    )
    op.create_index("ix_payment_intents_channel", "payment_intents", ["channel"])
    op.create_index("ix_payment_intents_provider_ref", "payment_intents", ["provider_ref"])
    op.create_index("ix_payment_intents_sale_id", "payment_intents", ["sale_id"])

    op.create_table(
        "payment_refunds",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("intent_id", sa.Uuid(), sa.ForeignKey("payment_intents.id"), nullable=False),
        sa.Column("return_id", sa.Uuid(), sa.ForeignKey("returns.id"), nullable=True),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="PENDING"),
        sa.Column("provider_ref", sa.String(120), nullable=True),
        sa.Column("error", sa.String(300), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_cents > 0", name="ck_payment_refunds_refund_amount_positive"),
    )
    op.create_index("ix_payment_refunds_intent_id", "payment_refunds", ["intent_id"])
    op.create_index("ix_payment_refunds_return_id", "payment_refunds", ["return_id"])
    op.create_index("ix_payment_refunds_status", "payment_refunds", ["status"])


def downgrade() -> None:
    op.drop_index("ix_payment_refunds_status", table_name="payment_refunds")
    op.drop_index("ix_payment_refunds_return_id", table_name="payment_refunds")
    op.drop_index("ix_payment_refunds_intent_id", table_name="payment_refunds")
    op.drop_table("payment_refunds")
    op.drop_index("ix_payment_intents_sale_id", table_name="payment_intents")
    op.drop_index("ix_payment_intents_provider_ref", table_name="payment_intents")
    op.drop_index("ix_payment_intents_channel", table_name="payment_intents")
    op.drop_constraint("ck_payment_intents_intent_refund_range", "payment_intents", type_="check")
    for column in (
        "refunded_cents",
        "failure_reason",
        "card_last4",
        "card_brand",
        "auth_code",
        "customer_phone",
        "customer_url",
        "terminal_id",
        "channel",
    ):
        op.drop_column("payment_intents", column)
    op.drop_index("ix_payment_terminals_store_id", table_name="payment_terminals")
    op.drop_table("payment_terminals")
