"""Disposable PostgreSQL RLS proof for O8.4.

Opens only 127.0.0.1:55952 database axizpos_o84. Refuses every other target.
The checked session logs in as ai_pos_app. SET ROLE is not used.
"""

from __future__ import annotations

import os
import uuid

os.environ["APP_ENV"] = "acceptance"
os.environ["DATABASE_URL"] = "postgresql+psycopg://o84boot@127.0.0.1:55952/axizpos_o84"
os.environ["CONTROL_DATABASE_URL"] = ""
os.environ["JWT_SECRET"] = "o84-jwt-secret-must-be-32-chars!!"
os.environ["PIN_SALT"] = "o84-pin-pepper-16"
os.environ["ENCRYPTION_SECRET"] = "o84-encryption-secret-32-chars!!"
os.environ["API_KEY"] = "o84-api-key-value"
os.environ["CORS_ORIGINS"] = "http://127.0.0.1:55952"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["TENANCY_ENABLED"] = "false"
os.environ["ALEMBIC_TENANT_ID"] = "00000000-0000-4000-8000-0000000000a1"

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BOOT = "postgresql+psycopg://o84boot@127.0.0.1:55952/postgres"
OPS = os.environ["DATABASE_URL"]
APP_PASSWORD = "o84-app-role-password"
TENANT = uuid.UUID("00000000-0000-4000-8000-0000000000a1")
OTHER = uuid.UUID("22222222-2222-4222-8222-22222222a844")
STORE_A = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaa844")
STORE_B = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbb844")
RESULTS: list[tuple[str, bool, str]] = []


def require_disposable(url: str) -> None:
    parsed = make_url(url)
    if parsed.host != "127.0.0.1" or parsed.port != 55952 or parsed.username not in {"o84boot", "ai_pos_app"}:
        raise SystemExit("Refusing: target is not the disposable O8.4 cluster.")
    if parsed.database not in {"postgres", "axizpos_o84"}:
        raise SystemExit("Refusing: database name is not disposable.")
    lowered = (parsed.database or "").lower()
    if any(word in lowered for word in ("prod", "laundry", "developer", "inventory")):
        raise SystemExit("Refusing: database name looks protected.")


def record(name: str, ok: bool, detail: str) -> None:
    RESULTS.append((name, ok, detail))
    print(("PASS" if ok else "FAIL"), name, detail)


