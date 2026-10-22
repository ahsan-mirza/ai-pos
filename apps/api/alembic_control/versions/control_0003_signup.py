"""Self-service signup requests: account, one-time code, business type, store, and provisioning progress.

Revision ID: control_0003
Revises: control_0002
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "control_0003"
down_revision: str | None = "control_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "signup_requests",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("phone", sa.String(32), nullable=False),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("access_hash", sa.String(64), nullable=False),
        sa.Column("otp_hash", sa.String(64), nullable=True),
        sa.Column("otp_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("otp_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("otp_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("profile", sa.String(32), nullable=True),
        sa.Column("sub_type", sa.String(32), nullable=True),
        sa.Column("store_name", sa.String(120), nullable=True),
        sa.Column("slug", sa.String(32), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("country", sa.String(2), nullable=True),
        sa.Column("trn", sa.String(15), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING_OTP"),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("owner_username", sa.String(32), nullable=True),
        sa.Column("handoff_jti", sa.String(64), nullable=True),
        sa.Column("handoff_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("handoff_jti", name="uq_signup_requests_handoff_jti"),
    )
    op.create_index("ix_signup_requests_email", "signup_requests", ["email"])
    op.create_index("ix_signup_requests_phone", "signup_requests", ["phone"])
    op.create_index("ix_signup_requests_slug", "signup_requests", ["slug"])
    op.create_index("ix_signup_requests_status", "signup_requests", ["status"])


def downgrade() -> None:
    op.drop_table("signup_requests")
