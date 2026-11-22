"""Disposable PostgreSQL RLS proof for O8.3, including a FastAPI process.

Opens only 127.0.0.1:55942 database axizpos_o83. The API logs in as ai_pos_app.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ["APP_ENV"] = "acceptance"
os.environ["DATABASE_URL"] = "postgresql+psycopg://o82boot@127.0.0.1:55942/axizpos_o83"
os.environ["CONTROL_DATABASE_URL"] = ""
os.environ["JWT_SECRET"] = "o83-jwt-secret-must-be-32-chars!!"
os.environ["PIN_SALT"] = "o83-pin-pepper-16"
os.environ["ENCRYPTION_SECRET"] = "o83-encryption-secret-32-chars!!"
os.environ["API_KEY"] = "o83-api-key-value"
os.environ["CORS_ORIGINS"] = "http://127.0.0.1:18083"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["DEFAULT_TENANT"] = ""
os.environ["O83_RLS_HARNESS"] = "1"

import httpx
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.security import create_access_token
from datetime import UTC, datetime

from app.models.business_settings import BusinessSettings
from app.models.device import Device
from app.models.product import Product
from app.models.role import Role, RolePermission
from app.models.store import Store
from app.models.sync_event import SyncEvent
from app.models.terminal_allocation import TerminalAllocation
from app.models.user import User
from app.tenancy.context import TenantRef, use_tenant

BOOT = "postgresql+psycopg://o82boot@127.0.0.1:55942/postgres"
OPS = os.environ["DATABASE_URL"]
APP = "postgresql+psycopg://ai_pos_app:o83-app-role-password@127.0.0.1:55942/axizpos_o83"
TENANT_A = uuid.UUID("11111111-1111-4111-8111-111111111a83")
TENANT_B = uuid.UUID("22222222-2222-4222-8222-222222222b83")
STORE_A = uuid.UUID("33333333-3333-4333-8333-333333333a83")
STORE_B = uuid.UUID("44444444-4444-4444-8444-444444444b83")
STORE_C = uuid.UUID("55555555-5555-4555-8555-555555555c83")
RESULTS: list[tuple[str, bool, str]] = []


def require_disposable(url: str) -> None:
    parsed = make_url(url)
    if parsed.host != "127.0.0.1" or parsed.port != 55942:
        raise SystemExit("Refusing: target is not the disposable O8.3 cluster.")
    if parsed.database not in {"postgres", "axizpos_o83"}:
        raise SystemExit("Refusing: database name is not disposable.")


def record(name: str, ok: bool, detail: str) -> None:
    RESULTS.append((name, ok, detail))
    print(("PASS" if ok else "FAIL"), name, detail)


def seed(owner) -> tuple[str, str]:
    factory = sessionmaker(bind=owner, expire_on_commit=False)
    tokens: list[str] = []
    settings = get_settings()
    for tenant, name, username in ((TENANT_A, "a", "manager-a"), (TENANT_B, "b", "manager-b")):
        ref = TenantRef(id=str(tenant), slug=name, name=name, database_url=OPS)
        with use_tenant(ref), factory() as db:
            role = Role(name=f"Manager {name}", description="", is_system=False)
            db.add(role)
            db.flush()
            for permission in ("portal:access", "users:read"):
                db.add(RolePermission(role_id=role.id, permission=permission, tenant_id=tenant))
            user = User(
                username=username,
                email=f"{username}@example.test",
                full_name=f"Manager {name}",
                hashed_password="not-used",
                is_active=True,
                store_id=None,
                role_id=role.id,
                has_pos_access=False,
                has_portal_access=True,
                token_version=0,
            )
            db.add(user)
            db.add(BusinessSettings(id=uuid.uuid4(), currency="USD"))
            db.flush()
            db.add(
                Product(
                    sku=f"sku-{name}",
                    barcode=f"bar-{name}",
                    name=f"Product {name}",
                    category="Grocery",
                    price_cents=100,
                    currency="USD",
                )
            )
            now = datetime.now(UTC)
            db.add(
                SyncEvent(
                    idempotency_key=f"sale-{name}",
                    device_id=f"till-{name}",
                    entity_type="sale",
                    payload_hash="hash",
                    occurred_at=now,
                    applied_at=now,
                )
            )
            db.commit()
            token, _ = create_access_token(
                subject=str(user.id),
                scope="portal",
                token_version=0,
                settings=settings,
                tenant_id=str(tenant),
            )
            tokens.append(token)
    with factory() as db, use_tenant(TenantRef(id=str(TENANT_A), slug="a", name="a", database_url=OPS)):
        for store, code, qty in ((STORE_A, "A", 40), (STORE_B, "B", 35)):
            db.add(Store(id=store, code=code, name=f"Store {code}", currency="USD"))
            db.flush()
            device_id = uuid.uuid4()
            db.add(
                Device(
                    id=device_id,
                    store_id=store,
                    code=code,
                    name=f"Till {code}",
                    key_hash=f"{code.lower()}-hash".ljust(64, "0"),
                    key_hint=code,
                )
            )
            db.add(
                TerminalAllocation(
                    store_id=store,
                    device_id=device_id,
                    device_thumbprint="aa",
                    product_id=uuid.uuid4(),
                    quantity_allocated=qty,
                    signing_key_id="o2-test",
                    manifest_payload="{}",
                    manifest_signature="sig",
                )
            )
        db.commit()
    return tokens[0], tokens[1]


def main() -> None:
    require_disposable(BOOT)
    require_disposable(OPS)
    admin = create_engine(BOOT, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS axizpos_o83"))
        conn.execute(text("CREATE DATABASE axizpos_o83"))
    admin.dispose()

    os.chdir(os.path.join(os.path.dirname(__file__), ".."))
    config = Config("alembic.ini")
    config.attributes["database_url"] = OPS
    command.upgrade(config, "head")

    owner = create_engine(OPS, isolation_level="AUTOCOMMIT")
    with owner.connect() as conn:
        if conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = 'ai_pos_app'")).scalar() is None:
            conn.exec_driver_sql(
                "CREATE ROLE ai_pos_app LOGIN PASSWORD 'o83-app-role-password' "
                "NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE"
            )
        conn.execute(text("GRANT CONNECT ON DATABASE axizpos_o83 TO ai_pos_app"))
        conn.execute(text("GRANT USAGE ON SCHEMA public TO ai_pos_app"))
        conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ai_pos_app"))
        conn.execute(text("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ai_pos_app"))
        role = conn.execute(
            text("SELECT rolsuper, rolbypassrls, rolcanlogin FROM pg_roles WHERE rolname = 'ai_pos_app'")
        ).one()
        record("role attributes", role.rolcanlogin and not role.rolsuper and not role.rolbypassrls, "LOGIN NOSUPERUSER NOBYPASSRLS")
    owner.dispose()

    token_a, token_b = seed(create_engine(OPS))
    env = os.environ.copy()
    env["DATABASE_URL"] = APP
    api = subprocess.Popen(
        [os.environ.get("O83_PYTHON", "python"), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "18083"],
        env=env,
        cwd=os.getcwd(),
    )
    try:
        identity = None
        for _ in range(40):
            try:
                response = httpx.get("http://127.0.0.1:18083/o83-harness-identity", timeout=2)
                if response.status_code == 200:
                    identity = response.json()
                    break
            except httpx.HTTPError:
                time.sleep(0.5)
        record("api identity", identity == {"role": "ai_pos_app", "database": "axizpos_o83", "port": "55942"}, str(identity))
        listed = httpx.get(
            "http://127.0.0.1:18083/api/v1/users",
            headers={"Authorization": f"Bearer {token_a}", "X-O83-Tenant": str(TENANT_A)},
            timeout=10,
        )
        names = [item["username"] for item in listed.json()] if listed.status_code == 200 else []
        record("api tenant A users", listed.status_code == 200 and names == ["manager-a"], f"{listed.status_code} {names}")
        foreign = httpx.get(
            "http://127.0.0.1:18083/api/v1/users",
            headers={"Authorization": f"Bearer {token_b}", "X-O83-Tenant": str(TENANT_A)},
            timeout=10,
        )
        record("api rejects a token from the other tenant", foreign.status_code == 401, str(foreign.status_code))
        products = httpx.get(
            "http://127.0.0.1:18083/api/v1/products",
            headers={"Authorization": f"Bearer {token_a}", "X-O83-Tenant": str(TENANT_A)},
            timeout=10,
        )
        product_names = [item["name"] for item in products.json()] if products.status_code == 200 else []
        record("api tenant A products", products.status_code == 200 and product_names == ["Product a"], f"{products.status_code} {product_names}")
    finally:
        api.terminate()
        api.wait(timeout=20)

    app = create_engine(APP)
    with app.connect() as conn:
        who = conn.execute(text("SELECT current_user")).scalar()
        record("direct login", who == "ai_pos_app", str(who))
        conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        conn.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(TENANT_A)})
        users = conn.execute(text("SELECT COUNT(*) FROM users")).scalar()
        products = conn.execute(text("SELECT COUNT(*) FROM products")).scalar()
        sync = conn.execute(text("SELECT COUNT(*) FROM sync_events")).scalar()
        record("bypass does not widen users", users == 1, f"count={users}")
        record("bypass does not widen products", products == 1, f"count={products}")
        record("bypass does not widen sync events", sync == 1, f"count={sync}")
        conn.execute(text("SELECT set_config('app.bypass_rls', 'off', true)"))
        conn.execute(text("SELECT set_config('app.store_id', '', true)"))
        conn.execute(text("SELECT set_config('app.device_id', '', true)"))
        hidden = conn.execute(text("SELECT COUNT(*) FROM terminal_allocations")).scalar()
        record("missing store hides allocations", hidden == 0, f"count={hidden}")
        conn.execute(text("SELECT set_config('app.store_id', :sid, true)"), {"sid": str(STORE_A)})
        one = conn.execute(text("SELECT COUNT(*) FROM terminal_allocations")).scalar()
        record("store A sees only its allocation", one == 1, f"count={one}")
        conn.execute(text("SELECT set_config('app.store_id', :sid, true)"), {"sid": str(STORE_C)})
        unknown = conn.execute(text("SELECT COUNT(*) FROM terminal_allocations")).scalar()
        record("unknown store sees no allocations", unknown == 0, f"count={unknown}")
        conn.execute(text("SELECT set_config('app.tenant_id', '', true)"))
        empty = conn.execute(text("SELECT COUNT(*) FROM users")).scalar()
        record("missing tenant hides users", empty == 0, f"count={empty}")
        conn.rollback()
    app.dispose()
    failed = [item for item in RESULTS if not item[1]]
    print(f"{len(RESULTS) - len(failed)} passed, {len(failed)} failed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
