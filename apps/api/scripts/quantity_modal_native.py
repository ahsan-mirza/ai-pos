"""Native acceptance for the quantity and portion dialog on the isolated restaurant zoom register.

Drives the window through its acceptance files. Does not send input to any other process.
Does not settle a sale. Does not open the installed register.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "apps" / "api" / "scripts"))
from zoom_acceptance_run import (  # noqa: E402
    APPDATA,
    EVIDENCE,
    TEMP,
    build,
    capture,
    click,
    ensure_key,
    read_json,
    start_server,
    wait_measured,
    wait_ready,
)

OUT = REPO / "docs" / "restaurant" / "quantity-modal-evidence"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def seed_named_dishes() -> None:
    import httpx

    ready = json.loads((TEMP / "restaurant" / "ready.json").read_text(encoding="utf-8"))
    login = httpx.post(
        "http://127.0.0.1:18093/api/v1/auth/login-password",
        json={"username": "zoomadmin", "password": "zoom-admin-password"},
        timeout=20,
    )
    if login.status_code != 200:
        raise SystemExit(f"Admin login failed ({login.status_code}).")
    auth = {"Authorization": f"Bearer {login.json()['access_token']}"}
    money = httpx.put(
        "http://127.0.0.1:18093/api/v1/settings/currency",
        headers=auth,
        json={"currency": "AED"},
        timeout=20,
    )
    if money.status_code != 200:
        raise SystemExit(f"Currency update failed ({money.status_code}).")
    category = httpx.post("http://127.0.0.1:18093/api/v1/categories", headers=auth, json={"name": "Acceptance Kitchen"}, timeout=20)
    if category.status_code not in (200, 201):
        raise SystemExit(f"Category failed ({category.status_code}) {category.text[:180]}")
    category_id = category.json()["id"]

    def create(sku: str, name: str, price: int) -> str:
        response = httpx.post(
            "http://127.0.0.1:18093/api/v1/inventory/products",
            headers=auth,
            json={
                "sku": sku,
                "barcode": "200000000001" if sku.endswith("WATER") else "200000000002",
                "name": name,
                "category_id": category_id,
                "price_cents": price,
                "opening_store_id": ready["store_id"],
                "opening_quantity": 20,
            },
            timeout=20,
        )
        if response.status_code not in (200, 201):
            raise SystemExit(f"{name} failed ({response.status_code}) {response.text[:240]}")
        return response.json()["id"]

    create("ACC-WATER", "Mineral Water", 200)
    daal = create("ACC-DAAL", "Daal Channa", 300)
    options = httpx.put(
        f"http://127.0.0.1:18093/api/v1/menu/products/{daal}/price-options",
        headers=auth,
        json={
            "options": [
                {"name": "Small Plate", "price_cents": 300, "is_active": True, "position": 0},
                {"name": "Medium Plate", "price_cents": 500, "is_active": True, "position": 1},
                {"name": "Full Plate", "price_cents": 900, "is_active": True, "position": 2},
            ]
        },
        timeout=20,
    )
    if options.status_code != 200:
        raise SystemExit(f"Daal portions failed ({options.status_code}) {options.text[:240]}")
    ready["named_dishes"] = True
    ready["currency"] = money.json().get("currency")
    (TEMP / "restaurant" / "ready.json").write_text(json.dumps(ready), encoding="utf-8")


def dialog_has(directory: Path, needle: str, timeout: float = 15) -> dict:
    return wait_measured(directory, lambda item, needle=needle: needle in item.get("dialog", "") or needle in item.get("text", ""), timeout)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pin = f"{int.from_bytes(os.urandom(2), 'big') % 9000 + 1000}"
    seed = ensure_key()
    server, log_path = start_server("restaurant", seed, pin)
    proc = None
    result: dict = {"profile": "restaurant", "touchscreen": "NOT RUN"}
    try:
        wait_ready(server, log_path, "restaurant")
        seed_named_dishes()
        exe = build("restaurant", 18093)
        result["executable"] = str(exe)
        result["sha256"] = sha256(exe)
        result["size"] = exe.stat().st_size
        directory = APPDATA / "com.axizpos.restaurant.zoom"
        if directory.exists():
            subprocess.check_call(["powershell", "-NoProfile", "-Command", f"Remove-Item -LiteralPath '{directory}' -Recurse -Force"])
        directory.mkdir(parents=True)
        ready = json.loads((TEMP / "restaurant" / "ready.json").read_text(encoding="utf-8"))
        (directory / "zoom-profile.txt").write_text("restaurant", encoding="utf-8")
        (directory / "zoom-activate.json").write_text(
            json.dumps({"subdomain": ready["store_code"], "activation_key": ready["activation_key"]}),
            encoding="utf-8",
        )
        (directory / "zoom-unlock.json").write_text(json.dumps({"username": ready["username"], "pin": ready["pin"]}), encoding="utf-8")
        (directory / "zoom-shift.json").write_text("{}", encoding="utf-8")
        (directory / "zoom-factor.txt").write_text("1", encoding="utf-8")
        proc = subprocess.Popen([str(exe)])
        identity = {}
        deadline = time.time() + 120
        while time.time() < deadline and not identity.get("hwnd"):
            identity = read_json(directory / "zoom-identity.json")
            if proc.poll() is not None:
                raise SystemExit(f"Register exited {proc.returncode} before the window opened.")
            time.sleep(0.4)
        hwnd = int(identity.get("hwnd") or 0)
        result["identity"] = {key: identity.get(key) for key in ("pid", "hwnd", "identifier", "title", "data_dir", "profile")}
        result["database"] = ready.get("database")
        result["api"] = ready.get("api")
        result["store_code"] = ready.get("store_code")
        seen = wait_measured(directory, lambda row: "Daal Channa" in row.get("text", "") and "Mineral Water" in row.get("text", ""), 90)
        result["catalogue"] = "Daal Channa" in seen.get("text", "") and "Mineral Water" in seen.get("text", "")
        if not result["catalogue"]:
            capture(hwnd, OUT / "catalogue-missing.png")
            result["status"] = "BLOCKED"
            result["screen"] = seen.get("text", "")[:800]
            return
        click(directory, "Daal Channa")
        opened = dialog_has(directory, "No portion selected")
        result["no_default_portion"] = "No portion selected" in opened.get("dialog", "")
        result["same_dialog"] = "Choose portion and quantity." in opened.get("dialog", "") and "Increase quantity" in opened.get("dialog", "")
        result["add_disabled_text"] = "Add to sale" in opened.get("dialog", "")
        capture(hwnd, OUT / "daal-unselected.png")
        click(directory, "Small Plate")
        click(directory, "Increase quantity")
        small = dialog_has(directory, "6.00")
        result["small_qty2"] = "Small Plate" in small.get("dialog", "") and "6.00" in small.get("dialog", "")
        capture(hwnd, OUT / "daal-small-qty2.png")
        click(directory, "Medium Plate")
        medium = dialog_has(directory, "10.00")
        result["medium_keeps_qty"] = "Medium Plate" in medium.get("dialog", "") and "10.00" in medium.get("dialog", "")
        click(directory, "Increase quantity")
        medium3 = dialog_has(directory, "15.00")
        result["medium_qty3"] = "15.00" in medium3.get("dialog", "")
        click(directory, "Full Plate")
        full = dialog_has(directory, "27.00")
        result["full_qty3"] = "Full Plate" in full.get("dialog", "") and "27.00" in full.get("dialog", "")
        capture(hwnd, OUT / "daal-full-qty3.png")
        click(directory, "Add 3")
        added = dialog_has(directory, "Daal Channa")
        result["one_line"] = "Full Plate" in added.get("text", "") and added.get("dialog", "") == ""
        capture(hwnd, OUT / "cart-full-plate.png")
        click(directory, "Daal Channa")
        dialog_has(directory, "No portion selected")
        click(directory, "Small Plate")
        click(directory, "Increase quantity")
        click(directory, "Cancel")
        cancelled = dialog_has(directory, "Mineral Water")
        result["cancel_keeps_cart"] = "Full Plate" in cancelled.get("text", "") and "Choose portion" not in cancelled.get("dialog", "")
        click(directory, "Mineral Water")
        water = dialog_has(directory, "How many are you selling?")
        result["water_no_portion"] = "How many are you selling?" in water.get("dialog", "") and "Portion size" not in water.get("dialog", "")
        click(directory, "Increase quantity")
        click(directory, "Increase quantity")
        water3 = dialog_has(directory, "6.00")
        result["water_qty3"] = "6.00" in water3.get("dialog", "") and "Portion size" not in water3.get("dialog", "")
        capture(hwnd, OUT / "water-qty3.png")
        click(directory, "Add 3")
        both = dialog_has(directory, "Mineral Water")
        result["two_lines"] = "Mineral Water" in both.get("text", "") and "Full Plate" in both.get("text", "")
        capture(hwnd, OUT / "cart-two-lines.png")
        click(directory, "Grilled Chicken")
        chicken = dialog_has(directory, "Extra cheese")
        result["modifier_dialog"] = "Extra cheese" in chicken.get("dialog", "") and "Increase quantity" in chicken.get("dialog", "")
        result["modifier_has_portions"] = "Breakfast" in chicken.get("dialog", "")
        capture(hwnd, OUT / "chicken-modifiers.png")
        click(directory, "Cancel")
        zooms = {}
        click(directory, "Daal Channa")
        dialog_has(directory, "Portion size")
        for label, factor in (("100", "1"), ("125", "1.25"), ("150", "1.5"), ("200", "2")):
            (directory / "zoom-factor.txt").write_text(factor, encoding="utf-8")
            row = wait_measured(directory, lambda item, label=label: str(item.get("requested_percent")) == label and "Portion size" in item.get("dialog", ""), 20)
            shot = OUT / f"zoom-{label}.png"
            capture(hwnd, shot)
            zooms[label] = {
                "requested_percent": row.get("requested_percent"),
                "dpr": row.get("dpr"),
                "scale": row.get("scale"),
                "font": row.get("font"),
                "overflow": (row.get("scrollWidth") or 0) > (row.get("clientWidth") or 0) + 8,
                "dialog_open": "Portion size" in row.get("dialog", ""),
                "screenshot": str(shot.relative_to(REPO)),
            }
        result["zoom"] = zooms
        result["status"] = "RECORDED"
    finally:
        (OUT / "restaurant.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        if proc is not None and proc.poll() is None:
            proc.terminate()
        if server.poll() is None:
            server.terminate()
        print("QUANTITY_NATIVE_DONE", result.get("status"), flush=True)


if __name__ == "__main__":
    main()
