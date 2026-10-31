"""Plugin-owned e-invoicing tables in the shared AxizPOS database.

Revision ID: einvoicing_0001
Revises:
Create Date: 2026-10-31

This history is stored in alembic_version_einvoicing, not the API's alembic_version.
Do not run it against production without an explicit approval.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "einvoicing_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _rls(table: str) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON {table}
        USING (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            OR current_setting('app.bypass_rls', true) = 'on'
        )
        WITH CHECK (
            tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
            OR current_setting('app.bypass_rls', true) = 'on'
        )
        """
    )


def upgrade() -> None:
    op.create_table(
        "einvoicing_settings",
        sa.Column("tenant_id", sa.Uuid(), primary_key=True),
        sa.Column("revenue_band", sa.String(24), nullable=False, server_default="unknown"),
        sa.Column("voluntary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("b2b_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("b2g_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("government_customer_ids", sa.JSON(), nullable=False),
        sa.Column("environment", sa.String(16), nullable=False, server_default="sandbox"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "einvoicing_provider_accounts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("provider_code", sa.String(32), nullable=False),
        sa.Column("participant_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("environment", sa.String(16), nullable=False, server_default="sandbox"),
        sa.Column("connection_status", sa.String(24), nullable=False, server_default="untested"),
        sa.Column("credential_ciphertext", sa.Text(), nullable=True),
        sa.Column("webhook_secret_ciphertext", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "provider_code", name="uq_einvoicing_provider_tenant"),
    )
    op.create_index("ix_einvoicing_provider_accounts_tenant_id", "einvoicing_provider_accounts", ["tenant_id"])
    op.create_table(
        "einvoicing_invoices",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), sa.ForeignKey("stores.id"), nullable=True),
        sa.Column("source_sale_id", sa.Uuid(), sa.ForeignKey("sales.id"), nullable=False),
        sa.Column("customer_id", sa.Uuid(), sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("document_number", sa.String(40), nullable=False, server_default=""),
        sa.Column("document_kind", sa.String(16), nullable=False),
        sa.Column("profile_version", sa.String(64), nullable=False),
        sa.Column("issue_date", sa.String(10), nullable=False, server_default=""),
        sa.Column("currency", sa.String(3), nullable=False, server_default="AED"),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("provider_code", sa.String(32), nullable=False, server_default=""),
        sa.Column("provider_status", sa.String(64), nullable=False, server_default=""),
        sa.Column("provider_reference", sa.String(120), nullable=False, server_default=""),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("error_detail", sa.String(500), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "source_sale_id", name="uq_einvoicing_invoice_sale"),
    )
    op.create_index("ix_einvoicing_invoices_tenant_id", "einvoicing_invoices", ["tenant_id"])
    op.create_index("ix_einvoicing_invoices_status", "einvoicing_invoices", ["tenant_id", "status"])
    op.create_index("ix_einvoicing_invoices_store", "einvoicing_invoices", ["tenant_id", "store_id"])
    op.create_table(
        "einvoicing_invoice_lines",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), sa.ForeignKey("einvoicing_invoices.id"), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(200), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("net_cents", sa.Integer(), nullable=False),
        sa.Column("tax_cents", sa.Integer(), nullable=False),
        sa.Column("tax_rate_bps", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "einvoicing_submissions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), sa.ForeignKey("einvoicing_invoices.id"), nullable=True),
        sa.Column("credit_note_id", sa.Uuid(), nullable=True),
        sa.Column("idempotency_key", sa.String(80), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_einvoicing_submission_key"),
    )
    op.create_table(
        "einvoicing_submission_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), sa.ForeignKey("einvoicing_submissions.id"), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("provider_status", sa.String(64), nullable=False, server_default=""),
        sa.Column("detail", sa.String(500), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "einvoicing_credit_notes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), sa.ForeignKey("stores.id"), nullable=True),
        sa.Column("invoice_id", sa.Uuid(), sa.ForeignKey("einvoicing_invoices.id"), nullable=False),
        sa.Column("source_return_id", sa.Uuid(), sa.ForeignKey("returns.id"), nullable=False),
        sa.Column("document_number", sa.String(40), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="AED"),
        sa.Column("net_cents", sa.Integer(), nullable=False),
        sa.Column("tax_cents", sa.Integer(), nullable=False),
        sa.Column("total_cents", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("provider_status", sa.String(64), nullable=False, server_default=""),
        sa.Column("provider_reference", sa.String(120), nullable=False, server_default=""),
        sa.Column("error_detail", sa.String(500), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "source_return_id", name="uq_einvoicing_credit_return"),
    )
    op.create_table(
        "einvoicing_outbox",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(500), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "kind", "source_id", name="uq_einvoicing_outbox_source"),
    )
    op.create_index("ix_einvoicing_outbox_status", "einvoicing_outbox", ["status", "created_at"])
    op.create_table(
        "einvoicing_webhook_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("provider_code", sa.String(32), nullable=False),
        sa.Column("event_id", sa.String(80), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "provider_code", "event_id", name="uq_einvoicing_webhook_event"),
    )
    op.create_table(
        "einvoicing_audit_logs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(48), nullable=False),
        sa.Column("subject_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("detail", sa.String(500), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_einvoicing_audit_logs_tenant", "einvoicing_audit_logs", ["tenant_id", "created_at"])
    for table in (
        "einvoicing_settings",
        "einvoicing_provider_accounts",
        "einvoicing_invoices",
        "einvoicing_invoice_lines",
        "einvoicing_submissions",
        "einvoicing_submission_attempts",
        "einvoicing_credit_notes",
        "einvoicing_outbox",
        "einvoicing_webhook_events",
        "einvoicing_audit_logs",
    ):
        _rls(table)


def downgrade() -> None:
    for table in (
        "einvoicing_audit_logs",
        "einvoicing_webhook_events",
        "einvoicing_outbox",
        "einvoicing_credit_notes",
        "einvoicing_submission_attempts",
        "einvoicing_submissions",
        "einvoicing_invoice_lines",
        "einvoicing_invoices",
        "einvoicing_provider_accounts",
        "einvoicing_settings",
    ):
        op.drop_table(table)
