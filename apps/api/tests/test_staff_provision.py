import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.test_sync import event, push

from app.core.permissions import STORE_MANAGER_ROLE_ID
from app.core.security import hash_password
from app.models.staff_provisioning import StaffProvisioningEvent
from app.models.user import User

STORE = "00000000-0000-4000-8000-0000000000c1"
VERIFIER = "$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$c2FtcGxldmVyaWZpZXI"


def _admin(client) -> dict[str, str]:
    response = client.post("/api/v1/auth/login-password", json={"username": "admin", "password": "root-password-123"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _body(**overrides) -> dict:
    body = {
        "event_id": "staff-event-0001",
        "operation": "create",
        "user_id": str(uuid.uuid4()),
        "username": "nora.cashier",
        "full_name": "Nora Cashier",
        "email": "nora.cashier@staff.local",
        "store_id": STORE,
        "role_name": "Cashier",
        "pin_verifier": VERIFIER,
    }
    body.update(overrides)
    return body


def test_a_register_cannot_grant_super_admin_and_a_cashier_cannot_provision(client, session: Session) -> None:
    seeded = push(client, [event("o7-store", "store", {"id": STORE, "code": "O7", "name": "Staff", "currency": "USD"})])
    assert seeded.status_code == 200, seeded.text
    admin = _admin(client)
    refused = client.post("/api/v1/users/provision", headers=admin, json=_body(role_name="Super Admin"))
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "role_not_allowed"
    platform = client.post(
        "/api/v1/users/provision",
        headers=admin,
        json=_body(event_id="staff-event-0002", role_name="Platform Super Admin"),
    )
    assert platform.status_code == 403
    cashier = client.post(
        "/api/v1/auth/login-pin",
        json={"username": "cashier", "pin": "1357"},
        headers={"X-Api-Key": "test-api-key-value"},
    )
    assert cashier.status_code == 200, cashier.text
    blocked = client.post(
        "/api/v1/users/provision",
        headers={"Authorization": f"Bearer {cashier.json()['access_token']}"},
        json=_body(event_id="staff-event-0003"),
    )
    assert blocked.status_code == 403
    session.expire_all()
    rejected = session.scalars(select(StaffProvisioningEvent).where(StaffProvisioningEvent.status == "rejected")).all()
    assert len(rejected) >= 2
    assert all("1357" not in row.safe_message for row in rejected)


def test_provisioning_is_idempotent_and_a_changed_payload_conflicts(client, session: Session) -> None:
    seeded = push(
        client,
        [event("o7-store-b", "store", {"id": STORE, "code": "O7B", "name": "Staff B", "currency": "USD"})],
    )
    assert seeded.status_code == 200, seeded.text
    admin = _admin(client)
    body = _body(event_id="staff-event-1001", username="ida.cashier", email="ida.cashier@staff.local")
    first = client.post("/api/v1/users/provision", headers=admin, json=body)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "accepted"
    again = client.post("/api/v1/users/provision", headers=admin, json=body)
    assert again.status_code == 200, again.text
    assert again.json()["status"] == "duplicate"
    session.expire_all()
    assert session.scalar(select(User).where(User.username == "ida.cashier")).hashed_pin == VERIFIER
    changed = dict(body)
    changed["full_name"] = "Ida Changed"
    collision = client.post("/api/v1/users/provision", headers=admin, json=changed)
    assert collision.status_code == 409
    assert collision.json()["error"]["code"] == "provisioning_conflict"
    session.expire_all()
    assert session.scalar(select(User).where(User.username == "ida.cashier")).full_name == "Nora Cashier"
    plaintext = dict(body)
    plaintext["event_id"] = "staff-event-1002"
    plaintext["username"] = "plain.cashier"
    plaintext["email"] = "plain.cashier@staff.local"
    plaintext["user_id"] = str(uuid.uuid4())
    plaintext["pin_verifier"] = "1357"
    rejected = client.post("/api/v1/users/provision", headers=admin, json=plaintext)
    assert rejected.status_code == 422
    assert session.scalar(select(User).where(User.username == "plain.cashier")) is None


OTHER = "00000000-0000-4000-8000-0000000000c2"


def test_store_scope_seat_limit_disable_and_feed(client, session: Session, monkeypatch) -> None:
    seeded = push(
        client,
        [
            event("o7-store-c", "store", {"id": STORE, "code": "O7C", "name": "Staff C", "currency": "USD"}),
            event("o7-store-d", "store", {"id": OTHER, "code": "O7D", "name": "Other", "currency": "USD"}),
        ],
    )
    assert seeded.status_code == 200, seeded.text
    session.add(
        User(
            username="manager",
            email="manager@example.com",
            full_name="Floor Manager",
            hashed_password=hash_password("manager-pass-123"),
            is_active=True,
            store_id=uuid.UUID(STORE),
            role_id=uuid.UUID(STORE_MANAGER_ROLE_ID),
            has_pos_access=True,
            has_portal_access=True,
            token_version=0,
        )
    )
    session.commit()
    signed = client.post("/api/v1/auth/login-password", json={"username": "manager", "password": "manager-pass-123"})
    assert signed.status_code == 200, signed.text
    manager = {"Authorization": f"Bearer {signed.json()['access_token']}"}
    other_branch = client.post(
        "/api/v1/users/provision",
        headers=manager,
        json=_body(
            event_id="staff-event-2001",
            username="branch.cashier",
            email="branch.cashier@staff.local",
            store_id=OTHER,
        ),
    )
    assert other_branch.status_code == 403
    assert other_branch.json()["error"]["code"] == "store_scope"
    promoted = client.post(
        "/api/v1/users/provision",
        headers=manager,
        json=_body(
            event_id="staff-event-2002",
            username="peer.manager",
            email="peer.manager@staff.local",
            role_name="Store Manager",
        ),
    )
    assert promoted.status_code == 403
    assert promoted.json()["error"]["code"] == "role_not_allowed"

    monkeypatch.setattr("app.console.plan_limits.limit_value", lambda resource: 2 if resource == "staff" else None)
    admin = _admin(client)
    capped = client.post(
        "/api/v1/users/provision",
        headers=admin,
        json=_body(event_id="staff-event-2003", username="capped.cashier", email="capped.cashier@staff.local"),
    )
    assert capped.status_code == 409
    assert capped.json()["error"]["code"] == "plan_limit"
    session.expire_all()
    assert session.scalar(select(User).where(User.username == "capped.cashier")) is None

    monkeypatch.setattr("app.console.plan_limits.limit_value", lambda _resource: None)
    created = client.post(
        "/api/v1/users/provision",
        headers=admin,
        json=_body(event_id="staff-event-2004", username="live.cashier", email="live.cashier@staff.local"),
    )
    assert created.status_code == 200, created.text
    user_id = created.json()["user_id"]
    hidden = client.get("/api/v1/users/staff-feed", headers=admin)
    assert hidden.status_code == 401
    feed = client.get("/api/v1/users/staff-feed", headers={"X-Api-Key": "test-api-key-value"})
    assert feed.status_code == 200, feed.text
    names = [row["username"] for row in feed.json()["staff"]]
    assert names == ["live.cashier"]
    assert feed.json()["staff"][0]["pin_verifier"].startswith("$argon2id$")
    assert "1357" not in feed.text
    disabled = client.post(
        "/api/v1/users/provision",
        headers=admin,
        json=_body(event_id="staff-event-2005", operation="disable", user_id=user_id, username="live.cashier"),
    )
    assert disabled.status_code == 200, disabled.text
    session.expire_all()
    assert session.scalar(select(User).where(User.username == "live.cashier")).is_active is False
    again = client.post(
        "/api/v1/users/provision",
        headers=admin,
        json=_body(
            event_id="staff-event-2005",
            operation="disable",
            user_id=user_id,
            username="live.cashier",
            full_name="Changed After Disable",
        ),
    )
    assert again.status_code == 409
    session.expire_all()
    assert session.scalar(select(User).where(User.username == "live.cashier")).is_active is False
    pulled = client.get("/api/v1/users/staff-feed", headers={"X-Api-Key": "test-api-key-value"})
    assert pulled.json()["staff"][0]["is_active"] is False


def test_online_pin_login_verifies_an_argon2_verifier_and_user_lists_do_not_return_it(client) -> None:
    from argon2 import PasswordHasher

    seeded = push(
        client,
        [event("o7-store-e", "store", {"id": STORE, "code": "O7E", "name": "Staff E", "currency": "USD"})],
    )
    assert seeded.status_code == 200, seeded.text
    verifier = PasswordHasher().hash("2468")
    admin = _admin(client)
    created = client.post(
        "/api/v1/users/provision",
        headers=admin,
        json=_body(
            event_id="staff-event-3001",
            username="argon.cashier",
            email="argon.cashier@staff.local",
            pin_verifier=verifier,
        ),
    )
    assert created.status_code == 200, created.text
    signed = client.post(
        "/api/v1/auth/login-pin",
        json={"username": "argon.cashier", "pin": "2468"},
        headers={"X-Api-Key": "test-api-key-value"},
    )
    assert signed.status_code == 200, signed.text
    refused = client.post(
        "/api/v1/auth/login-pin",
        json={"username": "argon.cashier", "pin": "0000"},
        headers={"X-Api-Key": "test-api-key-value"},
    )
    assert refused.status_code == 401
    listed = client.get("/api/v1/users", headers=admin)
    assert listed.status_code == 200, listed.text
    assert verifier not in listed.text
    assert "$argon2" not in listed.text
