"""Laundry production transitions, machines, packing, and conflicts."""

import uuid

from tests.test_laundry_orders import _login, _order, _ready

from app.core.permissions import CASHIER_ROLE_ID, STORE_MANAGER_ROLE_ID, SYSTEM_ROLES, Permission
from app.core.security import hash_password
from app.models.role import Role
from app.models.store import Store
from app.models.user import User
from app.tenancy.scoping import DEFAULT_TENANT_ID

CHECKLIST = {
    "cleaning": True,
    "stain": True,
    "finishing": True,
    "ironing": True,
    "fabric": True,
    "buttons": True,
    "zippers": True,
    "tag": True,
    "order": True,
    "instructions": True,
}
DRY = ["SORTING", "PRE_TREATMENT", "DRY_CLEANING", "FINISHING", "QUALITY_CHECK"]
WASH = ["SORTING", "WASHING", "DRYING", "FOLDING", "QUALITY_CHECK"]
FLOOR = {
    Permission.LAUNDRY_PRODUCTION_VIEW,
    Permission.LAUNDRY_PRODUCTION_SORT,
    Permission.LAUNDRY_PRODUCTION_PROCESS,
    Permission.LAUNDRY_PRODUCTION_FINISH,
    Permission.LAUNDRY_PRODUCTION_OVERRIDE,
    Permission.LAUNDRY_QUALITY_INSPECT,
    Permission.LAUNDRY_PACKING,
    Permission.LAUNDRY_INCIDENTS_REPORT,
    Permission.LAUNDRY_INCIDENTS_RESOLVE,
    Permission.LAUNDRY_MACHINES_OPERATE,
    Permission.LAUNDRY_MACHINES_CONFIGURE,
    Permission.LAUNDRY_BATCHES_MANAGE,
}


def test_floor_permissions_are_not_on_cashier_or_store_manager() -> None:
    roles = {role["id"]: set(role["permissions"]) for role in SYSTEM_ROLES}
    assert FLOOR.isdisjoint(roles[CASHIER_ROLE_ID])
    assert FLOOR.isdisjoint(roles[STORE_MANAGER_ROLE_ID])


