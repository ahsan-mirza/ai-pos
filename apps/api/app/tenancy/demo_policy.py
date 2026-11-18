"""Which tenants count as commercial customers.

Demo stores stay in `active_tenants()` so their own jobs still run. Revenue, subscription
counts, trial expiry, and platform messaging use this filter instead.
"""

from sqlalchemy import ColumnElement

from app.tenancy.models import Tenant


def commercial_tenant() -> ColumnElement[bool]:
    """True for a real customer. Demo rows are false, including a row left at the default."""
    return Tenant.is_demo.is_(False)
