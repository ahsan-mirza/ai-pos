"""Disposable Restaurant or Cafe API for portion-pricing native acceptance.

The database is a SQLite file under the temp directory. The process refuses any other URL.
It does not open the O8.10 restaurant database, the laundry till, or a protected database.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILES = {
    "restaurant": (18094, "restaurant", "portionr", "Portion Restaurant", "com.axizpos.restaurant.portion"),
    "cafe": (18095, "cafe", "portionc", "Portion Cafe", "com.axizpos.cafe.portion"),
}
PROFILE = os.environ.get("PORTION_PROFILE", "").strip()
if PROFILE not in PROFILES:
    raise SystemExit("PORTION_PROFILE must be restaurant or cafe.")
PORT, BUSINESS, STORE_CODE, STORE_NAME, IDENTIFIER = PROFILES[PROFILE]
TEMP = Path(os.environ["TEMP"]) / "axiz-portion" / PROFILE
DB_PATH = TEMP / f"axizpos_portion_{PROFILE}.sqlite"
URL = f"sqlite:///{DB_PATH.as_posix()}"
STORE = "00000000-0000-4000-8000-00000000d010" if PROFILE == "restaurant" else "00000000-0000-4000-8000-00000000d020"


def refuse(url: str) -> None:
    text = url.lower()
    expected = f"axizpos_portion_{PROFILE}.sqlite"
    if expected not in text or "axiz-portion" not in text:
        raise SystemExit("Refusing a database that is not this portion profile's disposable SQLite file.")
    for banned in ("prod", "laundry", "developer", "5432", "55821", "18080", "18089", "o810", "axiz-o810"):
        if banned in text:
            raise SystemExit("Refusing a database name that is not the disposable portion file.")


def main() -> None:
    seed_b64 = os.environ.get("PORTION_SIGNING_SEED", "").strip()
    key_id = os.environ.get("PORTION_KEY_ID", "").strip()
    if not seed_b64 or key_id != "portion-accept-1":
        raise SystemExit("Portion signing material is missing.")
    TEMP.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists() and os.environ.get("PORTION_RESUME", "").strip() != "1":
        DB_PATH.unlink()
    refuse(URL)
    os.environ["APP_ENV"] = "test"
    os.environ["DATABASE_URL"] = URL
    os.environ["CONTROL_DATABASE_URL"] = ""
    os.environ["DEFAULT_TENANT"] = ""
    os.environ["JWT_SECRET"] = "portion-jwt-secret-must-be-32-chars!"
    os.environ["PIN_SALT"] = "portion-pin-pepper16"
    os.environ["ENCRYPTION_SECRET"] = "portion-encryption-secret-32-chars!"
    os.environ["CORS_ORIGINS"] = f"http://127.0.0.1:{PORT}"
    os.environ["API_KEY"] = "portion-api-key-value-not-production"
    os.environ["API_HOST"] = "127.0.0.1"
    os.environ["API_PORT"] = str(PORT)
    os.environ["SCHEDULER_ENABLED"] = "false"
    os.environ["ENTITLEMENT_SIGNING_SEED"] = seed_b64
    os.environ["ENTITLEMENT_SIGNING_KEY_ID"] = key_id
    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from sqlalchemy import text
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
    with engine.connect() as conn:
        columns = [row[1] for row in conn.execute(text("PRAGMA table_info(products)"))]
    if "sell_without_recipe" not in columns:
        raise SystemExit("The disposable schema is missing products.sell_without_recipe.")
    resume = os.environ.get("PORTION_RESUME", "").strip() == "1"
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    if resume:
        db.close()
        engine.dispose()
    else:
        ensure_system_roles(db)
        ensure_super_admin(
            db,
            settings,
            username="portionowner",
            email=f"owner-{PROFILE}@acceptance.invalid",
            full_name="Portion Owner",
            password="portion-owner-password",
            pin="2480",
        )
        db.add(
            User(
                id=uuid.uuid4(),
                username="portioncashier",
                email=f"cashier-{PROFILE}@acceptance.invalid",
                full_name="Portion Cashier",
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

    class PortionTenant:
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

    app.add_middleware(PortionTenant)
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
        print("PORTION_READY", PROFILE, "resumed", flush=True)
        while not server.should_exit:
            time.sleep(1)
        return

    login = httpx.post(
        f"http://127.0.0.1:{PORT}/api/v1/auth/login-password",
        json={"username": "portionowner", "password": "portion-owner-password"},
        timeout=20,
    )
    if login.status_code != 200:
        raise SystemExit(f"Owner login failed ({login.status_code}).")
    auth = {"Authorization": f"Bearer {login.json()['access_token']}"}
    profile = httpx.put(
        f"http://127.0.0.1:{PORT}/api/v1/settings/profile",
        headers=auth,
        json={"business_profile": BUSINESS, "capabilities": [item.value for item in CAPABILITY_PROFILES[BUSINESS]]},
        timeout=20,
    )
    if profile.status_code != 200:
        raise SystemExit(f"Profile update failed ({profile.status_code}) {profile.text[:240]}")
    now = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    pushed = httpx.post(
        f"http://127.0.0.1:{PORT}/api/v1/sync/push",
        headers={"X-Api-Key": os.environ["API_KEY"]},
        json={
            "device_id": f"portion-seed-{PROFILE}",
            "events": [
                {
                    "idempotency_key": f"portion-store-{PROFILE}",
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
    category = httpx.post(f"http://127.0.0.1:{PORT}/api/v1/categories", headers=auth, json={"name": "Kitchen"}, timeout=20)
    if category.status_code not in (200, 201):
        raise SystemExit(f"Category failed ({category.status_code}) {category.text[:200]}")
    ingredient = httpx.post(
        f"http://127.0.0.1:{PORT}/api/v1/inventory/products",
        headers=auth,
        json={
            "sku": f"ING-CHANNA-{PROFILE[:3].upper()}",
            "barcode": "281000000001" if PROFILE == "restaurant" else "281000000002",
            "name": "Channa",
            "category_id": category.json()["id"],
            "price_cents": 0,
            "item_type": "RAW_INGREDIENT",
            "is_ingredient": True,
            "opening_store_id": STORE,
            "opening_quantity": 100,
        },
        timeout=20,
    )
    if ingredient.status_code not in (200, 201):
        raise SystemExit(f"Ingredient failed ({ingredient.status_code}) {ingredient.text[:240]}")
    if "tables" in {item.value for item in CAPABILITY_PROFILES[BUSINESS]}:
        area = httpx.post(
            f"http://127.0.0.1:{PORT}/api/v1/dining/areas",
            headers=auth,
            json={"store_id": STORE, "name": "Main Room"},
            timeout=20,
        )
        if area.status_code != 201:
            raise SystemExit(f"Dining area failed ({area.status_code}) {area.text[:200]}")
        table = httpx.post(
            f"http://127.0.0.1:{PORT}/api/v1/dining/tables",
            headers=auth,
            json={"area_id": area.json()["areas"][0]["id"], "label": "T1", "seats": 4},
            timeout=20,
        )
        if table.status_code != 201:
            raise SystemExit(f"Table failed ({table.status_code}) {table.text[:200]}")
    created = httpx.post(
        f"http://127.0.0.1:{PORT}/api/v1/devices",
        headers=auth,
        json={"store_id": STORE, "code": "PR1" if PROFILE == "restaurant" else "PC1", "name": STORE_NAME + " Till"},
        timeout=20,
    )
    if created.status_code != 201:
        raise SystemExit(f"Device create failed ({created.status_code}) {created.text[:240]}")
    device_id = created.json()["device"]["id"]
    issued = httpx.post(f"http://127.0.0.1:{PORT}/api/v1/devices/{device_id}/activation-key", headers=auth, timeout=20)
    if issued.status_code != 201:
        raise SystemExit(f"Activation key failed ({issued.status_code}).")
    ready = {
        "profile": PROFILE,
        "business_profile": profile.json()["business_profile"],
        "identifier": IDENTIFIER,
        "api": f"http://127.0.0.1:{PORT}",
        "database": str(DB_PATH),
        "store_code": STORE_CODE,
        "store_id": STORE,
        "store_name": STORE_NAME,
        "currency": money.json().get("currency"),
        "category_id": category.json()["id"],
        "ingredient_id": ingredient.json()["id"],
        "device_id": device_id,
        "activation_key": issued.json()["activation_key"],
        "owner_username": "portionowner",
        "owner_pin": "2480",
        "cashier_username": "portioncashier",
        "cashier_pin": "1357",
        "sell_without_recipe_column": True,
        "alembic": "not applied; schema comes from create_all and includes 20261122_0135 column",
    }
    (TEMP / "ready.json").write_text(json.dumps(ready), encoding="utf-8")
    print("PORTION_READY", PROFILE, profile.json()["business_profile"], money.json().get("currency"), flush=True)
    while not server.should_exit:
        time.sleep(1)


if __name__ == "__main__":
    main()
