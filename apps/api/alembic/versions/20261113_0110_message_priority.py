"""Priority on outbound messages so a receipt is chosen ahead of a campaign.

Revision ID: 20261113_0110
Revises: 20261113_0109
Create Date: 2026-11-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261113_0110"
down_revision: str | None = "20261113_0109"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "outbound_messages" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("outbound_messages")}
    if "priority" not in columns:
        op.add_column(
            "outbound_messages",
            sa.Column("priority", sa.SmallInteger(), nullable=False, server_default="1"),
        )
        columns.add("priority")
    if "template_key" in columns:
        op.execute(
            "UPDATE outbound_messages SET priority = 3 "
            "WHERE template_key IN ('campaign', 'coupon_issued')"
        )
        op.execute(
            "UPDATE outbound_messages SET priority = 2 WHERE template_key IN "
            "('overdue_reminder', 'warranty_expiry', 'layaway_reminder', 'reorder_due', 'ai_agent')"
        )
    indexed = {"status", "priority", "next_attempt_at"}
    indexes = {index["name"] for index in inspector.get_indexes("outbound_messages")}
    if indexed <= columns and "ix_outbound_messages_priority" not in indexes:
        op.create_index(
            "ix_outbound_messages_priority",
            "outbound_messages",
            ["status", "priority", "next_attempt_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "outbound_messages" not in inspector.get_table_names():
        return
    indexes = {index["name"] for index in inspector.get_indexes("outbound_messages")}
    if "ix_outbound_messages_priority" in indexes:
        op.drop_index("ix_outbound_messages_priority", table_name="outbound_messages")
    columns = {column["name"] for column in inspector.get_columns("outbound_messages")}
    if "priority" in columns:
        op.drop_column("outbound_messages", "priority")