def _card(client, headers, garment_id: str) -> dict:
    response = client.get(f"/api/v1/laundry/production/garments/{garment_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["garment"]


def _move(client, headers, garment: dict, target: str, **extra) -> dict:
    body = {
        "target": target,
        "version": garment["version"],
        "idempotency_key": extra.pop("idempotency_key", str(uuid.uuid4())),
        "sorting_category": extra.pop("sorting_category", "mixed" if target == "SORTING" else ""),
        "reason": extra.pop("reason", ""),
        "workflow_code": extra.pop("workflow_code", ""),
    }
    response = client.post(
        f"/api/v1/laundry/production/garments/{garment['id']}/transition",
        headers=headers,
        json=body,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _inspect(client, headers, garment: dict, result: str, stage: str = "") -> dict:
    response = client.post(
        "/api/v1/laundry/production/inspections",
        headers=headers,
        json={
            "garment_id": garment["id"],
            "version": garment["version"],
            "result": result,
            "checklist": CHECKLIST,
            "reason": "Stain remains" if result != "PASS" else "",
            "required_stage": stage,
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _pack(client, headers, garment: dict) -> dict:
    response = client.post(
        "/api/v1/laundry/production/packing/scans",
        headers=headers,
        json={
            "order_id": garment["order_id"],
            "garment_id": garment["id"],
            "bag_code": "BAG-1",
            "version": garment["version"],
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _ready_order(client, headers, garment: dict) -> dict:
    response = client.post(
        f"/api/v1/laundry/production/orders/{garment['order_id']}/packing/complete",
        headers=headers,
        json={"idempotency_key": str(uuid.uuid4())},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _new_order(client, headers, shirt, store, customer):
    created = client.post(
        "/api/v1/laundry/orders",
        headers=headers,
        json=_order(shirt["id"], str(store.id), str(customer.id), f"prod-{uuid.uuid4().hex[:8]}"),
    )
    assert created.status_code == 201, created.text
    order = created.json()
    garment = _card(client, headers, order["garments"][0]["id"])
    return order, garment


def _through(client, headers, garment: dict, stages: list[str], *, workflow: str = "") -> dict:
    current = garment
    for index, stage in enumerate(stages):
        extra = {"workflow_code": workflow} if index == 0 and workflow else {}
        current = _move(client, headers, current, stage, **extra)
    return current


def test_dry_clean_and_wash_fold_reach_ready_without_changing_money(client, session) -> None:
    headers = _login(client)
    shirt, _fold, store, customer = _ready(client, headers, session)
    dry_order, dry = _new_order(client, headers, shirt, store, customer)
    dry = _through(client, headers, dry, DRY)
    _inspect(client, headers, dry, "PASS")
    dry = _card(client, headers, dry["id"])
    dry = _move(client, headers, dry, "PACKING")
    _pack(client, headers, dry)
    finished = _ready_order(client, headers, dry)
    assert finished["operational_status"] == "READY_FOR_COLLECTION"
    assert finished["stage"] == "READY"
    assert finished["total_cents"] == dry_order["total_cents"]
    assert finished["tax_cents"] == dry_order["tax_cents"]
    assert finished["amount_paid_cents"] == dry_order["amount_paid_cents"]
    assert finished["balance_due_cents"] == dry_order["balance_due_cents"]
    assert finished["tag_code"] == dry["tag_code"]
    again = _ready_order(client, headers, dry)
    assert again["operational_status"] == "READY_FOR_COLLECTION"

    wash_order, wash = _new_order(client, headers, shirt, store, customer)
    wash = _through(client, headers, wash, WASH, workflow="WASH_FOLD")
    assert wash["workflow_code"] == "WASH_FOLD"
    _inspect(client, headers, wash, "PASS")
    wash = _card(client, headers, wash["id"])
    wash = _move(client, headers, wash, "PACKING")
    _pack(client, headers, wash)
    folded = _ready_order(client, headers, wash)
    assert folded["operational_status"] == "READY_FOR_COLLECTION"
    assert folded["total_cents"] == wash_order["total_cents"]
    assert folded["amount_paid_cents"] == wash_order["amount_paid_cents"]


def test_qc_failure_rework_and_a_second_pass(client, session) -> None:
    headers = _login(client)
    shirt, _fold, store, customer = _ready(client, headers, session)
    _order_body, garment = _new_order(client, headers, shirt, store, customer)
    garment = _through(client, headers, garment, DRY)
    failed = _inspect(client, headers, garment, "REWORK_REQUIRED", "PRE_TREATMENT")
    sent = _card(client, headers, garment["id"])
    assert sent["stage"] == "PRE_TREATMENT"
    assert sent["rework_count"] == 1
    assert sent["qc_result"] == "REWORK_REQUIRED"
    history = client.get(f"/api/v1/laundry/production/garments/{garment['id']}", headers=headers).json()
    assert len(history["inspections"]) == 1
    assert history["inspections"][0]["id"] == failed["id"]
    assert history["open_rework"]["required_stage"] == "PRE_TREATMENT"
    assert history["open_rework"]["status"] == "OPEN"
    blocked = client.post(
        f"/api/v1/laundry/production/orders/{garment['order_id']}/packing/complete",
        headers=headers,
        json={"idempotency_key": str(uuid.uuid4())},
    )
    assert blocked.status_code == 422
    garment = _through(client, headers, sent, ["DRY_CLEANING", "FINISHING", "QUALITY_CHECK"])
    _inspect(client, headers, garment, "PASS")
    garment = _card(client, headers, garment["id"])
    assert garment["qc_result"] == "PASS"
    assert (
        len(client.get(f"/api/v1/laundry/production/garments/{garment['id']}", headers=headers).json()["inspections"])
        == 2
    )
    garment = _move(client, headers, garment, "PACKING")
    _pack(client, headers, garment)
    ready = _ready_order(client, headers, garment)
    assert ready["operational_status"] == "READY_FOR_COLLECTION"


def test_unknown_replaced_and_duplicate_moves(client, session) -> None:
    headers = _login(client)
    shirt, _fold, store, customer = _ready(client, headers, session)
    order, garment = _new_order(client, headers, shirt, store, customer)
    missing = client.post("/api/v1/laundry/production/scan", headers=headers, json={"code": "LD-NO-SUCH-TAG"})
    assert missing.status_code == 404
    tag = order["tags"][0]
    replaced = client.post(
        f"/api/v1/laundry/tags/{tag['id']}/replace",
        headers=headers,
        json={"idempotency_key": "replace-floor-0001"},
    )
    assert replaced.status_code == 200, replaced.text
    old = client.post("/api/v1/laundry/production/scan", headers=headers, json={"code": tag["code"]})
    assert old.status_code == 409
    scanned = client.post("/api/v1/laundry/production/scan", headers=headers, json={"code": replaced.json()["code"]})
    assert scanned.status_code == 200, scanned.text
    assert scanned.json()["result"] == "valid"
    again = client.post("/api/v1/laundry/production/scan", headers=headers, json={"code": replaced.json()["code"]})
    assert again.json()["result"] == "already_scanned"
    key = "move-key-floor-01"
    first = _move(client, headers, garment, "SORTING", idempotency_key=key)
    replay = _move(client, headers, garment, "SORTING", idempotency_key=key)
    assert replay["version"] == first["version"]
    conflict = client.post(
        f"/api/v1/laundry/production/garments/{garment['id']}/transition",
        headers=headers,
        json={
            "target": "SORTING",
            "version": garment["version"],
            "idempotency_key": "move-key-floor-02",
            "sorting_category": "mixed",
        },
    )
    assert conflict.status_code == 409
    session.rollback()
    jumped = client.post(
        f"/api/v1/laundry/production/garments/{garment['id']}/transition",
        headers=headers,
        json={"target": "PACKING", "version": first["version"], "idempotency_key": "move-key-floor-03"},
    )
    assert jumped.status_code == 422


def test_machine_batch_capacity_and_reassignment(client, session) -> None:
    headers = _login(client)
    shirt, _fold, store, customer = _ready(client, headers, session)
    _order_body, garment = _new_order(client, headers, shirt, store, customer)
    garment = _move(client, headers, garment, "SORTING")
    machine = client.post(
        "/api/v1/laundry/production/machines",
        headers=headers,
        json={
            "code": "W1",
            "name": "Dry cleaner 1",
            "machine_type": "DRY_CLEANING",
            "store_id": str(store.id),
            "capacity": 1000,
            "capacity_unit": "G",
        },
    )
    assert machine.status_code == 201, machine.text
    other = client.post(
        "/api/v1/laundry/production/machines",
        headers=headers,
        json={
            "code": "W2",
            "name": "Dry cleaner 2",
            "machine_type": "DRY_CLEANING",
            "store_id": str(store.id),
            "capacity": 1000,
        },
    )
    assert other.status_code == 201, other.text
    batch = client.post(
        "/api/v1/laundry/production/batches",
        headers=headers,
        json={"store_id": str(store.id), "workflow_code": "DRY_CLEAN", "idempotency_key": "batch-key-floor-01"},
    )
    assert batch.status_code == 201, batch.text
    added = client.post(
        f"/api/v1/laundry/production/batches/{batch.json()['id']}/items",
        headers=headers,
        json={"garment_id": garment["id"], "version": batch.json()["version"]},
    )
    assert added.status_code == 200, added.text
    duplicate = client.post(
        f"/api/v1/laundry/production/batches/{batch.json()['id']}/items",
        headers=headers,
        json={"garment_id": garment["id"], "version": added.json()["version"]},
    )
    assert duplicate.status_code == 200
    second_batch = client.post(
        "/api/v1/laundry/production/batches",
        headers=headers,
        json={"store_id": str(store.id), "workflow_code": "DRY_CLEAN", "idempotency_key": "batch-key-floor-02"},
    )
    assert second_batch.status_code == 201, second_batch.text
    raced = client.post(
        f"/api/v1/laundry/production/batches/{second_batch.json()['id']}/items",
        headers=headers,
        json={"garment_id": garment["id"], "version": second_batch.json()["version"]},
    )
    assert raced.status_code == 409
    heavy = client.post(
        f"/api/v1/laundry/production/machines/{machine.json()['id']}/cycles",
        headers=headers,
        json={
            "batch_id": batch.json()["id"],
            "cycle_code": "cotton",
            "load_weight": 1001,
            "idempotency_key": "cycle-heavy-01",
        },
    )
    assert heavy.status_code == 422
    started = client.post(
        f"/api/v1/laundry/production/machines/{machine.json()['id']}/cycles",
        headers=headers,
        json={
            "batch_id": batch.json()["id"],
            "cycle_code": "cotton",
            "load_weight": 800,
            "idempotency_key": "cycle-ok-0001",
        },
    )
    assert started.status_code == 201, started.text
    busy = client.post(
        f"/api/v1/laundry/production/machines/{machine.json()['id']}/cycles",
        headers=headers,
        json={
            "batch_id": batch.json()["id"],
            "cycle_code": "cotton",
            "load_weight": 100,
            "idempotency_key": "cycle-ok-0002",
        },
    )
    assert busy.status_code == 409
    fault = client.post(
        f"/api/v1/laundry/production/cycles/{started.json()['id']}/fault",
        headers=headers,
        json={"reason": "Door lock failed", "idempotency_key": "cycle-fault-01"},
    )
    assert fault.status_code == 200, fault.text
    assert fault.json()["status"] == "FAILED"
    listed = client.get("/api/v1/laundry/production/machines", headers=headers)
    broken = next(row for row in listed.json() if row["id"] == machine.json()["id"])
    assert broken["status"] == "OUT_OF_SERVICE"
    fresh = client.get("/api/v1/laundry/production/batches", headers=headers).json()
    current = next(row for row in fresh if row["id"] == batch.json()["id"])
    moved = client.post(
        f"/api/v1/laundry/production/batches/{batch.json()['id']}/machine?machine_id={other.json()['id']}",
        headers=headers,
        json={"version": current["version"]},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["machine_id"] == other.json()["id"]
    assert moved.json()["item_count"] == 1
    still = _card(client, headers, garment["id"])
    assert still["id"] == garment["id"]
    assert still["total_cents"] == garment["total_cents"]


def test_incident_blocks_ready_and_does_not_refund(client, session) -> None:
    headers = _login(client)
    shirt, _fold, store, customer = _ready(client, headers, session)
    order, garment = _new_order(client, headers, shirt, store, customer)
    opened = client.post(
        "/api/v1/laundry/production/incidents",
        headers=headers,
        json={
            "order_id": order["id"],
            "garment_id": garment["id"],
            "kind": "DAMAGED",
            "description": "Button torn in process",
            "blocks_ready": True,
        },
    )
    assert opened.status_code == 201, opened.text
    held = _card(client, headers, garment["id"])
    assert held["hold"] is True
    assert held["amount_paid_cents"] == order["amount_paid_cents"]
    garment = _through(client, headers, held, DRY)
    refused = client.post(
        "/api/v1/laundry/production/inspections",
        headers=headers,
        json={
            "garment_id": garment["id"],
            "version": garment["version"],
            "result": "PASS",
            "checklist": CHECKLIST,
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert refused.status_code == 201, refused.text
    garment = _card(client, headers, garment["id"])
    blocked = client.post(
        f"/api/v1/laundry/production/garments/{garment['id']}/transition",
        headers=headers,
        json={"target": "PACKING", "version": garment["version"], "idempotency_key": str(uuid.uuid4())},
    )
    assert blocked.status_code == 422
    closed = client.post(
        f"/api/v1/laundry/production/incidents/{opened.json()['id']}/resolve",
        headers=headers,
        json={"status": "CLOSED", "resolution": "Rework agreed, no refund posted"},
    )
    assert closed.status_code == 200, closed.text
    released = _card(client, headers, garment["id"])
    assert released["hold"] is False
    assert released["amount_paid_cents"] == order["amount_paid_cents"]


def test_cashier_cannot_move_a_garment_and_production_is_not_an_offline_entity(client, session) -> None:
    headers = _login(client)
    shirt, _fold, store, customer = _ready(client, headers, session)
    _order_body, garment = _new_order(client, headers, shirt, store, customer)
    cashier_role = Role(name="Portal cashier", description="", is_system=False, tenant_id=DEFAULT_TENANT_ID)
    cashier_role.set_permissions({Permission.POS_ACCESS.value, Permission.PORTAL_ACCESS.value})
    session.add(cashier_role)
    session.flush()
    cashier = User(
        username="floorcashier",
        email="floorcashier@example.com",
        full_name="Floor Cashier",
        hashed_password=hash_password("sorter-pass-1"),
        is_active=True,
        store_id=store.id,
        role_id=cashier_role.id,
        has_pos_access=True,
        has_portal_access=True,
        tenant_id=DEFAULT_TENANT_ID,
    )
    session.add(cashier)
    session.commit()
    signed = client.post("/api/v1/auth/login-password", json={"username": "floorcashier", "password": "sorter-pass-1"})
    assert signed.status_code == 200, signed.text
    cashier_headers = {"Authorization": f"Bearer {signed.json()['access_token']}"}
    denied = client.post(
        f"/api/v1/laundry/production/garments/{garment['id']}/transition",
        headers=cashier_headers,
        json={
            "target": "SORTING",
            "version": garment["version"],
            "idempotency_key": str(uuid.uuid4()),
            "sorting_category": "mixed",
        },
    )
    assert denied.status_code == 403
    pushed = client.post(
        "/api/v1/sync/push",
        headers={"X-Api-Key": "test-api-key-value"},
        json={
            "device_id": "laundry-acceptance-01",
            "events": [
                {
                    "idempotency_key": "stage-offline-01",
                    "entity_type": "laundry_stage",
                    "operation": "upsert",
                    "payload": {"garment_id": garment["id"]},
                    "occurred_at": "2026-11-21T09:00:00Z",
                }
            ],
        },
    )
    assert pushed.status_code == 422
    other = Store(code="B", name="Shop B", currency="AED", tenant_id=DEFAULT_TENANT_ID)
    sorter_role = Role(name="Sorter only", description="", is_system=False, tenant_id=DEFAULT_TENANT_ID)
    sorter_role.set_permissions({Permission.LAUNDRY_PRODUCTION_SORT.value, Permission.PORTAL_ACCESS.value})
    session.add_all([other, sorter_role])
    session.flush()
    sorter = User(
        username="sorteronly",
        email="sorteronly@example.com",
        full_name="Sorter",
        hashed_password=hash_password("sorter-pass-1"),
        is_active=True,
        store_id=other.id,
        role_id=sorter_role.id,
        has_pos_access=True,
        has_portal_access=True,
        tenant_id=DEFAULT_TENANT_ID,
    )
    session.add(sorter)
    session.commit()
    sorter_login = client.post(
        "/api/v1/auth/login-password", json={"username": "sorteronly", "password": "sorter-pass-1"}
    )
    assert sorter_login.status_code == 200, sorter_login.text
    wrong_branch = client.post(
        "/api/v1/laundry/production/scan",
        headers={"Authorization": f"Bearer {sorter_login.json()['access_token']}"},
        json={"code": garment["tag_code"]},
    )
    assert wrong_branch.status_code == 403


def test_duplicate_packing_scan_is_rejected(client, session) -> None:
    headers = _login(client)
    shirt, _fold, store, customer = _ready(client, headers, session)
    _order_body, garment = _new_order(client, headers, shirt, store, customer)
    garment = _through(client, headers, garment, DRY)
    _inspect(client, headers, garment, "PASS")
    garment = _card(client, headers, garment["id"])
    garment = _move(client, headers, garment, "PACKING")
    _pack(client, headers, garment)
    garment = _card(client, headers, garment["id"])
    second = client.post(
        "/api/v1/laundry/production/packing/scans",
        headers=headers,
        json={
            "order_id": garment["order_id"],
            "garment_id": garment["id"],
            "bag_code": "BAG-2",
            "version": garment["version"],
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert second.status_code == 409
    session.rollback()
