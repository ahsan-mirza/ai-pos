"""Stage 3E.4 stack for the isolated acceptance register.

The API is pinned to 127.0.0.1:18080. The developer register is not started.
Activation keys are written to the runtime env file and are not copied into evidence.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EVIDENCE = HERE / "evidence" / "stage-3e-6-1"
RUNTIME = HERE / ".env.acceptance.runtime"
sys.path.insert(0, str(HERE))

import exercise  # noqa: E402
from exercise import Api, _expect, _login  # noqa: E402
from run import (  # noqa: E402
    CONTAINER,
    ENV_FILE,
    NPM,
    NODE_PYTHON,
    PYTHON,
    child_env,
    grant_app_role,
    run,
    switch_database_role,
    wait_http,
    write_env,
)

import secrets  # noqa: E402

API = "http://127.0.0.1:18080"
STORE = "11111111-1111-4111-8111-111111111111"
TILL_BARCODE = "6291000000099"


def developer_listing() -> str:
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        return "APPDATA is unset\n"
    directory = Path(appdata) / "com.aipos.desktop"
    completed = subprocess.run(
        ["cmd", "/c", "dir", "/a", str(directory)],
        check=False,
        capture_output=True,
        text=True,
    )
    return (completed.stdout or "") + (completed.stderr or "")


def appoint(base: str) -> None:
    staff = os.environ["ACCEPTANCE_STAFF_PASSWORD"]
    admin = Api(base, "pharmacy-accept")
    _login(admin, "admin", os.environ["ACCEPTANCE_ADMIN_PASSWORD"])
    _, roles = admin("GET", "/api/v1/roles")
    manager = next(row["id"] for row in roles if row.get("name") == "Store Manager")
    _, users = admin("GET", "/api/v1/users")

    def user_id(username: str) -> str:
        return next(row["id"] for row in users if row.get("username") == username)

    clerk_a = Api(base, "pharmacy-accept")
    _login(clerk_a, "clerk.a", staff)
    clerk_b = Api(base, "pharmacy-accept")
    _login(clerk_b, "clerk.b", staff)
    for username, label in (("officer.one", "first"), ("officer.two", "second")):
        clerk_a(
            "POST",
            "/api/v1/pharmacy/governance-officers",
            {"user_id": user_id(username), "reason": f"Nominate {label} acceptance officer", "confirm": True},
        )
        clerk_b(
            "POST",
            f"/api/v1/pharmacy/governance-officers/{user_id(username)}/confirm",
            {"reason": f"Confirm {label} acceptance officer", "confirm": True},
        )
    one = Api(base, "pharmacy-accept")
    _login(one, "officer.one", staff)
    two = Api(base, "pharmacy-accept")
    _login(two, "officer.two", staff)
    created, _ = _expect(
        one,
        "POST",
        "/api/v1/pharmacy/pharmacists",
        {"user_id": user_id("pharmacist.one"), "reason": "Request acceptance pharmacist", "confirm": True},
        {201},
        "desktop-pharmacist-requested",
        [],
    )
    if created != 201:
        raise SystemExit("Pharmacist request failed.")
    approved, _ = _expect(
        two,
        "POST",
        f"/api/v1/pharmacy/pharmacists/{user_id('pharmacist.one')}/approve",
        {"reason": "Approve acceptance pharmacist", "confirm": True},
        {200},
        "desktop-pharmacist-approved",
        [],
    )
    if approved != 200:
        raise SystemExit("Pharmacist approval failed.")
    del manager


def till_lot(base: str) -> None:
    admin = Api(base, "pharmacy-accept")
    _login(admin, "admin", os.environ["ACCEPTANCE_ADMIN_PASSWORD"])
    _, categories = admin("GET", "/api/v1/categories")
    category_id = next(row["id"] for row in categories if row.get("code") == "OTC")
    _, product = admin(
        "POST",
        "/api/v1/inventory/products",
        {
            "sku": "ACCEPT-TILL",
            "barcode": TILL_BARCODE,
            "name": "Acceptance Till Medicine",
            "price_cents": 1500,
            "brand": "Acceptance Pharma",
            "category_id": category_id,
            "pharmacy": {
                "product_kind": "MEDICINE",
                "dispensing_class": "OTC",
                "generic_name": "Acceptance Till Medicine",
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
                    {
                        "name": "Acceptance Till Medicine",
                        "strength_amount": "500",
                        "strength_unit": "mg",
                        "is_active_ingredient": True,
                    }
                ],
            },
        },
    )
    _, order = admin(
        "POST",
        "/api/v1/inventory/purchase-orders",
        {
            "supplier_name": "Acceptance Pharma",
            "destination_store_id": STORE,
            "notes": "ACCEPT-TILL",
            "lines": [{"product_id": product["id"], "quantity_ordered": 6, "unit_cost_cents": 400}],
        },
    )
    admin("POST", f"/api/v1/inventory/purchase-orders/{order['id']}/order")
    _, received = admin(
        "POST",
        f"/api/v1/inventory/purchase-orders/{order['id']}/receive",
        {
            "note": "ACCEPT-TILL",
            "lines": [
                {
                    "purchase_order_line_id": order["lines"][0]["id"],
                    "quantity": 6,
                    "manufacturer_lot": "ACCEPT-TILL-LOT",
                    "expiry_date": "2027-06-01",
                }
            ],
        },
    )
    layer_id = received["receipts"][-1]["lots"][0]["batch_item_id"]
    pharmacist = Api(base, "pharmacy-accept")
    _login(pharmacist, "pharmacist.one", os.environ["ACCEPTANCE_STAFF_PASSWORD"])
    status, _ = pharmacist(
        "POST",
        f"/api/v1/pharmacy/lots/{layer_id}/release",
        {"reason": "Release acceptance till lot", "confirm": True},
    )
    if status != 200:
        raise SystemExit(f"Till lot release failed: HTTP {status}")


def activation_for(api: Api, store_id: str, code: str, name: str, label: str) -> None:
    _, device = api("POST", "/api/v1/devices", {"store_id": store_id, "code": code, "name": name})
    _, issued = api("POST", f"/api/v1/devices/{device['device']['id']}/activation-key")
    with RUNTIME.open("a", encoding="utf-8") as handle:
        handle.write(f"{label}_DEVICE_ID={device['device']['id']}\n")
        handle.write(f"{label}_ACTIVATION_KEY={issued['activation_key']}\n")


def grocery_terminal(base: str) -> None:
    admin = Api(base, "accept-grocery")
    _login(admin, "admin", os.environ["ACCEPTANCE_ADMIN_PASSWORD"])
    admin(
        "PUT",
        "/api/v1/settings/profile",
        {"business_profile": "grocery", "capabilities": None, "complete_onboarding": True},
    )
    store_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    admin(
        "POST",
        "/api/v1/sync/push",
        {
            "device_id": "grocery-desktop-bootstrap",
            "events": [
                {
                    "idempotency_key": f"store-{store_id}",
                    "entity_type": "store",
                    "operation": "upsert",
                    "payload": {"id": store_id, "code": "GROCERY", "name": "Acceptance Grocery", "currency": "USD"},
                    "occurred_at": now,
                }
            ],
        },
        auth="shared",
    )
    _, categories = admin("GET", "/api/v1/categories")
    if isinstance(categories, list) and categories:
        category_id = categories[0]["id"]
    else:
        _, created = admin("POST", "/api/v1/categories", {"name": "Acceptance", "code": "ACCEPT"})
        category_id = created["id"]
    _, roles = admin("GET", "/api/v1/roles")
    cashier_role = next(row["id"] for row in roles if row.get("name") == "Cashier")
    admin(
        "POST",
        "/api/v1/users",
        {
            "username": "cashier.g",
            "email": "cashier.g@acceptance.example",
            "full_name": "Grocery Cashier",
            "role_id": cashier_role,
            "store_id": store_id,
            "password": os.environ["ACCEPTANCE_STAFF_PASSWORD"],
            "pin": "2468",
            "has_portal_access": False,
            "has_pos_access": True,
        },
    )
    _, product = admin(
        "POST",
        "/api/v1/inventory/products",
        {
            "sku": "GROC-TILL",
            "barcode": "6291000000088",
            "name": "Acceptance Grocery Tin",
            "price_cents": 500,
            "category_id": category_id,
        },
    )
    status, _ = admin(
        "POST",
        "/api/v1/inventory/adjust",
        {
            "adjustment_id": str(uuid.uuid4()),
            "product_id": product["id"],
            "store_id": store_id,
            "mode": "add",
            "quantity": 8,
            "reason_code": "SUPPLIER_SAMPLE_IN",
            "note": "Acceptance grocery till receipt",
            "unit_cost_cents": 100,
            "lot_number": "GROC-TILL",
            "expiry_date": "2027-03-01",
        },
    )
    if status not in {200, 201}:
        raise SystemExit(f"Grocery stock failed: HTTP {status}")
    _, fefo = admin(
        "POST",
        "/api/v1/inventory/products",
        {
            "sku": "GROC-FEFO",
            "barcode": "6291000000077",
            "name": "Acceptance Grocery FEFO",
            "price_cents": 400,
            "category_id": category_id,
        },
    )
    for lot, quantity, expiry in (
        ("GROC-EARLY", 3, "2026-12-15"),
        ("GROC-LATER", 5, "2027-08-01"),
    ):
        layer_status, _ = admin(
            "POST",
            "/api/v1/inventory/adjust",
            {
                "adjustment_id": str(uuid.uuid4()),
                "product_id": fefo["id"],
                "store_id": store_id,
                "mode": "add",
                "quantity": quantity,
                "reason_code": "SUPPLIER_SAMPLE_IN",
                "note": "Acceptance grocery FEFO layer",
                "unit_cost_cents": 100,
                "lot_number": lot,
                "expiry_date": expiry,
            },
        )
        if layer_status not in {200, 201}:
            raise SystemExit(f"Grocery FEFO layer {lot} failed: HTTP {layer_status}")
    activation_for(admin, store_id, "GROC1", "Grocery acceptance register", "GROCERY")
    (EVIDENCE / "grocery-ready.json").write_text(
        json.dumps(
            {
                "tenant": "accept-grocery",
                "cashier": "cashier.g",
                "product": "Acceptance Grocery Tin",
                "fefo_product": "Acceptance Grocery FEFO",
                "fefo_layers": [
                    {"lot": "GROC-EARLY", "quantity": 3, "expiry": "2026-12-15"},
                    {"lot": "GROC-LATER", "quantity": 5, "expiry": "2027-08-01"},
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def up() -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "developer-before.txt").write_text(developer_listing(), encoding="utf-8")
    import socket

    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", 18080))
        except OSError as error:
            raise SystemExit("127.0.0.1:18080 is busy. Refusing to point the acceptance register at another API.") from error
    db_port = 55432
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", db_port))
        except OSError as error:
            raise SystemExit("127.0.0.1:55432 is busy. Refusing to choose another database port.") from error
    password = secrets.token_urlsafe(24)
    secrets_map = {
        "jwt": secrets.token_urlsafe(48),
        "pin": secrets.token_urlsafe(24),
        "encryption": secrets.token_urlsafe(48),
        "api_key": secrets.token_urlsafe(24),
        "admin": "accept-admin-" + secrets.token_hex(4),
        "staff": "accept-staff-" + secrets.token_hex(4),
    }
    RUNTIME.write_text(f"ACCEPTANCE_DB_PASSWORD={password}\nACCEPTANCE_DB_PORT={db_port}\n", encoding="utf-8")
    run(["docker", "compose", "-f", str(HERE / "docker-compose.yml"), "--env-file", str(RUNTIME), "up", "-d", "--wait"], cwd=HERE)
    published = subprocess.run(["docker", "port", CONTAINER, "5432"], check=False, capture_output=True, text=True)
    if published.stdout.strip() != f"127.0.0.1:{db_port}":
        raise SystemExit(f"Postgres published at {published.stdout.strip()!r}.")
    run(
        [
            "docker",
            "exec",
            CONTAINER,
            "psql",
            "-U",
            "axizpos_acceptance",
            "-d",
            "axizpos_pharmacy_acceptance",
            "-c",
            "CREATE DATABASE axizpos_pharmacy_acceptance_control",
        ]
    )
    write_env(db_port, 18080, 15173, password, secrets_map)
    guard = subprocess.run([str(PYTHON), str(HERE / "guard.py")], cwd=ROOT, env=child_env(), text=True, capture_output=True, check=False)
    (EVIDENCE / "isolation.txt").write_text((guard.stdout or "") + (guard.stderr or ""), encoding="utf-8")
    if guard.returncode != 0:
        raise SystemExit("Isolation guard refused to continue.")
    node = ["node", str(NODE_PYTHON), "--env=acceptance", "-m", "app.tenancy.cli"]
    run(node + ["init"])
    for slug, name, profile in (
        ("pharmacy-accept", "Acceptance Pharmacy", "pharmacy"),
        ("pharmacy-accept-b", "Acceptance Pharmacy B", "pharmacy"),
        ("accept-electronics-wholesale", "Acceptance Electronics", "electronics_wholesale"),
        ("accept-wholesale-retail", "Acceptance Wholesale", "wholesale_retail"),
        ("accept-retail-fashion", "Acceptance Fashion", "retail_fashion"),
        ("accept-grocery", "Acceptance Grocery", "grocery"),
        ("accept-restaurant", "Acceptance Restaurant", "restaurant"),
        ("accept-cafe", "Acceptance Cafe", "cafe"),
        ("accept-quick-service", "Acceptance Quick Service", "quick_service"),
    ):
        run(node + ["create", slug, "--name", name, "--profile", profile])
    run([str(PYTHON), str(HERE / "assign_plan.py")])
    app_password = secrets.token_hex(24)
    grant_app_role(app_password)
    switch_database_role(app_password)
    guard = subprocess.run(
        [str(PYTHON), str(HERE / "guard.py")],
        cwd=ROOT,
        env=child_env({"ACCEPTANCE_EXPECT_APP_ROLE": "1"}),
        text=True,
        capture_output=True,
        check=False,
    )
    with (EVIDENCE / "isolation.txt").open("a", encoding="utf-8") as handle:
        handle.write("\n# application role\n")
        handle.write((guard.stdout or "") + (guard.stderr or ""))
    if guard.returncode != 0:
        raise SystemExit("Application role guard failed.")
    env = child_env(
        {
            "ACCEPTANCE_API_URL": API,
            "ACCEPTANCE_ADMIN_PASSWORD": secrets_map["admin"],
            "ACCEPTANCE_STAFF_PASSWORD": secrets_map["staff"],
            "ACCEPTANCE_API_KEY": secrets_map["api_key"],
            "ADMIN_USERNAME": "admin",
        }
    )
    os.environ.update(env)
    proc = subprocess.Popen(["node", str(NODE_PYTHON), "--env=acceptance", "-m", "app.serve"], cwd=ROOT, env=child_env())
    (EVIDENCE / "api.pid").write_text(str(proc.pid), encoding="utf-8")
    wait_http(f"{API}/health", 90)
    exercise.setup()
    appoint(API)
    till_lot(API)
    admin = Api(API, "pharmacy-accept")
    _login(admin, "admin", secrets_map["admin"])
    activation_for(admin, STORE, "ACC2", "Pharmacy acceptance register", "PHARMACY")
    grocery_terminal(API)
    (EVIDENCE / "ready.json").write_text(
        json.dumps(
            {
                "api": API,
                "tenant": "pharmacy-accept",
                "cashier": "cashier.one",
                "product": "Acceptance Till Medicine",
                "barcode": TILL_BARCODE,
                "database": "127.0.0.1:55432/axizpos_pharmacy_acceptance",
                "role_expected": "ai_pos_app",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print("acceptance stack ready", API)


def down() -> None:
    pid_file = EVIDENCE / "api.pid"
    if pid_file.exists():
        subprocess.run(["taskkill", "/PID", pid_file.read_text(encoding="utf-8").strip(), "/T", "/F"], check=False)
    subprocess.run(["docker", "compose", "-f", str(HERE / "docker-compose.yml"), "--env-file", str(RUNTIME), "down", "-v"], cwd=HERE, check=False)
    if ENV_FILE.exists():
        ENV_FILE.unlink()
    if RUNTIME.exists():
        RUNTIME.unlink()
    (EVIDENCE / "developer-after.txt").write_text(developer_listing(), encoding="utf-8")
    print("acceptance stack removed")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "up"
    if command == "up":
        try:
            up()
        except Exception:
            down()
            raise
    elif command == "down":
        down()
    else:
        raise SystemExit("Use up or down.")
