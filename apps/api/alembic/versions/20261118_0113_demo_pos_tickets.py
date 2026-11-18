"""Demo register flag and single-use POS enrollment tickets.

Revision ID: 20261118_0113
Revises: 20261114_0112
Create Date: 2026-11-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261118_0113"
down_revision: str | None = "20261114_0112"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "devices" in tables:
        columns = {column["name"] for column in inspector.get_columns("devices")}
        if "is_demo" not in columns:
            op.add_column(
                "devices",
                sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()),
            )
    if "demo_pos_tickets" not in tables and "devices" in tables:
        op.create_table(
            "demo_pos_tickets",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("tenant_id", sa.Uuid(), nullable=False),
            sa.Column("device_id", sa.Uuid(), nullable=False),
            sa.Column("code_hash", sa.String(length=64), nullable=False),
            sa.Column("application_scope", sa.String(length=16), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("used_by_machine", sa.String(length=120), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["device_id"],
                ["devices.id"],
                name="fk_demo_pos_tickets_device_id_devices",
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id", name="pk_demo_pos_tickets"),
            sa.UniqueConstraint("tenant_id", "code_hash", name="uq_demo_pos_tickets_code_hash"),
        )
        op.create_index("ix_demo_pos_tickets_tenant_id", "demo_pos_tickets", ["tenant_id"])
        op.create_index("ix_demo_pos_tickets_device_id", "demo_pos_tickets", ["device_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "demo_pos_tickets" in tables:
        op.drop_index("ix_demo_pos_tickets_device_id", table_name="demo_pos_tickets")
        op.drop_index("ix_demo_pos_tickets_tenant_id", table_name="demo_pos_tickets")
        op.drop_table("demo_pos_tickets")
    if "devices" in tables:
        columns = {column["name"] for column in inspector.get_columns("devices")}
        if "is_demo" in columns:
            op.drop_column("devices", "is_demo")
