"""Keys that must be unique per store once every store shares one database.

Revision ID: 20261025_0072
Revises: 20261024_0071
Create Date: 2026-10-25

Currency codes, job names, and tax-authority names were primary keys. Two stores cannot both
keep a row called AED or gl_posting unless the tenant id is part of the key. The brand link
table gains a tenant id and the same row-level policy as the other operational tables.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261025_0072"
down_revision: str | None = "20261024_0071"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POLICY = (
    "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid "
    "OR current_setting('app.bypass_rls', true) = 'on') "
    "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid "
    "OR current_setting('app.bypass_rls', true) = 'on')"
)


def _pk_name(table: str) -> str:
    pk = sa.inspect(op.get_bind()).get_pk_constraint(table) or {}
    return pk.get("name") or f"{table}_pkey"


def _replace_pk(table: str, columns: list[str]) -> None:
    name = _pk_name(table)
    with op.batch_alter_table(table) as batch:
        batch.drop_constraint(name, type_="primary")
        batch.create_primary_key(f"pk_{table}", columns)


def _drop_fks_to(table: str, referred: str) -> None:
    for fk in sa.inspect(op.get_bind()).get_foreign_keys(table):
        if fk.get("referred_table") == referred and fk.get("name"):
            op.drop_constraint(fk["name"], table, type_="foreignkey")


def _rls(table: str) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'CREATE POLICY tenant_isolation ON "{table}" {POLICY}'))


def upgrade() -> None:
    _drop_fks_to("exchange_rates", "accepted_currencies")
    _replace_pk("accepted_currencies", ["tenant_id", "code"])
    op.create_foreign_key(
        "fk_exchange_rates_tenant_currency_accepted_currencies",
        "exchange_rates",
        "accepted_currencies",
        ["tenant_id", "currency"],
        ["tenant_id", "code"],
    )
    _replace_pk("scheduled_jobs", ["tenant_id", "name"])
    _replace_pk("e_invoice_chains", ["tenant_id", "authority"])
    _replace_pk("tax_authority_credentials", ["tenant_id", "authority"])

    op.add_column("sub_category_brands", sa.Column("tenant_id", sa.Uuid(), nullable=True))
    op.execute(
        sa.text(
            "UPDATE sub_category_brands SET tenant_id = ("
            "SELECT tenant_id FROM sub_categories WHERE sub_categories.id = sub_category_brands.sub_category_id)"
        )
    )
    op.execute(sa.text("DELETE FROM sub_category_brands WHERE tenant_id IS NULL"))
    op.alter_column("sub_category_brands", "tenant_id", nullable=False)
    _replace_pk("sub_category_brands", ["tenant_id", "sub_category_id", "brand_id"])
    _rls("sub_category_brands")

    op.add_column(
        "business_settings",
        sa.Column("cache_generation", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_table(
        "cache_invalidations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("cache_key", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_cache_invalidations"),
    )
    op.create_index("ix_cache_invalidations_tenant_id", "cache_invalidations", ["tenant_id"])
    _rls("cache_invalidations")

    op.create_index("ix_sales_tenant_store_created", "sales", ["tenant_id", "store_id", "created_at"])
    op.create_index(
        "ix_stock_movements_tenant_store_created",
        "stock_movements",
        ["tenant_id", "store_id", "created_at"],
    )
    op.create_index(
        "ix_sync_events_tenant_device_key",
        "sync_events",
        ["tenant_id", "device_id", "idempotency_key"],
    )
    op.create_index("ix_audit_logs_tenant_occurred", "audit_logs", ["tenant_id", "occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_tenant_occurred", table_name="audit_logs")
    op.drop_index("ix_sync_events_tenant_device_key", table_name="sync_events")
    op.drop_index("ix_stock_movements_tenant_store_created", table_name="stock_movements")
    op.drop_index("ix_sales_tenant_store_created", table_name="sales")
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text('DROP POLICY IF EXISTS tenant_isolation ON "cache_invalidations"'))
        op.execute(sa.text('DROP POLICY IF EXISTS tenant_isolation ON "sub_category_brands"'))
    op.drop_index("ix_cache_invalidations_tenant_id", table_name="cache_invalidations")
    op.drop_table("cache_invalidations")
    op.drop_column("business_settings", "cache_generation")
    _replace_pk("sub_category_brands", ["sub_category_id", "brand_id"])
    op.drop_column("sub_category_brands", "tenant_id")
    _replace_pk("tax_authority_credentials", ["authority"])
    _replace_pk("e_invoice_chains", ["authority"])
    _replace_pk("scheduled_jobs", ["name"])
    op.drop_constraint(
        "fk_exchange_rates_tenant_currency_accepted_currencies", "exchange_rates", type_="foreignkey"
    )
    _replace_pk("accepted_currencies", ["code"])
    op.create_foreign_key(
        "fk_exchange_rates_currency_accepted_currencies",
        "exchange_rates",
        "accepted_currencies",
        ["currency"],
        ["code"],
    )
