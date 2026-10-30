"""Variant signature, inherited prices, and an active flag.

Revision ID: 20261030_0087
Revises: 20261030_0086
Create Date: 2026-10-30

Existing variants are marked override so a later model price cannot rewrite prices already in the catalog.
Duplicate combinations abort the migration instead of deleting a product.
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261030_0087"
down_revision: str | None = "20261030_0086"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _signature(raw: object) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, dict):
        return None
    pairs: list[tuple[str, str]] = []
    for key, value in raw.items():
        name = str(key).strip().lower().replace(" ", "_")
        text = " ".join(str(value).split())
        if name and text:
            pairs.append((name, text.lower()))
    if not pairs:
        return None
    pairs.sort()
    return "|".join(f"{key}={value}" for key, value in pairs)


def upgrade() -> None:
    op.add_column("products", sa.Column("variant_signature", sa.String(length=400), nullable=True))
    op.add_column(
        "products",
        sa.Column("price_source", sa.String(length=16), nullable=False, server_default="override"),
    )
    op.add_column("products", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("product_models", sa.Column("default_price_cents", sa.Integer(), nullable=True))
    op.add_column(
        "product_models",
        sa.Column("price_rules", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "product_models",
        sa.Column("axis_swatches", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.create_check_constraint(
        "ck_products_price_source",
        "products",
        "price_source IN ('default', 'rule', 'override')",
    )

    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, sku, product_model_id, variant_attributes FROM products WHERE product_model_id IS NOT NULL")
    ).all()
    seen: dict[tuple[str, str], str] = {}
    duplicates: list[str] = []
    for row in rows:
        signature = _signature(row.variant_attributes)
        if signature is None:
            continue
        key = (str(row.product_model_id), signature)
        if key in seen:
            duplicates.append(f"{row.sku} matches {seen[key]}")
            continue
        seen[key] = str(row.sku)
        bind.execute(
            sa.text("UPDATE products SET variant_signature = :signature WHERE id = :id"),
            {"signature": signature, "id": row.id},
        )
    if duplicates:
        raise RuntimeError(
            "Variant combinations are not unique, so the signature index was not created: " + "; ".join(duplicates)
        )
    op.create_unique_constraint(
        "uq_products_model_variant",
        "products",
        ["tenant_id", "product_model_id", "variant_signature"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_products_model_variant", "products", type_="unique")
    op.drop_constraint("ck_products_price_source", "products", type_="check")
    op.drop_column("products", "is_active")
    op.drop_column("products", "price_source")
    op.drop_column("products", "variant_signature")
    op.drop_column("product_models", "axis_swatches")
    op.drop_column("product_models", "price_rules")
    op.drop_column("product_models", "default_price_cents")
