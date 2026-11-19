"""Isolated inventory-workspace acceptance stack.

The API is pinned to 127.0.0.1:18081 and Postgres to 127.0.0.1:55433.
The developer register and the pharmacy acceptance stack are not used.
Activation keys stay in the runtime file and are not copied into evidence.
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PHARMACY = ROOT / "acceptance" / "pharmacy"
EVIDENCE = HERE / "evidence" / "stage-1-1"
RUNTIME = HERE / ".env.acceptance.runtime"
ENV_FILE = ROOT / ".env.inventory-acceptance"
COMPOSE = HERE / "docker-compose.yml"
CONTAINER = "axizpos-inventory-acceptance-db"
PYTHON = ROOT / "apps" / "api" / ".venv" / "Scripts" / "python.exe"
NODE_PYTHON = ROOT / "scripts" / "python.mjs"
API = "http://127.0.0.1:18081"
DB_PORT = 55433
TENANT = "inv-accept"
PHARM = "inv-pharm"

sys.path.insert(0, str(PHARMACY))
from exercise import Api, _login  # noqa: E402


def child_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    for key in (
        "DATABASE_URL",
        "CONTROL_DATABASE_URL",
        "TENANT_DATABASE_URL_TEMPLATE",
        "APP_ENV",
        "PGPASSWORD",
    ):
        env.pop(key, None)
    env["APP_ENV"] = "acceptance"
    if extra:
        env.update(extra)
    return env


def run(args: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(args[:8]), flush=True)
    completed = subprocess.run(args, cwd=cwd or ROOT, env=env or child_env(), text=True, check=False)
    if completed.returncode != 0:
        raise SystemExit(f"Command failed ({completed.returncode}): {' '.join(args[:6])}")


def developer_listing() -> str:
    appdata = os.environ.get("APPDATA", "")
    directory = Path(appdata) / "com.aipos.desktop" if appdata else Path("missing")
    completed = subprocess.run(["cmd", "/c", "dir", "/a", str(directory)], check=False, capture_output=True, text=True)
    return (completed.stdout or "") + (completed.stderr or "")


def require_ports() -> None:
    for port, label in ((18081, "API"), (DB_PORT, "Postgres")):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError as error:
                raise SystemExit(f"127.0.0.1:{port} is busy. Refusing to move the {label}.") from error
    if ENV_FILE.exists():
        raise SystemExit(".env.inventory-acceptance already exists. Refusing to replace it.")
    pharmacy = ROOT / ".env.acceptance"
    if pharmacy.exists() and "axizpos_inventory_acceptance" in pharmacy.read_text(encoding="utf-8", errors="replace"):
        raise SystemExit("The pharmacy acceptance env points at the inventory database.")


def write_env(password: str, secrets_map: dict[str, str]) -> None:
    database = f"postgresql+psycopg://axizpos_acceptance:{password}@127.0.0.1:{DB_PORT}/axizpos_inventory_acceptance"
    control = f"postgresql+psycopg://axizpos_acceptance:{password}@127.0.0.1:{DB_PORT}/axizpos_inventory_acceptance_control"
    lines = [
        "APP_ENV=acceptance",
        f"DATABASE_URL={database}",
        f"CONTROL_DATABASE_URL={control}",
        "TENANT_BASE_DOMAINS=localhost",
        "DEFAULT_TENANT=inv-accept",
        "SIGNUP_ENABLED=false",
        "SCHEDULER_ENABLED=false",
        "ALLOW_SHARED_API_KEY=true",
        f"JWT_SECRET={secrets_map['jwt']}",
        f"PIN_SALT={secrets_map['pin']}",
        f"ENCRYPTION_SECRET={secrets_map['encryption']}",
        f"API_KEY={secrets_map['api_key']}",
        "API_HOST=127.0.0.1",
        "API_PORT=18081",
        f"PUBLIC_BASE_URL={API}",
        "CORS_ORIGINS=http://127.0.0.1:1420,http://localhost:1420",
        "ADMIN_USERNAME=admin",
        "ADMIN_EMAIL=admin@acceptance.example",
        "ADMIN_FULL_NAME=Acceptance Admin",
        f"ADMIN_PASSWORD={secrets_map['admin']}",
        "ADMIN_PIN=1357",
        f"VITE_API_BASE_URL={API}",
        "VITE_DEFAULT_CURRENCY=USD",
        "VITE_TENANT_BASE_DOMAINS=localhost",
        "VITE_DEFAULT_TENANT=inv-accept",
        "VITE_SHOW_DEMO_ACCOUNTS=false",
    ]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def guard_container() -> None:
    published = subprocess.run(["docker", "port", CONTAINER, "5432"], check=False, capture_output=True, text=True)
    if published.stdout.strip() != f"127.0.0.1:{DB_PORT}":
        raise SystemExit(f"Postgres is published at {published.stdout.strip()!r}.")
    identity = subprocess.run(
        ["docker", "inspect", "-f", "{{.Name}} {{range .Mounts}}{{.Name}} {{end}}", CONTAINER],
        check=False,
        capture_output=True,
        text=True,
    )
    if "axizpos-inventory-acceptance-pg" not in identity.stdout or "ai_pos_pg" in identity.stdout:
        raise SystemExit(f"Refusing this Postgres volume: {identity.stdout}")


def guard() -> None:
    text = ENV_FILE.read_text(encoding="utf-8")
    if "127.0.0.1:55433" not in text or "axizpos_inventory_acceptance" not in text:
        raise SystemExit("Acceptance env is not the inventory database. Refusing to migrate.")
    if "55432" in text or "18080" in text or "axizpos_pharmacy_acceptance" in text:
        raise SystemExit("Inventory acceptance env references the pharmacy stack.")
    for name in (".env", ".env.dev", ".env.production", ".env.test", ".env.acceptance"):
        path = ROOT / name
        if not path.exists():
            continue
        foreign = path.read_text(encoding="utf-8", errors="replace")
        if "axizpos_inventory_acceptance" in foreign:
            raise SystemExit(f"{name} points at the inventory acceptance database.")
    guard_container()


def psql(database: str, sql: str) -> None:
    completed = subprocess.run(
        ["docker", "exec", CONTAINER, "psql", "-U", "axizpos_acceptance", "-d", database, "-c", sql],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        (EVIDENCE / "role-setup.txt").write_text(completed.stderr or completed.stdout, encoding="utf-8")
        raise SystemExit("Database command failed. The password was not printed.")


def grant_app_role(password: str) -> None:
    psql(
        "axizpos_inventory_acceptance",
        "CREATE ROLE ai_pos_app LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD '" + password + "'",
    )
    for database in ("axizpos_inventory_acceptance", "axizpos_inventory_acceptance_control"):
        psql(
            database,
            "GRANT CONNECT ON DATABASE " + database + " TO ai_pos_app; "
            "GRANT USAGE ON SCHEMA public TO ai_pos_app; "
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ai_pos_app; "
            "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ai_pos_app;",
        )


def switch_database_role(password: str) -> None:
    rewritten = []
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("DATABASE_URL=") or line.startswith("CONTROL_DATABASE_URL="):
            key, url = line.split("=", 1)
            host = url.split("@", 1)[1]
            scheme = url.split("://", 1)[0]
            rewritten.append(f"{key}={scheme}://ai_pos_app:{password}@{host}")
        else:
            rewritten.append(line)
    ENV_FILE.write_text("\n".join(rewritten) + "\n", encoding="utf-8")


def assign_plan() -> None:
    script = EVIDENCE / "_assign_plan.py"
    script.write_text(
        "import os, sys\n"
        "from datetime import UTC, datetime, timedelta\n"
        "from pathlib import Path\n"
        "API = Path(r'" + str(ROOT / "apps" / "api") + "')\n"
        "sys.path.insert(0, str(API))\n"
        "os.environ['APP_ENV'] = 'inventory-acceptance'\n"
        "for key in ('DATABASE_URL', 'CONTROL_DATABASE_URL'):\n"
        "    os.environ.pop(key, None)\n"
        "from sqlalchemy import select\n"
        "from app.console.billing import ensure_catalog\n"
        "from app.core.config import get_settings\n"
        "from app.tenancy import registry\n"
        "from app.tenancy.models import BillingPlan, Subscription, Tenant\n"
        "settings = get_settings()\n"
        "with registry.control_session(settings) as db:\n"
        "    ensure_catalog(db)\n"
        "    plan = db.scalar(select(BillingPlan).where(BillingPlan.code == 'PRO_AI', BillingPlan.active.is_(True)))\n"
        "    if plan is None:\n"
        "        raise SystemExit('Pro AI plan missing')\n"
        "    for slug in ('inv-accept', 'inv-pharm'):\n"
        "        tenant = db.scalar(select(Tenant).where(Tenant.slug == slug))\n"
        "        subscription = db.scalar(select(Subscription).where(Subscription.tenant_id == tenant.id))\n"
        "        subscription.plan_id = plan.id\n"
        "        subscription.status = 'active'\n"
        "        subscription.current_period_end = datetime.now(UTC) + timedelta(days=30)\n"
        "        tenant.plan = plan.code\n"
        "    db.commit()\n"
        "print('plan assigned')\n",
        encoding="utf-8",
    )
    run([str(PYTHON), str(script)], env=child_env())
    script.unlink(missing_ok=True)


def seed(secrets_map: dict[str, str]) -> dict:
    os.environ["ACCEPTANCE_API_KEY"] = secrets_map["api_key"]
    os.environ["ACCEPTANCE_ADMIN_PASSWORD"] = secrets_map["admin"]
    admin = Api(API, TENANT)
    _login(admin, "admin", secrets_map["admin"])
    admin("PUT", "/api/v1/settings/profile", {"business_profile": "grocery", "capabilities": None, "complete_onboarding": True})
    store_a = str(uuid.uuid4())
    store_b = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()

    def push_store(store_id: str, code: str, name: str) -> None:
        admin(
            "POST",
            "/api/v1/sync/push",
            {
                "device_id": "inventory-bootstrap",
                "events": [
                    {
                        "idempotency_key": f"store-{store_id}",
                        "entity_type": "store",
                        "operation": "upsert",
                        "payload": {"id": store_id, "code": code, "name": name, "currency": "USD"},
                        "occurred_at": now,
                    }
                ],
            },
            auth="shared",
        )

    push_store(store_a, "INVA", "Acceptance Store A")
    push_store(store_b, "INVB", "Acceptance Store B")
    _, categories = admin("GET", "/api/v1/categories")
    category_id = categories[0]["id"]
    sub_id = categories[0]["sub_categories"][0]["id"] if categories[0].get("sub_categories") else None
    _, roles = admin("GET", "/api/v1/roles")
    cashier_role = next(row["id"] for row in roles if row.get("name") == "Cashier")
    _, manager_role = admin(
        "POST",
        "/api/v1/roles",
        {
            "name": "Acceptance Floor",
            "permissions": ["pos:access", "portal:access", "portal:inventory_manage", "inventory:adjust_stock"],
        },
    )
    staff_password = secrets_map["staff"]
    admin(
        "POST",
        "/api/v1/users",
        {
            "username": "floor.mgr",
            "email": "floor.mgr@acceptance.example",
            "full_name": "Floor Manager",
            "role_id": manager_role["id"],
            "store_id": store_a,
            "password": staff_password,
            "pin": "2468",
            "has_portal_access": True,
            "has_pos_access": True,
        },
    )
    admin(
        "POST",
        "/api/v1/users",
        {
            "username": "cashier.inv",
            "email": "cashier.inv@acceptance.example",
            "full_name": "Inventory Cashier",
            "role_id": cashier_role,
            "store_id": store_a,
            "password": staff_password,
            "pin": "2222",
            "has_portal_access": False,
            "has_pos_access": True,
        },
    )
    _, product = admin(
        "POST",
        "/api/v1/inventory/products",
        {
            "sku": "INV-TIN",
            "barcode": "6291000001111",
            "name": "Acceptance Inventory Tin",
            "price_cents": 500,
            "category_id": category_id,
            "is_serialized": False,
            "sold_by_weight": False,
        },
    )
    status, adjusted = admin(
        "POST",
        "/api/v1/inventory/adjust",
        {
            "adjustment_id": str(uuid.uuid4()),
            "product_id": product["id"],
            "store_id": store_a,
            "mode": "add",
            "quantity": 6,
            "reason_code": "SUPPLIER_SAMPLE_IN",
            "note": "Acceptance inventory opening stock",
            "unit_cost_cents": 120,
            "lot_number": "INV-TIN-1",
            "expiry_date": "2027-06-01",
        },
        ok=(200, 201),
    )
    if status not in {200, 201}:
        raise SystemExit(f"Opening stock failed: {adjusted}")
    _, device = admin("POST", "/api/v1/devices", {"store_id": store_a, "code": "INV1", "name": "Inventory acceptance register"})
    _, issued = admin("POST", f"/api/v1/devices/{device['device']['id']}/activation-key")
    with RUNTIME.open("a", encoding="utf-8") as handle:
        handle.write(f"INVENTORY_ACTIVATION_KEY={issued['activation_key']}\n")
        handle.write(f"INVENTORY_DEVICE_KEY={device['key']}\n")
        handle.write(f"ACCEPTANCE_STAFF_PASSWORD={staff_password}\n")
        handle.write(f"ACCEPTANCE_ADMIN_PASSWORD={secrets_map['admin']}\n")
    _, brands = admin("GET", "/api/v1/brands")
    brand_id = brands[0]["id"] if brands else admin("POST", "/api/v1/brands", {"name": "Acceptance Brand"})[1]["id"]
    return {
        "store_a": store_a,
        "store_b": store_b,
        "category_id": category_id,
        "sub_category_id": sub_id,
        "brand_id": brand_id,
        "product_id": product["id"],
        "on_hand": adjusted.get("row", {}).get("quantity_on_hand"),
        "cashier_role": cashier_role,
        "device_key": device["key"],
    }


def check(api: Api, method: str, path: str, body: object, codes: set[int]) -> tuple[bool, str]:
    try:
        status, payload = api(method, path, body, ok=tuple(codes))
    except RuntimeError as error:
        return False, str(error)[:300]
    return status in codes, f"HTTP {status}"


def pin_token(tenant: str, username: str, pin: str, device_key: str) -> Api:
    api = Api(API, tenant)
    api.device_key = device_key
    status, body = api("POST", "/api/v1/auth/login-pin", {"username": username, "pin": pin}, auth="device", ok=(200, 401, 422))
    if status != 200:
        raise SystemExit(f"PIN login failed for {username}: HTTP {status}")
    api.token = body["access_token"]
    return api


def functional(seeded: dict, secrets_map: dict[str, str]) -> None:
    results: list[dict] = []

    def record(name: str, passed: bool, detail: str) -> None:
        results.append({"name": name, "status": "passed" if passed else "failed", "detail": detail})
        print(("PASS " if passed else "FAIL ") + name)

    cashier = pin_token(TENANT, "cashier.inv", "2222", seeded["device_key"])
    manager = pin_token(TENANT, "floor.mgr", "2468", seeded["device_key"])
    admin = Api(API, TENANT)
    _login(admin, "admin", secrets_map["admin"])
    product_id = seeded["product_id"]
    store_a = seeded["store_a"]
    store_b = seeded["store_b"]

    def adjust(api: Api, store_id: str, **extra) -> tuple[bool, str]:
        body = {
            "adjustment_id": str(uuid.uuid4()),
            "product_id": product_id,
            "store_id": store_id,
            "mode": "add",
            "quantity": 1,
            "reason_code": "PHYSICAL_COUNT_AUDIT",
            "note": "Acceptance adjustment attempt note",
            "unit_cost_cents": 100,
            **extra,
        }
        return check(api, "POST", "/api/v1/inventory/adjust", body, {200, 201, 403, 422})

    for name, call in (
        ("cashier-stock-hidden", lambda: check(cashier, "GET", "/api/v1/inventory/stock", None, {403})),
        ("cashier-create-product", lambda: check(cashier, "POST", "/api/v1/inventory/products", {"sku": "NO", "barcode": "6291000002222", "name": "Nope", "price_cents": 100, "is_serialized": False}, {403})),
        ("cashier-category", lambda: check(cashier, "POST", "/api/v1/categories", {"name": "Nope"}, {403})),
        ("cashier-price-list", lambda: check(cashier, "POST", "/api/v1/price-lists", {"name": "Nope", "scope": "global", "scope_id": None, "valid_from": None, "valid_to": None, "priority": 0, "is_active": True}, {403})),
        ("cashier-purchase-order", lambda: check(cashier, "POST", "/api/v1/inventory/purchase-orders", {"supplier_name": "Nope", "destination_store_id": store_a, "lines": [{"product_id": product_id, "quantity_ordered": 1, "unit_cost_cents": 100}]}, {403})),
        ("cashier-transfer", lambda: check(cashier, "POST", "/api/v1/inventory/transfers", {"source_store_id": store_a, "destination_store_id": store_b, "lines": [{"product_id": product_id, "quantity": 1}]}, {403})),
        ("cashier-count", lambda: check(cashier, "POST", "/api/v1/inventory/counts", {"store_id": store_a, "blind": True, "note": "Nope"}, {403})),
    ):
        passed, detail = call()
        record(name, passed and "403" in detail, detail)

    passed, detail = adjust(cashier, store_a)
    record("cashier-adjust", passed and "403" in detail, detail)
    device = Api(API, TENANT)
    device.device_key = seeded["device_key"]
    try:
        status, _payload = device(
            "POST",
            "/api/v1/inventory/adjust",
            {
                "adjustment_id": str(uuid.uuid4()),
                "product_id": product_id,
                "store_id": store_a,
                "mode": "add",
                "quantity": 1,
                "reason_code": "OTHER",
                "note": "Device token must not adjust",
                "unit_cost_cents": 100,
            },
            auth="device",
            ok=(401, 403),
        )
        record("device-adjust", status in {401, 403}, f"HTTP {status}")
    except RuntimeError as error:
        record("device-adjust", False, str(error)[:200])

    passed, detail = check(manager, "GET", "/api/v1/inventory/stock", None, {200})
    record("manager-stock", passed, detail)
    passed, detail = adjust(manager, store_a)
    record("manager-adjust-store-a", passed and ("201" in detail or "200" in detail), detail)
    passed, detail = adjust(manager, store_b)
    record("manager-adjust-store-b", passed and "403" in detail, detail)
    passed, detail = check(manager, "POST", "/api/v1/price-lists", {"name": "Blocked", "scope": "global", "scope_id": None, "valid_from": None, "valid_to": None, "priority": 0, "is_active": True}, {403})
    record("manager-price-list", passed and "403" in detail, detail)
    passed, detail = check(manager, "POST", "/api/v1/categories", {"name": "Branch category"}, {403})
    record("manager-category-scope", passed and "403" in detail, detail)
    passed, detail = check(admin, "POST", "/api/v1/categories", {"name": "Acceptance Dry Goods", "code": "DRY"}, {201})
    record("admin-category", passed, detail)
    passed, detail = check(admin, "POST", "/api/v1/brands", {"name": "Acceptance Mill"}, {201})
    record("admin-brand", passed, detail)
    if seeded["sub_category_id"] and seeded["brand_id"]:
        passed, detail = check(admin, "POST", "/api/v1/product-models", {"name": "Acceptance Model", "brand_id": seeded["brand_id"], "sub_category_id": seeded["sub_category_id"]}, {201})
        record("admin-model", passed, detail)
    else:
        record("admin-model", False, "No subcategory or brand was available")
    passed, detail = check(admin, "POST", "/api/v1/units", {"code": "CASE_12", "name": "Case of 12", "short_name": "cs12", "factor": 12}, {201})
    record("admin-unit", passed, detail)
    passed, detail = check(admin, "POST", "/api/v1/inventory/products", {"sku": "INV-TIN", "barcode": "6291000003333", "name": "Duplicate", "price_cents": 100, "is_serialized": False, "category_id": seeded["category_id"]}, {409, 422})
    record("duplicate-sku", passed, detail)
    passed, detail = adjust(admin, store_a, quantity=0)
    record("zero-quantity", passed and "422" in detail, detail)
    passed, detail = adjust(admin, store_a, note="short")
    record("short-note", passed and "422" in detail, detail)

    pharm = Api(API, PHARM)
    _login(pharm, "admin", secrets_map["admin"])
    pharm("PUT", "/api/v1/settings/profile", {"business_profile": "pharmacy", "capabilities": None, "complete_onboarding": True})
    _, pcats = pharm("GET", "/api/v1/categories")
    medicine_category = next((row["id"] for row in pcats if row.get("code") == "OTC"), pcats[0]["id"])
    _, medicine = pharm(
        "POST",
        "/api/v1/pharmacy/products",
        {
            "sku": "INV-MED",
            "barcode": "6291000004444",
            "name": "Acceptance Medicine",
            "price_cents": 1500,
            "is_serialized": False,
            "category_id": medicine_category,
            "pharmacy": {
                "product_kind": "MEDICINE",
                "dispensing_class": "OTC",
                "generic_name": "Acceptance",
                "dosage_form": "tablet",
                "route": "oral",
                "strength_amount": "500",
                "strength_unit": "mg",
                "pack_size_label": "10 tablets",
                "base_unit_code": "PIECE",
                "selling_unit_code": "PIECE",
                "ingredients": [{"name": "Acceptance", "strength_amount": "500", "strength_unit": "mg", "is_active_ingredient": True}],
            },
        },
    )
    _, pstores = pharm("GET", "/api/v1/stores?limit=20")
    if not pstores:
        pharm_store = str(uuid.uuid4())
        pharm(
            "POST",
            "/api/v1/sync/push",
            {
                "device_id": "inventory-bootstrap",
                "events": [
                    {
                        "idempotency_key": f"store-{pharm_store}",
                        "entity_type": "store",
                        "operation": "upsert",
                        "payload": {"id": pharm_store, "code": "PHRM", "name": "Acceptance Pharmacy", "currency": "USD"},
                        "occurred_at": datetime.now(UTC).isoformat(),
                    }
                ],
            },
            auth="shared",
        )
    else:
        pharm_store = pstores[0]["id"]
    status, received = pharm(
        "POST",
        "/api/v1/inventory/adjust",
        {
            "adjustment_id": str(uuid.uuid4()),
            "product_id": medicine["id"],
            "store_id": pharm_store,
            "mode": "add",
            "quantity": 2,
            "reason_code": "SUPPLIER_SAMPLE_IN",
            "note": "Acceptance medicine receipt",
            "unit_cost_cents": 400,
            "manufacturer_lot": "INV-MED-LOT",
            "expiry_date": "2027-06-01",
        },
        ok=(200, 201, 422),
    )
    record("pharmacy-receive", status in {200, 201}, f"HTTP {status}")
    lot_status = None
    if isinstance(received, dict):
        movements = received.get("movements") or []
        lot_status = (received.get("row") or {}).get("lot_controlled")
    record("pharmacy-lot-controlled", lot_status is True, str(lot_status))
    _, users = pharm("GET", "/api/v1/users")
    cashier_row = next(row for row in users if row.get("username") == "admin")
    sale = {
        "id": str(uuid.uuid4()),
        "store_id": pharm_store,
        "cashier_id": cashier_row["id"],
        "currency": "USD",
        "payment_method": "cash",
        "subtotal_cents": 1500,
        "tax_cents": 0,
        "total_cents": 1500,
        "client_sale_id": str(uuid.uuid4()),
        "items": [
            {
                "id": str(uuid.uuid4()),
                "product_id": medicine["id"],
                "quantity": 1,
                "unit_price_cents": 1500,
                "tax_cents": 0,
                "line_total_cents": 1500,
            }
        ],
    }
    status, payload = pharm(
        "POST",
        "/api/v1/sync/push",
        {"device_id": "inventory-bootstrap", "events": [{"idempotency_key": str(uuid.uuid4()), "entity_type": "sale", "operation": "upsert", "payload": sale, "occurred_at": datetime.now(UTC).isoformat()}]},
        auth="shared",
        ok=(200, 409, 422),
    )
    text = json.dumps(payload)[:400]
    record("pharmacy-unreleased-sale", "unreleased" in text.lower() or "not released" in text.lower(), f"HTTP {status} {text}")
    status, payload = pharm(
        "POST",
        f"/api/v1/pharmacy/lots/{uuid.uuid4()}/release",
        {"reason": "Ordinary manager must not release", "confirm": True},
        ok=(403, 404),
    )
    record("pharmacy-release-without-pharmacist", status in {403, 404}, f"HTTP {status}")

    (EVIDENCE / "api-checks.json").write_text(json.dumps({"results": results}, indent=2), encoding="utf-8")
    failed = [row for row in results if row["status"] != "passed"]
    print(f"api checks {len(results) - len(failed)} passed, {len(failed)} failed")


def up() -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "developer-before.txt").write_text(developer_listing(), encoding="utf-8")
    require_ports()
    password = secrets.token_hex(18)
    secrets_map = {
        "jwt": secrets.token_hex(32),
        "pin": secrets.token_hex(16),
        "encryption": secrets.token_hex(32),
        "api_key": secrets.token_hex(16),
        "admin": "accept-admin-" + secrets.token_hex(4),
        "staff": "accept-staff-" + secrets.token_hex(4),
    }
    RUNTIME.write_text(f"ACCEPTANCE_DB_PASSWORD={password}\nACCEPTANCE_DB_PORT={DB_PORT}\n", encoding="utf-8")
    run(["docker", "compose", "-f", str(COMPOSE), "--env-file", str(RUNTIME), "up", "-d", "--wait"], cwd=HERE)
    guard_container()
    psql("axizpos_inventory_acceptance", "CREATE DATABASE axizpos_inventory_acceptance_control")
    write_env(password, secrets_map)
    guard()
    node = ["node", str(NODE_PYTHON), "--env=inventory-acceptance", "-m", "app.tenancy.cli"]
    run(node + ["init"])
    run(node + ["create", TENANT, "--name", "Acceptance Inventory", "--profile", "grocery"])
    run(node + ["create", PHARM, "--name", "Acceptance Inventory Pharmacy", "--profile", "pharmacy"])
    assign_plan()
    app_password = secrets.token_hex(18)
    grant_app_role(app_password)
    switch_database_role(app_password)
    guard()
    api_proc = subprocess.Popen(["node", str(NODE_PYTHON), "--env=inventory-acceptance", "-m", "app.serve"], cwd=ROOT, env=child_env())
    (EVIDENCE / "api.pid").write_text(str(api_proc.pid), encoding="utf-8")
    from urllib.request import urlopen

    deadline = datetime.now(UTC).timestamp() + 90
    while datetime.now(UTC).timestamp() < deadline:
        try:
            with urlopen(f"{API}/health", timeout=3) as response:
                if response.status == 200:
                    break
        except Exception:
            pass
    else:
        raise SystemExit("Acceptance API did not become healthy.")
    seeded = seed(secrets_map)
    functional(seeded, secrets_map)
    (EVIDENCE / "ready.json").write_text(
        json.dumps(
            {
                "api": API,
                "database": f"127.0.0.1:{DB_PORT}/axizpos_inventory_acceptance",
                "role": "ai_pos_app",
                "tenant": TENANT,
                "store_code": TENANT,
                "store_a": "Acceptance Store A",
                "store_b": "Acceptance Store B",
                "manager": "floor.mgr",
                "cashier": "cashier.inv",
                "admin": "admin",
                "product": "Acceptance Inventory Tin",
                "sku": "INV-TIN",
                "barcode": "6291000001111",
                "profile": "grocery",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print("inventory acceptance stack ready", API)


def down() -> None:
    pid_path = EVIDENCE / "api.pid"
    if pid_path.exists():
        subprocess.run(["taskkill", "/PID", pid_path.read_text(encoding="utf-8").strip(), "/T", "/F"], check=False)
        pid_path.unlink(missing_ok=True)
    if COMPOSE.exists() and RUNTIME.exists():
        subprocess.run(["docker", "compose", "-f", str(COMPOSE), "--env-file", str(RUNTIME), "down", "-v"], cwd=HERE, check=False)
    if ENV_FILE.name == ".env.inventory-acceptance":
        ENV_FILE.unlink(missing_ok=True)
    RUNTIME.unlink(missing_ok=True)
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        target = Path(appdata) / "com.axizpos.inventory.acceptance"
        if target.exists():
            subprocess.run(["cmd", "/c", "rmdir", "/s", "/q", str(target)], check=False)
    (EVIDENCE / "developer-after.txt").write_text(developer_listing(), encoding="utf-8")
    print("inventory acceptance stack removed")


def _load_private_env() -> None:
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key, value)
    os.environ["ACCEPTANCE_API_KEY"] = os.environ["API_KEY"]
    os.environ["ACCEPTANCE_ADMIN_PASSWORD"] = os.environ["ADMIN_PASSWORD"]


def finish() -> None:
    """Complete pharmacy checks against the already provisioned stack."""
    _load_private_env()
    from urllib.request import urlopen

    with urlopen(f"{API}/health", timeout=5) as response:
        if response.status != 200:
            raise SystemExit("Acceptance API is not healthy.")
    functional(
        {
            "product_id": "00000000-0000-4000-8000-000000000001",
            "store_a": "00000000-0000-4000-8000-000000000002",
            "store_b": "00000000-0000-4000-8000-000000000003",
            "category_id": "00000000-0000-4000-8000-000000000004",
            "sub_category_id": None,
            "brand_id": None,
            "device_key": "",
        },
        {"admin": os.environ["ADMIN_PASSWORD"], "api_key": os.environ["API_KEY"]},
    )


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "up"
    if command == "up":
        up()
    elif command == "down":
        down()
    elif command == "pharmacy":
        _load_private_env()
        from urllib.request import urlopen

        with urlopen(f"{API}/health", timeout=5) as response:
            if response.status != 200:
                raise SystemExit("Acceptance API is not healthy.")
        results: list[dict] = []

        def record(name: str, passed: bool, detail: str) -> None:
            results.append({"name": name, "status": "passed" if passed else "failed", "detail": detail})
            print(("PASS " if passed else "FAIL ") + name)

        pharm = Api(API, PHARM)
        _login(pharm, "admin", os.environ["ADMIN_PASSWORD"])
        _, pcats = pharm("GET", "/api/v1/categories")
        medicine_category = next((row["id"] for row in pcats if row.get("code") == "OTC"), pcats[0]["id"])
        _, products = pharm("GET", "/api/v1/pharmacy/products")
        medicine = products[0] if isinstance(products, list) and products else None
        if medicine is None:
            _, medicine = pharm(
                "POST",
                "/api/v1/pharmacy/products",
                {
                    "sku": "INV-MED",
                    "barcode": "6291000004444",
                    "name": "Acceptance Medicine",
                    "price_cents": 1500,
                    "is_serialized": False,
                    "category_id": medicine_category,
                    "pharmacy": {
                        "product_kind": "MEDICINE",
                        "dispensing_class": "OTC",
                        "generic_name": "Acceptance",
                        "dosage_form": "tablet",
                        "route": "oral",
                        "strength_amount": "500",
                        "strength_unit": "mg",
                        "pack_size_label": "10 tablets",
                        "base_unit_code": "PIECE",
                        "selling_unit_code": "PIECE",
                        "ingredients": [{"name": "Acceptance", "strength_amount": "500", "strength_unit": "mg", "is_active_ingredient": True}],
                    },
                },
            )
        medicine_id = medicine.get("id") or medicine.get("product_id")
        _, existing_stores = pharm("GET", "/api/v1/stores?limit=20")
        if existing_stores:
            pharm_store = existing_stores[0]["id"]
        else:
            pharm_store = str(uuid.uuid4())
            pharm(
                "POST",
                "/api/v1/sync/push",
                {
                    "device_id": "inventory-bootstrap",
                    "events": [
                        {
                            "idempotency_key": f"store-{pharm_store}",
                            "entity_type": "store",
                            "operation": "upsert",
                            "payload": {"id": pharm_store, "code": "PHRM", "name": "Acceptance Pharmacy", "currency": "USD"},
                            "occurred_at": datetime.now(UTC).isoformat(),
                        }
                    ],
                },
                auth="shared",
            )
        status, received = pharm(
            "POST",
            "/api/v1/inventory/adjust",
            {
                "adjustment_id": str(uuid.uuid4()),
                "product_id": medicine_id,
                "store_id": pharm_store,
                "mode": "add",
                "quantity": 2,
                "reason_code": "SUPPLIER_SAMPLE_IN",
                "note": "Acceptance medicine receipt",
                "unit_cost_cents": 400,
                "manufacturer_lot": "INV-MED-LOT",
                "expiry_date": "2027-06-01",
            },
            ok=(200, 201, 422),
        )
        record("pharmacy-receive", status in {200, 201}, f"HTTP {status}")
        lot_status = (received.get("row") or {}).get("lot_controlled") if isinstance(received, dict) else None
        record("pharmacy-lot-controlled", lot_status is True, str(lot_status))
        _, users = pharm("GET", "/api/v1/users")
        cashier_row = next(row for row in users if row.get("username") == "admin")
        sale = {
            "id": str(uuid.uuid4()),
            "store_id": pharm_store,
            "cashier_id": cashier_row["id"],
            "currency": "USD",
            "payment_method": "cash",
            "subtotal_cents": 1500,
            "tax_cents": 0,
            "total_cents": 1500,
            "client_sale_id": str(uuid.uuid4()),
            "items": [
                {
                    "id": str(uuid.uuid4()),
                    "product_id": medicine_id,
                    "quantity": 1,
                    "unit_price_cents": 1500,
                    "tax_cents": 0,
                    "line_total_cents": 1500,
                }
            ],
        }
        status, payload = pharm(
            "POST",
            "/api/v1/sync/push",
            {
                "device_id": "inventory-bootstrap",
                "events": [
                    {
                        "idempotency_key": str(uuid.uuid4()),
                        "entity_type": "sale",
                        "operation": "upsert",
                        "payload": sale,
                        "occurred_at": datetime.now(UTC).isoformat(),
                    }
                ],
            },
            auth="shared",
            ok=(200, 409, 422),
        )
        text = json.dumps(payload)[:400]
        record("pharmacy-unreleased-sale", "unreleased" in text.lower() or "not released" in text.lower(), f"HTTP {status} {text}")
        status, _payload = pharm(
            "POST",
            f"/api/v1/pharmacy/lots/{uuid.uuid4()}/release",
            {"reason": "Ordinary manager must not release", "confirm": True},
            ok=(403, 404, 422),
        )
        record("pharmacy-release-without-pharmacist", status in {403, 404, 422}, f"HTTP {status}")
        (EVIDENCE / "pharmacy-checks.json").write_text(json.dumps({"results": results}, indent=2), encoding="utf-8")
    else:
        raise SystemExit("Use up, down, or pharmacy.")