def main() -> None:
    require_disposable(BOOT)
    require_disposable(OPS)
    admin = create_engine(BOOT, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = 'axizpos_o84'")).scalar()
        if exists is None:
            conn.execute(text("CREATE DATABASE axizpos_o84"))
    admin.dispose()

    os.chdir(os.path.join(os.path.dirname(__file__), ".."))
    config = Config("alembic.ini")
    config.attributes["database_url"] = OPS
    command.upgrade(config, "head")

    from sqlalchemy.orm import sessionmaker

    from app.core.security import hash_password
    from app.services.rbac_service import ensure_system_roles

    seed = sessionmaker(bind=create_engine(OPS))()
    ensure_system_roles(seed)
    seed.commit()
    seed.close()

    password_hash = hash_password("o84-review-password")
    owner = create_engine(OPS, isolation_level="AUTOCOMMIT")
    with owner.connect() as conn:
        if conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = 'ai_pos_app'")).scalar() is None:
            conn.exec_driver_sql(
                "CREATE ROLE ai_pos_app LOGIN PASSWORD 'o84-app-role-password' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE"
            )
        conn.execute(text("GRANT CONNECT ON DATABASE axizpos_o84 TO ai_pos_app"))
        conn.execute(text("GRANT USAGE ON SCHEMA public TO ai_pos_app"))
        conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ai_pos_app"))
        conn.execute(text("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ai_pos_app"))
        role = conn.execute(
            text("SELECT rolsuper, rolbypassrls, rolcanlogin FROM pg_roles WHERE rolname = 'ai_pos_app'")
        ).one()
        record(
            "role attributes",
            role.rolcanlogin is True and role.rolsuper is False and role.rolbypassrls is False,
            "LOGIN NOSUPERUSER NOBYPASSRLS",
        )
        head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        record("migration head", head == "20261122_0131", str(head))
        conn.execute(
            text(
                """
                INSERT INTO stores (id, tenant_id, code, name, currency, created_at, updated_at)
                VALUES (:a, :t, 'OA', 'Store A', 'USD', NOW(), NOW()),
                       (:b, :t, 'OB', 'Store B', 'USD', NOW(), NOW())
                """
            ),
            {"a": STORE_A, "b": STORE_B, "t": TENANT},
        )
        conn.execute(
            text(
                """
                INSERT INTO sync_events (
                    id, tenant_id, idempotency_key, device_id, entity_type, payload_hash, occurred_at, applied_at
                ) VALUES
                    (:ida, :ta, 'sale-a', 'till-a', 'sale', 'hash-a', NOW(), NOW()),
                    (:idb, :tb, 'sale-b', 'till-b', 'sale', 'hash-b', NOW(), NOW())
                """
            ),
            {"ida": uuid.uuid4(), "idb": uuid.uuid4(), "ta": TENANT, "tb": OTHER},
        )
        conn.execute(
            text(
                """
                INSERT INTO users (
                    id, tenant_id, username, email, full_name, hashed_password, is_active,
                    store_id, role_id, has_pos_access, has_portal_access, can_sell_open_price,
                    failed_login_attempts, token_version, created_at, updated_at
                )
                SELECT :id, :tenant, :username, :email, :name, :password, true,
                       :store, r.id, false, true, false, 0, 0, NOW(), NOW()
                FROM roles r
                WHERE r.name = 'Super Admin'
                LIMIT 1
                """
            ),
            {
                "id": uuid.uuid4(),
                "tenant": TENANT,
                "username": "store.a",
                "email": "store.a@example.com",
                "name": "Store A",
                "password": password_hash,
                "store": STORE_A,
            },
        )
        inserted_user = conn.execute(text("SELECT COUNT(*) FROM users WHERE username = 'store.a'")).scalar()
        record("seeded store user", inserted_user == 1, f"count={inserted_user}")
        conn.execute(
            text(
                """
                INSERT INTO terminal_allocations (
                    id, tenant_id, manifest_id, version, store_id, device_id, device_thumbprint, product_id,
                    unit, quantity_allocated, quantity_consumed, last_sequence, status, policy_version,
                    signing_key_id, manifest_payload, manifest_signature, issued_at, created_at, updated_at
                ) VALUES
                    (:id1, :ta, :m1, 1, :store_a, :dev, 'aa', :product, 'each', 40, 0, 0, 'ACTIVE', 1,
                     'o2-test', '{}', 'sig', NOW(), NOW(), NOW()),
                    (:id2, :ta, :m2, 1, :store_b, :dev, 'bb', :product, 'each', 35, 0, 0, 'ACTIVE', 1,
                     'o2-test', '{}', 'sig', NOW(), NOW(), NOW())
                """
            ),
            {
                "id1": uuid.uuid4(),
                "id2": uuid.uuid4(),
                "m1": uuid.uuid4(),
                "m2": uuid.uuid4(),
                "ta": TENANT,
                "store_a": STORE_A,
                "store_b": STORE_B,
                "dev": uuid.uuid4(),
                "product": uuid.uuid4(),
            },
        )
    owner.dispose()

    app_url = OPS.replace("o84boot@", "ai_pos_app:" + APP_PASSWORD + "@")
    require_disposable(app_url)
    app_engine = create_engine(app_url)
    with app_engine.connect() as conn:
        who = conn.execute(text("SELECT current_user, session_user")).one()
        record("login", who.current_user == "ai_pos_app" and who.session_user == "ai_pos_app", who.current_user)
        conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        conn.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(TENANT)})
        conn.execute(text("SELECT set_config('app.store_id', '', true)"))
        users = conn.execute(text("SELECT COUNT(*) FROM users")).scalar()
        record("bypass does not widen users", users == 1, f"count={users}")
        events = conn.execute(text("SELECT COUNT(*) FROM sync_events")).scalar()
        record("bypass does not widen sync events", events == 1, f"count={events}")
        products = conn.execute(text("SELECT COUNT(*) FROM products")).scalar()
        record("bypass does not widen products", products == 0, f"count={products}")
        missing_store = conn.execute(text("SELECT COUNT(*) FROM terminal_allocations")).scalar()
        record("missing store hides allocations", missing_store == 0, f"count={missing_store}")
        conn.execute(text("SELECT set_config('app.store_id', :sid, true)"), {"sid": str(STORE_A)})
        own_store = conn.execute(text("SELECT COUNT(*) FROM terminal_allocations")).scalar()
        record("store A sees only its allocation", own_store == 1, f"count={own_store}")
        conn.execute(text("SELECT set_config('app.store_id', :sid, true)"), {"sid": str(uuid.uuid4())})
        unknown = conn.execute(text("SELECT COUNT(*) FROM terminal_allocations")).scalar()
        record("unknown store sees no allocations", unknown == 0, f"count={unknown}")
        conn.execute(text("SELECT set_config('app.tenant_id', '', true)"))
        conn.execute(text("SELECT set_config('app.store_id', '', true)"))
        empty = conn.execute(text("SELECT COUNT(*) FROM sync_events")).scalar()
        record("missing tenant hides sync events", empty == 0, f"count={empty}")
        conn.commit()
    app_engine.dispose()

    os.environ["DATABASE_URL"] = app_url
    from app.core.config import get_settings
    from app.core import database

    get_settings.cache_clear()
    database._engine = None
    database._session_factory = None
    from fastapi.testclient import TestClient

    from app.main import app

    try:
        with TestClient(app) as client:
            login = client.post(
                "/api/v1/auth/login-password",
                json={"username": "store.a", "password": "o84-review-password"},
            )
            record("fastapi login", login.status_code == 200, f"status={login.status_code}")
            if login.status_code == 200:
                token = login.json()["access_token"]
                listed = client.get(
                    "/api/v1/inventory/allocations",
                    headers={"Authorization": f"Bearer {token}"},
                )
                body = listed.json() if listed.status_code == 200 else []
                stores = {item.get("store_id") for item in body} if isinstance(body, list) else set()
                record(
                    "fastapi allocations stay on store A",
                    listed.status_code == 200 and stores == {str(STORE_A)},
                    f"status={listed.status_code} stores={stores}",
                )
                users_response = client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
                raw = users_response.text
                record(
                    "fastapi user list omits a verifier",
                    users_response.status_code == 200 and "hashed_pin" not in raw and "pin_verifier" not in raw,
                    f"status={users_response.status_code}",
                )
    except Exception as exc:
        record("fastapi request", False, type(exc).__name__)

    failed = [item for item in RESULTS if not item[1]]
    print(f"{len(RESULTS) - len(failed)} passed, {len(failed)} failed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
