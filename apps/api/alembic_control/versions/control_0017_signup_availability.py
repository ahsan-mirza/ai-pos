"""Unique signup email and phone, plus a hold on a store address while it is provisioning.

Display names stay non-unique. Existing rows are kept; this migration fails closed if an email or
phone is already shared, instead of deleting a signup.

Revision ID: control_0017
Revises: control_0016
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "control_0017"
down_revision: str | None = "control_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_signup_requests_email", table_name="signup_requests")
    op.drop_index("ix_signup_requests_phone", table_name="signup_requests")
    op.create_unique_constraint("uq_signup_requests_email", "signup_requests", ["email"])
    op.create_unique_constraint("uq_signup_requests_phone", "signup_requests", ["phone"])
    op.create_table(
        "signup_slug_holds",
        sa.Column("slug", sa.String(32), primary_key=True),
        sa.Column("signup_id", sa.Uuid(as_uuid=True), sa.ForeignKey("signup_requests.id"), nullable=False),
    )
    op.create_index("ix_signup_slug_holds_signup_id", "signup_slug_holds", ["signup_id"])


def downgrade() -> None:
    op.drop_index("ix_signup_slug_holds_signup_id", table_name="signup_slug_holds")
    op.drop_table("signup_slug_holds")
    op.drop_constraint("uq_signup_requests_phone", "signup_requests", type_="unique")
    op.drop_constraint("uq_signup_requests_email", "signup_requests", type_="unique")
    op.create_index("ix_signup_requests_email", "signup_requests", ["email"])
    op.create_index("ix_signup_requests_phone", "signup_requests", ["phone"])
