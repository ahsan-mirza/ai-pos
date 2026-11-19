"""Start the disposable acceptance stack, run the checks, and remove it.

The development and production env files are never selected. Database URLs from
the parent process are removed before the API, migrations, or the guard start.
"""

from __future__ import annotations

import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env.acceptance"
RUNTIME = HERE / ".env.acceptance.runtime"
COMPOSE = HERE / "docker-compose.yml"
CONTAINER = "axizpos-pharmacy-acceptance-db"
EVIDENCE = HERE / "evidence"
PYTHON = ROOT / "apps" / "api" / ".venv" / "Scripts" / "python.exe"
NODE_PYTHON = ROOT / "scripts" / "python.mjs"
NPM = "npm.cmd" if os.name == "nt" else "npm"
NPX = "npx.cmd" if os.name == "nt" else "npx"


def free_port(candidates: list[int]) -> int:
    for port in candidates:
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise SystemExit(f"No free port in {candidates}.")


def child_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    for key in (
        "DATABASE_URL",
        "CONTROL_DATABASE_URL",
        "TENANT_DATABASE_URL_TEMPLATE",
        "APP_ENV",
        "PGPASSWORD",
        "REDIS_URL",
        "SMTP_HOST",
        "SMTP_PASSWORD",
        "SMTP_USERNAME",
    ):
        env.pop(key, None)
    env["APP_ENV"] = "acceptance"
    if extra:
        env.update(extra)
    return env


def run(
    args: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
    check: bool = True,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(args[:6]), flush=True)
    try:
        completed = subprocess.run(args, cwd=cwd or ROOT, env=env or child_env(), text=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise SystemExit(f"Command timed out after {timeout}s: {' '.join(args[:4])}") from error
    if check and completed.returncode != 0:
        raise SystemExit(f"Command failed ({completed.returncode}): {' '.join(args[:4])}")
    return completed


def wait_http(url: str, seconds: int = 60) -> None:
    deadline = time.time() + seconds
    last = ""
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=3) as response:
                if response.status == 200:
                    return
        except Exception as error:  # noqa: BLE001 - the process is still starting
            last = str(error)
        time.sleep(1)
    raise SystemExit(f"Timed out waiting for {url}: {last}")


