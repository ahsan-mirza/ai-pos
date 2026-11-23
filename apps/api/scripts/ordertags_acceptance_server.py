"""Disposable restaurant API for order-tag and register-settings acceptance.

The database is a SQLite file under the temp directory. The process refuses any other URL.
It does not open a production, laundry, or developer database.
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
PORT = 18096
STORE_CODE = "tagreg"
STORE_NAME = "Order Tag Register"
IDENTIFIER = "com.axizpos.ordertags.acceptance"
TEMP = Path(os.environ["TEMP"]) / "axiz-ordertags"
DB_PATH = TEMP / "axizpos_ordertags.sqlite"
URL = f"sqlite:///{DB_PATH.as_posix()}"
STORE = "00000000-0000-4000-8000-00000000d096"


def refuse(url: str) -> None:
    text = url.lower()
    if "axizpos_ordertags.sqlite" not in text or "axiz-ordertags" not in text:
        raise SystemExit("Refusing a database that is not the order-tag disposable SQLite file.")
    for banned in ("prod", "laundry", "developer", "5432", "55821", "18080", "18089", "18094", "o810"):
        if banned in text:
            raise SystemExit("Refusing a database name that is not the disposable order-tag file.")


def main() -> None:
    seed_b64 = os.environ.get("ORDERTAGS_SIGNING_SEED", "").strip()
    key_id = os.environ.get("ORDERTAGS_KEY_ID", "").strip()
    if not seed_b64 or key_id != "ordertags-accept-1":
        raise SystemExit("Order-tag signing material is missing.")
    TEMP.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists() and os.environ.get("ORDERTAGS_RESUME", "").strip() != "1":
        DB_PATH.unlink()
    refuse(URL)
    os.environ["APP_ENV"] = "test"
    os.environ["DATABASE_URL"] = URL
    os.environ["CONTROL_DATABASE_URL"] = ""
    os.environ["DEFAULT_TENANT"] = ""
    os.environ["JWT_SECRET"] = "ordertags-jwt-secret-must-be-32b!"
    os.environ["PIN_SALT"] = "ordertags-pin-pepper"
    os.environ["ENCRYPTION_SECRET"] = "ordertags-encryption-secret-32b!"
    os.environ["CORS_ORIGINS"] = f"http://127.0.0.1:{PORT}"
    os.environ["API_KEY"] = "ordertags-api-key-value-not-production"
    os.environ["API_HOST"] = "127.0.0.1"
    os.environ["API_PORT"] = str(PORT)
    os.environ["SCHEDULER_ENABLED"] = "false"
    os.environ["ENTITLEMENT_SIGNING_SEED"] = seed_b64
    os.environ["ENTITLEMENT_SIGNING_KEY_ID"] = key_id
    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from sqlalchemy.orm import sessionmaker

    from app.core.capabilities import PROFILES as CAPABILITY_PROFILES
    from app.core.config import get_settings
    from app.core.database import build_engine
    from app.core.permissions import CASHIER_ROLE_ID
    from app.core.security import hash_pin
    from app.models import Base, User
    from app.services.rbac_service import ensure_super_admin, ensure_system_roles

    get_settings.cache_clear()
    settings = get_settings()
    refuse(settings.database_url)
    if settings.tenancy_enabled:
        raise SystemExit("Tenancy is enabled. The disposable API must stay single-tenant.")
    engine = build_engine(settings.database_url)
    Base.metadata.create_all(engine)
    resume = os.environ.get("ORDERTAGS_RESUME", "").strip() == "1"
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    if resume:
        db.close()
        engine.dispose()
    else:
        ensure_system_roles(db)
        ensure_super_admin(
            db,
            settings,
            username="tagowner",
            email="owner-ordertags@acceptance.invalid",
            full_name="Tag Owner",
            password="tag-owner-password",
            pin="2480",
        )
        db.add(
            User(
                id=uuid.uuid4(),
                username="tagcashier",
                email="cashier-ordertags@acceptance.invalid",
                full_name="Tag Cashier",
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

    class OrderTagTenant:
        def __init__(self, asgi):
            self.asgi = asgi

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http":
                await self.asgi(scope, receive, send)
                return
            tenant = TenantRef(
                id="00000000-0000-4000-8000-0000000000a1",
                slug=STORE_CODE,
                name=STORE_NAME,
                database_url=URL,
                data_plane="shared",
            )
            with use_tenant(tenant):
                await self.asgi(scope, receive, send)

    app.add_middleware(OrderTagTenant)
    import uvicorn

    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    import threading

    threading.Thread(target=server.run, daemon=True).start()
    import httpx

    deadline = time.time() + 40
    while time.time() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{PORT}/health", timeout=2).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.3)
    else:
        raise SystemExit("Disposable API did not open /health.")

    if resume:
        print("ORDERTAGS_READY resumed", flush=True)
        while not server.should_exit:
            time.sleep(1)
        return

    login = httpx.post(
        f"http://127.0.0.1:{PORT}/api/v1/auth/login-password",
        json={"username": "tagowner", "password": "tag-owner-password"},
        timeout=20,
    )
    if login.status_code != 200:
        raise SystemExit(f"Owner login failed ({login.status_code}).")
    auth = {"Authorization": f"Bearer {login.json()['access_token']}"}
    profile = httpx.put(
        f"http://127.0.0.1:{PORT}/api/v1/settings/profile",
        headers=auth,
        json={"business_profile": "restaurant", "capabilities": [item.value for item in CAPABILITY_PROFILES["restaurant"]]},
        timeout=20,
    )
    if profile.status_code != 200:
        raise SystemExit(f"Profile update failed ({profile.status_code}) {profile.text[:240]}")
    now = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    pushed = httpx.post(
        f"http://127.0.0.1:{PORT}/api/v1/sync/push",
        headers={"X-Api-Key": os.environ["API_KEY"]},
        json={
            "device_id": "ordertags-seed",
            "events": [
                {
                    "idempotency_key": "ordertags-store",
                    "entity_type": "store",
                    "operation": "upsert",
                    "occurred_at": now,
                    "payload": {"id": STORE, "code": STORE_CODE.upper(), "name": STORE_NAME, "currency": "USD"},
                }
            ],
        },
        timeout=20,
    )
    if pushed.status_code != 200:
        raise SystemExit(f"Store seed failed ({pushed.status_code}) {pushed.text[:240]}")
    money = httpx.put(f"http://127.0.0.1:{PORT}/api/v1/settings/currency", headers=auth, json={"currency": "AED"}, timeout=20)
    if money.status_code != 200:
        raise SystemExit(f"Currency update failed ({money.status_code}) {money.text[:240]}")
    category = httpx.post(f"http://127.0.0.1:{PORT}/api/v1/categories", headers=auth, json={"name": "Counter"}, timeout=20)
    if category.status_code not in (200, 201):
        raise SystemExit(f"Category failed ({category.status_code}) {category.text[:200]}")
    water = httpx.post(
        f"http://127.0.0.1:{PORT}/api/v1/inventory/products",
        headers=auth,
        json={
            "sku": "TAG-WATER",
            "barcode": "281000000096",
            "name": "Mineral Water",
            "category_id": category.json()["id"],
            "price_cents": 200,
            "opening_store_id": STORE,
            "opening_quantity": 20,
        },
        timeout=20,
    )
    if water.status_code not in (200, 201):
        raise SystemExit(f"Water failed ({water.status_code}) {water.text[:240]}")
    created = httpx.post(
        f"http://127.0.0.1:{PORT}/api/v1/devices",
        headers=auth,
        json={"store_id": STORE, "code": "TG1", "name": "Order Tag Till"},
        timeout=20,
    )
    if created.status_code != 201:
        raise SystemExit(f"Device create failed ({created.status_code}) {created.text[:240]}")
    device_id = created.json()["device"]["id"]
    issued = httpx.post(f"http://127.0.0.1:{PORT}/api/v1/devices/{device_id}/activation-key", headers=auth, timeout=20)
    if issued.status_code != 201:
        raise SystemExit(f"Activation key failed ({issued.status_code}).")
    ready = {
        "identifier": IDENTIFIER,
        "api": f"http://127.0.0.1:{PORT}",
        "database": str(DB_PATH),
        "store_code": STORE_CODE,
        "store_id": STORE,
        "store_name": STORE_NAME,
        "currency": money.json().get("currency"),
        "business_profile": profile.json()["business_profile"],
        "device_id": device_id,
        "activation_key": issued.json()["activation_key"],
        "owner_username": "tagowner",
        "owner_pin": "2480",
        "cashier_username": "tagcashier",
        "cashier_pin": "1357",
        "product": "Mineral Water",
    }
    (TEMP / "ready.json").write_text(json.dumps(ready), encoding="utf-8")
    print("ORDERTAGS_READY", profile.json()["business_profile"], money.json().get("currency"), flush=True)
    while not server.should_exit:
        time.sleep(1)


if __name__ == "__main__":
    main()
