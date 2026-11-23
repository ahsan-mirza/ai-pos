"""Drive the already-open disposable laundry acceptance window. Does not print secrets."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from zoom_acceptance_run import REPO, capture, click, read_json, wait_measured

DIRECTORY = Path(os.environ["APPDATA"]) / "com.axizpos.laundry.acceptance"
OUT = REPO / "docs" / "restaurant" / "evidence" / "laundry"
EXE = REPO / "apps" / "desktop" / "src-tauri" / "target" / "laundry-evidence" / "debug" / "ai-pos-desktop.exe"


def env_value(name: str) -> str:
    for line in Path(r"D:\Work\ai-pos\.env.laundry-acceptance").read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError(f"missing {name}")


def see(needle: str, timeout: float = 15) -> dict:
    return wait_measured(
        DIRECTORY,
        lambda row, needle=needle: needle in (row.get("text") or "") or needle in (row.get("dialog") or ""),
        timeout,
    )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    identity = read_json(DIRECTORY / "zoom-identity.json")
    hwnd = int(identity.get("hwnd") or 0)
    if identity.get("identifier") != "com.axizpos.laundry.acceptance" or not hwnd:
        print("LAUNDRY_NATIVE_BLOCKED")
        return 2
    import hashlib

    digest = hashlib.sha256(EXE.read_bytes()).hexdigest()
    result = {
        "identifier": identity.get("identifier"),
        "title": identity.get("title"),
        "pid": identity.get("pid"),
        "hwnd": hwnd,
        "data_dir": identity.get("data_dir"),
        "executable": str(EXE),
        "sha256": digest,
        "api": "http://127.0.0.1:18082",
        "database": "acceptance/laundry/pgdata on 127.0.0.1:55821",
    }
    click(DIRECTORY, "Laundry Admin")
    time.sleep(0.4)
    for digit in env_value("ADMIN_PIN"):
        click(DIRECTORY, digit)
        time.sleep(0.15)
    click(DIRECTORY, "Unlock")
    unlocked = see("New Order", 20)
    result["unlocked"] = "New Order" in (unlocked.get("text") or "")
    if not result["unlocked"]:
        result["screen"] = (unlocked.get("text") or "")[:400]
        result["status"] = "BLOCKED"
        (OUT / "laundry.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print("LAUNDRY_NATIVE_BLOCKED")
        return 2
    click(DIRECTORY, "New Order")
    form = see("Quantity", 12)
    capture(hwnd, OUT / "laundry-order-entry.png", width=1200, height=900)
    result["portion_absent"] = "Portion size" not in (form.get("text") or "")
    (DIRECTORY / "zoom-action.json").write_text(json.dumps({"op": "fill-label", "text": "Quantity|2"}), encoding="utf-8")
    time.sleep(0.8)
    capture(hwnd, OUT / "laundry-quantity-2.png", move=False)
    (DIRECTORY / "zoom-action.json").write_text(json.dumps({"op": "fill-label", "text": "Quantity|0"}), encoding="utf-8")
    time.sleep(0.6)
    click(DIRECTORY, "Create Laundry Order")
    rejected = see("Quantity must be a whole number", 8)
    capture(hwnd, OUT / "laundry-quantity-rejected.png", move=False)
    result["rejected"] = "Quantity must be a whole number" in (rejected.get("text") or "")
    result["screen"] = (rejected.get("text") or "")[:800]
    result["status"] = "RECORDED"
    (OUT / "laundry.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("LAUNDRY_NATIVE_DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
