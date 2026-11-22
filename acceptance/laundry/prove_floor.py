"""Drive the production engine on the disposable laundry API. Does not print secrets."""

from __future__ import annotations

import json
import os
import sys
import threading
import uuid
from pathlib import Path
from urllib import error, request

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))
os.chdir(ROOT / "apps" / "api")

API = "http://127.0.0.1:18082"
CHECK = {name: True for name in ("cleaning", "stain", "finishing", "ironing", "fabric", "buttons", "zippers", "tag", "order", "instructions")}
DRY = ["SORTING", "PRE_TREATMENT", "DRY_CLEANING", "FINISHING", "QUALITY_CHECK"]
WASH = ["SORTING", "WASHING", "DRYING", "FOLDING", "QUALITY_CHECK"]
TABLES = (
    "laundry_sorting_categories",
    "laundry_machines",
    "laundry_batches",
    "laundry_batch_items",
    "laundry_machine_cycles",
    "laundry_stage_events",
    "laundry_inspections",
    "laundry_rework_tasks",
    "laundry_incidents",
    "laundry_packing_scans",
)


def _call(method: str, path: str, token: str, body: dict | None = None) -> tuple[int, dict | list | str]:
    data = None if body is None else json.dumps(body).encode()
    req = request.Request(
        API + path,
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=30) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw) if raw else {}
    except error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = raw
        return exc.code, parsed


def _card(token: str, garment_id: str) -> dict:
    status, payload = _call("GET", f"/api/v1/laundry/production/garments/{garment_id}", token)
    if status != 200 or not isinstance(payload, dict):
        raise SystemExit(f"Garment read failed {status}")
    return payload["garment"]


def _move(token: str, garment: dict, target: str, workflow: str = "") -> dict:
    status, payload = _call(
        "POST",
        f"/api/v1/laundry/production/garments/{garment['id']}/transition",
        token,
        {
            "target": target,
            "version": garment["version"],
            "idempotency_key": str(uuid.uuid4()),
            "sorting_category": "mixed" if target == "SORTING" else "",
            "workflow_code": workflow,
        },
    )
    if status != 200 or not isinstance(payload, dict):
        raise SystemExit(f"Move to {target} failed {status} {payload}")
    return payload


