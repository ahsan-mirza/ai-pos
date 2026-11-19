"""Allow a pharmacy public demo on the registry.

Revision ID: control_0041
Revises: control_0040
Create Date: 2026-11-19

Downgrade restores the previous check. It fails if a pharmacy demo row is still present.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "control_0041"
down_revision: str | None = "control_0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW = (
    "demo_business_type IS NULL OR demo_business_type IN "
    "('restaurant', 'supermarket', 'electronics', 'fashion', 'pharmacy')"
)
_OLD = (
    "demo_business_type IS NULL OR demo_business_type IN "
    "('restaurant', 'supermarket', 'electronics', 'fashion')"
)


def _postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if _postgres():
        op.drop_constraint("ck_tenants_demo_business_type_known", "tenants", type_="check")
        op.create_check_constraint("ck_tenants_demo_business_type_known", "tenants", _NEW)


def downgrade() -> None:
    if _postgres():
        op.drop_constraint("ck_tenants_demo_business_type_known", "tenants", type_="check")
        op.create_check_constraint("ck_tenants_demo_business_type_known", "tenants", _OLD)
