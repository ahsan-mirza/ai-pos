"""General ledger: accounts, journal entries and lines; bills for imported purchase batches; accounting permission.

Revision ID: 20261020_0039
Revises: 20261020_0038
Create Date: 2026-10-20
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261020_0039"
down_revision: str | None = "20261020_0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUPER_ADMIN_ROLE_ID = uuid.UUID("00000000-0000-4000-8000-0000000000a1")


def _grant(bind: sa.engine.Connection) -> None:
    roles = sa.table("roles", sa.column("id", sa.Uuid(as_uuid=True)))
    role_permissions = sa.table(
        "role_permissions", sa.column("role_id", sa.Uuid(as_uuid=True)), sa.column("permission", sa.String(64))
    )
    if bind.execute(sa.select(roles.c.id).where(roles.c.id == SUPER_ADMIN_ROLE_ID)).first() is None:
        return
    held = bind.execute(
        sa.select(role_permissions.c.permission).where(
            role_permissions.c.role_id == SUPER_ADMIN_ROLE_ID, role_permissions.c.permission == "accounting:manage"
        )
    ).first()
    if held is None:
        op.bulk_insert(role_permissions, [{"role_id": SUPER_ADMIN_ROLE_ID, "permission": "accounting:manage"}])


def upgrade() -> None:
    op.create_table(
        "gl_accounts",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(16), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("type", sa.String(10), nullable=False, index=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "journal_entries",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("number", sa.Integer(), nullable=False, unique=True),
        sa.Column("entry_date", sa.Date(), nullable=False, index=True),
        sa.Column("original_date", sa.Date(), nullable=True),
        sa.Column("journal", sa.String(12), nullable=False, index=True),
        sa.Column("reference", sa.String(80), nullable=False, server_default=""),
        sa.Column("memo", sa.String(255), nullable=False, server_default=""),
        sa.Column("source_ref", sa.String(120), nullable=True, index=True),
        sa.Column("fingerprint", sa.String(64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true(), index=True),
        sa.Column("reversal_of_id", sa.Uuid(as_uuid=True), sa.ForeignKey("journal_entries.id"), nullable=True),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "journal_lines",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "entry_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("journal_entries.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("account_id", sa.Uuid(as_uuid=True), sa.ForeignKey("gl_accounts.id"), nullable=False, index=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("debit_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("credit_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("memo", sa.String(255), nullable=False, server_default=""),
        sa.CheckConstraint("debit_cents >= 0 AND credit_cents >= 0", name="journal_line_nonnegative"),
        sa.CheckConstraint("(debit_cents = 0) <> (credit_cents = 0)", name="journal_line_one_side"),
    )
    op.add_column("business_settings", sa.Column("accounting", sa.JSON(), nullable=True))
    with op.batch_alter_table("supplier_bills") as batch:
        batch.add_column(sa.Column("purchase_batch_id", sa.Uuid(as_uuid=True), nullable=True))
        batch.create_foreign_key(
            "fk_supplier_bills_purchase_batch_id", "purchase_batches", ["purchase_batch_id"], ["id"]
        )
        batch.create_unique_constraint("uq_supplier_bills_purchase_batch_id", ["purchase_batch_id"])
    _grant(op.get_bind())


def downgrade() -> None:
    with op.batch_alter_table("supplier_bills") as batch:
        batch.drop_constraint("uq_supplier_bills_purchase_batch_id", type_="unique")
        batch.drop_constraint("fk_supplier_bills_purchase_batch_id", type_="foreignkey")
        batch.drop_column("purchase_batch_id")
    op.drop_column("business_settings", "accounting")
    op.drop_table("journal_lines")
    op.drop_table("journal_entries")
    op.drop_table("gl_accounts")
    op.execute("DELETE FROM role_permissions WHERE permission = 'accounting:manage'")
