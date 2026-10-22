"""Register shifts and cash movements; sales and returns remember the shift that rang them.

Revision ID: 20261019_0014
Revises: 20261019_0013
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0014"
down_revision: str | None = "20261019_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "register_shifts",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.Uuid(as_uuid=True), sa.ForeignKey("stores.id"), nullable=False, index=True),
        sa.Column("device_id", sa.Uuid(as_uuid=True), sa.ForeignKey("devices.id"), nullable=True),
        sa.Column("opened_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("closed_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="OPEN", index=True),
        sa.Column("opening_float_cents", sa.Integer(), nullable=False),
        sa.Column("counted_cash_cents", sa.Integer(), nullable=True),
        sa.Column("expected_cash_cents", sa.Integer(), nullable=True),
        sa.Column("variance_cents", sa.Integer(), nullable=True),
        sa.Column("blind_close", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("z_number", sa.String(40), nullable=True, unique=True),
        sa.Column("report", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("opening_float_cents >= 0", name="opening_float_nonnegative"),
    )
    op.create_table(
        "cash_movements",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("shift_id", sa.Uuid(as_uuid=True), sa.ForeignKey("register_shifts.id"), nullable=False, index=True),
        sa.Column("store_id", sa.Uuid(as_uuid=True), sa.ForeignKey("stores.id"), nullable=False, index=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("reason", sa.String(250), nullable=False, server_default=""),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_cents >= 0", name="cash_movement_nonnegative"),
    )
    op.add_column("sales", sa.Column("shift_id", sa.Uuid(as_uuid=True), nullable=True))
    op.create_index("ix_sales_shift_id", "sales", ["shift_id"])
    op.add_column("returns", sa.Column("shift_id", sa.Uuid(as_uuid=True), nullable=True))
    op.create_index("ix_returns_shift_id", "returns", ["shift_id"])


def downgrade() -> None:
    op.drop_index("ix_returns_shift_id", table_name="returns")
    op.drop_column("returns", "shift_id")
    op.drop_index("ix_sales_shift_id", table_name="sales")
    op.drop_column("sales", "shift_id")
    op.drop_table("cash_movements")
    op.drop_table("register_shifts")
