"""Disposable grocery register backend for the offline acceptance window.

Opens only 127.0.0.1:55944 database axizpos_o84act. Writes the test signing
seed and the one-time activation key to the temp directory, not to this repo.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PORT = 55944
DB = "axizpos_o84act"
os.environ["APP_ENV"] = "acceptance"
os.environ["DATABASE_URL"] = f"postgresql+psycopg://o82boot@127.0.0.1:{PORT}/{DB}"
os.environ["CONTROL_DATABASE_URL"] = ""
os.environ["JWT_SECRET"] = "o84-act-jwt-secret-32-characters!!"
os.environ["PIN_SALT"] = "o84-act-pin-pepper"
os.environ["ENCRYPTION_SECRET"] = "o84-act-encryption-secret-32chars!"
os.environ["API_KEY"] = "o84-act-api-key!!"
os.environ["CORS_ORIGINS"] = "http://127.0.0.1:18084"
os.environ["PUBLIC_BASE_URL"] = "http://127.0.0.1:18084"
os.environ["TENANT_PUBLIC_URL_TEMPLATE"] = "http://127.0.0.1:18084"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["DEFAULT_TENANT"] = ""

from alembic import command
from alembic.config import Config
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.deps import Principal
from app.core.security import hash_pin
from app.models.business_settings import BusinessSettings
from app.models.device import Device
from app.models.inventory import InventoryLevel
from app.models.product import Product
from app.models.role import Role, RolePermission
from app.models.store import Store
from app.models.user import User
from app.services.device_service import issue_activation_key

BOOT = f"postgresql+psycopg://o82boot@127.0.0.1:{PORT}/postgres"
OPS = os.environ["DATABASE_URL"]
APP = f"postgresql+psycopg://ai_pos_app:o84-act-app-password@127.0.0.1:{PORT}/{DB}"
TEMP = Path(os.environ["TEMP"])


def require(url: str) -> None:
    parsed = make_url(url)
    if parsed.host != "127.0.0.1" or parsed.port != PORT or parsed.database not in {"postgres", DB}:
        raise SystemExit("Refusing: this is not the disposable activation database.")


def main() -> None:
    require(BOOT)
    require(OPS)
    seed = os.urandom(32)
    private = Ed25519PrivateKey.from_private_bytes(seed)
    public = private.public_key().public_bytes_raw()
    os.environ["ENTITLEMENT_SIGNING_SEED"] = base64.b64encode(seed).decode("ascii")
    os.environ["ENTITLEMENT_SIGNING_KEY_ID"] = "o84-accept-1"
    get_settings.cache_clear()

    admin = create_engine(BOOT, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {DB}"))
        conn.execute(text(f"CREATE DATABASE {DB}"))
    admin.dispose()

    os.chdir(os.path.join(os.path.dirname(__file__), ".."))
    config = Config("alembic.ini")
    config.attributes["database_url"] = OPS
    command.upgrade(config, "head")

    owner = create_engine(OPS, isolation_level="AUTOCOMMIT")
    with owner.connect() as conn:
        if conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = 'ai_pos_app'")).scalar() is None:
            conn.exec_driver_sql(
                "CREATE ROLE ai_pos_app LOGIN PASSWORD 'o84-act-app-password' "
                "NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE"
            )
        conn.execute(text(f"GRANT CONNECT ON DATABASE {DB} TO ai_pos_app"))
        conn.execute(text("GRANT USAGE ON SCHEMA public TO ai_pos_app"))
        conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ai_pos_app"))
        conn.execute(text("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ai_pos_app"))
        role = conn.execute(
            text("SELECT rolsuper, rolbypassrls, rolcanlogin FROM pg_roles WHERE rolname = 'ai_pos_app'")
        ).one()
        if role.rolsuper or role.rolbypassrls or not role.rolcanlogin:
            raise SystemExit("Application role is not constrained.")
    owner.dispose()

    settings = get_settings()
    factory = sessionmaker(bind=create_engine(OPS), expire_on_commit=False)
    with factory() as db:
        role_row = Role(name="Acceptance manager", description="Disposable acceptance role", is_system=False)
        db.add(role_row)
        db.flush()
        for permission in ("portal:access", "users:read", "inventory:adjust_stock", "pos:sell"):
            db.add(RolePermission(role_id=role_row.id, permission=permission))
        manager = User(
            username="manager",
            email="manager@o84.test",
            full_name="Acceptance Manager",
            hashed_password="not-used",
            is_active=True,
            role_id=role_row.id,
            has_pos_access=False,
            has_portal_access=True,
            token_version=0,
        )
        cashier = User(
            username="cashier",
            email="cashier@o84.test",
            full_name="Acceptance Cashier",
            hashed_password="not-used",
            hashed_pin=hash_pin("2468", settings),
            is_active=True,
            role_id=role_row.id,
            has_pos_access=True,
            has_portal_access=False,
            token_version=0,
        )
        db.add(manager)
        db.add(cashier)
        db.add(BusinessSettings(id=uuid.uuid4(), currency="USD", business_profile="grocery", country="US"))
        store = Store(code="MAIN", name="O84 Grocery", currency="USD")
        db.add(store)
        db.flush()
        manager.store_id = None
        cashier.store_id = store.id
        till_a = Device(
            store_id=store.id,
            code="TILLA",
            name="Acceptance till A",
            key_hash=hashlib.sha256(b"o84-till-a-placeholder").hexdigest(),
            key_hint="placeA",
        )
        till_b = Device(
            store_id=store.id,
            code="TILLB",
            name="Acceptance till B",
            key_hash=hashlib.sha256(b"o84-till-b-placeholder").hexdigest(),
            key_hint="placeB",
            device_public_key_thumbprint=hashlib.sha256(b"o84-till-b-device-key").hexdigest(),
        )
        db.add(till_a)
        db.add(till_b)
        product = Product(
            sku="O84-APPLE",
            barcode="000000008401",
            name="O84 Test Apple",
            category="Grocery",
            price_cents=250,
            currency="USD",
            is_stock_tracked=True,
        )
        db.add(product)
        db.flush()
        db.add(InventoryLevel(product_id=product.id, store_id=store.id, quantity_on_hand=100, quantity_reserved=0))
        db.commit()
        principal = Principal(kind="user", scope="portal", user=manager, permissions=frozenset({"portal:access"}))
        issued = issue_activation_key(db, principal, till_a.id)
        db.commit()

    (TEMP / "o84-accept-public.txt").write_text(
        "o84-accept-1\n" + base64.b64encode(public).decode("ascii") + "\n",
        encoding="ascii",
    )
    (TEMP / "o84-accept-seed.txt").write_text(base64.b64encode(seed).decode("ascii"), encoding="ascii")
    (TEMP / "o84-activation.txt").write_text(
        json.dumps({"store_code": "o84grocery", "activation_key": issued.activation_key, "cashier": "cashier"}),
        encoding="ascii",
    )
    (TEMP / "o84-backend-identity.json").write_text(
        json.dumps(
            {
                "database": DB,
                "host": "127.0.0.1",
                "port": PORT,
                "role": "ai_pos_app",
                "role_attributes": "LOGIN NOSUPERUSER NOBYPASSRLS",
                "api": "http://127.0.0.1:18084",
                "profile": "grocery",
                "store_code": "MAIN",
                "key_id": "o84-accept-1",
            }
        ),
        encoding="ascii",
    )
    print("seeded", DB, "role constrained", "key_id o84-accept-1")


if __name__ == "__main__":
    main()
