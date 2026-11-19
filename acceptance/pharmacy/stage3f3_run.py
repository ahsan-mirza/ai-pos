"""Stage 3F.3 portal acceptance. This does not start a desktop register.

The inventory acceptance register, the developer API, and the developer database
are left running. Only the pharmacy acceptance container started here is removed.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

import run as acceptance

STAGE = acceptance.HERE / "evidence" / "stage-3f.3"
NODE = ["node", str(acceptance.NODE_PYTHON), "--env=acceptance"]
INHERITED_SECRETS = (
    "API_KEY",
    "JWT_SECRET",
    "PIN_SALT",
    "ENCRYPTION_SECRET",
    "ADMIN_PASSWORD",
    "ADMIN_PIN",
    "ADMIN_USERNAME",
    "ADMIN_EMAIL",
    "CORS_ORIGINS",
    "PUBLIC_BASE_URL",
    "VITE_API_BASE_URL",
    "VITE_DEFAULT_TENANT",
)


def isolated_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Drop parent secrets so the acceptance env file is the only source."""
    env = acceptance.child_env()
    for key in INHERITED_SECRETS:
        env.pop(key, None)
    if extra:
        env.update(extra)
    return env


def write_gate() -> None:
    STAGE.mkdir(parents=True, exist_ok=True)
    script = r"""
$desktops = Get-CimInstance Win32_Process -Filter "Name = 'ai-pos-desktop.exe'" | Select-Object ProcessId, ExecutablePath, CommandLine
$listeners = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -in 18081,55433,8000,5432 } | Select-Object LocalAddress, LocalPort, OwningProcess
$containers = docker ps --format "{{.Names}} {{.Ports}}"
[pscustomobject]@{
  desktops = @($desktops)
  listeners = @($listeners)
  containers = @($containers -split "`n" | Where-Object { $_ -ne "" })
} | ConvertTo-Json -Depth 4
"""
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        check=False,
        capture_output=True,
        text=True,
    )
    (STAGE / "process-gate.json").write_text(completed.stdout or completed.stderr, encoding="utf-8")
    text = completed.stdout or ""
    inventory = "acceptance\\inventory\\target\\release\\ai-pos-desktop.exe" in text or "acceptance/inventory/target/release/ai-pos-desktop.exe" in text
    (STAGE / "desktop-blocked.txt").write_text(
        "\n".join(
            [
                "Windows Pharmacy register: BLOCKED — INVENTORY ACCEPTANCE SESSION ACTIVE" if inventory else "Windows Pharmacy register: inventory acceptance process was not found",
                "The inventory acceptance executable was not closed, clicked, or replaced.",
                "No second AxizPOS register was launched.",
                "Tenant capability-cache reactivation on the Windows register: NOT RUN",
                "Pharmacy online register sale, double-click Charge, offline block, PIN reauthentication, and header states: NOT RUN",
                "Grocery offline synchronization on the Windows register: NOT RUN",
                f"inventory_acceptance_desktop={'yes' if inventory else 'no'}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (STAGE / "not-run.json").write_text(
        json.dumps(
            {
                "unreleased_status_preservation": "NOT RUN. No existing portal or pharmacy endpoint sets a sold released layer back to UNRELEASED, and quantities were not written with SQL.",
                "damaged_status_preservation": "NOT RUN. No existing service writes DAMAGED, and this stage does not add that workflow.",
                "windows_register": "BLOCKED — INVENTORY ACCEPTANCE SESSION ACTIVE" if inventory else "NOT RUN",
                "tenant_capability_cache": "NOT RUN. It requires the Pharmacy acceptance register, which was not launched while the inventory acceptance session is active." if inventory else "NOT RUN",
                "offline_and_header_states": "NOT RUN. Those states are produced by the register session, not by the Business Pro portal." if inventory else "NOT RUN",
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def developer_files() -> dict[str, dict[str, str]]:
    appdata = os.environ.get("APPDATA", "")
    root = Path(appdata) / "com.aipos.desktop" if appdata else None
    found: dict[str, dict[str, str]] = {}
    for name in ("ai-pos.db", "terminal.bin"):
        path = (root / name) if root else None
        if path and path.is_file():
            stat = path.stat()
            found[name] = {"bytes": str(stat.st_size), "mtime": str(stat.st_mtime_ns)}
        else:
            found[name] = {"present": "no"}
    env = acceptance.ROOT / ".env"
    if env.is_file():
        stat = env.stat()
        found[".env"] = {"bytes": str(stat.st_size), "mtime": str(stat.st_mtime_ns)}
    return found


def postgres_evidence() -> None:
    sql = (
        "SELECT bi.manufacturer_lot, bi.lot_status, bi.quantity_imported, bi.quantity_remaining "
        "FROM batch_items bi WHERE bi.manufacturer_lot LIKE 'LOT-%' OR bi.manufacturer_lot LIKE '3F3%' "
        "ORDER BY bi.manufacturer_lot;"
    )
    completed = subprocess.run(
        ["docker", "exec", acceptance.CONTAINER, "psql", "-U", "axizpos_acceptance", "-d", "axizpos_pharmacy_acceptance", "-c", sql],
        check=False,
        capture_output=True,
        text=True,
    )
    (STAGE / "lots.txt").write_text(completed.stdout or completed.stderr, encoding="utf-8")


def main() -> int:
    write_gate()
    before = developer_files()
    (STAGE / "developer-before.json").write_text(json.dumps(before, indent=2), encoding="utf-8")
    acceptance.EVIDENCE = STAGE
    if not (acceptance.HERE / "node_modules" / "playwright").exists():
        acceptance.run([acceptance.NPM, "install", "--silent"], cwd=acceptance.HERE, env=isolated_env())
        acceptance.run([acceptance.NPX, "playwright", "install", "chromium"], cwd=acceptance.HERE, env=isolated_env())
    db_port = acceptance.free_port([55432, 55434, 55435])
    api_port = acceptance.free_port([18080, 18082, 18083])
    web_port = acceptance.free_port([15173, 15174, 15175])
    if db_port in {5432, 55433} or api_port in {8000, 18081} or web_port in {5173, 5174, 5175}:
        raise SystemExit("Selected port belongs to a live environment.")
    password = secrets.token_urlsafe(24)
    secrets_map = {
        "jwt": secrets.token_urlsafe(48),
        "pin": secrets.token_urlsafe(24),
        "encryption": secrets.token_urlsafe(48),
        "api_key": secrets.token_urlsafe(24),
        "admin": "accept-admin-" + secrets.token_hex(4),
        "staff": "accept-staff-" + secrets.token_hex(4),
    }
    acceptance.RUNTIME.write_text(f"ACCEPTANCE_DB_PASSWORD={password}\nACCEPTANCE_DB_PORT={db_port}\n", encoding="utf-8")
    api_proc = None
    web_proc = None
    code = 0
    try:
        acceptance.run(["docker", "compose", "-f", str(acceptance.COMPOSE), "--env-file", str(acceptance.RUNTIME), "up", "-d", "--wait"], cwd=acceptance.HERE)
        published = subprocess.run(["docker", "port", acceptance.CONTAINER, "5432"], check=False, capture_output=True, text=True)
        if published.stdout.strip() != f"127.0.0.1:{db_port}":
            raise SystemExit(f"Postgres published at {published.stdout.strip()!r}.")
        acceptance.run(
            ["docker", "exec", acceptance.CONTAINER, "psql", "-U", "axizpos_acceptance", "-d", "axizpos_pharmacy_acceptance", "-c", "CREATE DATABASE axizpos_pharmacy_acceptance_control"]
        )
        acceptance.write_env(db_port, api_port, web_port, password, secrets_map)
        guard = subprocess.run([str(acceptance.PYTHON), str(acceptance.HERE / "guard.py")], cwd=acceptance.ROOT, env=isolated_env(), text=True, capture_output=True, check=False)
        (STAGE / "isolation.txt").write_text((guard.stdout or "") + (guard.stderr or ""), encoding="utf-8")
        print(guard.stdout or guard.stderr)
        if guard.returncode != 0:
            raise SystemExit("Isolation guard refused to continue. No migration was started.")
        acceptance.run(NODE + ["-m", "app.tenancy.cli", "init"])
        for slug, name, profile in (
            ("pharmacy-accept", "Acceptance Pharmacy", "pharmacy"),
            ("accept-grocery", "Acceptance Grocery", "grocery"),
        ):
            acceptance.run(NODE + ["-m", "app.tenancy.cli", "create", slug, "--name", name, "--profile", profile])
        acceptance.run(NODE + [str(acceptance.HERE / "stage3f3_plan.py")])
        app_password = secrets.token_hex(24)
        acceptance.grant_app_role(app_password)
        acceptance.switch_database_role(app_password)
        guard = subprocess.run(
            [str(acceptance.PYTHON), str(acceptance.HERE / "guard.py")],
            cwd=acceptance.ROOT,
            env=isolated_env({"ACCEPTANCE_EXPECT_APP_ROLE": "1"}),
            text=True,
            capture_output=True,
            check=False,
        )
        with (STAGE / "isolation.txt").open("a", encoding="utf-8") as handle:
            handle.write("\n# application role\n")
            handle.write((guard.stdout or "") + (guard.stderr or ""))
        print(guard.stdout or guard.stderr)
        if guard.returncode != 0:
            raise SystemExit("Isolation guard refused the application role. The API was not started.")
        (STAGE / "environment.txt").write_text(
            "\n".join(
                [
                    "identity=com.axizpos.pharmacy.acceptance was not launched",
                    "desktop=not started",
                    f"api=http://127.0.0.1:{api_port}",
                    f"portal=http://127.0.0.1:{web_port}",
                    f"postgres=127.0.0.1:{db_port}",
                    "operational_database=axizpos_pharmacy_acceptance",
                    "control_database=axizpos_pharmacy_acceptance_control",
                    "container=axizpos-pharmacy-acceptance-db",
                    "database_role=ai_pos_app",
                    "tenants=pharmacy-accept,accept-grocery",
                    "inventory_api=not used",
                    "developer_api=not used",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        api_proc = subprocess.Popen(NODE + ["-m", "app.serve"], cwd=acceptance.ROOT, env=isolated_env())
        acceptance.wait_http(f"http://127.0.0.1:{api_port}/health")
        seed_env = isolated_env(
            {
                "ACCEPTANCE_API_URL": f"http://127.0.0.1:{api_port}",
                "ACCEPTANCE_ADMIN_PASSWORD": secrets_map["admin"],
                "ACCEPTANCE_STAFF_PASSWORD": secrets_map["staff"],
                "ACCEPTANCE_API_KEY": secrets_map["api_key"],
                "ACCEPTANCE_PHASE": "seed",
            }
        )
        acceptance.run([str(acceptance.PYTHON), str(acceptance.HERE / "stage3f3_return.py")], env=seed_env, cwd=acceptance.HERE)
        web_proc = subprocess.Popen(
            [acceptance.NPX, "vite", "--mode", "acceptance", "--port", str(web_port), "--strictPort", "--host", "127.0.0.1"],
            cwd=acceptance.ROOT / "apps" / "web",
            env=isolated_env(),
        )
        acceptance.wait_http(f"http://127.0.0.1:{web_port}/", seconds=150)
        browser = acceptance.run(
            ["node", str(acceptance.HERE / "stage3f3_browser.mjs")],
            env=isolated_env(
                {
                    "ACCEPTANCE_WEB_URL": f"http://127.0.0.1:{web_port}",
                    "ACCEPTANCE_ADMIN_PASSWORD": secrets_map["admin"],
                }
            ),
            cwd=acceptance.HERE,
            check=False,
            timeout=240,
        )
        if browser.returncode != 0:
            code = 1
        seed_env["ACCEPTANCE_PHASE"] = "verify"
        verified = acceptance.run([str(acceptance.PYTHON), str(acceptance.HERE / "stage3f3_return.py")], env=seed_env, cwd=acceptance.HERE, check=False)
        if verified.returncode != 0:
            code = 1
        postgres_evidence()
    except SystemExit as error:
        print(error, file=sys.stderr)
        (STAGE / "runner-error.txt").write_text(str(error) + "\n", encoding="utf-8")
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
            ["docker", "compose", "-f", str(acceptance.COMPOSE), "--env-file", str(acceptance.RUNTIME), "down", "-v", "--remove-orphans"],
            cwd=acceptance.HERE,
            check=False,
        )
        acceptance.ENV_FILE.unlink(missing_ok=True)
        acceptance.RUNTIME.unlink(missing_ok=True)
        (acceptance.HERE / ".env.stage3f3.device").unlink(missing_ok=True)
        leftover = subprocess.run(["docker", "ps", "-q", "-f", f"name={acceptance.CONTAINER}"], capture_output=True, text=True, check=False)
        after = developer_files()
        (STAGE / "cleanup.txt").write_text(
            "\n".join(
                [
                    f"pharmacy_acceptance_container_remaining={'yes' if leftover.stdout.strip() else 'no'}",
                    f"developer_files_unchanged={'yes' if after == before else 'no'}",
                    "inventory_acceptance_register=not stopped by this run",
                    "developer_api=not stopped by this run",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (STAGE / "developer-after.json").write_text(json.dumps(after, indent=2), encoding="utf-8")
        print("STAGE3F3_DONE", code, flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
