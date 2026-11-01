"""Evolution connections, recipients, templates, and the prepaid credit ledger.

Revision ID: 20261101_0095
Revises: 20261031_0094
Create Date: 2026-11-01

Existing reach_campaigns, messaging_channels, and reach_usage rows stay. This revision only adds tables.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261101_0095"
down_revision: str | None = "20261031_0094"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POLICY = (
    "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid "
    "OR current_setting('app.bypass_rls', true) = 'on') "
    "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid "
    "OR current_setting('app.bypass_rls', true) = 'on')"
)


def _rls(table: str) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'CREATE POLICY tenant_isolation ON "{table}" {POLICY}'))


def upgrade() -> None:
    op.create_table(
        "reach_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("instance_name", sa.String(length=80), nullable=False),
        sa.Column("phone_number", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("webhook_key", sa.String(length=80), nullable=False),
        sa.Column("last_error", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "instance_name", name="uq_reach_connections_instance"),
        sa.UniqueConstraint("tenant_id", "webhook_key", name="uq_reach_connections_webhook"),
    )
    op.create_index("ix_reach_connections_tenant_id", "reach_connections", ["tenant_id"])
    op.create_table(
        "reach_recipients",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), sa.ForeignKey("reach_campaigns.id"), nullable=False),
        sa.Column("customer_id", sa.Uuid(), sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("outbound_message_id", sa.Uuid(), sa.ForeignKey("outbound_messages.id"), nullable=True),
        sa.Column("connection_id", sa.Uuid(), sa.ForeignKey("reach_connections.id"), nullable=True),
        sa.Column("phone", sa.String(length=254), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("provider_message_id", sa.String(length=120), nullable=True),
        sa.Column("failure_reason", sa.String(length=500), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "outbound_message_id", name="uq_reach_recipients_message"),
    )
    op.create_index("ix_reach_recipients_tenant_id", "reach_recipients", ["tenant_id"])
    op.create_index("ix_reach_recipients_campaign_id", "reach_recipients", ["campaign_id"])
    op.create_index("ix_reach_recipients_status", "reach_recipients", ["status"])
    op.create_table(
        "reach_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("channel", sa.String(length=12), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("media_kind", sa.String(length=24), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_reach_templates_name"),
    )
    op.create_index("ix_reach_templates_tenant_id", "reach_templates", ["tenant_id"])
    op.create_table(
        "reach_credit_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=24), nullable=False),
        sa.Column("balance", sa.Integer(), nullable=False),
        sa.Column("reserved", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "purpose", name="uq_reach_credit_accounts_purpose"),
    )
    op.create_index("ix_reach_credit_accounts_tenant_id", "reach_credit_accounts", ["tenant_id"])
    op.create_table(
        "reach_credit_transactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("reach_credit_accounts.id"), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=80), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=True),
        sa.Column("outbound_message_id", sa.Uuid(), nullable=True),
        sa.Column("note", sa.String(length=300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_reach_credit_tx_key"),
    )
    op.create_index("ix_reach_credit_transactions_tenant_id", "reach_credit_transactions", ["tenant_id"])
    op.create_table(
        "reach_webhook_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), sa.ForeignKey("reach_connections.id"), nullable=False),
        sa.Column("event_key", sa.String(length=120), nullable=False),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "event_key", name="uq_reach_webhook_events_key"),
    )
    op.create_index("ix_reach_webhook_events_tenant_id", "reach_webhook_events", ["tenant_id"])
    for table in (
        "reach_connections",
        "reach_recipients",
        "reach_templates",
        "reach_credit_accounts",
        "reach_credit_transactions",
        "reach_webhook_events",
    ):
        _rls(table)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in (
            "reach_webhook_events",
            "reach_credit_transactions",
            "reach_credit_accounts",
            "reach_templates",
            "reach_recipients",
            "reach_connections",
        ):
            op.execute(sa.text(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"'))
    op.drop_table("reach_webhook_events")
    op.drop_table("reach_credit_transactions")
    op.drop_table("reach_credit_accounts")
    op.drop_table("reach_templates")
    op.drop_table("reach_recipients")
    op.drop_table("reach_connections")
