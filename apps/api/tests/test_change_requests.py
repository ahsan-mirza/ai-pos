from sqlalchemy import select
from tests.governance_support import platform  # noqa: F401

from app.tenancy.models import Tenant, TenantChangeRequest


def test_tenants_file_change_requests_with_it_support(platform) -> None:  # noqa: F811
    headers = platform.headers("alpha")
    locked = platform.client.put(
        "/api/v1/settings/profile", headers=headers, json={"business_profile": "grocery", "capabilities": None}
    )
    assert locked.status_code == 409 and locked.json()["error"]["code"] == "business_type_locked"

    modules = platform.client.get("/api/v1/tenant/modules", headers=headers).json()
    assert modules["tenant_name"] == "Alpha Mobiles" and modules["locked"] is True

    same = {"kind": "BUSINESS_TYPE", "requested_value": "electronics_wholesale", "reason": "No change"}
    assert platform.client.post("/api/v1/tenant/change-requests", headers=headers, json=same).status_code == 422
    body = {"kind": "BUSINESS_TYPE", "requested_value": "grocery", "reason": "We now sell groceries too"}
    created = platform.client.post("/api/v1/tenant/change-requests", headers=headers, json=body)
    assert created.status_code == 201, created.text
    request = created.json()
    assert (request["status"], request["current_value"], request["requested_by_email"]) == (
        "PENDING",
        "electronics_wholesale",
        "admin@alpha.example",
    )
    assert request["snapshot"]["stores"] >= 0 and "sales" in request["snapshot"]
    again = platform.client.post("/api/v1/tenant/change-requests", headers=headers, json=body)
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_requested"

    module = {"kind": "MODULE", "requested_value": "weighed_items", "reason": "Scale at the deli"}
    assert platform.client.post("/api/v1/tenant/change-requests", headers=headers, json=module).status_code == 201

    listed = platform.client.get("/api/v1/tenant/change-requests", headers=headers).json()
    assert {item["kind"] for item in listed} == {"BUSINESS_TYPE", "MODULE"}
    bravo = platform.client.get("/api/v1/tenant/change-requests", headers=platform.headers("bravo")).json()
    assert bravo == []

    with platform.control() as control:
        alpha = control.scalar(select(Tenant).where(Tenant.slug == "alpha"))
        rows = control.scalars(select(TenantChangeRequest).where(TenantChangeRequest.tenant_id == alpha.id)).all()
        assert len(rows) == 2


def test_single_store_servers_fall_back_to_email(client) -> None:
    from wholesale_support import admin

    headers, _ = admin(client)
    body = {"kind": "BUSINESS_TYPE", "requested_value": "grocery", "reason": "We now sell groceries"}
    response = client.post("/api/v1/tenant/change-requests", headers=headers, json=body)
    assert response.status_code == 409 and response.json()["error"]["code"] == "support_contact"
    assert client.get("/api/v1/tenant/change-requests", headers=headers).json() == []
