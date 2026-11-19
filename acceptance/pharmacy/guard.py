"""Fail closed unless the resolved database targets are the disposable acceptance Postgres.

This does not trust APP_ENV by itself. It reads the acceptance env file, loads the
settings the API would use, and checks the host, port, database name, published
Docker port, container name, and volume. Passwords are never printed.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy.engine import make_url
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "apps" / "api"
ACCEPTANCE = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env.acceptance"
CONTAINER = "axizpos-pharmacy-acceptance-db"
NETWORK = "axizpos-pharmacy-acceptance-net"
VOLUME = "axizpos-pharmacy-acceptance-pg"
IDENTIFIER = "axizpos-pharmacy-acceptance"
OPERATIONAL_DB = "axizpos_pharmacy_acceptance"
CONTROL_DB = "axizpos_pharmacy_acceptance_control"
ALLOWED_DATABASES = frozenset(
    {OPERATIONAL_DB, CONTROL_DB, "postgres", "template0", "template1"}
)
FORBIDDEN_PORTS = frozenset({5432, 8000, 5173})
AUDITED_FILES = (".env", ".env.dev", ".env.production", ".env.test", ".env.local")
URL_KEYS = ("DATABASE_URL", "CONTROL_DATABASE_URL")


class IsolationError(RuntimeError):
    pass


def _parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _endpoint(url: str) -> tuple[str, int, str]:
    parsed = make_url(url)
    host = (parsed.host or "").lower()
    port = int(parsed.port or 5432)
    database = parsed.database or ""
    return host, port, database


def _public(url: str) -> str:
    host, port, database = _endpoint(url)
    return f"{host}:{port}/{database}"


def _audited_targets() -> list[tuple[str, str, int, str]]:
    found: list[tuple[str, str, int, str]] = []
    for name in AUDITED_FILES:
        values = _parse_env(ROOT / name)
        for key in URL_KEYS:
            raw = values.get(key, "")
            if not raw or raw.startswith("#"):
                continue
            try:
                host, port, database = _endpoint(raw)
            except Exception as error:  # noqa: BLE001 - a bad URL is still a target we must not match
                raise IsolationError(f"{name} {key} could not be parsed. Refusing to continue.") from error
            found.append((f"{name}:{key}", host, port, database))
    return found


def _run(args: list[str]) -> str:
    completed = subprocess.run(args, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise IsolationError(f"{' '.join(args[:3])} failed: {detail}")
    return completed.stdout.strip()


def _container() -> None:
    name = _run(["docker", "inspect", "-f", "{{.Name}}", CONTAINER])
    if name != f"/{CONTAINER}":
        raise IsolationError(f"Container identity is {name}, expected /{CONTAINER}.")
    image = _run(["docker", "inspect", "-f", "{{.Config.Image}}", CONTAINER])
    if not image.startswith("postgres:"):
        raise IsolationError(f"Container image is {image}.")
    networks = _run(["docker", "inspect", "-f", "{{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}", CONTAINER])
    if NETWORK not in networks.split():
        raise IsolationError(f"Container networks are {networks!r}, expected {NETWORK}.")
    mounts = _run(["docker", "inspect", "-f", "{{range .Mounts}}{{.Name}} {{end}}", CONTAINER])
    names = mounts.split()
    if VOLUME not in names:
        raise IsolationError(f"Container volumes are {names}, expected {VOLUME}.")
    if any("ai_pos" in item for item in names):
        raise IsolationError(f"Container is attached to a development volume: {names}.")
    published = _run(["docker", "port", CONTAINER, "5432"])
    # Example: 127.0.0.1:55432
    bindings = [line.strip() for line in published.splitlines() if line.strip()]
    if len(bindings) != 1 or not bindings[0].startswith("127.0.0.1:"):
        raise IsolationError(f"Postgres is not bound only to loopback: {bindings}.")


def _databases(url: str) -> set[str]:
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            current = connection.execute(text("SELECT current_database()")).scalar_one()
            names = {row[0] for row in connection.execute(text("SELECT datname FROM pg_database"))}
            role = connection.execute(
                text(
                    "SELECT r.rolname, r.rolsuper, r.rolbypassrls "
                    "FROM pg_roles r WHERE r.rolname = current_user"
                )
            ).one()
            print(f"database_role={role.rolname}")
            print(f"role_superuser={'yes' if role.rolsuper else 'no'}")
            print(f"role_bypassrls={'yes' if role.rolbypassrls else 'no'}")
            if os.environ.get("ACCEPTANCE_EXPECT_APP_ROLE") == "1" and (
                role.rolname != "ai_pos_app" or role.rolsuper or role.rolbypassrls
            ):
                raise IsolationError("The database role is not the non-superuser application role ai_pos_app.")
    finally:
        engine.dispose()
    if current != _endpoint(url)[2]:
        raise IsolationError(f"Connected database is {current}.")
    unexpected = names - ALLOWED_DATABASES
    if unexpected:
        raise IsolationError(
            "The server has databases outside this acceptance stack: " + ", ".join(sorted(unexpected))
        )
    return names


def main() -> int:
    if os.environ.get("APP_ENV", "").strip().lower() != "acceptance":
        raise IsolationError("APP_ENV is not acceptance. Refusing to continue.")
    for key in ("DATABASE_URL", "CONTROL_DATABASE_URL"):
        if os.environ.get(key):
            raise IsolationError(f"{key} is set in the process environment. Refusing to let it override the acceptance file.")
    file_values = _parse_env(ENV_FILE)
    if file_values.get("APP_ENV", "acceptance") not in {"", "acceptance"}:
        raise IsolationError("The acceptance env file does not designate acceptance.")
    operational = file_values.get("DATABASE_URL", "")
    control = file_values.get("CONTROL_DATABASE_URL", "")
    if not operational or not control:
        raise IsolationError("The acceptance env file has no operational or control database URL.")

    sys.path.insert(0, str(API))
    os.environ["APP_ENV"] = "acceptance"
    from app.core.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    if settings.app_env != "acceptance":
        raise IsolationError(f"Resolved app environment is {settings.app_env}.")
    if settings.database_url != operational or settings.control_database_url != control:
        raise IsolationError("Resolved settings do not match the acceptance env file.")

    op_host, op_port, op_db = _endpoint(settings.database_url)
    ct_host, ct_port, ct_db = _endpoint(settings.control_database_url or "")
    if op_host not in {"127.0.0.1", "localhost"} or ct_host not in {"127.0.0.1", "localhost"}:
        raise IsolationError("A database host is not loopback.")
    if op_host != ct_host or op_port != ct_port:
        raise IsolationError("Operational and control databases are not on the same acceptance server.")
    if op_port in FORBIDDEN_PORTS or ct_port in FORBIDDEN_PORTS:
        raise IsolationError("A database port is a development or production port.")
    if op_db != OPERATIONAL_DB or ct_db != CONTROL_DB:
        raise IsolationError("A database name is not an acceptance database.")
    if op_db == ct_db:
        raise IsolationError("Operational and control databases must be different names on the acceptance server.")

    for label, host, port, database in _audited_targets():
        if (host, port, database) in {(op_host, op_port, op_db), (ct_host, ct_port, ct_db)}:
            raise IsolationError(f"Acceptance target matches {label}.")
        if database in {op_db, ct_db}:
            raise IsolationError(f"{label} already uses an acceptance database name.")
        if host not in {"127.0.0.1", "localhost", ""} and host == op_host:
            raise IsolationError(f"Acceptance host matches non-local target {label}.")

    api = urlsplit(file_values.get("PUBLIC_BASE_URL", ""))
    if api.hostname not in {"127.0.0.1", "localhost"} or api.port in FORBIDDEN_PORTS or api.port is None:
        raise IsolationError("The acceptance API address is not an isolated loopback port.")
    vite = file_values.get("VITE_API_BASE_URL", "")
    if not vite.startswith("http://127.0.0.1:") or ":8000" in vite or ":5173" in vite:
        raise IsolationError("The portal API address does not point at the acceptance API.")

    _container()
    published = _run(["docker", "port", CONTAINER, "5432"])
    if published != f"127.0.0.1:{op_port}":
        raise IsolationError(f"Published Postgres port is {published}, expected 127.0.0.1:{op_port}.")

    names = _databases(settings.database_url)
    # The control URL is the same server. Listing from the operational connection is enough,
    # and the control database must already exist before its migration.
    if CONTROL_DB not in names or OPERATIONAL_DB not in names:
        raise IsolationError(f"Acceptance databases are missing. Found {sorted(names)}.")
    _databases(settings.control_database_url or "")

    print("ACCEPTANCE ISOLATION")
    print(f"identifier={IDENTIFIER}")
    print(f"postgres_container={CONTAINER}")
    print(f"network={NETWORK}")
    print(f"volume={VOLUME}")
    print(f"operational_target={_public(settings.database_url)}")
    print(f"control_target={_public(settings.control_database_url or '')}")
    print(f"api_target={file_values.get('PUBLIC_BASE_URL', '')}")
    print(f"portal_api_target={vite}")
    print("development_match=no")
    print("production_match=no")
    print("persistent_database_match=no")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except IsolationError as error:
        print(f"ACCEPTANCE ISOLATION REFUSED: {error}", file=sys.stderr)
        raise SystemExit(2) from error
