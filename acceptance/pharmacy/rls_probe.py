"""Tenant isolation as the non-superuser application role.

Connects with the acceptance application URL. Does not print the password.
Reads and attempted writes run inside a transaction that is rolled back.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
API = ROOT / "apps" / "api"
EVIDENCE = HERE / "evidence"
sys.path.insert(0, str(API))
sys.path.insert(0, str(HERE))
os.environ["APP_ENV"] = "acceptance"

from sqlalchemy import create_engine, text

from app.core.config import get_settings
from exercise import Api, _expect, _login

TABLES = (
    "batch_items",
    "batch_item_events",
    "pharmacist_authorizations",
    "pharmacy_governance_officers",
    "pharmacy_recalls",
    "pharmacy_recall_lots",
    "pharmacy_supplier_returns",
    "pharmacy_supplier_return_lines",
)


def _result(results: list[dict], name: str, passed: bool, detail: str) -> None:
    results.append({"name": name, "status": "passed" if passed else "failed", "detail": detail})
    print(f"{'PASS' if passed else 'FAIL'} {name}: {detail}")


def _seed_b(results: list[dict]) -> str | None:
    """Give pharmacy tenant B its own lot, event, officer, and pharmacist row."""
    base = os.environ["ACCEPTANCE_API_URL"]
    password = os.environ["ACCEPTANCE_ADMIN_PASSWORD"]
    staff = os.environ["ACCEPTANCE_STAFF_PASSWORD"]
    api = Api(base, "pharmacy-accept-b")
    _login(api, "admin", password)
    api(
        "PUT",
        "/api/v1/settings/profile",
        {"business_profile": "pharmacy", "capabilities": None, "complete_onboarding": True},
    )
    store_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    api(
        "POST",
        "/api/v1/sync/push",
        {
            "device_id": "tenant-b-bootstrap",
            "events": [
                {
                    "idempotency_key": f"store-{store_id}",
                    "entity_type": "store",
                    "operation": "upsert",
                    "payload": {"id": store_id, "code": "TENB", "name": "Pharmacy B", "currency": "USD", "is_warehouse": True},
                    "occurred_at": now,
                }
            ],
        },
        auth="shared",
    )
    _, categories = api("GET", "/api/v1/categories")
    category_id = next(row["id"] for row in categories if row.get("code") == "OTC")
    _, product = api(
        "POST",
        "/api/v1/inventory/products",
        {
            "sku": "TENANT-B",
            "barcode": "6291000000021",
            "name": "Tenant B Medicine",
            "price_cents": 1500,
            "category_id": category_id,
            "pharmacy": {
                "product_kind": "MEDICINE",
                "dispensing_class": "OTC",
                "generic_name": "Tenant B Medicine",
                "manufacturer": "Acceptance Pharma",
                "dosage_form": "tablet",
                "route": "oral",
                "strength_amount": "500",
                "strength_unit": "mg",
                "pack_size_label": "10 tablets",
                "units_per_pack": 1,
                "base_unit_code": "PIECE",
                "selling_unit_code": "PIECE",
                "price_control": "NONE",
                "ingredients": [
                    {"name": "Tenant B Medicine", "strength_amount": "500", "strength_unit": "mg", "is_active_ingredient": True}
                ],
            },
        },
    )
    _, order = api(
        "POST",
        "/api/v1/inventory/purchase-orders",
        {
            "supplier_name": "Acceptance Pharma",
            "destination_store_id": store_id,
            "notes": "TENANT-B",
            "lines": [{"product_id": product["id"], "quantity_ordered": 2, "unit_cost_cents": 400}],
        },
    )
    api("POST", f"/api/v1/inventory/purchase-orders/{order['id']}/order")
    api(
        "POST",
        f"/api/v1/inventory/purchase-orders/{order['id']}/receive",
        {
            "note": "TENANT-B",
            "lines": [
                {
                    "purchase_order_line_id": order["lines"][0]["id"],
                    "quantity": 2,
                    "manufacturer_lot": "TENANT-B-LOT",
                    "expiry_date": "2027-06-01",
                }
            ],
        },
    )
    _, roles = api("GET", "/api/v1/roles")
    role_rows = roles if isinstance(roles, list) else (roles.get("rows") or roles.get("roles") or [])
    manager = next(row["id"] for row in role_rows if row.get("name") == "Store Manager")
    _, role = api(
        "POST",
        "/api/v1/roles",
        {"name": "Tenant B clerk", "permissions": ["roles:manage", "portal:access", "users:read"]},
    )

    def user(username: str, role_id: str) -> str:
        _, created = api(
            "POST",
            "/api/v1/users",
            {
                "username": username,
                "email": f"{username}@acceptance.example",
                "full_name": username,
                "role_id": role_id,
                "store_id": store_id,
                "password": staff,
                "pin": "2468",
                "has_portal_access": True,
                "has_pos_access": True,
            },
        )
        return created["id"]

    clerk_a = user("clerk.b1", role["id"])
    clerk_b = user("clerk.b2", role["id"])
    officer = user("officer.b1", manager)
    pharmacist = user("pharmacist.b1", manager)
    a = Api(base, "pharmacy-accept-b")
    _login(a, "clerk.b1", staff)
    b = Api(base, "pharmacy-accept-b")
    _login(b, "clerk.b2", staff)
    _expect(a, "POST", "/api/v1/pharmacy/governance-officers", {"user_id": officer, "reason": "Nominate tenant B officer", "confirm": True}, {201}, "tenant-b-nominated", results)
    one = Api(base, "pharmacy-accept-b")
    _login(one, "officer.b1", staff)
    _expect(b, "POST", f"/api/v1/pharmacy/governance-officers/{officer}/confirm", {"reason": "Confirm tenant B officer", "confirm": True}, {200}, "tenant-b-officer", results)
    # A second officer is required before pharmacist approval is separated. Nominate the second clerk's target.
    second = user("officer.b2", manager)
    _expect(a, "POST", "/api/v1/pharmacy/governance-officers", {"user_id": second, "reason": "Nominate second tenant B officer", "confirm": True}, {201}, "tenant-b-second-nominated", results)
    _expect(b, "POST", f"/api/v1/pharmacy/governance-officers/{second}/confirm", {"reason": "Confirm second tenant B officer", "confirm": True}, {200}, "tenant-b-second-officer", results)
    _expect(one, "POST", "/api/v1/pharmacy/pharmacists", {"user_id": pharmacist, "reason": "Request tenant B pharmacist", "confirm": True}, {201}, "tenant-b-requested", results)
    two = Api(base, "pharmacy-accept-b")
    _login(two, "officer.b2", staff)
    _expect(two, "POST", f"/api/v1/pharmacy/pharmacists/{pharmacist}/approve", {"reason": "Approve tenant B pharmacist", "confirm": True}, {200}, "tenant-b-pharmacist", results)
    _, batches = api("GET", "/api/v1/inventory/batches?limit=20")
    layer_id = None
    for row in batches.get("rows") or []:
        _, detail = api("GET", f"/api/v1/inventory/batches/{row['id']}")
        for item in detail.get("items") or []:
            if item.get("manufacturer_lot") == "TENANT-B-LOT":
                layer_id = item["id"]
                break
        if layer_id:
            break
    if layer_id is None:
        _result(results, "tenant-b-released", False, "TENANT-B-LOT was not in the purchase-batch list")
        return product["id"]
    pharmacist_api = Api(base, "pharmacy-accept-b")
    _login(pharmacist_api, "pharmacist.b1", staff)
    _expect(
        pharmacist_api,
        "POST",
        f"/api/v1/pharmacy/lots/{layer_id}/release",
        {"reason": "Release tenant B lot", "confirm": True},
        {200},
        "tenant-b-released",
        results,
    )
    _expect(
        api,
        "POST",
        "/api/v1/pharmacy/supplier-returns",
        {"reference": "TENANT-B-RET", "reason": "Tenant B return", "lines": [{"batch_item_id": layer_id, "quantity": 1}]},
        {201},
        "tenant-b-return",
        results,
    )
    _expect(
        api,
        "POST",
        "/api/v1/pharmacy/recalls",
        {
            "reference": "TENANT-B-RECALL",
            "source_text": "Tenant B recall",
            "severity": "high",
            "reason": "Recall tenant B lot",
            "lots": [{"product_id": product["id"], "manufacturer_lot": "TENANT-B-LOT"}],
        },
        {201},
        "tenant-b-recall",
        results,
    )
    _result(results, "tenant-b-seeded", True, f"product={product['id']} clerks={clerk_a[:8]},{clerk_b[:8]}")
    return product["id"]


def _count(connection, table: str) -> int:
    return int(connection.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one())


def main() -> None:
    for key in ("DATABASE_URL", "CONTROL_DATABASE_URL"):
        if os.environ.get(key):
            raise SystemExit(f"{key} is set in the process. Refusing to probe.")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    if settings.app_env != "acceptance":
        raise SystemExit("Refusing to probe outside acceptance.")
    results: list[dict] = []
    product_b = _seed_b(results)
    operational = create_engine(settings.database_url)
    control = create_engine(settings.control_database_url)
    with control.connect() as connection:
        role = connection.execute(
            text("SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        ).one()
        tenants = {
            row.slug: str(row.id)
            for row in connection.execute(
                text("SELECT id, slug FROM tenants WHERE slug IN ('pharmacy-accept', 'pharmacy-accept-b', 'accept-grocery')")
            )
        }
    _result(
        results,
        "application-role",
        role.current_user == "ai_pos_app" and role.rolsuper is False and role.rolbypassrls is False,
        f"role={role.current_user} superuser={role.rolsuper} bypassrls={role.rolbypassrls}",
    )
    tenant_a = tenants["pharmacy-accept"]
    tenant_b = tenants["pharmacy-accept-b"]
    tenant_c = tenants["accept-grocery"]

    with operational.connect() as connection:
        connection.execute(text("SELECT set_config('app.bypass_rls', 'off', true)"))
        connection.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": tenant_a})
        own = {table: _count(connection, table) for table in TABLES}
        sample = {
            table: connection.execute(text(f'SELECT id FROM "{table}" LIMIT 1')).scalar()
            for table in TABLES
        }
        connection.rollback()
    with operational.connect() as connection:
        connection.execute(text("SELECT set_config('app.bypass_rls', 'off', true)"))
        connection.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": tenant_b})
        other = {table: _count(connection, table) for table in TABLES}
        sample_b = {
            table: connection.execute(text(f'SELECT id FROM "{table}" LIMIT 1')).scalar()
            for table in TABLES
        }
        connection.rollback()

    for table in TABLES:
        _result(results, f"{table}-tenant-a-sees-own", own[table] > 0, f"rows={own[table]}")
        _result(results, f"{table}-tenant-b-sees-own", other[table] > 0, f"rows={other[table]}")

    with operational.connect() as connection:
        connection.execute(text("SELECT set_config('app.bypass_rls', 'off', true)"))
        connection.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": tenant_a})
        hidden = {table: _count(connection, table) for table in TABLES}
        widened = {}
        connection.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        for table in TABLES:
            widened[table] = _count(connection, table)
            if sample_b[table] is not None:
                nested = connection.begin_nested()
                try:
                    updated = connection.execute(
                        text(f'UPDATE "{table}" SET id = id WHERE id = :id'),
                        {"id": sample_b[table]},
                    )
                    deleted = connection.execute(
                        text(f'DELETE FROM "{table}" WHERE id = :id'),
                        {"id": sample_b[table]},
                    )
                    nested.commit()
                    _result(
                        results,
                        f"{table}-tenant-a-cannot-write-tenant-b",
                        updated.rowcount == 0 and deleted.rowcount == 0,
                        f"update={updated.rowcount} delete={deleted.rowcount}",
                    )
                except Exception as error:  # noqa: BLE001 - a refused write is still isolation
                    nested.rollback()
                    _result(results, f"{table}-tenant-a-cannot-write-tenant-b", False, str(error)[:180])
        same = all(hidden[table] == widened[table] == own[table] for table in TABLES)
        _result(results, "application-role-bypass-does-not-widen", same, f"without={hidden} with_bypass={widened}")
        missing_hidden = True
        connection.execute(text("SELECT set_config('app.bypass_rls', 'off', true)"))
        connection.execute(text("SELECT set_config('app.tenant_id', '', true)"))
        for table in TABLES:
            if _count(connection, table) != 0:
                missing_hidden = False
        _result(results, "missing-tenant-context-fails-closed", missing_hidden, "empty tenant setting hides every probed table")
        invalid_failed = False
        try:
            connection.execute(text("SELECT set_config('app.tenant_id', 'not-a-uuid', true)"))
            connection.execute(text('SELECT count(*) FROM batch_items'))
        except Exception as error:  # noqa: BLE001 - invalid input must abort the read
            invalid_failed = "invalid" in str(error).lower() or "uuid" in str(error).lower()
        _result(results, "invalid-tenant-context-fails-closed", invalid_failed, "malformed tenant id aborted the read")
        connection.rollback()

    with operational.connect() as connection:
        connection.execute(text("SELECT set_config('app.bypass_rls', 'off', true)"))
        connection.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": tenant_c})
        pharmacy_tables = tuple(table for table in TABLES if table != "batch_items" and table != "batch_item_events")
        pharmacy_hidden = all(_count(connection, table) == 0 for table in pharmacy_tables)
        lot_visible = False
        if sample["batch_items"] is not None:
            lot_visible = int(
                connection.execute(
                    text("SELECT count(*) FROM batch_items WHERE id = :id"),
                    {"id": sample["batch_items"]},
                ).scalar_one()
            ) != 0
        _result(
            results,
            "tenant-c-cannot-read-pharmacy-records",
            pharmacy_hidden and not lot_visible,
            f"pharmacy_tables_hidden={pharmacy_hidden} pharmacy_lot_visible={lot_visible}",
        )
        connection.rollback()

    with operational.connect() as connection:
        connection.execute(text("SELECT set_config('app.bypass_rls', 'off', true)"))
        connection.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": tenant_b})
        leaked = False
        if sample["batch_items"] is not None:
            visible = connection.execute(
                text("SELECT count(*) FROM batch_items WHERE id = :id"),
                {"id": sample["batch_items"]},
            ).scalar_one()
            leaked = int(visible) != 0
        _result(results, "tenant-b-cannot-read-tenant-a-lot", not leaked, f"visible={leaked}")
        connection.rollback()

    base = os.environ["ACCEPTANCE_API_URL"]
    admin_a = Api(base, "pharmacy-accept")
    _login(admin_a, "admin", os.environ["ACCEPTANCE_ADMIN_PASSWORD"])
    admin_b = Api(base, "pharmacy-accept-b")
    _login(admin_b, "admin", os.environ["ACCEPTANCE_ADMIN_PASSWORD"])
    grocery = Api(base, "accept-grocery")
    _login(grocery, "admin", os.environ["ACCEPTANCE_ADMIN_PASSWORD"])
    _, visible = admin_a("GET", "/api/v1/products?q=TENANT-B&limit=20")
    visible_rows = visible if isinstance(visible, list) else (visible or {}).get("rows") or []
    _result(
        results,
        "api-tenant-a-cannot-read-tenant-b-product",
        not any(row.get("sku") == "TENANT-B" for row in visible_rows),
        f"matches={len(visible_rows)}",
    )
    _expect(grocery, "GET", "/api/v1/pharmacy/governance", None, {403}, "api-grocery-pharmacy-closed", results)
    _expect(admin_b, "GET", "/api/v1/pharmacy/governance", None, {200}, "api-tenant-b-governance-open", results)
    (EVIDENCE / "rls.json").write_text(
        json.dumps({"role": role.current_user, "superuser": bool(role.rolsuper), "bypassrls": bool(role.rolbypassrls), "results": results}, indent=2),
        encoding="utf-8",
    )
    if any(item["status"] == "failed" for item in results):
        raise SystemExit("RLS probe failed.")


if __name__ == "__main__":
    main()
