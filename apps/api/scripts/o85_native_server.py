"""Disposable O8.5 API for the pharmacy acceptance register.

The database is a SQLite file under the temp directory. The process refuses any other URL.
It does not open a protected database and it does not read a production env file's database.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMP = Path(os.environ["TEMP"]) / "axiz-o85"
DB_PATH = TEMP / "axizpos_o85.sqlite"
URL = f"sqlite:///{DB_PATH.as_posix()}"
PORT = 18080
STORE = "00000000-0000-4000-8000-000000000851"
PRODUCT = "00000000-0000-4000-8000-000000000852"


def refuse(url: str) -> None:
    text = url.lower()
    if "axizpos_o85.sqlite" not in text or "axiz-o85" not in text:
        raise SystemExit("Refusing a database that is not the O8.5 disposable SQLite file.")
    for banned in ("prod", "laundry", "developer", "inventory", "5432", "55821"):
        if banned in text:
            raise SystemExit("Refusing a database name that is not the disposable acceptance file.")


def seed_acceptance() -> tuple[str, dict[str, str]]:
    import httpx

    login = httpx.post(
        f"http://127.0.0.1:{PORT}/api/v1/auth/login-password",
        json={"username": "o85admin", "password": "o85-admin-password"},
        timeout=15,
    )
    if login.status_code != 200:
        raise SystemExit(f"Admin login failed ({login.status_code}).")
    token = login.json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}
    profile = httpx.put(
        f"http://127.0.0.1:{PORT}/api/v1/settings/profile",
        headers=auth,
        json={"business_profile": "grocery", "capabilities": None},
        timeout=15,
    )
    if profile.status_code != 200:
        raise SystemExit(f"Profile update failed ({profile.status_code}) {profile.text[:200]}")
    now = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    pushed = httpx.post(
        f"http://127.0.0.1:{PORT}/api/v1/sync/push",
        headers={"X-Api-Key": os.environ["API_KEY"]},
        json={
            "device_id": "o85-seed",
            "events": [
                {
                    "idempotency_key": "o85-store",
                    "entity_type": "store",
                    "operation": "upsert",
                    "occurred_at": now,
                    "payload": {"id": STORE, "code": "O85", "name": "O85 Grocery", "currency": "USD"},
                },
                {
                    "idempotency_key": "o85-product",
                    "entity_type": "product",
                    "operation": "upsert",
                    "occurred_at": now,
                    "payload": {
                        "id": PRODUCT,
                        "store_id": STORE,
                        "sku": "O85-RICE",
                        "barcode": "200000000085",
                        "name": "O85 Rice 1kg",
                        "category": "Grocery",
                        "price_cents": 1000,
                        "currency": "USD",
                        "is_serialized": False,
                        "stock_quantity": 100,
                    },
                },
            ],
        },
        timeout=20,
    )
    if pushed.status_code != 200:
        raise SystemExit(f"Seed push failed ({pushed.status_code}) {pushed.text[:300]}")
    created = httpx.post(
        f"http://127.0.0.1:{PORT}/api/v1/devices",
        headers=auth,
        json={"store_id": STORE, "code": "T85", "name": "O85 Till"},
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
        "store_code": "o85",
        "store_id": STORE,
        "product_id": PRODUCT,
        "barcode": "200000000085",
        "device_id": device_id,
        "activation_key": issued.json()["activation_key"],
        "profile": "grocery",
    }
    (TEMP / "ready.json").write_text(json.dumps(ready), encoding="utf-8")
    print("O85_READY", flush=True)
    return device_id, auth


def main() -> None:
    seed = os.environ.get("O85_SIGNING_SEED", "").strip()
    key_id = os.environ.get("O85_KEY_ID", "").strip()
    if not seed or key_id != "o85-accept-1":
        raise SystemExit("O85 signing material is missing.")
    TEMP.mkdir(parents=True, exist_ok=True)
    resume = os.environ.get("O85_RESUME", "").strip() == "1" and DB_PATH.exists()
    if DB_PATH.exists() and not resume:
        DB_PATH.unlink()
    refuse(URL)
    os.environ["APP_ENV"] = "test"
    os.environ["DATABASE_URL"] = URL
    os.environ["CONTROL_DATABASE_URL"] = ""
    os.environ["DEFAULT_TENANT"] = ""
    os.environ["JWT_SECRET"] = "o85-jwt-secret-must-be-32-chars!!"
    os.environ["PIN_SALT"] = "o85-pin-pepper-16c"
    os.environ["ENCRYPTION_SECRET"] = "o85-encryption-secret-32-chars!!"
    os.environ["CORS_ORIGINS"] = "http://127.0.0.1:18080"
    os.environ["API_KEY"] = "o85-api-key-value-not-production"
    os.environ["API_HOST"] = "127.0.0.1"
    os.environ["API_PORT"] = str(PORT)
    os.environ["SCHEDULER_ENABLED"] = "false"
    os.environ["ENTITLEMENT_SIGNING_SEED"] = seed
    os.environ["ENTITLEMENT_SIGNING_KEY_ID"] = key_id
    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    from app.core.config import get_settings
    from app.core.database import build_engine
    from app.core.permissions import CASHIER_ROLE_ID
    from app.core.security import hash_pin
    from app.models import Base, User
    from app.models.device import Device
    from app.services.rbac_service import ensure_super_admin, ensure_system_roles

    get_settings.cache_clear()
    settings = get_settings()
    refuse(settings.database_url)
    if settings.tenancy_enabled:
        raise SystemExit("Tenancy is enabled. The disposable API must stay single-tenant.")
    engine = build_engine(settings.database_url)
    if not resume:
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine, expire_on_commit=False)()
        ensure_system_roles(db)
        ensure_super_admin(
            db,
            settings,
            username="o85admin",
            email="o85admin@acceptance.invalid",
            full_name="O85 Admin",
            password="o85-admin-password",
            pin="2468",
        )
        db.add(
            User(
                id=uuid.UUID("00000000-0000-4000-8000-000000000002"),
                username="cashier",
                email="cashier@acceptance.invalid",
                full_name="Front Cashier",
                hashed_pin=hash_pin("1357", settings),
                is_active=True,
                store_id=None,
                role_id=uuid.UUID(CASHIER_ROLE_ID),
                has_pos_access=True,
                has_portal_access=False,
                failed_login_attempts=0,
                token_version=0,
            )
        )
        db.commit()
        db.close()
    engine.dispose()

    from app.main import app
    from app.tenancy.context import TenantRef, use_tenant

    class NameAcceptanceTenant:
        """Names this disposable API as the tenant the register activated against.

        Tenancy stays off, so the database does not change. Settings then return the same
        store code the activation response stored, and the register can cache the profile.
        """

        def __init__(self, asgi):
            self.asgi = asgi

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http":
                await self.asgi(scope, receive, send)
                return
            tenant = TenantRef(
                id="00000000-0000-4000-8000-0000000000a1",
                slug="default",
                name="O85",
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
        saved = json.loads((TEMP / "ready.json").read_text(encoding="utf-8"))
        device_id = saved["device_id"]
        auth = {}
        print("O85_RESUMED", flush=True)
        allocated = True
    else:
        device_id, auth = seed_acceptance()
        allocated = False

    watch = create_engine(URL)
    while not server.should_exit:
        if not allocated:
            with watch.connect() as conn:
                bound = conn.execute(
                    select(Device.device_public_key_thumbprint).where(Device.id == uuid.UUID(device_id))
                ).scalar()
            if bound:
                grant = httpx.post(
                    f"http://127.0.0.1:{PORT}/api/v1/inventory/allocations",
                    headers=auth,
                    json={"store_id": STORE, "device_id": device_id, "product_id": PRODUCT, "quantity": 40},
                    timeout=20,
                )
                if grant.status_code == 201:
                    allocated = True
                    print("O85_ALLOCATED", flush=True)
                else:
                    print(f"O85_ALLOCATE_{grant.status_code}", flush=True)
        time.sleep(1)
    watch.dispose()


if __name__ == "__main__":
    main()