def write_env(db_port: int, api_port: int, web_port: int, password: str, secrets_map: dict[str, str]) -> None:
    api = f"http://127.0.0.1:{api_port}"
    database = f"postgresql+psycopg://axizpos_acceptance:{password}@127.0.0.1:{db_port}/axizpos_pharmacy_acceptance"
    control = f"postgresql+psycopg://axizpos_acceptance:{password}@127.0.0.1:{db_port}/axizpos_pharmacy_acceptance_control"
    lines = [
        "APP_ENV=acceptance",
        f"DATABASE_URL={database}",
        f"CONTROL_DATABASE_URL={control}",
        "TENANT_BASE_DOMAINS=localhost",
        "DEFAULT_TENANT=pharmacy-accept",
        "SIGNUP_ENABLED=false",
        "SCHEDULER_ENABLED=false",
        "ALLOW_SHARED_API_KEY=true",
        f"JWT_SECRET={secrets_map['jwt']}",
        f"PIN_SALT={secrets_map['pin']}",
        f"ENCRYPTION_SECRET={secrets_map['encryption']}",
        f"API_KEY={secrets_map['api_key']}",
        "API_HOST=127.0.0.1",
        f"API_PORT={api_port}",
        f"PUBLIC_BASE_URL={api}",
        f"CORS_ORIGINS=http://127.0.0.1:{web_port},http://localhost:{web_port}",
        "ADMIN_USERNAME=admin",
        "ADMIN_EMAIL=admin@acceptance.example",
        'ADMIN_FULL_NAME=Acceptance Admin',
        f"ADMIN_PASSWORD={secrets_map['admin']}",
        "ADMIN_PIN=1357",
        f"VITE_API_BASE_URL={api}",
        "VITE_DEFAULT_CURRENCY=USD",
        "VITE_TENANT_BASE_DOMAINS=localhost",
        "VITE_DEFAULT_TENANT=pharmacy-accept",
        "VITE_SHOW_DEMO_ACCOUNTS=false",
    ]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def postgres_report() -> None:
    inspect = {
        "migration": "SELECT version_num FROM alembic_version",
        "databases": "SELECT datname FROM pg_database ORDER BY datname",
        "rls": (
            "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relname IN ("
            "'pharmacist_authorizations','pharmacy_governance_officers','batch_item_events',"
            "'pharmacy_recalls','pharmacy_recall_lots','pharmacy_supplier_returns','pharmacy_supplier_return_lines','batch_items'"
            ") ORDER BY relname"
        ),
        "append_only_trigger": (
            "SELECT tgname FROM pg_trigger WHERE tgname = 'batch_item_events_append_only' AND NOT tgisinternal"
        ),
        "forced_rls_hides_officers": "SELECT count(*) AS officers_visible_without_tenant FROM pharmacy_governance_officers",
    }
    revealed = {
        "duplicate_pharmacists": (
            "SELECT tenant_id, user_id, count(*) FROM pharmacist_authorizations "
            "WHERE status IN ('PENDING','ACTIVE') GROUP BY tenant_id, user_id HAVING count(*) > 1"
        ),
        "duplicate_officers": (
            "SELECT tenant_id, user_id, count(*) FROM pharmacy_governance_officers "
            "WHERE status IN ('PENDING','ACTIVE') GROUP BY tenant_id, user_id HAVING count(*) > 1"
        ),
        "active_officers": "SELECT status, count(*) FROM pharmacy_governance_officers GROUP BY status ORDER BY status",
        "pharmacist_statuses": "SELECT status, count(*) FROM pharmacist_authorizations GROUP BY status ORDER BY status",
        "lots": (
            "SELECT manufacturer_lot, lot_status, quantity_imported, quantity_remaining, expiry_date, "
            "(released_at IS NOT NULL) AS released, (released_by_id IS NOT NULL) AS released_by "
            "FROM batch_items WHERE manufacturer_lot LIKE 'ACCEPT%' ORDER BY manufacturer_lot, quantity_remaining"
        ),
        "allocations": (
            "SELECT bi.manufacturer_lot, ba.movement_type, ba.quantity "
            "FROM batch_allocations ba JOIN batch_items bi ON bi.id = ba.batch_item_id "
            "WHERE bi.manufacturer_lot LIKE 'ACCEPT%' ORDER BY bi.manufacturer_lot, ba.movement_type"
        ),
        "events": (
            "SELECT bi.manufacturer_lot, e.action, e.from_status, e.to_status "
            "FROM batch_item_events e JOIN batch_items bi ON bi.id = e.batch_item_id "
            "WHERE bi.manufacturer_lot LIKE 'ACCEPT%' ORDER BY bi.manufacturer_lot, e.created_at"
        ),
        "negative_stock": "SELECT count(*) FROM batch_items WHERE quantity_remaining < 0",
        "orphan_events": (
            "SELECT count(*) FROM batch_item_events e LEFT JOIN batch_items i ON i.id = e.batch_item_id WHERE i.id IS NULL"
        ),
    }
    lines = ["# Acceptance PostgreSQL (read only)"]
    for label, sql in inspect.items():
        completed = subprocess.run(
            ["docker", "exec", CONTAINER, "psql", "-U", "axizpos_acceptance", "-d", "axizpos_pharmacy_acceptance", "-c", sql],
            check=False,
            capture_output=True,
            text=True,
        )
        lines.append(f"\n## {label}\n{completed.stdout or completed.stderr}")
    control = subprocess.run(
        ["docker", "exec", CONTAINER, "psql", "-U", "axizpos_acceptance", "-d", "axizpos_pharmacy_acceptance_control", "-c", "SELECT version_num FROM alembic_version"],
        check=False,
        capture_output=True,
        text=True,
    )
    lines.append(f"\n## control_migration\n{control.stdout or control.stderr}")
    for label, sql in revealed.items():
        statement = f"BEGIN; SET LOCAL app.bypass_rls = 'on'; {sql}; ROLLBACK;"
        completed = subprocess.run(
            ["docker", "exec", CONTAINER, "psql", "-U", "axizpos_acceptance", "-d", "axizpos_pharmacy_acceptance", "-c", statement],
            check=False,
            capture_output=True,
            text=True,
        )
        lines.append(f"\n## {label}\n{completed.stdout or completed.stderr}")
    (EVIDENCE / "postgres.txt").write_text("\n".join(lines), encoding="utf-8")


