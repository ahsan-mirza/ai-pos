"""Disposable catalogue API for one zoom-acceptance profile.

The database is a SQLite file under the temp directory. The process refuses any other URL.
It does not open a protected database and it does not read a production env file.
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
    "grocery": (18090, "grocery", "gzoom", "Zoom Grocery"),
    "electronics": (18091, "electronics_wholesale", "ezoom", "Zoom Electronics"),
    "fashion": (18092, "retail_fashion", "fzoom", "Zoom Fashion"),
    "restaurant": (18093, "restaurant", "rzoom", "Zoom Restaurant"),
}
PROFILE = os.environ.get("ZOOM_PROFILE", "").strip()
if PROFILE not in PROFILES:
    raise SystemExit("ZOOM_PROFILE must be grocery, electronics, fashion, or restaurant.")
PORT, BUSINESS, STORE_CODE, STORE_NAME = PROFILES[PROFILE]
TEMP = Path(os.environ["TEMP"]) / "axiz-zoom" / PROFILE
DB_PATH = TEMP / f"axizpos_zoom_{PROFILE}.sqlite"
URL = f"sqlite:///{DB_PATH.as_posix()}"
STORE = f"00000000-0000-4000-8000-00000000c{PORT % 10}10"
LONG_NAME = "Zoom Extra Long Product Name For Catalogue Card Pressure Testing Across The Shared Tile"


def refuse(url: str) -> None:
    text = url.lower()
    if f"axizpos_zoom_{PROFILE}.sqlite" not in text or "axiz-zoom" not in text:
        raise SystemExit("Refusing a database that is not this zoom profile's disposable SQLite file.")
    for banned in ("prod", "laundry", "developer", "5432", "55821", "18080", "18089"):
        if banned in text:
            raise SystemExit("Refusing a database name that is not the disposable zoom file.")


def product(product_id: str, sku: str, name: str, price: int, stock: int, category: str, serialized: bool = False) -> dict:
    return {
        "id": product_id,
        "store_id": STORE,
        "sku": sku,
        "barcode": sku.replace("-", "")[:12].ljust(12, "0"),
        "name": name,
        "category": category,
        "price_cents": price,
        "currency": "USD",
        "is_serialized": serialized,
        "stock_quantity": stock,
    }


def catalogue() -> tuple[list[dict], str]:
    base = f"00000000-0000-4000-8000-00000000c{PORT % 10}"
    if PROFILE == "grocery":
        rows = [
            product(base + "01", "ZGROC-RICE", "Zoom Rice 1kg", 1000, 59, "Grocery"),
            product(base + "02", "ZGROC-LONG", LONG_NAME, 450, 12, "Grocery"),
            product(base + "03", "ZGROC-BIG", "Zoom Bulk Oil", 1234567, 4, "Grocery"),
            product(base + "04", "ZGROC-PLAIN", "Zoom Loose Tea", 350, 0, "Grocery"),
        ]
        return rows, rows[0]["id"]
    if PROFILE == "electronics":
        rows = [
            product(base + "01", "ZELEC-PHONE", "Zoom Handheld Scanner With a Very Long Electronics Name", 89900, 6, "Electronics"),
            product(base + "02", "ZELEC-CABLE", "Zoom USB Cable", 1500, 40, "Electronics"),
            product(base + "03", "ZELEC-BIG", "Zoom Display Wall", 1234567, 2, "Electronics"),
            product(base + "04", "ZELEC-SER", "Zoom Serialized Handset", 45000, 1, "Electronics", True),
        ]
        return rows, rows[0]["id"]
    if PROFILE == "restaurant":
        rows = [
            product(base + "01", "ZFOOD-SALAD", "House Salad", 650, 20, "Kitchen"),
            product(base + "02", "ZFOOD-CHICKEN", "Grilled Chicken", 1800, 20, "Kitchen"),
            product(base + "03", "ZFOOD-PASTA", "Special Pasta", 1000, 20, "Kitchen"),
            product(base + "04", "ZFOOD-JUICE", "Fresh Juice", 300, 20, "Kitchen"),
            product(base + "05", "ZFOOD-FEAST", LONG_NAME, 250000, 20, "Kitchen"),
        ]
        return rows, rows[1]["id"]
    return [], ""


def seed(auth: dict[str, str]) -> dict:
    import httpx

    now = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    profile = httpx.put(
        f"http://127.0.0.1:{PORT}/api/v1/settings/profile",
        headers=auth,
        json={"business_profile": BUSINESS, "capabilities": None},
        timeout=20,
    )
    if profile.status_code != 200:
        raise SystemExit(f"Profile update failed ({profile.status_code}) {profile.text[:240]}")
    rows, allocate_id = catalogue()
    events = [
        {
            "idempotency_key": f"zoom-store-{PROFILE}",
            "entity_type": "store",
            "operation": "upsert",
            "occurred_at": now,
            "payload": {"id": STORE, "code": STORE_CODE.upper(), "name": STORE_NAME, "currency": "USD"},
        }
    ]
    for row in rows:
        events.append(
            {
                "idempotency_key": f"zoom-product-{row['sku']}",
                "entity_type": "product",
                "operation": "upsert",
                "occurred_at": now,
                "payload": row,
            }
        )
    pushed = httpx.post(
        f"http://127.0.0.1:{PORT}/api/v1/sync/push",
        headers={"X-Api-Key": os.environ["API_KEY"]},
        json={"device_id": f"zoom-seed-{PROFILE}", "events": events},
        timeout=30,
    )
    if pushed.status_code != 200:
        raise SystemExit(f"Seed push failed ({pushed.status_code}) {pushed.text[:240]}")
    if PROFILE == "fashion":
        allocate_id = seed_fashion(auth)
    if PROFILE == "restaurant":
        seed_menu(auth, rows)
    created = httpx.post(
        f"http://127.0.0.1:{PORT}/api/v1/devices",
        headers=auth,
        json={"store_id": STORE, "code": "Z" + STORE_CODE[:3].upper(), "name": STORE_NAME + " Till"},
        timeout=20,
    )
    if created.status_code != 201:
        raise SystemExit(f"Device create failed ({created.status_code}).")
    device_id = created.json()["device"]["id"]
    issued = httpx.post(f"http://127.0.0.1:{PORT}/api/v1/devices/{device_id}/activation-key", headers=auth, timeout=20)
    if issued.status_code != 201:
        raise SystemExit(f"Activation key failed ({issued.status_code}).")
    upload_image(auth, rows[0]["id"] if rows else allocate_id)
    return {
        "profile": PROFILE,
        "business_profile": BUSINESS,
        "api": f"http://127.0.0.1:{PORT}",
        "database": str(DB_PATH),
        "store_code": STORE_CODE,
        "store_id": STORE,
        "store_name": STORE_NAME,
        "device_id": device_id,
        "activation_key": issued.json()["activation_key"],
        "username": "zoomcashier",
        "pin": os.environ["ZOOM_CASHIER_PIN"],
        "allocate_product_id": allocate_id,
        "expect": ["Zoom Longline Shirt", "Sand"] if PROFILE == "fashion" else [row["name"] for row in rows][:4],
    }


def seed_fashion(auth: dict[str, str]) -> str:
    import httpx

    category = httpx.post(f"http://127.0.0.1:{PORT}/api/v1/categories", headers=auth, json={"name": "Apparel"}, timeout=20)
    if category.status_code != 201:
        raise SystemExit(f"Category create failed ({category.status_code}).")
    created = httpx.post(
        f"http://127.0.0.1:{PORT}/api/v1/categories/{category.json()['id']}/sub-categories",
        headers=auth,
        json={"name": "Shirts"},
        timeout=20,
    )
    sub = next(row for row in created.json()["sub_categories"] if row["name"] == "Shirts")
    brand = httpx.post(f"http://127.0.0.1:{PORT}/api/v1/brands", headers=auth, json={"name": "Zoom Cloth"}, timeout=20).json()
    model = httpx.post(
        f"http://127.0.0.1:{PORT}/api/v1/product-models",
        headers=auth,
        json={"brand_id": brand["id"], "sub_category_id": sub["id"], "name": "Zoom Longline Shirt", "code": "ZSHIRT"},
        timeout=20,
    )
    if model.status_code != 201:
        raise SystemExit(f"Model create failed ({model.status_code}).")
    model_id = model.json()["id"]
    matrix = httpx.post(
        f"http://127.0.0.1:{PORT}/api/v1/product-models/{model_id}/matrix",
        headers=auth,
        json={
            "axes": [{"key": "Size", "values": ["S", "M"]}, {"key": "color", "values": ["Sand", "Navy"]}],
            "price_cents": 4900,
            "price_by_value": {"M": 5400},
        },
        timeout=30,
    )
    if matrix.status_code != 200:
        raise SystemExit(f"Matrix create failed ({matrix.status_code}).")
    cells = matrix.json()["cells"]
    for cell in cells:
        if cell["attributes"] == {"size": "S", "color": "Navy"}:
            continue
        adjusted = httpx.post(
            f"http://127.0.0.1:{PORT}/api/v1/inventory/adjust",
            headers=auth,
            json={
                "adjustment_id": str(uuid.uuid4()),
                "product_id": cell["product_id"],
                "store_id": STORE,
                "mode": "set",
                "quantity": 8,
                "reason_code": "PHYSICAL_COUNT_AUDIT",
                "note": "Zoom acceptance opening stock.",
                "unit_cost_cents": 100,
            },
            timeout=20,
        )
        if adjusted.status_code not in (200, 201):
            raise SystemExit(f"Stock adjust failed ({adjusted.status_code}) {adjusted.text[:240]}")
    upload_image(auth, cells[0]["product_id"])
    return cells[0]["product_id"]


def seed_menu(auth: dict[str, str], rows: list[dict]) -> None:
    import httpx

    by_sku = {row["sku"]: row["id"] for row in rows}
    options = {
        "ZFOOD-CHICKEN": [("Breakfast", 800), ("Lunch", 1200), ("Dinner", 1500)],
        "ZFOOD-PASTA": [("Small Plate", 800), ("Medium Plate", 1100), ("Large Plate", 1400)],
        "ZFOOD-JUICE": [("Small", 300), ("Large", 500)],
        "ZFOOD-FEAST": [
            ("Regular Plate", 1000),
            ("Large Plate", 1400),
            ("Family celebration platter with extra sides and bread", 250000),
            ("Counter portion", 900),
            ("Late supper", 1600),
            ("Staff meal", 700),
            ("Banquet", 320000),
            ("Tasting", 600),
        ],
    }
    for sku, choices in options.items():
        saved = httpx.put(
            f"http://127.0.0.1:{PORT}/api/v1/menu/products/{by_sku[sku]}/price-options",
            headers=auth,
            json={
                "options": [
                    {"name": name, "price_cents": price, "is_active": True, "position": index}
                    for index, (name, price) in enumerate(choices)
                ]
            },
            timeout=20,
        )
        if saved.status_code != 200:
            raise SystemExit(f"Price options failed for {sku} ({saved.status_code}).")
    group = httpx.post(
        f"http://127.0.0.1:{PORT}/api/v1/menu/modifier-groups",
        headers=auth,
        json={
            "name": "Extras",
            "min_select": 0,
            "max_select": 1,
            "position": 0,
            "is_active": True,
            "options": [{"name": "Extra cheese", "price_delta_cents": 150, "is_default": False, "is_active": True}],
        },
        timeout=20,
    )
    if group.status_code != 201:
        raise SystemExit(f"Modifier group failed ({group.status_code}).")
    linked = httpx.put(
        f"http://127.0.0.1:{PORT}/api/v1/menu/products/{by_sku['ZFOOD-CHICKEN']}/modifier-groups",
        headers=auth,
        json={"group_ids": [group.json()["id"]]},
        timeout=20,
    )
    if linked.status_code != 200:
        raise SystemExit(f"Modifier link failed ({linked.status_code}).")


def upload_image(auth: dict[str, str], product_id: str) -> None:
    import httpx

    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAoAAAAKCAYAAACNMs+9AAAAFUlEQVR42mP8z8BQz0AEYBxVSF+FABJADveWkH6oAAAAAElFTkSuQmCC"
    )
    response = httpx.post(
        f"http://127.0.0.1:{PORT}/api/v1/inventory/products/{product_id}/images",
        headers=auth,
        files={"file": ("zoom.png", png, "image/png")},
        timeout=20,
    )
    if response.status_code != 201:
        print(f"ZOOM_IMAGE_{response.status_code}", flush=True)


def main() -> None:
    seed_b64 = os.environ.get("ZOOM_SIGNING_SEED", "").strip()
    key_id = os.environ.get("ZOOM_KEY_ID", "").strip()
    pin = os.environ.get("ZOOM_CASHIER_PIN", "").strip()
    if not seed_b64 or key_id != "zoom-accept-1" or len(pin) != 4:
        raise SystemExit("Zoom signing material is missing.")
    TEMP.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    refuse(URL)
    os.environ["APP_ENV"] = "test"
    os.environ["DATABASE_URL"] = URL
    os.environ["CONTROL_DATABASE_URL"] = ""
    os.environ["DEFAULT_TENANT"] = ""
    os.environ["JWT_SECRET"] = "zoom-jwt-secret-must-be-32-chars!"
    os.environ["PIN_SALT"] = "zoom-pin-pepper16"
    os.environ["ENCRYPTION_SECRET"] = "zoom-encryption-secret-32-chars!"
    os.environ["CORS_ORIGINS"] = f"http://127.0.0.1:{PORT}"
    os.environ["API_KEY"] = "zoom-api-key-value-not-production"
    os.environ["API_HOST"] = "127.0.0.1"
    os.environ["API_PORT"] = str(PORT)
    os.environ["SCHEDULER_ENABLED"] = "false"
    os.environ["ENTITLEMENT_SIGNING_SEED"] = seed_b64
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
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    ensure_system_roles(db)
    ensure_super_admin(
        db,
        settings,
        username="zoomadmin",
        email=f"zoom-{PROFILE}@acceptance.invalid",
        full_name="Zoom Admin",
        password="zoom-admin-password",
        pin="9081",
    )
    db.add(
        User(
            id=uuid.uuid4(),
            username="zoomcashier",
            email=f"cashier-{PROFILE}@acceptance.invalid",
            full_name="Zoom Cashier",
            hashed_pin=hash_pin(pin, settings),
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

    class NameZoomTenant:
        def __init__(self, asgi):
            self.asgi = asgi

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http":
                await self.asgi(scope, receive, send)
                return
            tenant = TenantRef(
                id="00000000-0000-4000-8000-0000000000a1",
                slug="default",
                name=STORE_NAME,
                database_url=URL,
                data_plane="shared",
            )
            with use_tenant(tenant):
                await self.asgi(scope, receive, send)

    app.add_middleware(NameZoomTenant)
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
    login = httpx.post(
        f"http://127.0.0.1:{PORT}/api/v1/auth/login-password",
        json={"username": "zoomadmin", "password": "zoom-admin-password"},
        timeout=20,
    )
    if login.status_code != 200:
        raise SystemExit(f"Admin login failed ({login.status_code}).")
    auth = {"Authorization": f"Bearer {login.json()['access_token']}"}
    ready = seed(auth)
    (TEMP / "ready.json").write_text(json.dumps(ready), encoding="utf-8")
    print("ZOOM_READY", PROFILE, PORT, flush=True)
    watch = create_engine(URL)
    allocated = False
    while not server.should_exit:
        if not allocated and ready["allocate_product_id"]:
            with watch.connect() as conn:
                bound = conn.execute(
                    select(Device.device_public_key_thumbprint).where(Device.id == uuid.UUID(ready["device_id"]))
                ).scalar()
            if bound:
                grant = httpx.post(
                    f"http://127.0.0.1:{PORT}/api/v1/inventory/allocations",
                    headers=auth,
                    json={
                        "store_id": STORE,
                        "device_id": ready["device_id"],
                        "product_id": ready["allocate_product_id"],
                        "quantity": 40,
                    },
                    timeout=20,
                )
                if grant.status_code == 201:
                    allocated = True
                    print("ZOOM_ALLOCATED", PROFILE, flush=True)
                else:
                    print(f"ZOOM_ALLOCATE_{grant.status_code}", flush=True)
        time.sleep(1)
    watch.dispose()


if __name__ == "__main__":
    main()
