"""Disposable Laundry acceptance database. Refuses every other Postgres port."""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

PORT = 55821
HOST = "127.0.0.1"
OPS = "axizpos_laundry_acceptance"
CONTROL = "axizpos_laundry_acceptance_control"
FROM_PREVIOUS = "axizpos_laundry_from_0120"
PREVIOUS = "20261119_0120"
HEAD = "20261121_0121"
OWNER = "axizpos_laundry"
TENANT_B = uuid.UUID("22222222-2222-4222-8222-2222222222b2")
ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT / ".env.laundry-acceptance"
DATA = Path(__file__).resolve().parent / "pgdata"
PG_BIN = Path(r"C:\Program Files\PostgreSQL\18\bin")
EVIDENCE = Path(__file__).resolve().parent / "evidence"


def _refuse(url: str) -> None:
    parsed = make_url(url)
    if parsed.host != HOST or parsed.port != PORT or parsed.username != OWNER:
        raise SystemExit("Refusing: this script only opens the disposable laundry acceptance cluster.")
    if parsed.database in {"ai_pos", "postgres", "axizpos_inventory_acceptance", "axizpos_inventory_acceptance_control"}:
        raise SystemExit("Refusing: database name is not a laundry acceptance database.")


def _read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    if not ENV_PATH.exists():
        return values
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def _write_env(owner_password: str, app_password: str, admin_password: str) -> None:
    owner = f"postgresql+psycopg://{OWNER}:{owner_password}@{HOST}:{PORT}"
    app = f"postgresql+psycopg://ai_pos_app:{app_password}@{HOST}:{PORT}/{OPS}"
    lines = [
        f"DATABASE_URL={app}",
        f"CONTROL_DATABASE_URL={owner}/{CONTROL}",
        f"LAUNDRY_OWNER_URL={owner}/{OPS}",
        "DEFAULT_TENANT=laundry-a",
        "API_HOST=127.0.0.1",
        "API_PORT=18082",
        "CORS_ORIGINS=http://127.0.0.1:5174,http://localhost:5174",
        "PUBLIC_BASE_URL=http://127.0.0.1:18082",
        f"JWT_SECRET={secrets.token_hex(32)}",
        f"PIN_SALT={secrets.token_hex(16)}",
        f"ENCRYPTION_SECRET={secrets.token_hex(32)}",
        f"API_KEY={secrets.token_hex(16)}",
        f"ADMIN_PASSWORD={admin_password}",
        "ADMIN_PIN=2468",
        "SCHEDULER_ENABLED=false",
        "ALLOW_SHARED_API_KEY=true",
    ]
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _ensure_cluster(owner_password: str) -> None:
    if not (DATA / "PG_VERSION").exists():
        DATA.mkdir(parents=True, exist_ok=True)
        password_file = Path(__file__).resolve().parent / "owner.pw"
        password_file.write_text(owner_password, encoding="utf-8")
        subprocess.run(
            [
                str(PG_BIN / "initdb.exe"),
                "-D",
                str(DATA),
                "-U",
                OWNER,
                "--pwfile",
                str(password_file),
                "--auth=scram-sha-256",
                "--encoding=UTF8",
                "--locale=C",
            ],
            check=True,
        )
        password_file.unlink(missing_ok=True)
    running = subprocess.run(
        [str(PG_BIN / "pg_ctl.exe"), "-D", str(DATA), "status"],
        capture_output=True,
        text=True,
    )
    if running.returncode != 0:
        subprocess.run(
            [
                str(PG_BIN / "pg_ctl.exe"),
                "-D",
                str(DATA),
                "-l",
                str(Path(__file__).resolve().parent / "postgres.log"),
                "-o",
                f"-p {PORT} -h {HOST}",
                "start",
            ],
            check=True,
        )


def _upgrade(url: str, revision: str) -> None:
    from alembic import command
    from alembic.config import Config

    _refuse(url)
    config = Config("alembic.ini")
    config.attributes["database_url"] = url
    command.upgrade(config, revision)


def _downgrade(url: str, revision: str) -> None:
    from alembic import command
    from alembic.config import Config

    _refuse(url)
    config = Config("alembic.ini")
    config.attributes["database_url"] = url
    command.downgrade(config, revision)


def _maintenance(owner_url: str):
    _refuse(owner_url)
    return create_engine(make_url(owner_url).set(database="postgres"), isolation_level="AUTOCOMMIT")


