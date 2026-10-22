"""Background job leases, customer messaging (templates, outbox, consent), and messaging settings.

Revision ID: 20261019_0017
Revises: 20261019_0016
Create Date: 2026-10-19
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0017"
down_revision: str | None = "20261019_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TEMPLATES = {
    "receipt": (
        "Digital receipt",
        "Your receipt {{invoice}}",
        "Thank you for shopping at {{store}}. Invoice {{invoice}}, total {{total}}. Keep this for returns and warranty.",
    ),
    "statement": (
        "Statement of account",
        "Statement of account, {{customer}}",
        "Dear {{customer}}, your balance with {{business}} is {{balance}} ({{overdue}} overdue). Please contact us with any questions.",
    ),
    "overdue_reminder": (
        "Overdue reminder",
        "Payment reminder: {{overdue}} overdue",
        "Dear {{customer}}, invoices totalling {{overdue}} are past due (oldest {{days}} days). Kindly arrange payment. Thank you, {{business}}.",
    ),
    "warranty_expiry": (
        "Warranty expiring",
        "Your warranty ends on {{expires}}",
        "Hi {{customer}}, the warranty on your {{product}} ({{serial}}) ends on {{expires}}. Ask us about extended cover.",
    ),
    "repair_ready": (
        "Repair ready",
        "Your device is ready",
        "Hi {{customer}}, your {{device}} (ticket {{ticket}}) is ready for collection at {{store}}.",
    ),
    "layaway_reminder": (
        "Layaway reminder",
        "Layaway {{number}} reminder",
        "Hi {{customer}}, {{balance}} is left on layaway {{number}}; goods are held until {{expires}}.",
    ),
}


def upgrade() -> None:
    op.create_table(
        "scheduled_jobs",
        sa.Column("name", sa.String(64), primary_key=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(120), nullable=True),
        sa.Column("last_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(12), nullable=True),
        sa.Column("last_result", sa.Text(), nullable=True),
        sa.Column("run_count", sa.Integer(), nullable=False, server_default="0"),
    )
    templates = op.create_table(
        "message_templates",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("key", sa.String(48), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False, server_default=""),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "outbound_messages",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("channel", sa.String(12), nullable=False, index=True),
        sa.Column("to_address", sa.String(254), nullable=False),
        sa.Column("customer_id", sa.Uuid(as_uuid=True), sa.ForeignKey("customers.id"), nullable=True, index=True),
        sa.Column("template_key", sa.String(48), nullable=True),
        sa.Column("subject", sa.String(200), nullable=False, server_default=""),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="QUEUED", index=True),
        sa.Column("provider", sa.String(24), nullable=True),
        sa.Column("provider_message_id", sa.String(120), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("dedupe_key", sa.String(160), nullable=True, unique=True),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column("attachment_kind", sa.String(24), nullable=True),
        sa.Column("attachment_ref", sa.String(64), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("whatsapp_opt_in", "sms_opt_in", "email_opt_in"):
        op.add_column("customers", sa.Column(column, sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("business_settings", sa.Column("messaging", sa.JSON(), nullable=True))
    op.add_column("business_settings", sa.Column("message_events", sa.JSON(), nullable=True))
    now = datetime.now(UTC)
    op.bulk_insert(
        templates,
        [
            {
                "id": uuid.uuid4(),
                "key": key,
                "name": name,
                "subject": subject,
                "body": body,
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
            for key, (name, subject, body) in TEMPLATES.items()
        ],
    )


def downgrade() -> None:
    op.drop_column("business_settings", "message_events")
    op.drop_column("business_settings", "messaging")
    for column in ("email_opt_in", "sms_opt_in", "whatsapp_opt_in"):
        op.drop_column("customers", column)
    op.drop_table("outbound_messages")
    op.drop_table("message_templates")
    op.drop_table("scheduled_jobs")
