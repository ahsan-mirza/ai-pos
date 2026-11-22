"""Laundry service catalog, garment types, price lists, and workflow templates.

Revision ID: 20261121_0121
Revises: 20261119_0120
Create Date: 2026-11-21

Garments being cleaned are not stock. These tables do not change inventory quantities.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261121_0121"
down_revision: str | None = "20261119_0120"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "laundry_settings",
    "laundry_service_categories",
    "laundry_garment_types",
    "laundry_services",
    "laundry_service_garments",
    "laundry_price_lists",
    "laundry_price_rates",
    "laundry_workflow_templates",
    "laundry_branch_capacities",
)


def _policy(table: str) -> str:
    return f"""
    USING (
      tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
      OR app_owner_may_bypass('{table}'::regclass)
    )
    WITH CHECK (
      tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
      OR app_owner_may_bypass('{table}'::regclass)
    )
    """


def _rls(table: str) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))  # noqa: TID251
    op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))  # noqa: TID251
    op.execute(sa.text(f'CREATE POLICY tenant_isolation ON "{table}" {_policy(table)}'))  # noqa: TID251


def _drop_rls(table: str) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(sa.text(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"'))  # noqa: TID251
    op.execute(sa.text(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY'))  # noqa: TID251
    op.execute(sa.text(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY'))  # noqa: TID251


def upgrade() -> None:
    op.create_table(
        "laundry_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("operating_modes", sa.JSON(), nullable=False),
        sa.Column("tracking_mode", sa.String(length=16), nullable=False),
        sa.Column("weight_precision", sa.Integer(), nullable=False),
        sa.Column("express_daily_capacity", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("weight_precision >= 0 AND weight_precision <= 3", name="ck_laundry_settings_precision"),
        sa.CheckConstraint(
            "express_daily_capacity IS NULL OR express_daily_capacity >= 0",
            name="ck_laundry_settings_express",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_laundry_settings"),
        sa.UniqueConstraint("tenant_id", name="uq_laundry_settings_tenant"),
    )
    op.create_index("ix_laundry_settings_tenant_id", "laundry_settings", ["tenant_id"])
    op.create_table(
        "laundry_service_categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_laundry_service_categories"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_laundry_service_categories_code"),
    )
    op.create_index("ix_laundry_service_categories_tenant_id", "laundry_service_categories", ["tenant_id"])
    op.create_table(
        "laundry_garment_types",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_laundry_garment_types"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_laundry_garment_types_code"),
    )
    op.create_index("ix_laundry_garment_types_tenant_id", "laundry_garment_types", ["tenant_id"])
    op.create_table(
        "laundry_services",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("pricing_unit", sa.String(length=20), nullable=False),
        sa.Column("base_rate_cents", sa.Integer(), nullable=False),
        sa.Column("min_charge_cents", sa.Integer(), nullable=False),
        sa.Column("min_quantity", sa.Integer(), nullable=False),
        sa.Column("weight_precision", sa.Integer(), nullable=False),
        sa.Column("express_surcharge_cents", sa.Integer(), nullable=True),
        sa.Column("same_day_surcharge_cents", sa.Integer(), nullable=True),
        sa.Column("special_surcharge_cents", sa.Integer(), nullable=True),
        sa.Column("tax_category", sa.String(length=16), nullable=False),
        sa.Column("price_includes_tax", sa.Boolean(), nullable=False),
        sa.Column("allow_zero_rate", sa.Boolean(), nullable=False),
        sa.Column("turnaround_minutes", sa.Integer(), nullable=False),
        sa.Column("workflow_code", sa.String(length=40), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("base_rate_cents >= 0", name="ck_laundry_services_rate"),
        sa.CheckConstraint("min_charge_cents >= 0", name="ck_laundry_services_min_charge"),
        sa.CheckConstraint("min_quantity >= 0", name="ck_laundry_services_min_quantity"),
        sa.CheckConstraint("weight_precision >= 0 AND weight_precision <= 3", name="ck_laundry_services_precision"),
        sa.CheckConstraint("turnaround_minutes >= 0", name="ck_laundry_services_turnaround"),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["laundry_service_categories.id"],
            name="fk_laundry_services_category",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_laundry_services"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_laundry_services_code"),
    )
    op.create_index("ix_laundry_services_tenant_id", "laundry_services", ["tenant_id"])
    op.create_table(
        "laundry_service_garments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=False),
        sa.Column("garment_type_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["garment_type_id"],
            ["laundry_garment_types.id"],
            name="fk_laundry_service_garments_type",
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["laundry_services.id"],
            ondelete="CASCADE",
            name="fk_laundry_service_garments_service",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_laundry_service_garments"),
        sa.UniqueConstraint("tenant_id", "service_id", "garment_type_id", name="uq_laundry_service_garments"),
    )
    op.create_index("ix_laundry_service_garments_tenant_id", "laundry_service_garments", ["tenant_id"])
    op.create_table(
        "laundry_price_lists",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=True),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_laundry_price_lists_customer"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], name="fk_laundry_price_lists_store"),
        sa.PrimaryKeyConstraint("id", name="pk_laundry_price_lists"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_laundry_price_lists_code"),
    )
    op.create_index("ix_laundry_price_lists_tenant_id", "laundry_price_lists", ["tenant_id"])
    op.create_table(
        "laundry_price_rates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("price_list_id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=False),
        sa.Column("unit_price_cents", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("unit_price_cents >= 0", name="ck_laundry_price_rates_rate"),
        sa.ForeignKeyConstraint(
            ["price_list_id"],
            ["laundry_price_lists.id"],
            ondelete="CASCADE",
            name="fk_laundry_price_rates_list",
        ),
        sa.ForeignKeyConstraint(
            ["service_id"], ["laundry_services.id"], name="fk_laundry_price_rates_service"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_laundry_price_rates"),
        sa.UniqueConstraint("tenant_id", "price_list_id", "service_id", name="uq_laundry_price_rates_service"),
    )
    op.create_index("ix_laundry_price_rates_tenant_id", "laundry_price_rates", ["tenant_id"])
    op.create_table(
        "laundry_workflow_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("stages", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_laundry_workflow_templates"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_laundry_workflow_templates_code"),
    )
    op.create_index("ix_laundry_workflow_templates_tenant_id", "laundry_workflow_templates", ["tenant_id"])
    op.create_table(
        "laundry_branch_capacities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("express_daily_capacity", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "express_daily_capacity IS NULL OR express_daily_capacity >= 0",
            name="ck_laundry_branch_capacities_express",
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], name="fk_laundry_branch_capacities_store"),
        sa.PrimaryKeyConstraint("id", name="pk_laundry_branch_capacities"),
        sa.UniqueConstraint("tenant_id", "store_id", name="uq_laundry_branch_capacities"),
    )
    op.create_index("ix_laundry_branch_capacities_tenant_id", "laundry_branch_capacities", ["tenant_id"])
    for table in TABLES:
        _rls(table)


def downgrade() -> None:
    for table in reversed(TABLES):
        _drop_rls(table)
        op.drop_table(table)
