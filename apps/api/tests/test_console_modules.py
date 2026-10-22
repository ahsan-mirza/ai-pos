from sqlalchemy import select
from tests.governance_support import platform  # noqa: F401

from app.tenancy.models import OperatorAuditLog, TenantModuleOverride

SERIALS = "/api/v1/inventory/serials"


def put_modules(stores, console, tenant_id: str, overrides: dict, reason: str = "Support ticket 42"):
    return stores.client.put(
        f"/api/v1/super-admin/tenants/{tenant_id}/modules",
        headers=console,
        json={"overrides": overrides, "reason": reason},
    )


def test_support_forces_modules_on_and_off_for_one_store(platform) -> None:  # noqa: F811
    console = platform.operator()
    alpha_id = platform.tenant_id("alpha")
    alpha, bravo = platform.headers("alpha"), platform.headers("bravo")
    assert platform.client.get(SERIALS, headers=alpha).status_code != 403

    off = put_modules(platform, console, alpha_id, {"serial_tracking": "off", "weighed_items": "on"})
    assert off.status_code == 200, off.text
    states = {row["key"]: row for row in off.json()}
    assert (states["serial_tracking"]["enabled"], states["serial_tracking"]["override"]) == (False, "off")
    assert states["weighed_items"]["enabled"] and not states["weighed_items"]["fits_type"]

    assert platform.client.get(SERIALS, headers=alpha).status_code == 403
    assert platform.client.get(SERIALS, headers=bravo).status_code != 403
    modules = platform.client.get("/api/v1/tenant/modules", headers=alpha).json()
    assert modules["managed"] == {"serial_tracking": "off", "weighed_items": "on"}
    assert "weighed_items" in modules["enabled"]

    # The store cannot undo what support set: its own selection leaves managed modules as they are.
    own = platform.client.put(
        "/api/v1/settings/profile",
        headers=alpha,
        json={"business_profile": "electronics_wholesale", "capabilities": ["loyalty", "serial_tracking"]},
    )
    assert own.status_code == 200, own.text
    assert "weighed_items" in own.json()["capabilities"] and "serial_tracking" not in own.json()["capabilities"]

    blocked = put_modules(platform, console, alpha_id, {"tables": "on", "open_orders": "off"})
    assert blocked.status_code == 422 and blocked.json()["error"]["code"] == "capability_dependencies"

    cleared = put_modules(platform, console, alpha_id, {"serial_tracking": None})
    assert cleared.status_code == 200
    assert platform.client.get("/api/v1/tenant/modules", headers=alpha).json()["managed"] == {"weighed_items": "on"}

    with platform.control() as db:
        assert [row.module_key for row in db.scalars(select(TenantModuleOverride))] == ["weighed_items"]
        actions = db.scalars(select(OperatorAuditLog.action).where(OperatorAuditLog.action == "tenant.modules")).all()
        assert len(actions) == 2

    assert put_modules(platform, {}, alpha_id, {"serial_tracking": "on"}).status_code == 401
    assert put_modules(platform, console, alpha_id, {"teleport": "on"}).status_code == 422
