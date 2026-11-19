"""Pharmacy recalls, supplier-return documents, and the recall foreign key.

Revision ID: 20261118_0116
Revises: 20261118_0115
Create Date: 2026-11-19

No stock quantities are updated. Grocery rows are not given a lot status.
recall_id values already stored on batch_items are kept; the new foreign key
accepts only nulls until a pharmacy_recalls row exists.

Severity has no vocabulary in the architecture report, so the column is a
32-character string with no check. Reason and source text are unbounded text
for the same reason.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261118_0116"
down_revision: str | None = "20261118_0115"
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


def _drop_rls(table: str) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(sa.text(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"'))
    op.execute(sa.text(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY'))


def upgrade() -> None:
    op.create_table(
        "pharmacy_recalls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("reference", sa.String(length=64), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("opened_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('OPEN', 'CONTAINED', 'CLOSED')",
            name="ck_pharmacy_recalls_status",
        ),
        sa.ForeignKeyConstraint(
            ["opened_by_id"],
            ["users.id"],
            name="fk_pharmacy_recalls_opened_by_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pharmacy_recalls"),
        sa.UniqueConstraint("tenant_id", "reference", name="uq_pharmacy_recalls_reference"),
    )
    op.create_index("ix_pharmacy_recalls_tenant_id", "pharmacy_recalls", ["tenant_id"])
    op.create_table(
        "pharmacy_recall_lots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("recall_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("manufacturer_lot", sa.String(length=64), nullable=False),
        sa.Column("batch_item_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(manufacturer_lot) >= 1 AND length(manufacturer_lot) <= 64",
            name="ck_pharmacy_recall_lots_manufacturer_lot",
        ),
        sa.ForeignKeyConstraint(
            ["recall_id"],
            ["pharmacy_recalls.id"],
            name="fk_pharmacy_recall_lots_recall_id_pharmacy_recalls",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_pharmacy_recall_lots_product_id_products",
        ),
        sa.ForeignKeyConstraint(
            ["batch_item_id"],
            ["batch_items.id"],
            name="fk_pharmacy_recall_lots_batch_item_id_batch_items",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pharmacy_recall_lots"),
    )
    op.create_index("ix_pharmacy_recall_lots_tenant_id", "pharmacy_recall_lots", ["tenant_id"])
    op.create_index("ix_pharmacy_recall_lots_recall", "pharmacy_recall_lots", ["tenant_id", "recall_id"])
    op.create_index(
        "ix_pharmacy_recall_lots_lot",
        "pharmacy_recall_lots",
        ["tenant_id", "product_id", "manufacturer_lot"],
    )
    op.create_table(
        "pharmacy_supplier_returns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("reference", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name="fk_pharmacy_supplier_returns_created_by_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pharmacy_supplier_returns"),
        sa.UniqueConstraint("tenant_id", "reference", name="uq_pharmacy_supplier_returns_reference"),
    )
    op.create_index("ix_pharmacy_supplier_returns_tenant_id", "pharmacy_supplier_returns", ["tenant_id"])
    op.create_table(
        "pharmacy_supplier_return_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("return_id", sa.Uuid(), nullable=False),
        sa.Column("batch_item_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity >= 1", name="ck_pharmacy_supplier_return_lines_quantity"),
        sa.ForeignKeyConstraint(
            ["return_id"],
            ["pharmacy_supplier_returns.id"],
            name="fk_supplier_return_lines_return_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["batch_item_id"],
            ["batch_items.id"],
            name="fk_pharmacy_supplier_return_lines_batch_item_id_batch_items",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_pharmacy_supplier_return_lines_product_id_products",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pharmacy_supplier_return_lines"),
    )
    op.create_index(
        "ix_pharmacy_supplier_return_lines_tenant_id",
        "pharmacy_supplier_return_lines",
        ["tenant_id"],
    )
    for table in (
        "pharmacy_recalls",
        "pharmacy_recall_lots",
        "pharmacy_supplier_returns",
        "pharmacy_supplier_return_lines",
    ):
        _rls(table)
    op.create_index("ix_batch_items_recall_id", "batch_items", ["recall_id"])
    op.create_foreign_key(
        "fk_batch_items_recall_id_pharmacy_recalls",
        "batch_items",
        "pharmacy_recalls",
        ["recall_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_batch_item_events_recall_id_pharmacy_recalls",
        "batch_item_events",
        "pharmacy_recalls",
        ["recall_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_batch_item_events_recall_id_pharmacy_recalls",
        "batch_item_events",
        type_="foreignkey",
    )
    op.drop_constraint("fk_batch_items_recall_id_pharmacy_recalls", "batch_items", type_="foreignkey")
    op.drop_index("ix_batch_items_recall_id", table_name="batch_items")
    for table in (
        "pharmacy_supplier_return_lines",
        "pharmacy_supplier_returns",
        "pharmacy_recall_lots",
        "pharmacy_recalls",
    ):
        _drop_rls(table)
    op.drop_index("ix_pharmacy_supplier_return_lines_tenant_id", table_name="pharmacy_supplier_return_lines")
    op.drop_table("pharmacy_supplier_return_lines")
    op.drop_index("ix_pharmacy_supplier_returns_tenant_id", table_name="pharmacy_supplier_returns")
    op.drop_table("pharmacy_supplier_returns")
    op.drop_index("ix_pharmacy_recall_lots_lot", table_name="pharmacy_recall_lots")
    op.drop_index("ix_pharmacy_recall_lots_recall", table_name="pharmacy_recall_lots")
    op.drop_index("ix_pharmacy_recall_lots_tenant_id", table_name="pharmacy_recall_lots")
    op.drop_table("pharmacy_recall_lots")
    op.drop_index("ix_pharmacy_recalls_tenant_id", table_name="pharmacy_recalls")
    op.drop_table("pharmacy_recalls")
