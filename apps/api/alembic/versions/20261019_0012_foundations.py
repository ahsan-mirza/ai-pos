"""Foundations: VAT settings and product tax categories, open-price items, per-device credentials,
document numbering series with backfilled invoice / quotation / credit-note numbers, and sale-line
cost and description columns.

Revision ID: 20261019_0012
Revises: 20261019_0011
Create Date: 2026-10-19
"""

import re
import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "20261019_0012"
down_revision: str | None = "20261019_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUPER_ADMIN_ROLE_ID = uuid.UUID("00000000-0000-4000-8000-0000000000a1")
STORE_MANAGER_ROLE_ID = uuid.UUID("00000000-0000-4000-8000-0000000000a2")
NEW_PERMISSIONS = (
    "pos:open_price",
    "pos:below_floor_override",
    "pos:shift_manage",
    "reports:vat",
    "devices:manage",
    "cheques:manage",
    "warranty:manage",
    "replenishment:manage",
    "messaging:manage",
    "currencies:manage",
)
GRANTS = {SUPER_ADMIN_ROLE_ID: NEW_PERMISSIONS, STORE_MANAGER_ROLE_ID: NEW_PERMISSIONS}


def _series_code(code: str) -> str:
    return "-".join(re.findall(r"[A-Z0-9]+", code.upper())) or "STORE"


def _grant(bind: sa.engine.Connection, grants: dict[uuid.UUID, tuple[str, ...]]) -> None:
    roles = sa.table("roles", sa.column("id", sa.Uuid(as_uuid=True)))
    role_permissions = sa.table(
        "role_permissions", sa.column("role_id", sa.Uuid(as_uuid=True)), sa.column("permission", sa.String(64))
    )
    for role_id, permissions in grants.items():
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


