"""Bank accounts, imported statements and reconciliation, and the banking permission.

Revision ID: 20261020_0037
Revises: 20261020_0036
Create Date: 2026-10-20
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261020_0037"
down_revision: str | None = "20261020_0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUPER_ADMIN_ROLE_ID = uuid.UUID("00000000-0000-4000-8000-0000000000a1")
GRANTS = {SUPER_ADMIN_ROLE_ID: ("banking:manage",)}


def _grant(bind: sa.engine.Connection) -> None:
    roles = sa.table("roles", sa.column("id", sa.Uuid(as_uuid=True)))
    role_permissions = sa.table(
        "role_permissions", sa.column("role_id", sa.Uuid(as_uuid=True)), sa.column("permission", sa.String(64))
    )
    for role_id, permissions in GRANTS.items():
        if bind.execute(sa.select(roles.c.id).where(roles.c.id == role_id)).first() is None:
            continue
        held = {
            row[0]
            for row in bind.execute(
                sa.select(role_permissions.c.permission).where(role_permissions.c.role_id == role_id)
            )
        }
        missing = [{"role_id": role_id, "permission": item} for item in permissions if item not in held]
        if missing:
            op.bulk_insert(role_permissions, missing)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "bank_accounts",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("bank", sa.String(80), nullable=False),
        sa.Column("iban", sa.String(34), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
    )
    op.create_table(
        "bank_statements",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("account_id", sa.Uuid(as_uuid=True), sa.ForeignKey("bank_accounts.id"), nullable=False, index=True),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_format", sa.String(8), nullable=False),
        sa.Column("period_from", sa.Date(), nullable=True),
        sa.Column("period_to", sa.Date(), nullable=True),
        sa.Column("lines_imported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lines_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("imported_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        *_timestamps(),
    )
    op.create_table(
        "bank_statement_lines",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("account_id", sa.Uuid(as_uuid=True), sa.ForeignKey("bank_accounts.id"), nullable=False, index=True),
        sa.Column(
            "statement_id", sa.Uuid(as_uuid=True), sa.ForeignKey("bank_statements.id"), nullable=False, index=True
        ),
        sa.Column("booked_on", sa.Date(), nullable=False, index=True),
        sa.Column("description", sa.String(255), nullable=False, server_default=""),
        sa.Column("reference", sa.String(80), nullable=False, server_default=""),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("balance_cents", sa.Integer(), nullable=True),
        sa.Column("line_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="UNMATCHED", index=True),
        sa.Column("matched_key", sa.String(120), nullable=True),
        sa.Column("matched_label", sa.String(160), nullable=False, server_default=""),
        sa.Column("fee_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fee_expense_id", sa.Uuid(as_uuid=True), sa.ForeignKey("expenses.id"), nullable=True),
        sa.Column("matched_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("match_note", sa.String(255), nullable=False, server_default=""),
        *_timestamps(),
        sa.UniqueConstraint("account_id", "line_hash", name="uq_bank_statement_lines_hash"),
        sa.UniqueConstraint("account_id", "matched_key", name="uq_bank_statement_lines_matched"),
    )
    _grant(op.get_bind())


def downgrade() -> None:
    op.drop_table("bank_statement_lines")
    op.drop_table("bank_statements")
    op.drop_table("bank_accounts")
    op.execute("DELETE FROM role_permissions WHERE permission = 'banking:manage'")