def psql(database: str, sql: str, secret: str = "") -> None:
    completed = subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "psql", "-U", "axizpos_acceptance", "-d", database, "-v", "ON_ERROR_STOP=1", "-q"],
        input=sql,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or "psql failed").replace(secret, "***") if secret else "psql failed"
        (EVIDENCE / "role-setup.txt").write_text(detail, encoding="utf-8")
        raise SystemExit("Application role setup failed. The database password was not printed.")


def grant_app_role(password: str) -> None:
    """Match the production application role: login, not superuser, no bypassrls, DML only."""
    psql(
        "axizpos_pharmacy_acceptance",
        "CREATE ROLE ai_pos_app LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD '" + password + "'",
        password,
    )
    for database in ("axizpos_pharmacy_acceptance", "axizpos_pharmacy_acceptance_control"):
        psql(
            database,
            "GRANT CONNECT ON DATABASE " + database + " TO ai_pos_app; "
            "GRANT USAGE ON SCHEMA public TO ai_pos_app; "
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ai_pos_app; "
            "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ai_pos_app;",
        )


def switch_database_role(password: str) -> None:
    rewritten = []
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("DATABASE_URL=") or line.startswith("CONTROL_DATABASE_URL="):
            key, url = line.split("=", 1)
            scheme, rest = url.split("://", 1)
            host = rest.split("@", 1)[1]
            rewritten.append(f"{key}={scheme}://ai_pos_app:{password}@{host}")
        else:
            rewritten.append(line)
    ENV_FILE.write_text("\n".join(rewritten) + "\n", encoding="utf-8")


