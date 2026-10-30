"""Branch country and a tax profile that a sale can snapshot.

Revision ID: 20261030_0086
Revises: 20261029_0085
Create Date: 2026-10-30

Existing branches keep own=false, so they continue to use the business-wide tax settings.
No historical invoice is rewritten.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261030_0086"
down_revision: str | None = "20261029_0085"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("stores", sa.Column("country", sa.String(length=2), nullable=True))
    op.add_column("stores", sa.Column("city", sa.String(length=120), nullable=True))
    op.add_column("sales", sa.Column("tax_snapshot", sa.JSON(), nullable=True))
    op.create_table(
        "legal_entities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("legal_name", sa.String(length=160), nullable=True),
        sa.Column("legal_name_local", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_legal_entities"),
    )
    op.create_index("ix_legal_entities_tenant_id", "legal_entities", ["tenant_id"])
    op.create_table(
        "branch_tax_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("legal_entity_id", sa.Uuid(), nullable=True),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("region", sa.String(length=80), nullable=True),
        sa.Column("own", sa.Boolean(), nullable=False),
        sa.Column("registered", sa.Boolean(), nullable=False),
        sa.Column("registration_number", sa.String(length=32), nullable=True),
        sa.Column("secondary_registration_number", sa.String(length=32), nullable=True),
        sa.Column("legal_name", sa.String(length=160), nullable=True),
        sa.Column("legal_name_local", sa.String(length=160), nullable=True),
        sa.Column("prices_include_vat", sa.Boolean(), nullable=False),
        sa.Column("standard_rate_bps", sa.Integer(), nullable=False),
        sa.Column("tax_authority", sa.String(length=8), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("rate_confirmed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["legal_entity_id"],
            ["legal_entities.id"],
            name="fk_branch_tax_legal_entity",
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], name="fk_branch_tax_store"),
        sa.PrimaryKeyConstraint("id", name="pk_branch_tax_profiles"),
        sa.UniqueConstraint("tenant_id", "store_id", name="uq_branch_tax_store"),
    )
    op.create_index("ix_branch_tax_profiles_tenant_id", "branch_tax_profiles", ["tenant_id"])
    op.create_index("ix_branch_tax_profiles_store_id", "branch_tax_profiles", ["store_id"])


def downgrade() -> None:
    op.drop_index("ix_branch_tax_profiles_store_id", table_name="branch_tax_profiles")
    op.drop_index("ix_branch_tax_profiles_tenant_id", table_name="branch_tax_profiles")
    op.drop_table("branch_tax_profiles")
    op.drop_index("ix_legal_entities_tenant_id", table_name="legal_entities")
    op.drop_table("legal_entities")
    op.drop_column("sales", "tax_snapshot")
    op.drop_column("stores", "city")
    op.drop_column("stores", "country")
