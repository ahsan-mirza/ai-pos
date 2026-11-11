"""Tenant product attribute definitions and typed values.

Revision ID: 20261111_0104
Revises: 20261111_0103
Create Date: 2026-11-11

Existing products keep their specifications JSON. New rows are optional.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261111_0104"
down_revision: str | None = "20261111_0103"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_attribute_definitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("data_type", sa.String(length=16), nullable=False),
        sa.Column("unit", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("profiles", sa.JSON(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("searchable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("filterable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("origin", sa.String(length=16), nullable=False, server_default="custom"),
        sa.Column("template_key", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_product_attribute_definitions"),
        sa.UniqueConstraint("tenant_id", "key", name="uq_product_attribute_definitions_key"),
    )
    op.create_index("ix_product_attribute_definitions_tenant_id", "product_attribute_definitions", ["tenant_id"])
    op.create_table(
        "product_attribute_values",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("definition_id", sa.Uuid(), nullable=False),
        sa.Column("text_value", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("number_value", sa.Numeric(18, 4), nullable=True),
        sa.Column("bool_value", sa.Boolean(), nullable=True),
        sa.Column("date_value", sa.Date(), nullable=True),
        sa.Column("unit", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["definition_id"], ["product_attribute_definitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_product_attribute_values"),
        sa.UniqueConstraint("tenant_id", "product_id", "definition_id", name="uq_product_attribute_values_product"),
    )
    op.create_index("ix_product_attribute_values_tenant_id", "product_attribute_values", ["tenant_id"])
    op.create_index("ix_product_attribute_values_product_id", "product_attribute_values", ["product_id"])
    op.create_index("ix_product_attribute_values_definition_id", "product_attribute_values", ["definition_id"])


def downgrade() -> None:
    op.drop_table("product_attribute_values")
    op.drop_table("product_attribute_definitions")