def main() -> None:
    os.chdir(ROOT / "apps" / "api")
    sys.path.insert(0, str(ROOT / "apps" / "api"))
    existing = _read_env()
    owner_password = existing.get("LAUNDRY_OWNER_PASSWORD") or secrets.token_hex(16)
    app_password = existing.get("LAUNDRY_APP_PASSWORD") or secrets.token_hex(16)
    admin_password = existing.get("ADMIN_PASSWORD") or secrets.token_hex(12)
    if not ENV_PATH.exists():
        text_lines = _read_env()
        text_lines["LAUNDRY_OWNER_PASSWORD"] = owner_password
        text_lines["LAUNDRY_APP_PASSWORD"] = app_password
    _ensure_cluster(owner_password)
    owner_base = f"postgresql+psycopg://{OWNER}:{owner_password}@{HOST}:{PORT}"
    if not ENV_PATH.exists():
        _write_env(owner_password, app_password, admin_password)
        extra = ENV_PATH.read_text(encoding="utf-8")
        ENV_PATH.write_text(
            extra + f"LAUNDRY_OWNER_PASSWORD={owner_password}\nLAUNDRY_APP_PASSWORD={app_password}\n",
            encoding="utf-8",
        )
    owner_ops = f"{owner_base}/{OPS}"
    os.environ["DATABASE_URL"] = f"postgresql+psycopg://ai_pos_app:{app_password}@{HOST}:{PORT}/{OPS}"
    os.environ["CONTROL_DATABASE_URL"] = f"{owner_base}/{CONTROL}"
    from app.core.config import get_settings
    from app.tenancy.cli import upgrade_control

    get_settings.cache_clear()
    upgrade_control(get_settings())
    maintenance = _maintenance(owner_ops)
    with maintenance.connect() as conn:
        for name in (OPS, CONTROL, FROM_PREVIOUS):
            exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}).scalar()
            if exists is not None and name != CONTROL:
                conn.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = :name AND pid <> pg_backend_pid()"
                    ),
                    {"name": name},
                )
                conn.execute(text(f'DROP DATABASE "{name}"'))
                exists = None
            if exists is None:
                conn.execute(text(f'CREATE DATABASE "{name}"'))
        conn.execute(text("DROP ROLE IF EXISTS ai_pos_app"))
        conn.exec_driver_sql(
            f"CREATE ROLE ai_pos_app LOGIN PASSWORD '{app_password}' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE"
        )
    maintenance.dispose()

    _upgrade(owner_ops, HEAD)
    _upgrade(owner_ops, HEAD)
    version = create_engine(owner_ops).connect()
    head = version.execute(text("SELECT version_num FROM alembic_version")).scalar()
    version.close()
    if head != HEAD:
        raise SystemExit(f"Unexpected head {head}")

    from_previous = f"{owner_base}/{FROM_PREVIOUS}"
    _upgrade(from_previous, PREVIOUS)
    engine = create_engine(from_previous)
    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(TENANT_B)})
        conn.execute(
            text(
                "INSERT INTO brands (id, tenant_id, name, code, description, created_at, updated_at) "
                "VALUES (:id, :tenant, 'Grocery Kept', 'GROCERY-KEPT', '', :now, :now)"
            ),
            {"id": uuid.uuid4(), "tenant": TENANT_B, "now": datetime.now(UTC)},
        )
    _upgrade(from_previous, HEAD)
    _upgrade(from_previous, HEAD)
    with engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(TENANT_B)})
        kept = conn.execute(text("SELECT name FROM brands WHERE code = 'GROCERY-KEPT'")).scalar()
        again = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    engine.dispose()
    if kept != "Grocery Kept" or again != HEAD:
        raise SystemExit("Upgrade from the previous revision did not preserve the grocery brand.")

    _downgrade(from_previous, PREVIOUS)
    with create_engine(from_previous).connect() as conn:
        conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        conn.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(TENANT_B)})
        gone = conn.execute(text("SELECT to_regclass('public.laundry_services')")).scalar()
        previous = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        still = conn.execute(text("SELECT name FROM brands WHERE code = 'GROCERY-KEPT'")).scalar()
    if gone is not None or previous != PREVIOUS or still != "Grocery Kept":
        raise SystemExit("Downgrade did not return to the previous revision cleanly.")
    _upgrade(from_previous, HEAD)

    ops = create_engine(owner_ops)
    with ops.begin() as conn:
        for table in (
            "laundry_settings",
            "laundry_service_categories",
            "laundry_garment_types",
            "laundry_services",
            "laundry_service_garments",
            "laundry_price_lists",
            "laundry_price_rates",
            "laundry_workflow_templates",
            "laundry_branch_capacities",
        ):
            forced = conn.execute(text(f"SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = '{table}'")).one()
            if not forced[0] or not forced[1]:
                raise SystemExit(f"{table} is not force-protected by row level security.")
        conn.execute(text(f'GRANT CONNECT ON DATABASE "{OPS}" TO ai_pos_app'))
        conn.execute(text("GRANT USAGE ON SCHEMA public TO ai_pos_app"))
        conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ai_pos_app"))
        conn.execute(text("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ai_pos_app"))
        role = conn.execute(
            text("SELECT rolcanlogin, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'ai_pos_app'")
        ).one()
    ops.dispose()
    if not role[0] or role[1] or role[2]:
        raise SystemExit("ai_pos_app is not a non-bypass login.")

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    report = {
        "host": HOST,
        "port": PORT,
        "operational_database": OPS,
        "control_database": CONTROL,
        "previous_revision": PREVIOUS,
        "head": HEAD,
        "repeat_upgrade": "passed",
        "grocery_brand_preserved": kept,
        "downgrade_to": PREVIOUS,
        "role": "ai_pos_app",
        "login": True,
        "superuser": False,
        "bypassrls": False,
        "developer_database_used": False,
    }
    (EVIDENCE / "migration.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