def upgrade() -> None:
    op.add_column(
        "business_settings", sa.Column("vat_registered", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column("business_settings", sa.Column("trn", sa.String(length=15), nullable=True))
    op.add_column("business_settings", sa.Column("legal_name", sa.String(length=160), nullable=True))
    op.add_column("business_settings", sa.Column("legal_name_ar", sa.String(length=160), nullable=True))
    op.add_column(
        "business_settings", sa.Column("prices_include_vat", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column(
        "business_settings", sa.Column("standard_rate_bps", sa.Integer(), nullable=False, server_default="500")
    )
    # Registers already charged 5% on top of catalog prices; keep that behaviour, now enforced by the API.
    op.execute("UPDATE business_settings SET vat_registered = true")

    op.add_column("products", sa.Column("tax_category", sa.String(length=8), nullable=False, server_default="STANDARD"))
    op.add_column("products", sa.Column("is_open_price", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("stores", sa.Column("emirate", sa.String(length=16), nullable=True))

    op.create_table(
        "devices",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=12), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("key_hint", sa.String(length=12), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], name="fk_devices_store_id_stores"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name="fk_devices_created_by_id_users"),
        sa.UniqueConstraint("key_hash", name="uq_devices_key_hash"),
        sa.UniqueConstraint("store_id", "code", name="uq_devices_store_code"),
    )
    op.create_index("ix_devices_store_id", "devices", ["store_id"])

    sequences = op.create_table(
        "document_sequences",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("store_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("device_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("doc_type", sa.String(length=4), nullable=False),
        sa.Column("prefix", sa.String(length=40), nullable=False),
        sa.Column("last_value", sa.Integer(), nullable=False),
        sa.Column("gaps", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], name="fk_document_sequences_store_id_stores"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], name="fk_document_sequences_device_id_devices"),
        sa.UniqueConstraint("prefix", name="uq_document_sequences_prefix"),
        sa.CheckConstraint("last_value >= 0", name="ck_document_sequences_last_value_nonnegative"),
    )
    op.create_index("ix_document_sequences_store_id", "document_sequences", ["store_id"])
    op.create_index("ix_document_sequences_device_id", "document_sequences", ["device_id"])

    op.add_column("sales", sa.Column("invoice_number", sa.String(length=40), nullable=True))
    op.add_column("sales", sa.Column("device_id", sa.Uuid(as_uuid=True), nullable=True))
    op.create_unique_constraint("uq_sales_invoice_number", "sales", ["invoice_number"])
    op.create_foreign_key("fk_sales_device_id_devices", "sales", "devices", ["device_id"], ["id"])
    op.add_column("returns", sa.Column("credit_note_number", sa.String(length=40), nullable=True))
    op.create_unique_constraint("uq_returns_credit_note_number", "returns", ["credit_note_number"])

    op.add_column("sale_items", sa.Column("tax_rate_bps", sa.Integer(), nullable=True))
    op.add_column("sale_items", sa.Column("description", sa.String(length=160), nullable=True))
    op.add_column("sale_items", sa.Column("cost_cents", sa.Integer(), nullable=True))
    op.add_column("sale_items", sa.Column("cost_estimated", sa.Boolean(), nullable=False, server_default=sa.false()))

    bind = op.get_bind()
    now = datetime.now(UTC)
    codes = {row[0]: _series_code(row[1]) for row in bind.execute(sa.text("SELECT id, code FROM stores"))}
    counters: dict[tuple[uuid.UUID, str], int] = defaultdict(int)
    for sale_id, store_id, is_quote in bind.execute(
        sa.text("SELECT id, store_id, is_quote_proforma FROM sales ORDER BY created_at, id")
    ):
        doc = "QUO" if is_quote else "INV"
        counters[(store_id, doc)] += 1
        prefix = f"{codes[store_id]}-{'QUO' if is_quote else 'S'}"
        bind.execute(
            sa.text("UPDATE sales SET invoice_number = :number WHERE id = :id"),
            {"number": f"{prefix}-{counters[(store_id, doc)]:06d}", "id": sale_id},
        )
    for return_id, store_id in bind.execute(sa.text("SELECT id, store_id FROM returns ORDER BY created_at, id")):
        counters[(store_id, "CN")] += 1
        bind.execute(
            sa.text("UPDATE returns SET credit_note_number = :number WHERE id = :id"),
            {"number": f"{codes[store_id]}-CN-{counters[(store_id, 'CN')]:06d}", "id": return_id},
        )
    rows = []
    for store_id, code in codes.items():
        for doc, suffix in (("INV", "S"), ("QUO", "QUO"), ("CN", "CN"), ("Z", "Z"), ("PDC", "PDC")):
            rows.append(
                {
                    "id": uuid.uuid4(),
                    "store_id": store_id,
                    "device_id": None,
                    "doc_type": doc,
                    "prefix": f"{code}-{suffix}",
                    "last_value": counters[(store_id, doc)],
                    "gaps": 0,
                    "created_at": now,
                    "updated_at": now,
                }
            )
    if rows:
        op.bulk_insert(sequences, rows)
    _grant(bind, GRANTS)


def downgrade() -> None:
    quoted = ", ".join(f"'{item}'" for item in NEW_PERMISSIONS)
    op.execute(f"DELETE FROM role_permissions WHERE permission IN ({quoted})")
    for column in ("cost_estimated", "cost_cents", "description", "tax_rate_bps"):
        op.drop_column("sale_items", column)
    op.drop_constraint("uq_returns_credit_note_number", "returns", type_="unique")
    op.drop_column("returns", "credit_note_number")
    op.drop_constraint("fk_sales_device_id_devices", "sales", type_="foreignkey")
    op.drop_constraint("uq_sales_invoice_number", "sales", type_="unique")
    op.drop_column("sales", "device_id")
    op.drop_column("sales", "invoice_number")
    op.drop_table("document_sequences")
    op.drop_table("devices")
    op.drop_column("stores", "emirate")
    op.drop_column("products", "is_open_price")
    op.drop_column("products", "tax_category")
    for column in ("standard_rate_bps", "prices_include_vat", "legal_name_ar", "legal_name", "trn", "vat_registered"):
        op.drop_column("business_settings", column)
