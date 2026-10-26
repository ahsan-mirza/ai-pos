"""Bank accounts, transfer receipts, and verified payments.

Revision ID: control_0014
Revises: control_0013
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "control_0014"
down_revision: str | None = "control_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("billing_invoices", sa.Column("bank_snapshot", sa.JSON(), nullable=True))
    op.create_table(
        "platform_bank_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("bank_name", sa.String(120), nullable=False),
        sa.Column("holder_name", sa.String(120), nullable=False),
        sa.Column("account_number", sa.String(40), nullable=False, server_default=""),
        sa.Column("iban", sa.String(40), nullable=False, server_default=""),
        sa.Column("swift", sa.String(16), nullable=False, server_default=""),
        sa.Column("country", sa.String(2), nullable=False, server_default="AE"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="AED"),
        sa.Column("instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_platform_bank_accounts"),
    )
    op.create_table(
        "billing_policy",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("grace_days", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_billing_policy"),
    )
    op.create_table(
        "billing_transfers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending_review"),
        sa.Column("amount_fils", sa.Integer(), nullable=False),
        sa.Column("transferred_on", sa.String(10), nullable=False),
        sa.Column("bank_reference", sa.String(80), nullable=False, server_default=""),
        sa.Column("sending_bank", sa.String(120), nullable=False, server_default=""),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("idempotency_key", sa.String(80), nullable=False),
        sa.Column("filename", sa.String(120), nullable=False),
        sa.Column("content_type", sa.String(40), nullable=False),
        sa.Column("body", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["invoice_id"], ["billing_invoices.id"], name="fk_billing_transfers_invoice_id_billing_invoices"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_billing_transfers_tenant_id_tenants"),
        sa.PrimaryKeyConstraint("id", name="pk_billing_transfers"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_billing_transfers_idempotency"),
    )
    op.create_index("ix_billing_transfers_tenant_id", "billing_transfers", ["tenant_id"])
    op.create_index("ix_billing_transfers_invoice_id", "billing_transfers", ["invoice_id"])
    op.create_index("ix_billing_transfers_status", "billing_transfers", ["status"])
    op.create_table(
        "billing_payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("amount_fils", sa.Integer(), nullable=False),
        sa.Column("bank_reference", sa.String(80), nullable=True),
        sa.Column("recorded_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["invoice_id"], ["billing_invoices.id"], name="fk_billing_payments_invoice_id_billing_invoices"),
        sa.ForeignKeyConstraint(["submission_id"], ["billing_transfers.id"], name="fk_billing_payments_submission_id_billing_transfers"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_billing_payments_tenant_id_tenants"),
        sa.PrimaryKeyConstraint("id", name="pk_billing_payments"),
        sa.UniqueConstraint("bank_reference", name="uq_billing_payments_bank_reference"),
        sa.UniqueConstraint("submission_id", name="uq_billing_payments_submission_id"),
    )
    op.create_index("ix_billing_payments_tenant_id", "billing_payments", ["tenant_id"])
    op.create_index("ix_billing_payments_invoice_id", "billing_payments", ["invoice_id"])


def downgrade() -> None:
    op.drop_index("ix_billing_payments_invoice_id", table_name="billing_payments")
    op.drop_index("ix_billing_payments_tenant_id", table_name="billing_payments")
    op.drop_table("billing_payments")
    op.drop_index("ix_billing_transfers_status", table_name="billing_transfers")
    op.drop_index("ix_billing_transfers_invoice_id", table_name="billing_transfers")
    op.drop_index("ix_billing_transfers_tenant_id", table_name="billing_transfers")
    op.drop_table("billing_transfers")
    op.drop_table("billing_policy")
    op.drop_table("platform_bank_accounts")
    op.drop_column("billing_invoices", "bank_snapshot")
