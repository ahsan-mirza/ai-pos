"""Close the remaining quantity-modal checks on the disposable restaurant window.

Drives that window through its acceptance files. Does not send input to any other
process, does not settle a sale, and does not open the installed register.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from quantity_modal_native import OUT, TEMP, seed_named_dishes, sha256
from zoom_acceptance_run import (
    APPDATA,
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

DIRECTORY = APPDATA / "com.axizpos.restaurant.zoom"
PRESET = [
    "loyalty",
    "promotions",
    "multi_currency",
    "tables",
    "open_orders",
    "menu_modifiers",
    "kds",
    "recipes",
    "split_bills",
    "tips_service_charge",
    "delivery_channels",
]


def act(op: str, text: str = "") -> None:
    (DIRECTORY / "zoom-action.json").write_text(json.dumps({"op": op, "text": text}), encoding="utf-8")
    deadline = time.time() + 8
    while time.time() < deadline and (DIRECTORY / "zoom-action.json").exists():
        time.sleep(0.2)


def see(needle: str, timeout: float = 12) -> dict:
    return wait_measured(
        DIRECTORY,
        lambda row, needle=needle: needle in (row.get("dialog") or "")
        or needle in (row.get("text") or "")
        or needle in str((row.get("layout") or {}).get("cart") or ""),
        timeout,
    )


def brief(row: dict) -> dict:
    dialog = row.get("dialog") or ""
    kept = []
    for line in dialog.splitlines():
        text = " ".join(line.split())
        if text and any(
            word in text
            for word in (
                "Add",
                "Update",
                "Total",
                "Quantity",
                "Portion",
                "AED",
                "Enter a",
                "Extra",
                "Breakfast",
                "Lunch",
                "Dinner",
                "Small",
                "Medium",
                "Full",
                "How many",
                "No portion",
                "cheese",
            )
        ):
            kept.append(text)
    layout = row.get("layout") or {}
    return {
        "lines": kept[:40],
        "cart": layout.get("cart") or "",
        "addInside": layout.get("addInside"),
        "cancelInside": layout.get("cancelInside"),
        "minusInside": layout.get("minusInside"),
        "plusInside": layout.get("plusInside"),
        "quantityInside": layout.get("quantityInside"),
        "portionsInside": layout.get("portionsInside"),
        "portionCount": layout.get("portionCount"),
        "dialogScrolls": layout.get("dialogScrolls"),
        "bodyScrolls": layout.get("bodyScrolls"),
        "innerWidth": layout.get("innerWidth"),
        "innerHeight": layout.get("innerHeight"),
        "dpr": row.get("dpr"),
        "scale": row.get("scale"),
        "font": row.get("font"),
        "requested_percent": row.get("requested_percent"),
        "overflow": (row.get("scrollWidth") or 0) > (row.get("clientWidth") or 0) + 1,
    }


def shot(hwnd: int, name: str, row: dict) -> dict:
    capture(hwnd, OUT / name, move=False)
    summary = brief(row)
    summary["screenshot"] = str((OUT / name).relative_to(REPO))
    return summary


def open_cart() -> dict:
    click(DIRECTORY, "Review & charge")
    return see("Plate", 8)


def login() -> tuple[dict, dict]:
    import httpx

    ready = json.loads((TEMP / "restaurant" / "ready.json").read_text(encoding="utf-8"))
    response = httpx.post(
        "http://127.0.0.1:18093/api/v1/auth/login-password",
        json={"username": "zoomadmin", "password": "zoom-admin-password"},
        timeout=20,
    )
    if response.status_code != 200:
        raise RuntimeError(f"admin login {response.status_code}")
    return ready, {"Authorization": f"Bearer {response.json()['access_token']}"}


def seed_floor(steps: dict) -> None:
    import httpx

    ready, auth = login()
    current = httpx.get("http://127.0.0.1:18093/api/v1/settings", headers=auth, timeout=20)
    enabled = []
    if current.status_code == 200:
        enabled = list(current.json().get("capabilities") or [])
    if "delivery_channels" not in enabled:
        updated = httpx.put(
            "http://127.0.0.1:18093/api/v1/settings/profile",
            headers=auth,
            json={"business_profile": "restaurant", "capabilities": PRESET},
            timeout=20,
        )
        steps["delivery_capability"] = updated.status_code
    else:
        steps["delivery_capability"] = 200
    area = httpx.post(
        "http://127.0.0.1:18093/api/v1/dining/areas",
        headers=auth,
        json={"store_id": ready["store_id"], "name": "Acceptance Floor", "position": 0},
        timeout=20,
    )
    if area.status_code not in (200, 201):
        steps["floor"] = area.status_code
        return
    area_id = area.json()["areas"][0]["id"]
    table = httpx.post(
        "http://127.0.0.1:18093/api/v1/dining/tables",
        headers=auth,
        json={"area_id": area_id, "label": "Z1", "seats": 4},
        timeout=20,
    )
    steps["floor"] = table.status_code
    if steps["delivery_capability"] == 200:
        channel = httpx.post(
            "http://127.0.0.1:18093/api/v1/channels",
            headers=auth,
            json={"name": "Accept Drop", "code": "accept-drop", "store_id": ready["store_id"]},
            timeout=20,
        )
        steps["channel"] = channel.status_code


def saved_orders() -> list[dict]:
    import httpx

    ready, auth = login()
    response = httpx.get(
        "http://127.0.0.1:18093/api/v1/orders",
        headers=auth,
        params={"store_id": ready["store_id"], "status": "OPEN"},
        timeout=20,
    )
    if response.status_code != 200:
        return [{"status": response.status_code}]
    compact = []
    for order in response.json():
        compact.append(
            {
                "service_type": order.get("service_type"),
                "table_label": order.get("table_label"),
                "status": order.get("status"),
                "items": [
                    {
                        "name": item.get("product_name"),
                        "quantity": item.get("quantity"),
                        "unit_price_cents": item.get("unit_price_cents"),
                        "price_option_id": item.get("price_option_id"),
                        "price_option_name": item.get("price_option_name"),
                        "paid_sale_id": item.get("paid_sale_id"),
                    }
                    for item in order.get("items") or []
                ],
            }
        )
    return compact


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    marker = REPO / "apps" / "desktop" / "src-tauri" / "target" / "zoom-shared" / "zoom-profile.txt"
    if marker.exists():
        marker.unlink()
    pin = f"{int.from_bytes(os.urandom(2), 'big') % 9000 + 1000}"
    seed = ensure_key()
    server, log_path = start_server("restaurant", seed, pin)
    proc = None
    steps: dict = {}
    identity: dict = {}
    try:
        wait_ready(server, log_path, "restaurant")
        seed_named_dishes()
        seed_floor(steps)
        exe = build("restaurant", 18093)
        identity = {
            "executable": str(exe),
            "sha256": sha256(exe),
            "size": exe.stat().st_size,
            "api": "http://127.0.0.1:18093",
        }
        if DIRECTORY.exists():
            subprocess.check_call(["powershell", "-NoProfile", "-Command", f"Remove-Item -LiteralPath '{DIRECTORY}' -Recurse -Force"])
        DIRECTORY.mkdir(parents=True)
        ready = json.loads((TEMP / "restaurant" / "ready.json").read_text(encoding="utf-8"))
        identity["database"] = ready.get("database")
        identity["store_code"] = ready.get("store_code")
        (DIRECTORY / "zoom-profile.txt").write_text("restaurant", encoding="utf-8")
        (DIRECTORY / "zoom-activate.json").write_text(
            json.dumps({"subdomain": ready["store_code"], "activation_key": ready["activation_key"]}),
            encoding="utf-8",
        )
        (DIRECTORY / "zoom-unlock.json").write_text(json.dumps({"username": ready["username"], "pin": ready["pin"]}), encoding="utf-8")
        (DIRECTORY / "zoom-shift.json").write_text("{}", encoding="utf-8")
        (DIRECTORY / "zoom-factor.txt").write_text("1", encoding="utf-8")
        proc = subprocess.Popen([str(exe)])
        identity["pid"] = proc.pid
        window = {}
        deadline = time.time() + 120
        while time.time() < deadline and not window.get("hwnd"):
            window = read_json(DIRECTORY / "zoom-identity.json")
            if proc.poll() is not None:
                raise RuntimeError(f"register exited {proc.returncode}")
            time.sleep(0.4)
        hwnd = int(window.get("hwnd") or 0)
        identity.update({key: window.get(key) for key in ("hwnd", "identifier", "title", "data_dir")})
        capture(hwnd, OUT / "window-placed.png")
        time.sleep(0.8)
        seen = see("Daal Channa", 90)
        steps["catalogue"] = "Mineral Water" in seen.get("text", "")
        if not steps["catalogue"]:
            shot(hwnd, "catalogue-missing.png", seen)
            return 2

        click(DIRECTORY, "Daal Channa")
        opened = see("No portion selected")
        steps["unselected"] = shot(hwnd, "daal-unselected.png", opened)
        click(DIRECTORY, "Small Plate")
        act("fill", "2")
        small = see("6.00")
        steps["small_qty2"] = shot(hwnd, "daal-small-qty2.png", small)
        click(DIRECTORY, "Add 2")
        added = see("Full Plate", 4)
        if "Full Plate" not in (added.get("text") or ""):
            added = see("Daal Channa", 8)
        cart = open_cart()
        steps["cart_small"] = shot(hwnd, "cart-small.png", cart)

        click(DIRECTORY, "Daal Channa")
        see("No portion selected")
        click(DIRECTORY, "Full Plate")
        act("fill", "3")
        full = see("27.00")
        steps["full_qty3"] = shot(hwnd, "daal-full-qty3.png", full)
        click(DIRECTORY, "Add 3")
        see("Daal Channa")
        cart = open_cart()
        steps["cart_two"] = shot(hwnd, "cart-two-lines.png", cart)

        click(DIRECTORY, "cart:0:Daal Channa")
        edited = see("Small Plate", 8)
        steps["edit_small"] = shot(hwnd, "edit-small.png", edited)
        act("fill", "4")
        updated = see("12.00")
        steps["edit_small_qty4"] = brief(updated)
        click(DIRECTORY, "Update 4")
        see("Daal Channa")
        cart = open_cart()
        steps["cart_edited"] = shot(hwnd, "cart-edited.png", cart)

        click(DIRECTORY, "cart:1:Daal Channa")
        second = see("Full Plate", 8)
        steps["edit_full"] = shot(hwnd, "edit-full.png", second)
        click(DIRECTORY, "Cancel")
        see("Daal Channa")
        cart = open_cart()
        steps["cart_cancel_edit"] = shot(hwnd, "cart-cancel-edit.png", cart)

        click(DIRECTORY, "Mineral Water")
        see("How many are you selling?")
        act("double-add")
        time.sleep(1)
        cart = open_cart()
        steps["duplicate_add"] = shot(hwnd, "duplicate-add.png", cart)
        click(DIRECTORY, "Mineral Water")
        see("How many are you selling?")
        click(DIRECTORY, "Add 1")
        time.sleep(0.8)
        cart = open_cart()
        steps["second_water"] = shot(hwnd, "second-water.png", cart)

        click(DIRECTORY, "Mineral Water")
        see("How many are you selling?")
        typed = {}
        for value in ("", "0", "-1", "abc", "1.5", "1", "2", "9999", "10000"):
            act("fill", value)
            time.sleep(0.7)
            row = read_json(DIRECTORY / "zoom-measured.json")
            typed[value or "empty"] = brief(row).get("lines")
        steps["typed"] = typed
        click(DIRECTORY, "Cancel")
        click(DIRECTORY, "Mineral Water")
        see("How many are you selling?")
        click(DIRECTORY, "Decrease quantity")
        time.sleep(0.5)
        steps["minus_at_one"] = brief(read_json(DIRECTORY / "zoom-measured.json")).get("lines")
        click(DIRECTORY, "Increase quantity")
        plus = see("4.00")
        steps["plus_from_one"] = brief(plus).get("lines")
        click(DIRECTORY, "Cancel")

        click(DIRECTORY, "Grilled Chicken")
        see("Breakfast")
        act("scroll-dialog")
        time.sleep(0.6)
        chicken = read_json(DIRECTORY / "zoom-measured.json")
        steps["chicken_scrolled"] = shot(hwnd, "chicken-scrolled.png", chicken)
        click(DIRECTORY, "Breakfast")
        click(DIRECTORY, "Extra cheese")
        act("fill", "2")
        ready_line = see("Extra cheese", 8)
        steps["chicken_ready"] = shot(hwnd, "chicken-ready.png", ready_line)
        click(DIRECTORY, "Add to order")
        time.sleep(0.8)
        cart = open_cart()
        steps["chicken_cart"] = shot(hwnd, "chicken-cart.png", cart)

        click(DIRECTORY, "Daal Channa")
        see("Portion size")
        click(DIRECTORY, "Medium Plate")
        zooms = {}
        for label, factor in (("100", "1"), ("125", "1.25"), ("150", "1.5"), ("200", "2")):
            (DIRECTORY / "zoom-factor.txt").write_text(factor, encoding="utf-8")
            row = wait_measured(DIRECTORY, lambda item, label=label: str(item.get("requested_percent")) == label and "Portion size" in (item.get("dialog") or ""), 15)
            time.sleep(0.4)
            row = read_json(DIRECTORY / "zoom-measured.json")
            zooms[label] = shot(hwnd, f"zoom-{label}.png", row)
            act("scroll-dialog")
            time.sleep(0.6)
            scrolled = read_json(DIRECTORY / "zoom-measured.json")
            zooms[f"{label}-footer"] = shot(hwnd, f"zoom-{label}-footer.png", scrolled)
        steps["zoom"] = zooms
        click(DIRECTORY, "Cancel")
        (DIRECTORY / "zoom-factor.txt").write_text("1", encoding="utf-8")
        wait_measured(DIRECTORY, lambda item: item.get("requested_percent") == 100, 12)

        click(DIRECTORY, "Orders & Tables")
        floor = see("Z1", 15)
        steps["orders_floor"] = shot(hwnd, "orders-floor.png", floor)
        click(DIRECTORY, "Z1")
        seated = see("Seat", 8)
        steps["seat_dialog"] = brief(seated)
        click(DIRECTORY, "Seat 2")
        opened_table = see("seated", 12)
        steps["table_open"] = brief(opened_table)
        click(DIRECTORY, "Add More Items")
        time.sleep(0.4)
        click(DIRECTORY, "Daal Channa")
        see("Portion size")
        click(DIRECTORY, "Medium Plate")
        act("fill", "2")
        see("10.00")
        click(DIRECTORY, "Add 2")
        time.sleep(0.5)
        click(DIRECTORY, "Add to this order")
        saved = see("line added", 12)
        steps["dine_in_added"] = shot(hwnd, "dine-in-added.png", saved)
        click(DIRECTORY, "Close order")
        time.sleep(0.6)
        click(DIRECTORY, "Z1")
        reopened = see("Daal Channa", 12)
        steps["dine_in_reopen"] = shot(hwnd, "dine-in-reopen.png", reopened)

        click(DIRECTORY, "Takeaway tab")
        tab = see("New tab opened", 12)
        steps["takeaway_open"] = brief(tab)
        click(DIRECTORY, "Add More Items")
        time.sleep(0.4)
        click(DIRECTORY, "Daal Channa")
        see("Portion size")
        click(DIRECTORY, "Full Plate")
        act("fill", "3")
        see("27.00")
        click(DIRECTORY, "Add 3")
        time.sleep(0.4)
        click(DIRECTORY, "Add to this order")
        takeaway = see("line added", 12)
        steps["takeaway_added"] = shot(hwnd, "takeaway-added.png", takeaway)
        click(DIRECTORY, "Close order")
        time.sleep(0.5)
        click(DIRECTORY, "Takeaway ·")
        reopened_tab = see("Daal Channa", 12)
        steps["takeaway_reopen"] = shot(hwnd, "takeaway-reopen.png", reopened_tab)

        if steps.get("channel") == 201:
            click(DIRECTORY, "Delivery order")
            delivery = see("Delivery-app order", 8)
            steps["delivery_dialog"] = brief(delivery)
            click(DIRECTORY, "Accept Drop")
            act("fill-field", "App order number|ACC-9")
            time.sleep(0.4)
            click(DIRECTORY, "Open order")
            opened_delivery = see("Delivery order opened", 12)
            steps["delivery_open"] = brief(opened_delivery)
            click(DIRECTORY, "Add More Items")
            time.sleep(0.4)
            click(DIRECTORY, "Daal Channa")
            see("Portion size")
            click(DIRECTORY, "Small Plate")
            act("fill", "2")
            see("6.00")
            click(DIRECTORY, "Add 2")
            time.sleep(0.4)
            click(DIRECTORY, "Add to this order")
            delivered = see("line added", 12)
            steps["delivery_added"] = shot(hwnd, "delivery-added.png", delivered)
        steps["saved_orders"] = saved_orders()
        print("QUANTITY_CLOSURE_DONE")
        return 0
    except Exception as exc:
        steps["error"] = f"{type(exc).__name__}: {exc}"
        print("QUANTITY_CLOSURE_FAILED", type(exc).__name__)
        return 1
    finally:
        (OUT / "closure.json").write_text(json.dumps({"identity": identity, "steps": steps}, indent=2), encoding="utf-8")
        if proc is not None and proc.poll() is None:
            proc.terminate()
        if server.poll() is None:
            server.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
