"""Tax authority adapters: the business's authority, e-invoice records, invoice chain heads and signing credentials.

Revision ID: 20261020_0041
Revises: 20261020_0040
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261020_0041"
down_revision: str | None = "20261020_0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.add_column(
        "business_settings", sa.Column("tax_authority", sa.String(length=8), nullable=False, server_default="fta")
    )
    op.create_table(
        "e_invoices",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("authority", sa.String(length=8), nullable=False),
        sa.Column("source_type", sa.String(length=8), nullable=False),
        sa.Column("source_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("number", sa.String(length=40), nullable=False),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("document_uuid", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("counter", sa.Integer(), nullable=False),
        sa.Column("invoice_hash", sa.String(length=64), nullable=False),
        sa.Column("previous_hash", sa.String(length=128), nullable=False),
        sa.Column("qr", sa.Text(), nullable=False),
        sa.Column("xml", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("submission_mode", sa.String(length=12), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response", sa.JSON(), nullable=True),
        *timestamps(),
        sa.UniqueConstraint("source_type", "source_id", name="uq_e_invoices_source"),
        sa.UniqueConstraint("authority", "counter", name="uq_e_invoices_counter"),
        sa.UniqueConstraint("document_uuid", name="uq_e_invoices_document_uuid"),
    )
    op.create_index("ix_e_invoices_authority", "e_invoices", ["authority"])
    op.create_index("ix_e_invoices_source_id", "e_invoices", ["source_id"])
    op.create_index("ix_e_invoices_number", "e_invoices", ["number"])
    op.create_index("ix_e_invoices_status", "e_invoices", ["status"])
    op.create_table(
        "e_invoice_chains",
        sa.Column("authority", sa.String(length=8), primary_key=True),
        sa.Column("last_counter", sa.Integer(), nullable=False),
        sa.Column("last_hash", sa.String(length=128), nullable=False),
        *timestamps(),
    )
    op.create_table(
        "tax_authority_credentials",
        sa.Column("authority", sa.String(length=8), primary_key=True),
        sa.Column("environment", sa.String(length=12), nullable=False),
        sa.Column("private_key_encrypted", sa.Text(), nullable=False),
        sa.Column("certificate_pem", sa.Text(), nullable=False),
        *timestamps(),
    )


def downgrade() -> None:
    op.drop_table("tax_authority_credentials")
    op.drop_table("e_invoice_chains")
    for name in ("status", "number", "source_id", "authority"):
        op.drop_index(f"ix_e_invoices_{name}", table_name="e_invoices")
    op.drop_table("e_invoices")
    op.drop_column("business_settings", "tax_authority")
