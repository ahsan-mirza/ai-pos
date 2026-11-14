"""Feature access stays inside the authenticated store. A query parameter cannot choose the tenant."""

import uuid

import pytest
from tests.governance_support import platform  # noqa: F401

from app.console.billing import assign_free
from app.tenancy.models import Tenant

pytestmark = pytest.mark.usefixtures("platform")


def test_features_reject_a_missing_session_and_a_forged_tenant(platform) -> None:  # noqa: F811
    denied = platform.client.get("/api/v1/billing/features", headers={"X-Tenant-Domain": "alpha.axizpos.com"})
    assert denied.status_code == 401

    posted = platform.client.post("/api/v1/billing/features", headers=platform.headers("alpha"), json={})
    assert posted.status_code == 405

    with platform.control() as db:
        alpha = db.get(Tenant, uuid.UUID(platform.tenant_id("alpha")))
        assert alpha is not None
        assign_free(db, alpha)
        db.commit()

    alpha_body = platform.client.get(
        "/api/v1/billing/features",
        headers=platform.headers("alpha"),
        params={"tenant_id": platform.tenant_id("bravo")},
    )
    assert alpha_body.status_code == 200, alpha_body.text
    alpha_plans = {row["current_plan"] for row in alpha_body.json()["features"]}
    assert alpha_plans == {"FREE"}

    bravo_body = platform.client.get(
        "/api/v1/billing/features",
        headers=platform.headers("bravo"),
        params={"tenant_id": platform.tenant_id("alpha")},
    )
    assert bravo_body.status_code == 200, bravo_body.text
    bravo_plans = {row["current_plan"] for row in bravo_body.json()["features"]}
    assert "FREE" not in bravo_plans
    assert bravo_plans == {None}
