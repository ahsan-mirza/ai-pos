"""Console alerts for payment proofs waiting on review.

Revision ID: control_0021
Revises: control_0020
Create Date: 2026-10-30

The pending badge counts billing_transfers.status, which is already indexed.
These tables remember the alert and who has read it. A read is not a review.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "control_0021"
down_revision: str | None = "control_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "console_payment_notices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("transfer_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_name", sa.String(120), nullable=False, server_default=""),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_reference", sa.String(48), nullable=False, server_default=""),
        sa.Column("amount_fils", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="AED"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_console_payment_notices_tenant_id_tenants"),
        sa.ForeignKeyConstraint(
            ["transfer_id"],
            ["billing_transfers.id"],
            name="fk_console_payment_notices_transfer_id_billing_transfers",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_console_payment_notices"),
        sa.UniqueConstraint("transfer_id", name="uq_console_payment_notices_transfer_id"),
    )
    op.create_index("ix_console_payment_notices_tenant_id", "console_payment_notices", ["tenant_id"])
    op.create_index("ix_console_payment_notices_created_at", "console_payment_notices", ["created_at"])
    op.create_table(
        "console_payment_notice_reads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("notice_id", sa.Uuid(), nullable=False),
        sa.Column("operator_id", sa.Uuid(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["notice_id"],
            ["console_payment_notices.id"],
            name="fk_console_payment_notice_reads_notice_id",
        ),
        sa.ForeignKeyConstraint(
            ["operator_id"],
            ["operators.id"],
            name="fk_console_payment_notice_reads_operator_id",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_console_payment_notice_reads"),
        sa.UniqueConstraint("notice_id", "operator_id", name="uq_console_payment_notice_reads"),
    )
    op.create_index("ix_console_payment_notice_reads_notice_id", "console_payment_notice_reads", ["notice_id"])
    op.create_index("ix_console_payment_notice_reads_operator_id", "console_payment_notice_reads", ["operator_id"])


def downgrade() -> None:
    op.drop_index("ix_console_payment_notice_reads_operator_id", table_name="console_payment_notice_reads")
    op.drop_index("ix_console_payment_notice_reads_notice_id", table_name="console_payment_notice_reads")
    op.drop_table("console_payment_notice_reads")
    op.drop_index("ix_console_payment_notices_created_at", table_name="console_payment_notices")
    op.drop_index("ix_console_payment_notices_tenant_id", table_name="console_payment_notices")
    op.drop_table("console_payment_notices")
