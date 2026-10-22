"""Fashion till essentials: gift cards (GIFT_CARD store credits sold as a sale line), cashier discounts with a
reason and a per-role limit, final-sale items, and the per-business till rules (pos_policy); grants the retail
back-office permissions to the system manager roles.

Revision ID: 20261021_0059
Revises: 20261021_0058
Create Date: 2026-10-21
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261021_0059"
down_revision: str | None = "20261021_0058"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUPER_ADMIN_ROLE_ID = uuid.UUID("00000000-0000-4000-8000-0000000000a1")
STORE_MANAGER_ROLE_ID = uuid.UUID("00000000-0000-4000-8000-0000000000a2")
PERMISSIONS = ("gift_cards:manage", "tax_free:manage", "online_orders:manage")
# Managers approve bigger discounts than the business default; Super Admin approves any.
DISCOUNT_LIMITS = {SUPER_ADMIN_ROLE_ID: 10_000, STORE_MANAGER_ROLE_ID: 5_000}


def upgrade() -> None:
    with op.batch_alter_table("store_credits") as batch:
        batch.add_column(sa.Column("kind", sa.String(16), nullable=False, server_default="VOUCHER"))
        batch.add_column(sa.Column("issued_sale_id", sa.Uuid(as_uuid=True), nullable=True))
        batch.add_column(sa.Column("customer_id", sa.Uuid(as_uuid=True), nullable=True))
        batch.add_column(sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("note", sa.String(255), nullable=False, server_default=""))
        batch.create_foreign_key("fk_store_credits_issued_sale", "sales", ["issued_sale_id"], ["id"])
        batch.create_foreign_key("fk_store_credits_customer", "customers", ["customer_id"], ["id"])
        batch.create_index("ix_store_credits_kind", ["kind"])
        batch.create_index("ix_store_credits_issued_sale_id", ["issued_sale_id"])
        batch.create_index("ix_store_credits_customer_id", ["customer_id"])

    with op.batch_alter_table("sale_items") as batch:
        batch.add_column(sa.Column("manual_discount_cents", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("discount_reason", sa.String(32), nullable=True))
        batch.add_column(sa.Column("discount_approved_by_id", sa.Uuid(as_uuid=True), nullable=True))
        batch.add_column(sa.Column("gift_card_code", sa.String(32), nullable=True))
        batch.add_column(sa.Column("final_sale", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.create_foreign_key("fk_sale_items_discount_approver", "users", ["discount_approved_by_id"], ["id"])
        batch.create_unique_constraint("uq_sale_items_gift_card_code", ["gift_card_code"])

    with op.batch_alter_table("roles") as batch:
        batch.add_column(sa.Column("max_discount_bps", sa.Integer(), nullable=True))
    with op.batch_alter_table("products") as batch:
        batch.add_column(sa.Column("is_final_sale", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("business_settings") as batch:
        batch.add_column(sa.Column("pos_policy", sa.JSON(), nullable=True))

    bind = op.get_bind()
    roles = sa.table("roles", sa.column("id", sa.Uuid(as_uuid=True)), sa.column("max_discount_bps", sa.Integer()))
    role_permissions = sa.table(
        "role_permissions", sa.column("role_id", sa.Uuid(as_uuid=True)), sa.column("permission", sa.String(64))
    )
    for role_id, limit in DISCOUNT_LIMITS.items():
        bind.execute(roles.update().where(roles.c.id == role_id).values(max_discount_bps=limit))
    present = {row[0] for row in bind.execute(sa.select(roles.c.id))}
    for role_id in (SUPER_ADMIN_ROLE_ID, STORE_MANAGER_ROLE_ID):
        if role_id not in present:
            continue
        granted = {
            row[0]
            for row in bind.execute(sa.select(role_permissions.c.permission).where(role_permissions.c.role_id == role_id))
        }
        rows = [{"role_id": role_id, "permission": item} for item in PERMISSIONS if item not in granted]
        if rows:
            op.bulk_insert(role_permissions, rows)


def downgrade() -> None:
    role_permissions = sa.table("role_permissions", sa.column("permission", sa.String(64)))
    op.execute(role_permissions.delete().where(role_permissions.c.permission.in_(PERMISSIONS)))
    with op.batch_alter_table("business_settings") as batch:
        batch.drop_column("pos_policy")
    with op.batch_alter_table("products") as batch:
        batch.drop_column("is_final_sale")
    with op.batch_alter_table("roles") as batch:
        batch.drop_column("max_discount_bps")
    with op.batch_alter_table("sale_items") as batch:
        batch.drop_constraint("uq_sale_items_gift_card_code", type_="unique")
        batch.drop_constraint("fk_sale_items_discount_approver", type_="foreignkey")
        for column in ("final_sale", "gift_card_code", "discount_approved_by_id", "discount_reason"):
            batch.drop_column(column)
        batch.drop_column("manual_discount_cents")
    with op.batch_alter_table("store_credits") as batch:
        batch.drop_index("ix_store_credits_customer_id")
        batch.drop_index("ix_store_credits_issued_sale_id")
        batch.drop_index("ix_store_credits_kind")
        batch.drop_constraint("fk_store_credits_customer", type_="foreignkey")
        batch.drop_constraint("fk_store_credits_issued_sale", type_="foreignkey")
        for column in ("note", "voided_at", "expires_at", "customer_id", "issued_sale_id", "kind"):
            batch.drop_column(column)
