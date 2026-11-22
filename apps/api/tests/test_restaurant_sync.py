"""Menu and floor share the catalogue feed. A second dine-in on one table is a manager review, not a lost ticket."""

import uuid

from tests.test_orders import CASHIER_ID, STORE_ID, line, setup
from tests.test_returns import admin_id, admin_token, bearer, device, push
from tests.test_terminal_activation import _key

MARINA = "00000000-0000-4000-8000-0000000000b6"


def _till(client, headers, store_id: str, code: str) -> dict[str, str]:
    created = client.post(
        "/api/v1/devices", headers=headers, json={"store_id": store_id, "code": code, "name": code}
    )
    assert created.status_code == 201, created.text
    device_id = created.json()["device"]["id"]
    activated = client.post(
        "/api/v1/terminals/activate",
        json={"activation_key": _key(client, headers, device_id), "machine_name": code},
    )
    assert activated.status_code == 200, activated.text
    return {"X-Terminal-Token": activated.json()["device_token"]}


def _cursor(client, auth: dict[str, str]) -> str:
    started = client.post("/api/v1/terminals/bootstrap/sessions", headers=auth)
    assert started.status_code == 200, started.text
    page = client.get(
        f"/api/v1/terminals/bootstrap/sessions/{started.json()['session_id']}/pages",
        headers=auth,
        params={"dataset": "floor", "after_position": -1, "limit": 50},
    )
    assert page.status_code == 200, page.text
    assert page.json()["done"] is True
    return page.json()["cursor"]


def test_menu_reaches_both_branches_and_floor_stays_on_its_branch(client) -> None:
    token, _table = setup(client)
    headers = bearer(token)
    created = push(client, "store", {"id": MARINA, "code": "MARINA", "name": "Marina Restaurant", "currency": "USD"})
    assert created.status_code == 200, created.text
    downtown = _till(client, headers, STORE_ID, "DTA")
    marina = _till(client, headers, MARINA, "MRA")
    downtown_cursor = _cursor(client, downtown)
    marina_cursor = _cursor(client, marina)
    group = client.post(
        "/api/v1/menu/modifier-groups",
        headers=headers,
        json={
            "name": "Oat milk",
            "min_select": 0,
            "max_select": 1,
            "options": [{"name": "Oat", "price_delta_cents": 200}],
        },
    )
    assert group.status_code == 201, group.text
    area = client.post(
        "/api/v1/dining/areas", headers=headers, json={"store_id": MARINA, "name": "Marina Room"}
    )
    assert area.status_code == 201, area.text

    downtown_pull = client.get(
        "/api/v1/terminals/bootstrap/pull", headers=downtown, params={"cursor": downtown_cursor, "limit": 50}
    )
    assert downtown_pull.status_code == 200, downtown_pull.text
    downtown_body = downtown_pull.text
    assert "Oat milk" in downtown_body
    assert "Marina Room" not in downtown_body
    downtown_changes = downtown_pull.json()["changes"]
    assert any(change["operation"] == "omit" and change["dataset"] == "floor" for change in downtown_changes)

    marina_pull = client.get(
        "/api/v1/terminals/bootstrap/pull", headers=marina, params={"cursor": marina_cursor, "limit": 50}
    )
    assert marina_pull.status_code == 200, marina_pull.text
    assert "Marina Room" in marina_pull.text
    assert "Oat milk" in marina_pull.text


def test_same_table_conflict_is_reviewed_once_and_does_not_merge_bills(client) -> None:
    token, table = setup(client)
    headers = bearer(token)
    first = {
        "id": str(uuid.uuid4()),
        "store_id": STORE_ID,
        "table_id": table["id"],
        "covers": 2,
        "opened_by_id": CASHIER_ID,
        "opened_at": "2026-11-21T08:00:00Z",
        "items": [line()],
    }
    opened = client.post(
        "/api/v1/sync/push",
        headers=device(),
        json={
            "device_id": "till-a",
            "events": [
                {
                    "idempotency_key": f"order-{first['id']}",
                    "entity_type": "open_order",
                    "operation": "upsert",
                    "payload": first,
                    "occurred_at": "2026-11-21T08:00:00Z",
                }
            ],
        },
    )
    assert opened.status_code == 200, opened.text
    assert opened.json()["results"][0]["status"] == "applied"
    second_item = line()
    second = {
        "id": str(uuid.uuid4()),
        "store_id": STORE_ID,
        "table_id": table["id"],
        "covers": 1,
        "opened_by_id": CASHIER_ID,
        "opened_at": "2026-11-21T08:05:00Z",
        "items": [second_item],
    }
    event = {
        "idempotency_key": f"order-{second['id']}",
        "entity_type": "open_order",
        "operation": "upsert",
        "payload": second,
        "occurred_at": "2026-11-21T08:05:00Z",
    }
    held = client.post("/api/v1/sync/push", headers=device(), json={"device_id": "till-b", "events": [event]})
    assert held.status_code == 200, held.text
    conflict_id = held.json()["results"][0]["conflict_id"]
    again = client.post("/api/v1/sync/push", headers=device(), json={"device_id": "till-b", "events": [event]})
    assert again.json()["results"][0]["conflict_id"] == conflict_id
    listed = client.get("/api/v1/orders/table-conflicts", headers=headers, params={"store_id": STORE_ID})
    assert listed.status_code == 200, listed.text
    assert len(listed.json()) == 1
    assert listed.json()[0]["primary"]["id"] == first["id"]
    assert listed.json()[0]["conflicting"]["items"][0]["unit_price_cents"] == second_item["unit_price_cents"]
    refused = client.post(
        f"/api/v1/orders/table-conflicts/{conflict_id}/resolve",
        headers=headers,
        json={"user_id": CASHIER_ID, "decision": "void"},
    )
    assert refused.status_code == 403
    decided = client.post(
        f"/api/v1/orders/table-conflicts/{conflict_id}/resolve",
        headers=headers,
        json={"user_id": admin_id(client), "decision": "separate"},
    )
    assert decided.status_code == 200, decided.text
    primary = client.get(f"/api/v1/orders/{first['id']}", headers=device()).json()
    other = client.get(f"/api/v1/orders/{second['id']}", headers=device()).json()
    assert primary["status"] == "OPEN" and primary["table_id"] == table["id"]
    assert other["status"] == "OPEN" and other["service_type"] == "TAKEAWAY" and other["table_id"] is None
    assert other["items"][0]["id"] == second_item["id"]
    conflicts = client.get(
        "/api/v1/orders/table-conflicts",
        headers=bearer(admin_token(client)),
        params={"store_id": STORE_ID},
    )
    assert conflicts.json() == []
