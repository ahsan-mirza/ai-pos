from sqlalchemy import select
from tests.governance_support import platform  # noqa: F401

from app.console.stats import collect_all
from app.core.config import get_settings
from app.models import Customer
from app.tenancy.models import OperatorAuditLog

BASE = "/api/v1/super-admin"


def test_directory_lists_stores_with_their_stats(platform) -> None:  # noqa: F811
    console = platform.operator()
    assert collect_all(get_settings()) == (2, 0)
    listed = platform.client.get(f"{BASE}/tenants", headers=console, params={"limit": 1})
    assert listed.status_code == 200, listed.text
    assert listed.headers["X-Total-Count"] == "2" and len(listed.json()) == 1
    rows = platform.client.get(f"{BASE}/tenants", headers=console).json()
    alpha = next(row for row in rows if row["slug"] == "alpha")
    assert (alpha["domain"], alpha["plan"], alpha["profile_label"]) == (
        "alpha.qios.ae",
        "standard",
        "Electronics & Wholesale",
    )
    assert alpha["stats"]["onboarded"] is True and alpha["stats"]["users"] == 1
    assert "serial_tracking" in alpha["stats"]["enabled_modules"]
    assert alpha["stats"]["db_size_bytes"] > 0

    found = platform.client.get(f"{BASE}/tenants", headers=console, params={"q": "brav"}).json()
    assert [row["slug"] for row in found] == ["bravo"]

    detail = platform.client.get(f"{BASE}/tenants/{alpha['id']}/details", headers=console)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["tenant"]["slug"] == "alpha" and body["unreachable"] is None
    assert next(row for row in body["modules"] if row["key"] == "serial_tracking")["enabled"] is True


def test_suspending_a_store_blocks_it_and_is_audited(platform) -> None:  # noqa: F811
    console = platform.operator()
    alpha_id = platform.tenant_id("alpha")
    suspended = platform.client.patch(
        f"{BASE}/tenants/{alpha_id}", headers=console, json={"status": "suspended", "plan": "pro", "reason": "Unpaid"}
    )
    assert suspended.status_code == 200 and (suspended.json()["status"], suspended.json()["plan"]) == (
        "suspended",
        "pro",
    )
    blocked = platform.client.get("/api/v1/tenant", headers={"X-Tenant-Domain": "alpha.qios.ae"})
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "tenant_suspended"
    # The console still reaches a suspended store.
    assert platform.client.get(f"{BASE}/tenants/{alpha_id}/details", headers=console).status_code == 200
    platform.client.patch(f"{BASE}/tenants/{alpha_id}", headers=console, json={"status": "active", "reason": "Paid"})
    assert platform.client.get("/api/v1/tenant", headers={"X-Tenant-Domain": "alpha.qios.ae"}).status_code == 200


def test_customer_records_are_break_glass(platform) -> None:  # noqa: F811
    admin = platform.operator()
    support = platform.operator(email="desk@qios.ae", role="SUPPORT")
    alpha_id = platform.tenant_id("alpha")
    with platform.session("alpha") as db:
        db.add(Customer(code="C-9", name="Sara Noor", phone="+971501234567", email="sara@example.com"))
        db.commit()
    url = f"{BASE}/tenants/{alpha_id}/customers"
    assert platform.client.get(url, headers=support).status_code == 422
    masked = platform.client.get(url, headers=support, params={"reason": "Ticket 77: duplicate account"})
    assert masked.status_code == 200, masked.text
    row = masked.json()[0]
    assert (row["phone"], row["email"]) == ("+971•••567", "sa•••@example.com")
    assert platform.client.get(url, headers=support, params={"reason": "Ticket 77", "reveal": True}).status_code == 403
    revealed = platform.client.get(url, headers=admin, params={"reason": "Ticket 77", "reveal": True}).json()
    assert revealed[0]["phone"] == "+971501234567"
    with platform.control() as db:
        views = db.scalars(select(OperatorAuditLog).where(OperatorAuditLog.action == "tenant.customers_viewed")).all()
        assert len(views) == 2 and {view.reason for view in views} == {"Ticket 77: duplicate account", "Ticket 77"}


def test_support_works_the_change_request_queue(platform) -> None:  # noqa: F811
    console = platform.operator()
    alpha = platform.headers("alpha")
    request = platform.client.post(
        "/api/v1/tenant/change-requests",
        headers=alpha,
        json={"kind": "MODULE", "requested_value": "weighed_items", "reason": "We sell loose nuts"},
    ).json()
    queue = platform.client.get(f"{BASE}/change-requests", headers=console, params={"status": "PENDING"}).json()
    assert [(item["id"], item["tenant_slug"]) for item in queue] == [(request["id"], "alpha")]
    rejected = platform.client.post(
        f"{BASE}/change-requests/{request['id']}/reject", headers=console, json={"notes": "Use the weighed plan"}
    )
    assert rejected.status_code == 200 and rejected.json()["status"] == "REJECTED"
    again = platform.client.post(
        f"{BASE}/change-requests/{request['id']}/resolve", headers=console, json={"notes": "x y z"}
    )
    assert again.status_code == 409
    mine = platform.client.get("/api/v1/tenant/change-requests", headers=alpha).json()
    assert mine[0]["status"] == "REJECTED" and mine[0]["resolution_notes"] == "Use the weighed plan"
