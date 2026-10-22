"""Delivery channels: the apps that send orders (signed webhook or keyed in), their payouts, and one open order per
channel order id.

Revision ID: 20261021_0054
Revises: 20261021_0053
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261021_0054"
down_revision: str | None = "20261021_0053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "delivery_channels",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("store_id", sa.Uuid(as_uuid=True), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("adapter", sa.String(20), nullable=False, server_default="generic"),
        sa.Column("commission_bps", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("price_markup_bps", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("webhook_secret", sa.String(500), nullable=False),
        sa.Column("auto_accept", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("default_prep_minutes", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "commission_bps >= 0 AND commission_bps <= 10000", name="ck_delivery_channels_commission_range"
        ),
        sa.CheckConstraint("price_markup_bps >= 0", name="ck_delivery_channels_markup_nonnegative"),
    )
    op.create_table(
        "channel_payouts",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "channel_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("delivery_channels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("commission_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reference", sa.String(80), nullable=True),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_cents >= 0", name="ck_channel_payouts_amount_nonnegative"),
        sa.CheckConstraint("commission_cents >= 0", name="ck_channel_payouts_commission_nonnegative"),
    )
    op.create_index("ix_channel_payouts_channel_id", "channel_payouts", ["channel_id"])
    op.create_index("ix_channel_payouts_received_at", "channel_payouts", ["received_at"])
    op.create_foreign_key(
        "fk_open_orders_channel_id_delivery_channels", "open_orders", "delivery_channels", ["channel_id"], ["id"]
    )
    op.create_unique_constraint("uq_open_orders_channel_ref", "open_orders", ["channel_id", "external_ref"])


def downgrade() -> None:
    op.drop_constraint("uq_open_orders_channel_ref", "open_orders", type_="unique")
    op.drop_constraint("fk_open_orders_channel_id_delivery_channels", "open_orders", type_="foreignkey")
    op.drop_table("channel_payouts")
    op.drop_table("delivery_channels")