def _advance(token: str, garment: dict, stages: list[str], workflow: str = "") -> dict:
    current = garment
    for index, stage in enumerate(stages):
        current = _move(token, current, stage, workflow if index == 0 else "")
    status, _inspection = _call(
        "POST",
        "/api/v1/laundry/production/inspections",
        token,
        {
            "garment_id": current["id"],
            "version": current["version"],
            "result": "PASS",
            "checklist": CHECK,
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    if status != 201:
        raise SystemExit(f"Inspection failed {status} {_inspection}")
    current = _card(token, current["id"])
    current = _move(token, current, "PACKING")
    status, scan = _call(
        "POST",
        "/api/v1/laundry/production/packing/scans",
        token,
        {
            "order_id": current["order_id"],
            "garment_id": current["id"],
            "bag_code": "BAG-1",
            "version": current["version"],
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    if status != 201:
        raise SystemExit(f"Packing scan failed {status} {scan}")
    return current


def _money(card: dict) -> dict:
    return {
        "total_cents": card["total_cents"],
        "tax_cents": card["tax_cents"],
        "amount_paid_cents": card["amount_paid_cents"],
        "balance_due_cents": card["balance_due_cents"],
        "tag_code": card["tag_code"],
        "id": card["id"],
    }


def main() -> None:
    from app.core.config import env_files, get_settings

    settings = get_settings()
    app_url = make_url(settings.database_url)
    if (
        app_url.host != "127.0.0.1"
        or app_url.port != 55821
        or app_url.username != "ai_pos_app"
        or app_url.database != "axizpos_laundry_acceptance"
    ):
        raise SystemExit("Refusing: database URL is not the disposable laundry application login.")
    loaded = [path.name for path in env_files() if path.exists()]
    if ".env" in loaded or ".env.inventory-acceptance" in loaded:
        raise SystemExit("Refusing: a developer or inventory env file is loaded.")

    status, login = _call(
        "POST",
        "/api/v1/auth/login-password",
        "",
        {"username": settings.admin_username, "password": settings.admin_password},
    )
    if status != 200 or not isinstance(login, dict):
        raise SystemExit(f"Login failed {status}")
    token = str(login["access_token"])
    status, orders = _call("GET", "/api/v1/laundry/orders", token)
    if status != 200 or not isinstance(orders, list):
        raise SystemExit("Order list failed")
    by_code = {}
    for row in orders:
        detail_status, detail = _call("GET", f"/api/v1/laundry/orders/{row['id']}", token)
        if detail_status == 200 and isinstance(detail, dict):
            by_code[detail["code"]] = detail

    processed = []
    for code, stages, workflow in (
        ("LD-7B77A286", DRY, ""),
        ("LD-9584F748", WASH, "WASH_FOLD"),
    ):
        order = by_code.get(code)
        if order is None or not order["garments"]:
            processed.append({"code": code, "result": "missing"})
            continue
        before = [_card(token, item["id"]) for item in order["garments"]]
        if any(item["stage"] != "TAGGED" for item in before):
            processed.append({"code": code, "result": "already_moved", "stages": [item["stage"] for item in before]})
            continue
        for index, garment in enumerate(before):
            _advance(token, garment, stages, workflow)
        status, ready = _call(
            "POST",
            f"/api/v1/laundry/production/orders/{order['id']}/packing/complete",
            token,
            {"idempotency_key": str(uuid.uuid4())},
        )
        if status != 200:
            raise SystemExit(f"Ready failed for {code} {status} {ready}")
        after = [_card(token, item["id"]) for item in before]
        processed.append(
            {
                "code": code,
                "before": [_money(item) for item in before],
                "after": [_money(item) for item in after],
                "status": after[-1]["operational_status"],
                "money_same": all(
                    before[index]["total_cents"] == after[index]["total_cents"]
                    and before[index]["tax_cents"] == after[index]["tax_cents"]
                    and before[index]["amount_paid_cents"] == after[index]["amount_paid_cents"]
                    and before[index]["balance_due_cents"] == after[index]["balance_due_cents"]
                    and before[index]["tag_code"] == after[index]["tag_code"]
                    and before[index]["id"] == after[index]["id"]
                    for index in range(len(before))
                ),
            }
        )

    race_order = next(item for item in by_code.values() if item["garments"])
    # A new order keeps the Phase 2.1 rows for the workflow walk above.
    shirt = race_order["garments"][0]["service_id"]
    created_status, created = _call(
        "POST",
        "/api/v1/laundry/orders",
        token,
        {
            "idempotency_key": f"race-{uuid.uuid4().hex[:8]}",
            "intake_store_id": race_order["intake_store_id"],
            "customer_id": race_order["customer_id"],
            "order_type": "WALK_IN",
            "garments": [{"service_id": shirt, "quantity": 1, "description": "Race shirt"}],
        },
    )
    if created_status != 201 or not isinstance(created, dict):
        raise SystemExit(f"Race order failed {created_status}")
    garment_id = created["garments"][0]["id"]
    results: list[int] = []

    def post_same() -> None:
        code, _payload = _call(
            "POST",
            f"/api/v1/laundry/production/garments/{garment_id}/transition",
            token,
            {
                "target": "SORTING",
                "version": 1,
                "idempotency_key": str(uuid.uuid4()),
                "sorting_category": "mixed",
            },
        )
        results.append(code)

    first = threading.Thread(target=post_same)
    second = threading.Thread(target=post_same)
    first.start()
    second.start()
    first.join()
    second.join()

    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        identity = conn.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")).one()
        forced = {
            name: bool(
                conn.execute(text("SELECT relforcerowsecurity FROM pg_class WHERE relname = :name"), {"name": name}).scalar()
            )
            for name in TABLES
        }
        missing = conn.execute(text("SELECT count(*) FROM laundry_stage_events")).scalar()
    control = create_engine(settings.control_database_url)
    with control.connect() as conn:
        tenants = dict(conn.execute(text("SELECT slug, id::text FROM tenants WHERE slug IN ('laundry-a', 'grocery-b')")).all())
    control.dispose()
    with engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": tenants["laundry-a"]})
        own = conn.execute(text("SELECT count(*) FROM laundry_stage_events")).scalar()
    with engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": tenants["grocery-b"]})
        foreign = conn.execute(text("SELECT count(*) FROM laundry_stage_events")).scalar()
        blocked = None
        try:
            conn.execute(
                text(
                    "INSERT INTO laundry_stage_events (id, tenant_id, garment_id, order_id, from_stage, to_stage, idempotency_key, reason, created_at) "
                    "VALUES (:id, :tenant, :garment, :order_id, 'TAGGED', 'SORTING', :key, '', now())"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "tenant": tenants["laundry-a"],
                    "garment": garment_id,
                    "order_id": created["id"],
                    "key": f"cross-{uuid.uuid4().hex[:8]}",
                },
            )
            conn.commit()
            blocked = "inserted"
        except Exception as exc:  # noqa: BLE001
            blocked = getattr(getattr(exc, "orig", None), "sqlstate", None) or type(exc).__name__
    engine.dispose()
    print(
        json.dumps(
            {
                "processed": processed,
                "race_codes": sorted(results),
                "role_super": identity[0],
                "role_bypass": identity[1],
                "rls_forced": all(forced.values()),
                "missing_context_events": missing,
                "laundry_events": own,
                "grocery_events": foreign,
                "cross_tenant_insert": blocked,
            }
        )
    )


if __name__ == "__main__":
    main()
