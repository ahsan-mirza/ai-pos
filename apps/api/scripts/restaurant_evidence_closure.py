"""Photograph the dine-in order line and the reopened chicken edit.

The previous restaurant process is not reused. This starts a new disposable
restaurant window, recreates the same unpaid lines, and captures them inside
the window. It does not settle a sale.
"""

from __future__ import annotations

import json
import os
import subprocess
import time

from quantity_modal_closure import DIRECTORY, OUT, seed_floor
from quantity_modal_native import TEMP, seed_named_dishes, sha256
from zoom_acceptance_run import (
    build,
    capture,
    click,
    ensure_key,
    read_json,
    start_server,
    wait_measured,
    wait_ready,
)


def act(op: str, text: str = "") -> None:
    (DIRECTORY / "zoom-action.json").write_text(json.dumps({"op": op, "text": text}), encoding="utf-8")
    deadline = time.time() + 8
    while time.time() < deadline and (DIRECTORY / "zoom-action.json").exists():
        time.sleep(0.2)


def see(needle: str, timeout: float = 12) -> dict:
    return wait_measured(
        DIRECTORY,
        lambda row, needle=needle: needle in (row.get("dialog") or "") or needle in (row.get("text") or ""),
        timeout,
    )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    from zoom_acceptance_run import REPO

    built = REPO / "apps" / "desktop" / "src-tauri" / "target" / "zoom-shared" / "zoom-profile.txt"
    if built.exists():
        built.unlink()
    pin = f"{int.from_bytes(os.urandom(2), 'big') % 9000 + 1000}"
    seed = ensure_key()
    server, log_path = start_server("restaurant", seed, pin)
    proc = None
    result: dict = {"previous_pid_reused": False}
    try:
        wait_ready(server, log_path, "restaurant")
        seed_named_dishes()
        seed_floor(result)
        exe = build("restaurant", 18093)
        result["identity"] = {
            "executable": str(exe),
            "sha256": sha256(exe),
            "size": exe.stat().st_size,
            "api": "http://127.0.0.1:18093",
        }
        if DIRECTORY.exists():
            subprocess.check_call(["powershell", "-NoProfile", "-Command", f"Remove-Item -LiteralPath '{DIRECTORY}' -Recurse -Force"])
        DIRECTORY.mkdir(parents=True)
        ready = json.loads((TEMP / "restaurant" / "ready.json").read_text(encoding="utf-8"))
        result["identity"]["database"] = ready.get("database")
        result["identity"]["store_code"] = ready.get("store_code")
        (DIRECTORY / "zoom-profile.txt").write_text("restaurant", encoding="utf-8")
        (DIRECTORY / "zoom-activate.json").write_text(
            json.dumps({"subdomain": ready["store_code"], "activation_key": ready["activation_key"]}),
            encoding="utf-8",
        )
        (DIRECTORY / "zoom-unlock.json").write_text(json.dumps({"username": ready["username"], "pin": ready["pin"]}), encoding="utf-8")
        (DIRECTORY / "zoom-shift.json").write_text("{}", encoding="utf-8")
        (DIRECTORY / "zoom-factor.txt").write_text("1", encoding="utf-8")
        proc = subprocess.Popen([str(exe)])
        result["identity"]["pid"] = proc.pid
        window = {}
        deadline = time.time() + 120
        while time.time() < deadline and not window.get("hwnd"):
            window = read_json(DIRECTORY / "zoom-identity.json")
            if proc.poll() is not None:
                raise RuntimeError(f"register exited {proc.returncode}")
            time.sleep(0.4)
        hwnd = int(window.get("hwnd") or 0)
        result["identity"].update({key: window.get(key) for key in ("hwnd", "identifier", "title", "data_dir")})
        seen = see("Daal Channa", 90)
        if "Daal Channa" not in (seen.get("text") or ""):
            result["status"] = "BLOCKED"
            return 2
        # Narrower than the lg breakpoint so the open order sheet covers the window.
        capture(hwnd, OUT / "restaurant-window.png", width=1000, height=1200)
        time.sleep(0.6)
        click(DIRECTORY, "Orders & Tables")
        see("Z1", 15)
        click(DIRECTORY, "Z1")
        see("Seat", 8)
        click(DIRECTORY, "Seat 2")
        see("seated", 12)
        click(DIRECTORY, "Add More Items")
        time.sleep(0.4)
        click(DIRECTORY, "Daal Channa")
        see("Portion size")
        click(DIRECTORY, "Medium Plate")
        act("fill", "2")
        see("10.00")
        click(DIRECTORY, "Add 2")
        time.sleep(0.4)
        click(DIRECTORY, "Add to this order")
        added = see("Medium Plate", 12)
        capture(hwnd, OUT / "restaurant-z1-medium-plate-order-line.png", move=False)
        result["z1"] = {
            "medium_in_page": "Medium Plate" in (added.get("text") or ""),
            "amount_in_page": "10.00" in (added.get("text") or ""),
            "excerpt": (added.get("text") or "")[:1500],
        }
        result["saved_orders_after_dine_in"] = "pending"

        click(DIRECTORY, "Checkout")
        time.sleep(0.8)
        click(DIRECTORY, "Grilled Chicken")
        see("Breakfast")
        click(DIRECTORY, "Breakfast")
        click(DIRECTORY, "Extra cheese")
        act("fill", "2")
        see("19.00", 8)
        click(DIRECTORY, "Add to order")
        time.sleep(0.8)
        click(DIRECTORY, "Review & charge")
        time.sleep(0.5)
        click(DIRECTORY, "cart:Grilled Chicken")
        restored = see("Breakfast", 8)
        capture(hwnd, OUT / "restaurant-grilled-chicken-edit-restored.png", move=False)
        act("scroll-dialog")
        time.sleep(0.5)
        quantity_view = read_json(DIRECTORY / "zoom-measured.json")
        capture(hwnd, OUT / "restaurant-grilled-chicken-edit-quantity.png", move=False)
        result["chicken_edit"] = {
            "breakfast": "Breakfast" in (restored.get("dialog") or ""),
            "cheese": "Extra cheese" in (restored.get("dialog") or ""),
            "total": "19.00" in (restored.get("dialog") or ""),
            "dialog": (restored.get("dialog") or "")[:800],
            "quantity_view": "19.00" in (quantity_view.get("dialog") or ""),
        }
        click(DIRECTORY, "Cancel")
        time.sleep(0.5)
        after = read_json(DIRECTORY / "zoom-measured.json")
        result["chicken_after_cancel"] = ((after.get("layout") or {}).get("cart") or "")[:500]
        from quantity_modal_closure import saved_orders

        result["saved_orders"] = saved_orders()
        result["status"] = "RECORDED"
        print("RESTAURANT_EVIDENCE_DONE")
        return 0
    except Exception as exc:
        result["status"] = "FAILED"
        result["error"] = f"{type(exc).__name__}: {exc}"
        print("RESTAURANT_EVIDENCE_FAILED", type(exc).__name__)
        return 1
    finally:
        (OUT / "evidence-closure.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        if proc is not None and proc.poll() is None:
            proc.terminate()
        if server.poll() is None:
            server.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
