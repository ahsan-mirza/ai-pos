"""Disposable Restaurant capability and RLS proof for O8.9.

Opens only 127.0.0.1:55971 database axizpos_o89. Refuses every other target.
The checked session logs in as ai_pos_app. SET ROLE is not used.
A business-wide owner turns on the restaurant preset. A store-bound admin cannot.
The cluster is stopped and its data directory removed after the results are printed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from pathlib import Path

os.environ["APP_ENV"] = "acceptance"
os.environ["DATABASE_URL"] = "postgresql+psycopg://o89boot:o89-boot-password@127.0.0.1:55971/axizpos_o89"
os.environ["CONTROL_DATABASE_URL"] = ""
os.environ["JWT_SECRET"] = "o89-jwt-secret-must-be-32-chars!!"
os.environ["PIN_SALT"] = "o89-pin-pepper-16"
os.environ["ENCRYPTION_SECRET"] = "o89-encryption-secret-32-chars!!"
os.environ["API_KEY"] = "o89-api-key-value"
os.environ["CORS_ORIGINS"] = "http://127.0.0.1:55971"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["TENANCY_ENABLED"] = "false"
os.environ["O89_RLS_HARNESS"] = "1"
os.environ["ALEMBIC_TENANT_ID"] = "00000000-0000-4000-8000-0000000000a1"

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

PORT = 55971
DB = "axizpos_o89"
DATA = Path(os.environ["TEMP"]) / "axiz-o89-pg"
PG_BIN = Path(r"C:\Program Files\PostgreSQL\18\bin")
BOOT = "postgresql+psycopg://o89boot:o89-boot-password@127.0.0.1:55971/postgres"
OPS = os.environ["DATABASE_URL"]
APP_PASSWORD = "o89-app-role-password"
TENANT_A = uuid.UUID("00000000-0000-4000-8000-0000000000a1")
TENANT_B = uuid.UUID("00000000-0000-4000-8000-000000000872")
DOWNTOWN = uuid.UUID("00000000-0000-4000-8000-000000000873")
MARINA = uuid.UUID("00000000-0000-4000-8000-000000000874")
HARBOR = uuid.UUID("00000000-0000-4000-8000-000000000875")
RESULTS: list[tuple[str, bool, str]] = []


def require_disposable(url: str) -> None:
    parsed = make_url(url)
    if parsed.host != "127.0.0.1" or parsed.port != PORT or parsed.username not in {"o89boot", "ai_pos_app"}:
        raise SystemExit("Refusing: target is not the disposable O8.7 cluster.")
    if parsed.database not in {"postgres", DB}:
        raise SystemExit("Refusing: database name is not disposable.")
    lowered = (parsed.database or "").lower()
    if any(word in lowered for word in ("prod", "laundry", "developer", "inventory", "o85")):
        raise SystemExit("Refusing: database name looks protected.")


def record(name: str, ok: bool, detail: str) -> None:
    RESULTS.append((name, ok, detail))
    print(("PASS" if ok else "FAIL"), name, detail)


def ensure_cluster() -> None:
    if DATA.exists() and not (DATA / "PG_VERSION").exists():
        raise SystemExit("Refusing: data directory exists and is not a Postgres cluster.")
    if not (DATA / "PG_VERSION").exists():
        DATA.mkdir(parents=True, exist_ok=True)
        password = DATA.parent / "o89-owner.pw"
        password.write_text("o89-boot-password", encoding="utf-8")
        subprocess.run(
            [
                str(PG_BIN / "initdb.exe"),
                "-D",
                str(DATA),
                "-U",
                "o89boot",
                "--pwfile",
                str(password),
                "--auth=scram-sha-256",
                "--encoding=UTF8",
                "--locale=C",
            ],
            check=True,
        )
        password.unlink(missing_ok=True)
    status = subprocess.run([str(PG_BIN / "pg_ctl.exe"), "-D", str(DATA), "status"], capture_output=True, text=True)
    if status.returncode != 0:
        subprocess.run(
            [
                str(PG_BIN / "pg_ctl.exe"),
                "-D",
                str(DATA),
                "-l",
                str(DATA.parent / "o89-postgres.log"),
                "-o",
                f"-p {PORT} -h 127.0.0.1",
                "start",
            ],
            check=True,
        )


def stop_cluster() -> None:
    subprocess.run([str(PG_BIN / "pg_ctl.exe"), "-D", str(DATA), "stop", "-m", "fast"], check=False)
    if DATA.is_dir() and DATA.name == "axiz-o89-pg":
        shutil.rmtree(DATA, ignore_errors=True)


def main() -> None:
    require_disposable(BOOT)
    require_disposable(OPS)
    ensure_cluster()
    try:
        _run()
    finally:
        failed = [item for item in RESULTS if not item[1]]
        print(f"{len(RESULTS) - len(failed)} passed, {len(failed)} failed")
        stop_cluster()
        print("CLUSTER_REMOVED", not DATA.exists())
        if failed:
            raise SystemExit(1)


def _run() -> None:
    admin = create_engine(BOOT, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = 'axizpos_o89'")).scalar()
        if exists is None:
            conn.execute(text("CREATE DATABASE axizpos_o89"))
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

    password_hash = hash_password("o89-review-password")
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    order_a = uuid.uuid4()
    order_b = uuid.uuid4()
    area_down = uuid.uuid4()
    area_marina = uuid.uuid4()
    area_harbor = uuid.uuid4()
    group_a = uuid.uuid4()
    group_b = uuid.uuid4()
    owner = create_engine(OPS, isolation_level="AUTOCOMMIT")
    with owner.connect() as conn:
        if conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = 'ai_pos_app'")).scalar() is None:
            conn.exec_driver_sql(
                "CREATE ROLE ai_pos_app LOGIN PASSWORD 'o89-app-role-password' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE"
            )
        conn.execute(text("GRANT CONNECT ON DATABASE axizpos_o89 TO ai_pos_app"))
        conn.execute(text("GRANT USAGE ON SCHEMA public TO ai_pos_app"))
        conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ai_pos_app"))
        conn.execute(text("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ai_pos_app"))
        role = conn.execute(text("SELECT rolsuper, rolbypassrls, rolcanlogin FROM pg_roles WHERE rolname = 'ai_pos_app'")).one()
        record("role attributes", role.rolcanlogin is True and role.rolsuper is False and role.rolbypassrls is False, "LOGIN NOSUPERUSER NOBYPASSRLS")
        conn.execute(
            text(
                """
                INSERT INTO stores (id, tenant_id, code, name, currency, is_warehouse, is_active, created_at, updated_at)
                VALUES
                    (:down, :ta, 'DOWN', 'Downtown Restaurant', 'USD', false, true, NOW(), NOW()),
                    (:marina, :ta, 'MAR', 'Marina Restaurant', 'USD', false, true, NOW(), NOW()),
                    (:harbor, :tb, 'HAR', 'Harbor Restaurant', 'USD', false, true, NOW(), NOW())
                """
            ),
            {"down": DOWNTOWN, "marina": MARINA, "harbor": HARBOR, "ta": TENANT_A, "tb": TENANT_B},
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
                       :store, r.id, true, true, false, 0, 0, NOW(), NOW()
                FROM roles r
                WHERE r.name = 'Super Admin'
                LIMIT 1
                """
            ),
            {"id": user_a, "tenant": TENANT_A, "username": "downtown.admin", "email": "downtown.admin@example.com", "name": "Downtown Admin", "password": password_hash, "store": DOWNTOWN},
        )
        owner_id = uuid.uuid4()
        conn.execute(
            text(
                """
                INSERT INTO users (
                    id, tenant_id, username, email, full_name, hashed_password, is_active,
                    store_id, role_id, has_pos_access, has_portal_access, can_sell_open_price,
                    failed_login_attempts, token_version, created_at, updated_at
                )
                SELECT :id, :tenant, 'restaurant.owner', 'restaurant.owner@example.com', 'Restaurant Owner', :password, true,
                       NULL, r.id, true, true, false, 0, 0, NOW(), NOW()
                FROM roles r
                WHERE r.name = 'Super Admin'
                LIMIT 1
                """
            ),
            {"id": owner_id, "tenant": TENANT_A, "password": password_hash},
        )
        role_b = uuid.uuid4()
        conn.execute(
            text(
                """
                INSERT INTO roles (id, tenant_id, name, description, is_system, created_at, updated_at)
                VALUES (:id, :tenant, 'Super Admin', 'O87 tenant B', true, NOW(), NOW())
                """
            ),
            {"id": role_b, "tenant": TENANT_B},
        )
        conn.execute(
            text(
                """
                INSERT INTO users (
                    id, tenant_id, username, email, full_name, hashed_password, is_active,
                    store_id, role_id, has_pos_access, has_portal_access, can_sell_open_price,
                    failed_login_attempts, token_version, created_at, updated_at
                ) VALUES (
                    :id, :tenant, 'harbor.admin', 'harbor.admin@example.com', 'Harbor Admin', :password, true,
                    :store, :role, true, true, false, 0, 0, NOW(), NOW()
                )
                """
            ),
            {"id": user_b, "tenant": TENANT_B, "password": password_hash, "store": HARBOR, "role": role_b},
        )
        for area, store, tenant, name in (
            (area_down, DOWNTOWN, TENANT_A, "Downtown Room"),
            (area_marina, MARINA, TENANT_A, "Marina Room"),
            (area_harbor, HARBOR, TENANT_B, "Harbor Room"),
        ):
            conn.execute(
                text(
                    """
                    INSERT INTO dining_areas (id, tenant_id, store_id, name, position, is_active, created_at, updated_at)
                    VALUES (:id, :tenant, :store, :name, 0, true, NOW(), NOW())
                    """
                ),
                {"id": area, "tenant": tenant, "store": store, "name": name},
            )
        for group, tenant, name in ((group_a, TENANT_A, "O87 Milk"), (group_b, TENANT_B, "O87 Secret Milk")):
            conn.execute(
                text(
                    """
                    INSERT INTO modifier_groups (id, tenant_id, name, min_select, max_select, position, is_active, is_sample, created_at, updated_at)
                    VALUES (:id, :tenant, :name, 0, 1, 0, true, false, NOW(), NOW())
                    """
                ),
                {"id": group, "tenant": tenant, "name": name},
            )
        for order, store, tenant, user, number in (
            (order_a, DOWNTOWN, TENANT_A, user_a, 1),
            (order_b, HARBOR, TENANT_B, user_b, 1),
        ):
            conn.execute(
                text(
                    """
                    INSERT INTO open_orders (
                        id, tenant_id, store_id, number, service_type, status, covers, opened_by_id,
                        revision, cod_expected_cents, cod_collected_cents, cod_handed_cents, opened_at, updated_at
                    ) VALUES (
                        :id, :tenant, :store, :number, 'DINE_IN', 'OPEN', 2, :user,
                        1, 0, 0, 0, NOW(), NOW()
                    )
                    """
                ),
                {"id": order, "tenant": tenant, "store": store, "number": number, "user": user},
            )
    owner.dispose()

    app_url = OPS.replace("o89boot:o89-boot-password@", "ai_pos_app:" + APP_PASSWORD + "@")
    require_disposable(app_url)
    app_engine = create_engine(app_url)
    with app_engine.connect() as conn:
        who = conn.execute(text("SELECT current_user, session_user")).one()
        record("login", who.current_user == "ai_pos_app" and who.session_user == "ai_pos_app", who.current_user)
        conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        conn.execute(text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(TENANT_A)})
        menus = conn.execute(text("SELECT name FROM modifier_groups ORDER BY name")).scalars().all()
        record("tenant A menu hides tenant B", menus == ["O87 Milk"], ",".join(menus))
        orders = conn.execute(text("SELECT COUNT(*) FROM open_orders")).scalar()
        record("tenant A orders hide tenant B", orders == 1, f"count={orders}")
        floors = set(conn.execute(text("SELECT name FROM dining_areas")).scalars().all())
        record("tenant A floor hides tenant B", floors == {"Downtown Room", "Marina Room"}, ",".join(sorted(floors)))
        inserted = False
        try:
            conn.execute(
                text(
                    """
                    INSERT INTO open_orders (
                        id, tenant_id, store_id, number, service_type, status, covers, opened_by_id,
                        revision, cod_expected_cents, cod_collected_cents, cod_handed_cents, opened_at, updated_at
                    ) VALUES (
                        :id, :tenant, :store, 9, 'DINE_IN', 'OPEN', 1, :user,
                        1, 0, 0, 0, NOW(), NOW()
                    )
                    """
                ),
                {"id": uuid.uuid4(), "tenant": TENANT_B, "store": HARBOR, "user": user_b},
            )
            inserted = True
        except Exception as exc:
            conn.rollback()
            message = str(getattr(exc, "orig", exc)).splitlines()[0][:180]
            record(
                "tenant A cannot insert tenant B order",
                "row-level security" in message.lower() or "policy" in message.lower(),
                message,
            )
        if inserted:
            record("tenant A cannot insert tenant B order", False, "insert succeeded")
        conn.execute(text("SELECT set_config('app.tenant_id', '', true)"))
        hidden = conn.execute(text("SELECT COUNT(*) FROM open_orders")).scalar()
        record("missing tenant hides orders", hidden == 0, f"count={hidden}")
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

    with TestClient(app) as client:
        own = client.post(
            "/api/v1/auth/login-password",
            headers={"x-o83-tenant": str(TENANT_A)},
            json={"username": "downtown.admin", "password": "o89-review-password"},
        )
        record("fastapi tenant A login", own.status_code == 200, f"status={own.status_code}")
        other = client.post(
            "/api/v1/auth/login-password",
            headers={"x-o83-tenant": str(TENANT_B)},
            json={"username": "downtown.admin", "password": "o89-review-password"},
        )
        record("fastapi tenant B rejects tenant A user", other.status_code != 200, f"status={other.status_code}")
        if own.status_code == 200:
            token = own.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}", "x-o83-tenant": str(TENANT_A)}
            closed = client.get("/api/v1/orders", headers=headers, params={"store_id": str(DOWNTOWN)})
            code = closed.json().get("error", {}).get("code") if closed.headers.get("content-type", "").startswith("application/json") else ""
            record(
                "orders stay closed until the module is on",
                closed.status_code == 403 and code == "capability_disabled",
                f"status={closed.status_code} code={code}",
            )
            switched = client.put(
                "/api/v1/settings/profile",
                headers=headers,
                json={"business_profile": "restaurant", "capabilities": ["open_orders", "tables"]},
            )
            switched_code = switched.json().get("error", {}).get("code") if switched.status_code != 200 else "ok"
            record(
                "store-bound admin cannot change the business type",
                switched.status_code == 403 and switched_code == "forbidden",
                f"status={switched.status_code} code={switched_code}",
            )
            marina = client.get("/api/v1/orders", headers=headers, params={"store_id": str(MARINA)})
            marina_code = marina.json().get("error", {}).get("code") if marina.headers.get("content-type", "").startswith("application/json") else ""
            record(
                "downtown user cannot list another branch while orders are off",
                marina.status_code == 403 and marina_code == "capability_disabled",
                f"status={marina.status_code} code={marina_code}",
            )
            anonymous = client.get(
                "/api/v1/orders",
                headers={"x-o83-tenant": str(TENANT_A)},
                params={"store_id": str(DOWNTOWN)},
            )
            anonymous_code = (
                anonymous.json().get("error", {}).get("code")
                if anonymous.headers.get("content-type", "").startswith("application/json")
                else ""
            )
            record(
                "unauthenticated order list stays closed while the module is off",
                anonymous.status_code == 403 and anonymous_code == "capability_disabled",
                f"status={anonymous.status_code} code={anonymous_code}",
            )
            owner_login = client.post(
                "/api/v1/auth/login-password",
                headers={"x-o83-tenant": str(TENANT_A)},
                json={"username": "restaurant.owner", "password": "o89-review-password"},
            )
            record("business-wide owner login", owner_login.status_code == 200, f"status={owner_login.status_code}")
            if owner_login.status_code == 200:
                owner_headers = {
                    "Authorization": f"Bearer {owner_login.json()['access_token']}",
                    "x-o83-tenant": str(TENANT_A),
                }
                from app.core.capabilities import PROFILES

                opened = client.put(
                    "/api/v1/settings/profile",
                    headers=owner_headers,
                    json={
                        "business_profile": "restaurant",
                        "capabilities": [item.value for item in PROFILES["restaurant"]],
                    },
                )
                opened_code = opened.json().get("error", {}).get("code") if opened.status_code != 200 else "ok"
                profile_name = opened.json().get("business_profile") if opened.status_code == 200 else ""
                enabled = opened.json().get("capabilities") if opened.status_code == 200 else []
                record(
                    "business-wide owner enables the restaurant preset",
                    opened.status_code == 200 and profile_name == "restaurant" and "open_orders" in enabled,
                    f"status={opened.status_code} code={opened_code} profile={profile_name}",
                )
                signed_out = client.get(
                    "/api/v1/orders",
                    headers={"x-o83-tenant": str(TENANT_A)},
                    params={"store_id": str(DOWNTOWN)},
                )
                record(
                    "unauthenticated order list is refused after the module is on",
                    signed_out.status_code == 401,
                    f"status={signed_out.status_code}",
                )
                listed = client.get("/api/v1/orders", headers=owner_headers, params={"store_id": str(DOWNTOWN)})
                ids = [row.get("id") for row in listed.json()] if listed.status_code == 200 else []
                record(
                    "authorized owner lists the downtown order",
                    listed.status_code == 200 and str(order_a) in ids and str(order_b) not in ids,
                    f"status={listed.status_code} count={len(ids)}",
                )
                scoped = client.get("/api/v1/orders", headers=headers, params={"store_id": str(DOWNTOWN)})
                scoped_ids = [row.get("id") for row in scoped.json()] if scoped.status_code == 200 else []
                record(
                    "store-bound admin lists only the downtown order",
                    scoped.status_code == 200 and str(order_a) in scoped_ids and str(order_b) not in scoped_ids,
                    f"status={scoped.status_code} count={len(scoped_ids)}",
                )
                cross = client.get("/api/v1/orders", headers=headers, params={"store_id": str(MARINA)})
                cross_code = cross.json().get("error", {}).get("code") if cross.headers.get("content-type", "").startswith("application/json") else ""
                record(
                    "store-bound admin cannot list marina after the module is on",
                    cross.status_code == 403 and cross_code == "store_scope",
                    f"status={cross.status_code} code={cross_code}",
                )
                unknown = client.get(
                    "/api/v1/orders",
                    headers=headers,
                    params={"store_id": "00000000-0000-4000-8000-000000000099"},
                )
                unknown_code = unknown.json().get("error", {}).get("code") if unknown.headers.get("content-type", "").startswith("application/json") else ""
                record(
                    "store-bound admin cannot list an unknown store",
                    unknown.status_code == 403 and unknown_code == "store_scope",
                    f"status={unknown.status_code} code={unknown_code}",
                )


if __name__ == "__main__":
    main()
