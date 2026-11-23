"""Quantity dialog check on the disposable grocery, electronics, and fashion windows.

Each window has its own identity, database, and port. This does not open the
installed register, the live laundry register, or settle a sale.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from zoom_acceptance_run import (
    APPDATA,
    PROFILES,
    REPO,
    build,
    capture,
    click,
    ensure_key,
    read_json,
    start_server,
    wait_measured,
    wait_ready,
)

OUT = REPO / "docs" / "ui-ux" / "quantity-profile-evidence"
CHECKS = {
    "grocery": ["Zoom Rice 1kg"],
    "electronics": ["Zoom USB Cable", "Zoom Serialized Handset"],
    "fashion": ["Zoom Longline Shirt"],
}


def see(directory: Path, needle: str, timeout: float = 20) -> dict:
    return wait_measured(
        directory,
        lambda row, needle=needle: needle in (row.get("dialog") or "") or needle in (row.get("text") or ""),
        timeout,
    )


def brief(row: dict) -> dict:
    dialog = " ".join((row.get("dialog") or "").split())
    return {
        "dialog": dialog[:500],
        "has_portion": "Portion size" in dialog,
        "has_stepper": "Decrease quantity" in (row.get("text") or "") or "Quantity" in dialog,
        "has_scale": "scale" in dialog.lower() or "weight" in dialog.lower(),
        "has_serial": "serial" in dialog.lower(),
        "has_size": "Size" in dialog or "Sand" in dialog or "Navy" in dialog,
    }


def run(profile: str, seed: str, pin: str) -> dict:
    port, identifier, title = PROFILES[profile]
    server, log_path = start_server(profile, seed, pin)
    result: dict = {"profile": profile, "port": port, "identifier": identifier, "title": title}
    proc = None
    try:
        wait_ready(server, log_path, profile)
        ready = json.loads((Path(os.environ["TEMP"]) / "axiz-zoom" / profile / "ready.json").read_text(encoding="utf-8"))
        exe = build(profile, port)
        result["executable"] = str(exe)
        result["database"] = ready.get("database")
        result["api"] = ready.get("api")
        directory = APPDATA / identifier
        if directory.exists():
            subprocess.check_call(["powershell", "-NoProfile", "-Command", f"Remove-Item -LiteralPath '{directory}' -Recurse -Force"])
        directory.mkdir(parents=True)
        (directory / "zoom-profile.txt").write_text(profile, encoding="utf-8")
        (directory / "zoom-activate.json").write_text(
            json.dumps({"subdomain": ready["store_code"], "activation_key": ready["activation_key"]}),
            encoding="utf-8",
        )
        (directory / "zoom-unlock.json").write_text(json.dumps({"username": ready["username"], "pin": ready["pin"]}), encoding="utf-8")
        (directory / "zoom-shift.json").write_text("{}", encoding="utf-8")
        (directory / "zoom-factor.txt").write_text("1", encoding="utf-8")
        proc = subprocess.Popen([str(exe)])
        result["pid"] = proc.pid
        identity = {}
        deadline = time.time() + 90
        while time.time() < deadline and not identity.get("hwnd"):
            identity = read_json(directory / "zoom-identity.json")
            if proc.poll() is not None:
                result["status"] = "BLOCKED"
                result["reason"] = f"exited {proc.returncode}"
                return result
            time.sleep(0.4)
        hwnd = int(identity.get("hwnd") or 0)
        result["hwnd"] = hwnd
        result["data_dir"] = identity.get("data_dir")
        opened = {}
        for name in CHECKS[profile]:
            seen = see(directory, name, 40)
            if name not in (seen.get("text") or ""):
                opened[name] = {"status": "NOT RUN", "reason": "product text was not on screen"}
                capture(hwnd, OUT / f"{profile}-missing.png")
                continue
            click(directory, name)
            dialog = see(directory, "Quantity", 8)
            if not dialog.get("dialog"):
                dialog = read_json(directory / "zoom-measured.json")
            opened[name] = brief(dialog)
            capture(hwnd, OUT / f"{profile}-{name.split()[0].lower()}.png", move=False)
            click(directory, "Cancel")
            time.sleep(0.4)
        result["opened"] = opened
        result["status"] = "RECORDED"
        return result
    except Exception as exc:
        result["status"] = "BLOCKED"
        result["reason"] = f"{type(exc).__name__}: {exc}"
        return result
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
        if server.poll() is None:
            server.terminate()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    seed = ensure_key()
    pin = f"{int.from_bytes(os.urandom(2), 'big') % 9000 + 1000}"
    previous = json.loads((OUT / "profiles.json").read_text(encoding="utf-8")) if (OUT / "profiles.json").exists() else []
    fresh = run("fashion", seed, pin)
    results = [row for row in previous if row.get("profile") != "fashion"]
    results.append(fresh)
    (OUT / "profiles.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("PROFILE_CLOSURE_DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
