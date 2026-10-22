"""Repairs 2.0: technician, priority and promise date, intake checklist and passcode, estimate approval, photos,
deposits, parts reservation, public tracking, and repair warranties.

Revision ID: 20261021_0061
Revises: 20261021_0060
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261021_0061"
down_revision: str | None = "20261021_0060"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TICKET_COLUMNS = (
    sa.Column("technician_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
    sa.Column("priority", sa.String(8), nullable=False, server_default="NORMAL"),
    sa.Column("promised_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("passcode_encrypted", sa.Text(), nullable=True),
    sa.Column("intake_checklist", sa.JSON(), nullable=True),
    sa.Column("accessories", sa.String(300), nullable=False, server_default=""),
    sa.Column("approval_status", sa.String(12), nullable=True),
    sa.Column("approval_amount_cents", sa.Integer(), nullable=True),
    sa.Column("approval_requested_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("approval_decided_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("approval_channel", sa.String(12), nullable=True),
    sa.Column("approval_note", sa.String(300), nullable=False, server_default=""),
    sa.Column("approval_token_hash", sa.String(64), nullable=True),
    sa.Column("approval_expires_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("repair_warranty_days", sa.Integer(), nullable=True),
    sa.Column("tracking_token", sa.String(32), nullable=True),
    sa.Column("picked_up_at", sa.DateTime(timezone=True), nullable=True),
)


def upgrade() -> None:
    op.alter_column("repair_tickets", "status", type_=sa.String(20), existing_type=sa.String(16))
    op.alter_column("repair_events", "from_status", type_=sa.String(20), existing_type=sa.String(16))
    op.alter_column("repair_events", "to_status", type_=sa.String(20), existing_type=sa.String(16))
    for column in TICKET_COLUMNS:
        op.add_column("repair_tickets", column)
    op.create_index("ix_repair_tickets_technician_id", "repair_tickets", ["technician_id"])
    op.create_index("ix_repair_tickets_approval_token_hash", "repair_tickets", ["approval_token_hash"])
    op.create_unique_constraint("uq_repair_tickets_tracking_token", "repair_tickets", ["tracking_token"])
    op.add_column("repair_lines", sa.Column("reserved_quantity", sa.Integer(), nullable=False, server_default="0"))

    op.create_table(
        "repair_attachments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ticket_id", sa.Uuid(), sa.ForeignKey("repair_tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("file_name", sa.String(160), nullable=False),
        sa.Column("content_type", sa.String(80), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(120), nullable=False),
        sa.Column("uploaded_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_repair_attachments_ticket_id", "repair_attachments", ["ticket_id"])

    op.create_table(
        "repair_deposits",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ticket_id", sa.Uuid(), sa.ForeignKey("repair_tickets.id"), nullable=False),
        sa.Column("store_id", sa.Uuid(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("reference", sa.String(64), nullable=False, server_default=""),
        sa.Column("status", sa.String(10), nullable=False, server_default="HELD"),
        sa.Column("received_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("shift_id", sa.Uuid(), nullable=True),
        sa.Column("refund_shift_id", sa.Uuid(), nullable=True),
        sa.Column("applied_sale_id", sa.Uuid(), sa.ForeignKey("sales.id"), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("amount_cents > 0", name="ck_repair_deposits_deposit_positive"),
    )
    op.create_index("ix_repair_deposits_ticket_id", "repair_deposits", ["ticket_id"])
    op.create_index("ix_repair_deposits_store_id", "repair_deposits", ["store_id"])
    op.create_index("ix_repair_deposits_status", "repair_deposits", ["status"])
    op.create_index("ix_repair_deposits_shift_id", "repair_deposits", ["shift_id"])
    op.create_index("ix_repair_deposits_refund_shift_id", "repair_deposits", ["refund_shift_id"])

    op.add_column(
        "warranty_registrations", sa.Column("kind", sa.String(8), nullable=False, server_default="SALE")
    )
    op.add_column(
        "warranty_registrations",
        sa.Column("repair_ticket_id", sa.Uuid(), sa.ForeignKey("repair_tickets.id"), nullable=True),
    )
    op.add_column("warranty_registrations", sa.Column("identifier_hash", sa.String(64), nullable=True))
    op.create_index("ix_warranty_registrations_identifier_hash", "warranty_registrations", ["identifier_hash"])


def downgrade() -> None:
    op.drop_index("ix_warranty_registrations_identifier_hash", table_name="warranty_registrations")
    op.drop_column("warranty_registrations", "identifier_hash")
    op.drop_column("warranty_registrations", "repair_ticket_id")
    op.drop_column("warranty_registrations", "kind")
    for index in ("refund_shift_id", "shift_id", "status", "store_id", "ticket_id"):
        op.drop_index(f"ix_repair_deposits_{index}", table_name="repair_deposits")
    op.drop_table("repair_deposits")
    op.drop_index("ix_repair_attachments_ticket_id", table_name="repair_attachments")
    op.drop_table("repair_attachments")
    op.drop_column("repair_lines", "reserved_quantity")
    op.drop_constraint("uq_repair_tickets_tracking_token", "repair_tickets", type_="unique")
    op.drop_index("ix_repair_tickets_approval_token_hash", table_name="repair_tickets")
    op.drop_index("ix_repair_tickets_technician_id", table_name="repair_tickets")
    for column in reversed(TICKET_COLUMNS):
        op.drop_column("repair_tickets", column.name)
    op.alter_column("repair_events", "to_status", type_=sa.String(16), existing_type=sa.String(20))
    op.alter_column("repair_events", "from_status", type_=sa.String(16), existing_type=sa.String(20))
    op.alter_column("repair_tickets", "status", type_=sa.String(16), existing_type=sa.String(20))
