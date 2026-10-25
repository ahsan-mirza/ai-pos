import uuid

from sqlalchemy import select
from tests.governance_support import platform  # noqa: F401

from app.models import Customer
from app.tenancy.models import OperatorAuditLog, Tenant, TenantChangeRequest

BASE = "/api/v1/super-admin/tenants"


def preflight(stores, console, tenant_id: str, target: str):
    return stores.client.post(
        f"{BASE}/{tenant_id}/migrate-business-type/preflight", headers=console, json={"target_profile": target}
    )


def migrate(stores, console, tenant_id: str, token: str, target: str = "cafe", **extra):
    body = {
        "target_profile": target,
        "preflight_token": token,
        "confirm_slug": "alpha",
        "reason": "Customer asked by ticket",
        **extra,
    }
    return stores.client.post(f"{BASE}/{tenant_id}/migrate-business-type", headers=console, json=body)


def test_business_type_migrates_only_after_clean_safety_checks(platform) -> None:  # noqa: F811
    admin = platform.operator()
    alpha_id = platform.tenant_id("alpha")

    with platform.session("alpha") as db:
        db.add(Customer(code="C-1", name="Owes us", current_balance_cents=5_000, customer_type="WHOLESALE"))
        db.commit()
    checked = preflight(platform, admin, alpha_id, "cafe")
    assert checked.status_code == 200, checked.text
    body = checked.json()
    assert "serial_tracking" in body["lost"] and "open_orders" in body["gained"]
    assert [check["code"] for check in body["blockers"]] == ["on_account_balances"]
    blocked = migrate(platform, admin, alpha_id, body["preflight_token"])
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "migration_blocked"

    with platform.session("alpha") as db:
        db.scalar(select(Customer)).current_balance_cents = 0
        db.commit()
    # The module diff itself did not change, so the same token still holds once the blocker is cleared.
    cleared = migrate(platform, admin, alpha_id, body["preflight_token"])
    assert cleared.status_code == 200, cleared.text

    # A token signed for another store never migrates this one.
    again = preflight(platform, admin, platform.tenant_id("bravo"), "grocery").json()
    assert migrate(platform, admin, alpha_id, again["preflight_token"], target="grocery").status_code == 409


def test_migration_needs_admin_matching_slug_and_resolves_the_request(platform) -> None:  # noqa: F811
    admin = platform.operator()
    support = platform.operator(email="desk@axizpos.com", role="SUPPORT")
    alpha_id = platform.tenant_id("alpha")
    alpha = platform.headers("alpha")
    request = platform.client.post(
        "/api/v1/tenant/change-requests",
        headers=alpha,
        json={"kind": "BUSINESS_TYPE", "requested_value": "grocery", "reason": "We sell groceries now"},
    ).json()
    token = preflight(platform, support, alpha_id, "grocery").json()["preflight_token"]
    assert migrate(platform, support, alpha_id, token, target="grocery").status_code == 403
    wrong = migrate(platform, admin, alpha_id, token, target="grocery", confirm_slug="bravo")
    assert wrong.status_code == 422 and wrong.json()["error"]["code"] == "confirm_mismatch"
    assert migrate(platform, admin, alpha_id, "123.deadbeef", target="grocery").status_code == 409

    done = migrate(platform, admin, alpha_id, token, target="grocery", change_request_id=request["id"])
    assert done.status_code == 200, done.text
    enabled = {row["key"] for row in done.json() if row["enabled"]}
    assert {"weighed_items", "fefo"} <= enabled and "serial_tracking" not in enabled

    modules = platform.client.get("/api/v1/tenant/modules", headers=alpha).json()
    assert (modules["business_profile"], modules["locked"]) == ("grocery", True)
    assert platform.client.get("/api/v1/inventory/serials", headers=alpha).status_code == 403

    with platform.control() as db:
        tenant = db.get(Tenant, uuid.UUID(alpha_id))
        assert tenant.profile == "grocery"
        resolved = db.get(TenantChangeRequest, uuid.UUID(request["id"]))
        assert resolved.status == "RESOLVED" and resolved.resolved_at is not None
        actions = set(db.scalars(select(OperatorAuditLog.action)).all())
        assert {"tenant.migration_preflight", "tenant.migrate_business_type"} <= actions
