"""Disposable O8.10 Restaurant API for the restaurant acceptance register.

The database is a SQLite file under the temp directory. The process refuses any other URL.
It does not open a protected database. Tenancy stays off, matching the grocery acceptance API.
The business-wide owner sets the Restaurant preset. A store-bound user is not used for that change.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMP = Path(os.environ["TEMP"]) / "axiz-o810"
DB_PATH = TEMP / "axizpos_o810.sqlite"
URL = f"sqlite:///{DB_PATH.as_posix()}"
PORT = 18089
DOWNTOWN = "00000000-0000-4000-8000-000000000a10"
MARINA = "00000000-0000-4000-8000-000000000a11"
GRILL = "00000000-0000-4000-8000-000000000a12"
KEY_ID = "o810-accept-1"


def refuse(url: str) -> None:
    text = url.lower()
    if "axizpos_o810.sqlite" not in text or "axiz-o810" not in text:
        raise SystemExit("Refusing a database that is not the O8.10 disposable SQLite file.")
    for banned in ("prod", "laundry", "developer", "inventory", "5432", "55821", "o85"):
        if banned in text:
            raise SystemExit("Refusing a database name that is not the disposable acceptance file.")


def ensure_signing_material() -> str:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

    TEMP.mkdir(parents=True, exist_ok=True)
    seed_path = TEMP / "seed.b64"
    if not seed_path.exists():
        raw = Ed25519PrivateKey.generate().private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        seed_path.write_text(base64.b64encode(raw).decode("ascii"), encoding="utf-8")
    seed = seed_path.read_text(encoding="utf-8").strip()
    key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(seed))
    public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    (TEMP / "public.b64").write_text(base64.b64encode(public).decode("ascii"), encoding="utf-8")
    (TEMP / "key-id.txt").write_text(KEY_ID, encoding="utf-8")
    return seed


def seed_acceptance() -> str:
    import httpx

    from app.core.capabilities import PROFILES

    login = httpx.post(
        f"http://127.0.0.1:{PORT}/api/v1/auth/login-password",
        json={"username": "o810owner", "password": "o810-owner-password"},
        timeout=15,
    )
    if login.status_code != 200:
        raise SystemExit(f"Owner login failed ({login.status_code}).")
    token = login.json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}
    profile = httpx.put(
        f"http://127.0.0.1:{PORT}/api/v1/settings/profile",
        headers=auth,
        json={
            "business_profile": "restaurant",
            "capabilities": [item.value for item in PROFILES["restaurant"]],
        },
        timeout=15,
    )
    if profile.status_code != 200:
        raise SystemExit(f"Profile update failed ({profile.status_code}) {profile.text[:240]}")
    body = profile.json()
    if body.get("business_profile") != "restaurant" or "open_orders" not in body.get("capabilities", []):
        raise SystemExit("Restaurant preset did not include open_orders.")
    now = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    pushed = httpx.post(
        f"http://127.0.0.1:{PORT}/api/v1/sync/push",
        headers={"X-Api-Key": os.environ["API_KEY"]},
        json={
            "device_id": "o810-seed",
            "events": [
                {
                    "idempotency_key": "o810-downtown",
                    "entity_type": "store",
                    "operation": "upsert",
                    "occurred_at": now,
                    "payload": {"id": DOWNTOWN, "code": "O810", "name": "Downtown Restaurant", "currency": "USD"},
                },
                {
                    "idempotency_key": "o810-marina",
                    "entity_type": "store",
                    "operation": "upsert",
                    "occurred_at": now,
                    "payload": {"id": MARINA, "code": "O810M", "name": "Marina Restaurant", "currency": "USD"},
                },
                {
                    "idempotency_key": "o810-grill",
                    "entity_type": "product",
                    "operation": "upsert",
                    "occurred_at": now,
                    "payload": {
                        "id": GRILL,
                        "store_id": DOWNTOWN,
                        "sku": "O810-GRILL",
                        "barcode": "200000000810",
                        "name": "O810 Grill",
                        "category": "Mains",
                        "price_cents": 1800,
                        "currency": "USD",
                        "is_serialized": False,
                        "stock_quantity": 50,
                    },
                },
            ],
        },
        timeout=20,
    )
    if pushed.status_code != 200:
        raise SystemExit(f"Seed push failed ({pushed.status_code}) {pushed.text[:300]}")
    group = httpx.post(
        f"http://127.0.0.1:{PORT}/api/v1/menu/modifier-groups",
        headers=auth,
        json={
            "name": "O810 Doneness",
            "min_select": 1,
            "max_select": 1,
            "options": [
                {"name": "Medium", "price_delta_cents": 0, "is_default": True},
                {"name": "Well done", "price_delta_cents": 0},
            ],
        },
        timeout=15,
    )
    if group.status_code != 201:
        raise SystemExit(f"Modifier group failed ({group.status_code}) {group.text[:240]}")
    area = httpx.post(
        f"http://127.0.0.1:{PORT}/api/v1/dining/areas",
        headers=auth,
        json={"store_id": DOWNTOWN, "name": "Downtown Room"},
        timeout=15,
    )
    if area.status_code != 201:
        raise SystemExit(f"Downtown area failed ({area.status_code}) {area.text[:240]}")
    area_id = area.json()["areas"][0]["id"]
    table = httpx.post(
        f"http://127.0.0.1:{PORT}/api/v1/dining/tables",
        headers=auth,
        json={"area_id": area_id, "label": "5", "seats": 4},
        timeout=15,
    )
    if table.status_code != 201:
        raise SystemExit(f"Downtown table failed ({table.status_code}) {table.text[:240]}")
    marina = httpx.post(
        f"http://127.0.0.1:{PORT}/api/v1/dining/areas",
        headers=auth,
        json={"store_id": MARINA, "name": "Marina Room"},
        timeout=15,
    )
    if marina.status_code != 201:
        raise SystemExit(f"Marina area failed ({marina.status_code}) {marina.text[:240]}")
    roles = httpx.get(f"http://127.0.0.1:{PORT}/api/v1/roles", headers=auth, timeout=15)
    if roles.status_code != 200:
        raise SystemExit(f"Roles failed ({roles.status_code})")
    cashier_role = next(role["id"] for role in roles.json() if role["name"] == "Cashier")
    manager_role = next(role["id"] for role in roles.json() if role["name"] == "Store Manager")
    for username, email, name, role_id, store_id, pin in (
        ("o810cashier", "o810cashier@acceptance.invalid", "Downtown Cashier", cashier_role, DOWNTOWN, "1358"),
        ("o810manager", "o810manager@acceptance.invalid", "Downtown Manager", manager_role, DOWNTOWN, "2460"),
    ):
        made = httpx.post(
            f"http://127.0.0.1:{PORT}/api/v1/users",
            headers=auth,
            json={
                "username": username,
                "email": email,
                "full_name": name,
                "role_id": role_id,
                "store_id": store_id,
                "pin": pin,
                "has_pos_access": True,
                "password": f"{username}-password",
                "has_portal_access": username.endswith("manager"),
            },
            timeout=15,
        )
        if made.status_code != 201:
            raise SystemExit(f"User {username} failed ({made.status_code}) {made.text[:240]}")
    created = httpx.post(
        f"http://127.0.0.1:{PORT}/api/v1/devices",
        headers=auth,
        json={"store_id": DOWNTOWN, "code": "DTA", "name": "Downtown Till A"},
        timeout=15,
    )
    if created.status_code != 201:
        raise SystemExit(f"Device create failed ({created.status_code}) {created.text[:300]}")
    device_id = created.json()["device"]["id"]
    issued = httpx.post(
        f"http://127.0.0.1:{PORT}/api/v1/devices/{device_id}/activation-key",
        headers=auth,
        timeout=15,
    )
    if issued.status_code != 201:
        raise SystemExit(f"Activation key failed ({issued.status_code}) {issued.text[:200]}")
    ready = {
        "api": f"http://127.0.0.1:{PORT}",
        "database": str(DB_PATH),
        "store_code": "o810",
        "store_id": DOWNTOWN,
        "marina_store_id": MARINA,
        "product_id": GRILL,
        "device_id": device_id,
        "activation_key": issued.json()["activation_key"],
        "profile": body["business_profile"],
        "capabilities": body["capabilities"],
        "key_id": KEY_ID,
    }
    (TEMP / "ready.json").write_text(json.dumps(ready), encoding="utf-8")
    print("O810_READY", body["business_profile"], "open_orders", flush=True)
    return device_id


def main() -> None:
    seed = ensure_signing_material()
    TEMP.mkdir(parents=True, exist_ok=True)
    resume = os.environ.get("O810_RESUME", "").strip() == "1" and DB_PATH.exists()
    if DB_PATH.exists() and not resume:
        DB_PATH.unlink()
    refuse(URL)
    os.environ["APP_ENV"] = "test"
    os.environ["DATABASE_URL"] = URL
    os.environ["CONTROL_DATABASE_URL"] = ""
    os.environ["DEFAULT_TENANT"] = ""
    os.environ["JWT_SECRET"] = "o810-jwt-secret-must-be-32-chars!"
    os.environ["PIN_SALT"] = "o810-pin-pepper-16"
    os.environ["ENCRYPTION_SECRET"] = "o810-encryption-secret-32-chars!"
    os.environ["CORS_ORIGINS"] = "http://127.0.0.1:18089"
    os.environ["API_KEY"] = "o810-api-key-value-not-production"
    os.environ["API_HOST"] = "127.0.0.1"
    os.environ["API_PORT"] = str(PORT)
    os.environ["SCHEDULER_ENABLED"] = "false"
    os.environ["ENTITLEMENT_SIGNING_SEED"] = seed
    os.environ["ENTITLEMENT_SIGNING_KEY_ID"] = KEY_ID
    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from app.core.config import get_settings
    from app.core.database import build_engine
    from app.models import Base
    from app.services.rbac_service import ensure_super_admin, ensure_system_roles

    get_settings.cache_clear()
    settings = get_settings()
    refuse(settings.database_url)
    if settings.tenancy_enabled:
        raise SystemExit("Tenancy is enabled. The disposable API must stay single-tenant.")
    engine = build_engine(settings.database_url)
    if not resume:
        Base.metadata.create_all(engine)
        from sqlalchemy.orm import sessionmaker

        db = sessionmaker(bind=engine, expire_on_commit=False)()
        ensure_system_roles(db)
        ensure_super_admin(
            db,
            settings,
            username="o810owner",
            email="o810owner@acceptance.invalid",
            full_name="O810 Owner",
            password="o810-owner-password",
            pin="2480",
        )
        db.commit()
        db.close()
    engine.dispose()

    from app.main import app
    from app.tenancy.context import TenantRef, use_tenant

    class NameAcceptanceTenant:
        def __init__(self, asgi):
            self.asgi = asgi

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http":
                await self.asgi(scope, receive, send)
                return
            tenant = TenantRef(
                id="00000000-0000-4000-8000-0000000000a1",
                slug="o810",
                name="O810 Restaurant",
                database_url=URL,
                data_plane="shared",
            )
            with use_tenant(tenant):
                await self.asgi(scope, receive, send)

    app.add_middleware(NameAcceptanceTenant)

    import uvicorn

    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning")
    server = uvicorn.Server(config)

    import threading

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    import httpx

    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            health = httpx.get(f"http://127.0.0.1:{PORT}/health", timeout=2)
            if health.status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.3)
    else:
        raise SystemExit("Disposable API did not open /health.")

    if resume:
        print("O810_RESUMED", flush=True)
    else:
        seed_acceptance()

    while not server.should_exit:
        time.sleep(1)


if __name__ == "__main__":
    main()