def write_offline_blocker() -> None:
    """The developer register already has data. Do not start it."""
    appdata = os.environ.get("APPDATA", "")
    existing = Path(appdata) / "com.aipos.desktop" if appdata else None
    present = bool(existing and (existing / "ai-pos.db").is_file())
    text = "\n".join(
        [
            "Offline pharmacy checkout was not run.",
            "The pharmacy block runs only inside the Tauri webview. A browser preview does not enter that path.",
            "Debug builds load the repo-root .env before activation.",
            "The installed register identifier com.aipos.desktop already has terminal.bin and ai-pos.db under the user application data directory.",
            f"existing_register_data={'yes' if present else 'no'}",
            "This run did not start that application and did not open its SQLite files.",
            "A separate acceptance identifier was not launched because the webview cannot be driven without risking that existing register.",
        ]
    )
    (EVIDENCE / "offline.txt").write_text(text + "\n", encoding="utf-8")


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    if not (HERE / "node_modules" / "playwright").exists():
        run([NPM, "install", "--silent"], cwd=HERE, env=child_env())
        run([NPX, "playwright", "install", "chromium"], cwd=HERE, env=child_env())
    db_port = free_port([55432, 55433, 55434])
    api_port = free_port([18080, 18081, 18082])
    web_port = free_port([15173, 15174, 15175])
    password = secrets.token_urlsafe(24)
    secrets_map = {
        "jwt": secrets.token_urlsafe(48),
        "pin": secrets.token_urlsafe(24),
        "encryption": secrets.token_urlsafe(48),
        "api_key": secrets.token_urlsafe(24),
        "admin": "accept-admin-" + secrets.token_hex(4),
        "staff": "accept-staff-" + secrets.token_hex(4),
    }
    RUNTIME.write_text(
        f"ACCEPTANCE_DB_PASSWORD={password}\nACCEPTANCE_DB_PORT={db_port}\n",
        encoding="utf-8",
    )
    api_proc = None
    web_proc = None
    code = 0
    try:
        run(
            ["docker", "compose", "-f", str(COMPOSE), "--env-file", str(RUNTIME), "up", "-d", "--wait"],
            cwd=HERE,
        )
        identity = subprocess.run(
            ["docker", "inspect", "-f", "{{.Name}} {{range .Mounts}}{{.Name}} {{end}}", CONTAINER],
            check=False,
            capture_output=True,
            text=True,
        )
        if identity.returncode != 0 or "axizpos-pharmacy-acceptance-pg" not in identity.stdout or "ai_pos" in identity.stdout:
            raise SystemExit(f"Refusing to touch Postgres before the guard. Inspect said: {identity.stdout} {identity.stderr}")
        published = subprocess.run(["docker", "port", CONTAINER, "5432"], check=False, capture_output=True, text=True)
        if published.stdout.strip() != f"127.0.0.1:{db_port}":
            raise SystemExit(f"Refusing to continue. Postgres is published at {published.stdout.strip()!r}.")
        run(
            [
                "docker",
                "exec",
                CONTAINER,
                "psql",
                "-U",
                "axizpos_acceptance",
                "-d",
                "axizpos_pharmacy_acceptance",
                "-c",
                "CREATE DATABASE axizpos_pharmacy_acceptance_control",
            ]
        )
        write_env(db_port, api_port, web_port, password, secrets_map)
        guard = subprocess.run(
            [str(PYTHON), str(HERE / "guard.py")],
            cwd=ROOT,
            env=child_env(),
            text=True,
            capture_output=True,
            check=False,
        )
        (EVIDENCE / "isolation.txt").write_text((guard.stdout or "") + (guard.stderr or ""), encoding="utf-8")
        print(guard.stdout or guard.stderr)
        if guard.returncode != 0:
            raise SystemExit("Isolation guard refused to continue. No migration was started.")
        node = ["node", str(NODE_PYTHON), "--env=acceptance", "-m", "app.tenancy.cli"]
        run(node + ["init"])
        tenants = [
            ("pharmacy-accept", "Acceptance Pharmacy", "pharmacy"),
            ("pharmacy-accept-b", "Acceptance Pharmacy B", "pharmacy"),
            ("accept-electronics-wholesale", "Acceptance Electronics", "electronics_wholesale"),
            ("accept-wholesale-retail", "Acceptance Wholesale", "wholesale_retail"),
            ("accept-retail-fashion", "Acceptance Fashion", "retail_fashion"),
            ("accept-grocery", "Acceptance Grocery", "grocery"),
            ("accept-restaurant", "Acceptance Restaurant", "restaurant"),
            ("accept-cafe", "Acceptance Cafe", "cafe"),
            ("accept-quick-service", "Acceptance Quick Service", "quick_service"),
        ]
        for slug, name, profile in tenants:
            run(node + ["create", slug, "--name", name, "--profile", profile])
        # The CLI assigns Free, which allows 2 staff and 1 branch. The pharmacy
        # acceptance tenant is moved to the existing Pro AI plan so the two-person
        # workflow and a destination store fit the published caps. No inventory rows
        # are written here.
        run([str(PYTHON), str(HERE / "assign_plan.py")])
        app_password = secrets.token_hex(24)
        grant_app_role(app_password)
        switch_database_role(app_password)
        guard = subprocess.run(
            [str(PYTHON), str(HERE / "guard.py")],
            cwd=ROOT,
            env=child_env({"ACCEPTANCE_EXPECT_APP_ROLE": "1"}),
            text=True,
            capture_output=True,
            check=False,
        )
        with (EVIDENCE / "isolation.txt").open("a", encoding="utf-8") as handle:
            handle.write("\n# application role\n")
            handle.write((guard.stdout or "") + (guard.stderr or ""))
        print(guard.stdout or guard.stderr)
        if guard.returncode != 0:
            raise SystemExit("Isolation guard refused the application role. The API was not started.")
        api_proc = subprocess.Popen(
            ["node", str(NODE_PYTHON), "--env=acceptance", "-m", "app.serve"],
            cwd=ROOT,
            env=child_env(),
        )
        wait_http(f"http://127.0.0.1:{api_port}/health")
        exercise_env = child_env(
            {
                "ACCEPTANCE_API_URL": f"http://127.0.0.1:{api_port}",
                "ACCEPTANCE_ADMIN_PASSWORD": secrets_map["admin"],
                "ACCEPTANCE_STAFF_PASSWORD": secrets_map["staff"],
                "ACCEPTANCE_API_KEY": secrets_map["api_key"],
                "ADMIN_USERNAME": "admin",
                "ACCEPTANCE_PHASE": "setup",
            }
        )
        run([str(PYTHON), str(HERE / "exercise.py")], env=exercise_env)
        web_proc = subprocess.Popen(
            [NPX, "vite", "--mode", "acceptance", "--port", str(web_port), "--strictPort", "--host", "127.0.0.1"],
            cwd=ROOT / "apps" / "web",
            env=child_env(),
        )
        wait_http(f"http://127.0.0.1:{web_port}/", seconds=150)
        browser_env = child_env(
            {
                "ACCEPTANCE_WEB_URL": f"http://127.0.0.1:{web_port}",
                "ACCEPTANCE_ADMIN_PASSWORD": secrets_map["admin"],
                "ACCEPTANCE_STAFF_PASSWORD": secrets_map["staff"],
                "BROWSER_PHASE": "main",
            }
        )
        browser = run(["node", str(HERE / "browser.mjs")], env=browser_env, cwd=HERE, check=False, timeout=240)
        if browser.returncode != 0:
            code = 1
        exercise_env["ACCEPTANCE_PHASE"] = "portal-prep"
        prepared = run([str(PYTHON), str(HERE / "exercise.py")], env=exercise_env, check=False)
        if prepared.returncode != 0:
            code = 1
        browser_env["BROWSER_PHASE"] = "portal"
        portal = run(["node", str(HERE / "browser.mjs")], env=browser_env, cwd=HERE, check=False, timeout=300)
        if portal.returncode != 0:
            code = 1
        exercise_env["ACCEPTANCE_PHASE"] = "portal-verify"
        verified = run([str(PYTHON), str(HERE / "exercise.py")], env=exercise_env, check=False)
        if verified.returncode != 0:
            code = 1
        exercise_env["ACCEPTANCE_PHASE"] = "finish"
        finished = run([str(PYTHON), str(HERE / "exercise.py")], env=exercise_env, check=False)
        if finished.returncode != 0:
            code = 1
        browser_env["BROWSER_PHASE"] = "after"
        after = run(["node", str(HERE / "browser.mjs")], env=browser_env, cwd=HERE, check=False, timeout=240)
        if after.returncode != 0:
            code = 1
        exercise_env["ACCEPTANCE_PHASE"] = "revoke"
        revoked = run([str(PYTHON), str(HERE / "exercise.py")], env=exercise_env, check=False)
        if revoked.returncode != 0:
            code = 1
        browser_env["BROWSER_PHASE"] = "profiles"
        profiles = run(["node", str(HERE / "browser.mjs")], env=browser_env, cwd=HERE, check=False, timeout=300)
        if profiles.returncode != 0:
            code = 1
        probed = run([str(PYTHON), str(HERE / "rls_probe.py")], env=exercise_env, check=False, timeout=180)
        if probed.returncode != 0:
            code = 1
        postgres_report()
        write_offline_blocker()
    except SystemExit as error:
        print(error, file=sys.stderr)
        code = 1
    finally:
        for proc in (web_proc, api_proc):
            if proc is None or proc.poll() is not None:
                continue
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], check=False, capture_output=True)
            else:
                proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
        subprocess.run(
            ["docker", "compose", "-f", str(COMPOSE), "--env-file", str(RUNTIME), "down", "-v", "--remove-orphans"],
            cwd=HERE,
            check=False,
        )
        ENV_FILE.unlink(missing_ok=True)
        RUNTIME.unlink(missing_ok=True)
        leftover = subprocess.run(["docker", "ps", "-q", "-f", f"name={CONTAINER}"], capture_output=True, text=True, check=False)
        print("cleanup_container_remaining", "yes" if leftover.stdout.strip() else "no")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
