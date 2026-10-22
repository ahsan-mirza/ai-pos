"""Audit trail: before/after snapshots, action types, request origin, reason notes, desktop event ids,
an audit:read permission, and a Postgres trigger that makes audit_logs append-only.

Revision ID: 20261019_0010
Revises: 20261019_0009
Create Date: 2026-10-19
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0010"
down_revision: str | None = "20261019_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSION = "audit:read"
SUPER_ADMIN_ROLE_ID = uuid.UUID("00000000-0000-4000-8000-0000000000a1")

IMMUTABLE_FUNCTION = """
CREATE OR REPLACE FUNCTION audit_logs_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs is append-only';
END;
$$ LANGUAGE plpgsql;
"""
IMMUTABLE_TRIGGER = """
CREATE TRIGGER audit_logs_append_only
BEFORE UPDATE OR DELETE ON audit_logs
FOR EACH ROW EXECUTE FUNCTION audit_logs_append_only();
"""


def upgrade() -> None:
    bind = op.get_bind()
    postgres = bind.dialect.name == "postgresql"

    op.drop_index("ix_audit_logs_actor_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_entity_id", table_name="audit_logs")
    with op.batch_alter_table("audit_logs") as batch:
        batch.drop_constraint("fk_audit_logs_actor_id_users", type_="foreignkey")
        batch.alter_column("actor_id", new_column_name="user_id", existing_type=sa.Uuid(as_uuid=True), nullable=True)
        batch.alter_column(
            "entity_type",
            new_column_name="target_entity",
            existing_type=sa.String(length=32),
            type_=sa.String(length=40),
        )
        batch.alter_column(
            "entity_id",
            new_column_name="target_entity_id",
            existing_type=sa.Uuid(as_uuid=True),
            nullable=True,
        )
        batch.add_column(sa.Column("action_type", sa.String(length=32), nullable=False, server_default="UPDATE"))
        batch.add_column(sa.Column("old_values", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("new_values", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("reason_notes", sa.Text(), nullable=True))
        batch.add_column(sa.Column("ip_address", sa.String(length=45), nullable=True))
        batch.add_column(sa.Column("client_device", sa.String(length=16), nullable=False, server_default="system"))
        batch.add_column(sa.Column("request_path", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("user_name", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("user_role", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("client_event_id", sa.Uuid(as_uuid=True), nullable=True))
        batch.add_column(sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key("fk_audit_logs_user_id_users", "users", ["user_id"], ["id"])
        batch.create_unique_constraint("uq_audit_logs_client_event_id", ["client_event_id"])

    op.execute("UPDATE audit_logs SET occurred_at = created_at")
    op.execute("UPDATE audit_logs SET action_type = 'REFUND_PROCESSED' WHERE action LIKE 'return.%'")
    op.execute("UPDATE audit_logs SET target_entity = 'Settings' WHERE target_entity = 'business_settings'")
    op.execute("UPDATE audit_logs SET target_entity = 'SaleReturn' WHERE target_entity = 'sale_return'")
    op.execute(
        "UPDATE audit_logs SET "
        "user_name = (SELECT full_name FROM users WHERE users.id = audit_logs.user_id), "
        "user_role = (SELECT roles.name FROM users JOIN roles ON roles.id = users.role_id "
        "WHERE users.id = audit_logs.user_id)"
    )
    with op.batch_alter_table("audit_logs") as batch:
        batch.alter_column("occurred_at", existing_type=sa.DateTime(timezone=True), nullable=False)
        batch.alter_column("action_type", existing_type=sa.String(length=32), server_default=None)

    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_target_entity", "audit_logs", ["target_entity"])
    op.create_index("ix_audit_logs_target_entity_id", "audit_logs", ["target_entity_id"])
    op.create_index("ix_audit_logs_action_type", "audit_logs", ["action_type"])
    op.create_index("ix_audit_logs_occurred_at", "audit_logs", ["occurred_at"])
    op.create_index("ix_audit_logs_action_type_occurred_at", "audit_logs", ["action_type", "occurred_at"])

    exists = bind.execute(sa.text("SELECT 1 FROM roles WHERE id = :id"), {"id": SUPER_ADMIN_ROLE_ID}).first()
    held = bind.execute(
        sa.text("SELECT 1 FROM role_permissions WHERE role_id = :id AND permission = :permission"),
        {"id": SUPER_ADMIN_ROLE_ID, "permission": PERMISSION},
    ).first()
    if exists and not held:
        bind.execute(
            sa.text("INSERT INTO role_permissions (role_id, permission) VALUES (:id, :permission)"),
            {"id": SUPER_ADMIN_ROLE_ID, "permission": PERMISSION},
        )

    if postgres:
        op.execute(IMMUTABLE_FUNCTION)
        op.execute(IMMUTABLE_TRIGGER)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS audit_logs_append_only ON audit_logs")
        op.execute("DROP FUNCTION IF EXISTS audit_logs_append_only()")
    op.execute(sa.text("DELETE FROM role_permissions WHERE permission = :permission").bindparams(permission=PERMISSION))
    for name in (
        "ix_audit_logs_action_type_occurred_at",
        "ix_audit_logs_occurred_at",
        "ix_audit_logs_action_type",
        "ix_audit_logs_target_entity_id",
        "ix_audit_logs_target_entity",
        "ix_audit_logs_user_id",
    ):
        op.drop_index(name, table_name="audit_logs")
    op.execute("DELETE FROM audit_logs WHERE user_id IS NULL OR target_entity_id IS NULL")
    with op.batch_alter_table("audit_logs") as batch:
        batch.drop_constraint("uq_audit_logs_client_event_id", type_="unique")
        batch.drop_constraint("fk_audit_logs_user_id_users", type_="foreignkey")
        for column in (
            "occurred_at",
            "client_event_id",
            "user_role",
            "user_name",
            "request_path",
            "client_device",
            "ip_address",
            "reason_notes",
            "new_values",
            "old_values",
            "action_type",
        ):
            batch.drop_column(column)
        batch.alter_column("target_entity_id", new_column_name="entity_id", existing_type=sa.Uuid(), nullable=False)
        batch.alter_column(
            "target_entity", new_column_name="entity_type", existing_type=sa.String(40), type_=sa.String(32)
        )
        batch.alter_column("user_id", new_column_name="actor_id", existing_type=sa.Uuid(), nullable=False)
        batch.create_foreign_key("fk_audit_logs_actor_id_users", "users", ["actor_id"], ["id"])
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_entity_id", "audit_logs", ["entity_id"])
