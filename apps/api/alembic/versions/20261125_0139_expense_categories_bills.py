"""Expense categories and one compressed bill per expense.

Revision ID: 20261125_0139
Revises: 20261125_0138
Create Date: 2026-11-25

Existing expense rows keep their category code. category_id stays null
until the application links a seeded category. No bill is invented for
an expense that never had one. Not applied to a protected database.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261125_0139"
down_revision: str | None = "20261125_0138"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "expense_categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("name_key", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_expense_categories_code"),
        sa.UniqueConstraint("tenant_id", "name_key", name="uq_expense_categories_name_key"),
    )
    op.create_index("ix_expense_categories_tenant_id", "expense_categories", ["tenant_id"])
    op.alter_column("expenses", "category", existing_type=sa.String(length=12), type_=sa.String(length=32))
    op.add_column("expenses", sa.Column("category_id", sa.Uuid(), nullable=True))
    op.create_index("ix_expenses_category_id", "expenses", ["category_id"])
    op.create_foreign_key("fk_expenses_category_id_expense_categories", "expenses", "expense_categories", ["category_id"], ["id"])
    op.create_table(
        "expense_attachments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("expense_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("file_name", sa.String(length=160), nullable=False),
        sa.Column("content_type", sa.String(length=80), nullable=False),
        sa.Column("original_size_bytes", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=180), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False, server_default="STORED"),
        sa.Column("uploaded_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["expense_id"], ["expenses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "expense_id", name="uq_expense_attachments_expense"),
    )
    op.create_index("ix_expense_attachments_tenant_id", "expense_attachments", ["tenant_id"])
    op.create_index("ix_expense_attachments_expense_id", "expense_attachments", ["expense_id"])
    op.create_index("ix_expense_attachments_store_id", "expense_attachments", ["store_id"])
    if op.get_bind().dialect.name != "postgresql":
        return
    policy = """
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    """
    for table in ("expense_categories", "expense_attachments"):
        op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'CREATE POLICY tenant_isolation ON "{table}" {policy}'))


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in ("expense_attachments", "expense_categories"):
            op.execute(sa.text(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"'))
            op.execute(sa.text(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY'))
            op.execute(sa.text(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY'))
    op.drop_index("ix_expense_attachments_store_id", table_name="expense_attachments")
    op.drop_index("ix_expense_attachments_expense_id", table_name="expense_attachments")
    op.drop_index("ix_expense_attachments_tenant_id", table_name="expense_attachments")
    op.drop_table("expense_attachments")
    op.drop_constraint("fk_expenses_category_id_expense_categories", "expenses", type_="foreignkey")
    op.drop_index("ix_expenses_category_id", table_name="expenses")
    op.drop_column("expenses", "category_id")
    op.alter_column("expenses", "category", existing_type=sa.String(length=32), type_=sa.String(length=12))
    op.drop_index("ix_expense_categories_tenant_id", table_name="expense_categories")
    op.drop_table("expense_categories")
