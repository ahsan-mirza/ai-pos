"""Order list authorization. A closed module is 403. A missing permission is 403. Another branch is 403."""

import uuid

from tests.test_menu import enable
from tests.test_orders import line
from tests.test_returns import CASHIER_ID, STORE_ID, admin_token, bearer, device, seed_catalog

OTHER = "00000000-0000-4000-8000-000000000099"


def test_orders_stay_closed_until_the_module_is_on_and_then_follow_store_scope(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    headers = bearer(token)
    closed = client.get("/api/v1/orders", headers=headers, params={"store_id": STORE_ID})
    assert closed.status_code == 403, closed.text
    assert closed.json()["error"]["code"] == "capability_disabled"
    missing_while_closed = client.get("/api/v1/orders", headers=headers)
    assert missing_while_closed.status_code == 403, missing_while_closed.text
    assert missing_while_closed.json()["error"]["code"] == "capability_disabled"
    enable(client, token, "open_orders")
    missing = client.get("/api/v1/orders", headers=headers)
    assert missing.status_code == 422, missing.text
    profile = client.get("/api/v1/settings", headers=headers)
    assert profile.status_code == 200, profile.text
    assert profile.json()["business_profile"] == "restaurant"
    assert "open_orders" in profile.json()["capabilities"]
    listed = client.get("/api/v1/orders", headers=headers, params={"store_id": STORE_ID})
    assert listed.status_code == 200, listed.text
    assert listed.json() == []
    opened = client.post(
        "/api/v1/orders",
        headers=device(),
        json={
            "id": str(uuid.uuid4()),
            "store_id": STORE_ID,
            "covers": 2,
            "user_id": CASHIER_ID,
            "service_type": "TAKEAWAY",
            "items": [line()],
        },
    )
    assert opened.status_code == 201, opened.text
    again = client.get("/api/v1/orders", headers=headers, params={"store_id": STORE_ID})
    assert again.status_code == 200, again.text
    assert opened.json()["id"] in {item["id"] for item in again.json()}
    roles = client.get("/api/v1/roles", headers=headers)
    assert roles.status_code == 200, roles.text
    technician = next(role["id"] for role in roles.json() if role["name"] == "Technician")
    created = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": "o88.tech",
            "email": "o88.tech@example.com",
            "full_name": "O88 Tech",
            "role_id": technician,
            "store_id": STORE_ID,
            "password": "o88-tech-password",
            "pin": "8020",
            "has_pos_access": True,
        },
    )
    assert created.status_code == 201, created.text
    signed = client.post(
        "/api/v1/auth/login-pin",
        headers=device(),
        json={"username": "o88.tech", "pin": "8020"},
    )
    assert signed.status_code == 200, signed.text
    refused = client.get(
        "/api/v1/orders",
        headers=bearer(signed.json()["access_token"]),
        params={"store_id": STORE_ID},
    )
    assert refused.status_code == 403, refused.text
    assert refused.json()["error"]["code"] == "forbidden"
    manager = next(role["id"] for role in roles.json() if role["name"] == "Store Manager")
    made = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": "o88.manager",
            "email": "o88.manager@example.com",
            "full_name": "O88 Manager",
            "role_id": manager,
            "store_id": STORE_ID,
            "password": "o88-manager-password",
            "has_portal_access": True,
        },
    )
    assert made.status_code == 201, made.text
    session = client.post(
        "/api/v1/auth/login-password", json={"username": "o88.manager", "password": "o88-manager-password"}
    )
    assert session.status_code == 200, session.text
    other = client.get(
        "/api/v1/orders",
        headers=bearer(session.json()["access_token"]),
        params={"store_id": OTHER},
    )
    assert other.status_code == 403, other.text
    assert other.json()["error"]["code"] == "store_scope"
    cashier_role = next(role["id"] for role in roles.json() if role["name"] == "Cashier")
    till = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": "o89.till",
            "email": "o89.till@example.com",
            "full_name": "O89 Till",
            "role_id": cashier_role,
            "store_id": STORE_ID,
            "password": "o89-till-password",
            "pin": "8190",
            "has_pos_access": True,
        },
    )
    assert till.status_code == 201, till.text
    signed_till = client.post(
        "/api/v1/auth/login-pin",
        headers=device(),
        json={"username": "o89.till", "pin": "8190"},
    )
    assert signed_till.status_code == 200, signed_till.text
    own_orders = client.get(
        "/api/v1/orders",
        headers=bearer(signed_till.json()["access_token"]),
        params={"store_id": STORE_ID},
    )
    assert own_orders.status_code == 200, own_orders.text
    other_branch = client.get(
        "/api/v1/orders",
        headers=bearer(signed_till.json()["access_token"]),
        params={"store_id": OTHER},
    )
    assert other_branch.status_code == 403, other_branch.text
    assert other_branch.json()["error"]["code"] == "store_scope"
    anonymous = client.get("/api/v1/orders", params={"store_id": STORE_ID})
    assert anonymous.status_code == 401, anonymous.text
    super_admin = next(role["id"] for role in roles.json() if role["name"] == "Super Admin")
    bound = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": "o89.branchadmin",
            "email": "o89.branchadmin@example.com",
            "full_name": "O89 Branch Admin",
            "role_id": super_admin,
            "store_id": STORE_ID,
            "password": "o89-branch-admin-password",
            "has_portal_access": True,
        },
    )
    assert bound.status_code == 201, bound.text
    branch_session = client.post(
        "/api/v1/auth/login-password",
        json={"username": "o89.branchadmin", "password": "o89-branch-admin-password"},
    )
    assert branch_session.status_code == 200, branch_session.text
    refused_profile = client.put(
        "/api/v1/settings/profile",
        headers=bearer(branch_session.json()["access_token"]),
        json={"business_profile": "grocery", "capabilities": None},
    )
    assert refused_profile.status_code == 403, refused_profile.text
    assert "business-wide" in refused_profile.json()["error"]["message"]
