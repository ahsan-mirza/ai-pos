"""Customer-care conversations for AxizReach. Does not change campaign or credit tables.

Revision ID: 20261105_0099
Revises: 20261105_0098
Create Date: 2026-11-05

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261105_0099"
down_revision: str | None = "20261105_0098"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POLICY = (
    "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid "
    "OR current_setting('app.bypass_rls', true) = 'on') "
    "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid "
    "OR current_setting('app.bypass_rls', true) = 'on')"
)

TABLES = (
    "reach_ai_agents",
    "reach_ai_knowledge",
    "reach_ai_conversations",
    "reach_ai_messages",
    "reach_ai_actions",
    "reach_ai_events",
    "reach_ai_usage",
)


def _rls(table: str) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'CREATE POLICY tenant_isolation ON "{table}" {POLICY}'))


def upgrade() -> None:
    op.create_table(
        "reach_ai_agents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("slot", sa.String(length=16), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("greeting", sa.String(length=300), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("tone", sa.String(length=24), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("product_help", sa.Boolean(), nullable=False),
        sa.Column("order_help", sa.Boolean(), nullable=False),
        sa.Column("action_detection", sa.Boolean(), nullable=False),
        sa.Column("handoff", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "slot", name="uq_reach_ai_agents_slot"),
    )
    op.create_index("ix_reach_ai_agents_tenant_id", "reach_ai_agents", ["tenant_id"])
    op.create_table(
        "reach_ai_knowledge",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reach_ai_knowledge_tenant_id", "reach_ai_knowledge", ["tenant_id"])
    op.create_table(
        "reach_ai_conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=False),
        sa.Column("customer_name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("handler", sa.String(length=8), nullable=False),
        sa.Column("priority", sa.String(length=8), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("intent", sa.String(length=24), nullable=False),
        sa.Column("assigned_user_id", sa.Uuid(), nullable=True),
        sa.Column("unread_count", sa.Integer(), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_preview", sa.String(length=180), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["reach_connections.id"]),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reach_ai_conversations_tenant_id", "reach_ai_conversations", ["tenant_id"])
    op.create_index("ix_reach_ai_conversations_connection_id", "reach_ai_conversations", ["connection_id"])
    op.create_index("ix_reach_ai_conversations_phone", "reach_ai_conversations", ["phone"])
    op.create_index("ix_reach_ai_conversations_status", "reach_ai_conversations", ["status"])
    op.create_table(
        "reach_ai_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("reply_to_id", sa.Uuid(), nullable=True),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("author", sa.String(length=12), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("provider_message_id", sa.String(length=120), nullable=True),
        sa.Column("outbound_message_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["reach_ai_conversations.id"]),
        sa.ForeignKeyConstraint(["outbound_message_id"], ["outbound_messages.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "provider_message_id", name="uq_reach_ai_messages_provider"),
        sa.UniqueConstraint("tenant_id", "reply_to_id", name="uq_reach_ai_messages_reply"),
    )
    op.create_index("ix_reach_ai_messages_tenant_id", "reach_ai_messages", ["tenant_id"])
    op.create_index("ix_reach_ai_messages_conversation_id", "reach_ai_messages", ["conversation_id"])
    op.create_index("ix_reach_ai_messages_status", "reach_ai_messages", ["status"])
    op.create_table(
        "reach_ai_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("dedupe_key", sa.String(length=80), nullable=False),
        sa.Column("category", sa.String(length=24), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(length=8), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("consequential", sa.Boolean(), nullable=False),
        sa.Column("assigned_user_id", sa.Uuid(), nullable=True),
        sa.Column("result", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["reach_ai_conversations.id"]),
        sa.ForeignKeyConstraint(["message_id"], ["reach_ai_messages.id"]),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "dedupe_key", name="uq_reach_ai_actions_dedupe"),
    )
    op.create_index("ix_reach_ai_actions_tenant_id", "reach_ai_actions", ["tenant_id"])
    op.create_index("ix_reach_ai_actions_conversation_id", "reach_ai_actions", ["conversation_id"])
    op.create_index("ix_reach_ai_actions_status", "reach_ai_actions", ["status"])
    op.create_table(
        "reach_ai_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("action_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("detail", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reach_ai_events_tenant_id", "reach_ai_events", ["tenant_id"])
    op.create_index("ix_reach_ai_events_conversation_id", "reach_ai_events", ["conversation_id"])
    op.create_table(
        "reach_ai_usage",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reach_ai_usage_tenant_id", "reach_ai_usage", ["tenant_id"])
    for table in TABLES:
        _rls(table)


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_index(f"ix_{table}_tenant_id", table_name=table)
        op.drop_table(table)
