"""Drive the disposable Cafe portion window. It does not open the restaurant database."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from quantity_modal_native import sha256
from zoom_acceptance_run import REPO, capture, click, read_json, wait_measured

DESKTOP = REPO / "apps" / "desktop"
TARGET = DESKTOP / "src-tauri" / "target" / "portion-cafe-build"
EXE = TARGET / "debug" / "ai-pos-desktop.exe"
DIRECTORY = Path(os.environ["APPDATA"]) / "com.axizpos.cafe.portion"
OUT = REPO / "docs" / "restaurant" / "evidence" / "cafe"
PORT = 18095
TEMP = Path(os.environ["TEMP"]) / "axiz-portion" / "cafe"


def signing_seed() -> str:
    folder = Path(os.environ["TEMP"]) / "axiz-portion"
    folder.mkdir(parents=True, exist_ok=True)
    seed_path = folder / "seed.b64"
    if not seed_path.exists():
        import base64

        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        raw = os.urandom(32)
        key = Ed25519PrivateKey.from_private_bytes(raw)
        public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        (folder / "public.b64").write_text(base64.b64encode(public).decode("ascii"), encoding="ascii")
        (folder / "key-id.txt").write_text("portion-accept-1", encoding="ascii")
        seed_path.write_text(base64.b64encode(raw).decode("ascii"), encoding="ascii")
    return seed_path.read_text(encoding="ascii").strip()


def build() -> Path:
    marker = TARGET / "portion-profile.txt"
    if EXE.exists() and marker.exists() and marker.read_text(encoding="utf-8").strip() == "cafe-quantity":
        return EXE
    env = os.environ.copy()
    env.update(
        {
            "POS_ENV": "acceptance",
            "ACCEPTANCE_PROFILE": "portion-cafe",
            "ACCEPTANCE_TENANT_URL_TEMPLATE": f"http://127.0.0.1:{PORT}",
            "ACCEPTANCE_TENANT_BASE_DOMAIN": "acceptance.invalid",
            "CARGO_TARGET_DIR": str(TARGET),
        }
    )
    pnpm = "pnpm.cmd" if os.name == "nt" else "pnpm"
    subprocess.check_call(
        [pnpm, "exec", "tauri", "build", "--debug", "--no-bundle", "--config", "src-tauri/tauri.portion.cafe.conf.json"],
        cwd=DESKTOP,
        env=env,
    )
    marker.write_text("cafe-quantity", encoding="utf-8")
    return EXE


def seed_products() -> None:
    import httpx

    login = httpx.post(
        f"http://127.0.0.1:{PORT}/api/v1/auth/login-password",
        json={"username": "portionowner", "password": "portion-owner-password"},
        timeout=20,
    )
    if login.status_code != 200:
        raise RuntimeError(f"cafe login {login.status_code}")
    auth = {"Authorization": f"Bearer {login.json()['access_token']}"}
    ready = json.loads((TEMP / "ready.json").read_text(encoding="utf-8"))

    def create(sku: str, name: str, price: int, barcode: str) -> str:
        response = httpx.post(
            f"http://127.0.0.1:{PORT}/api/v1/inventory/products",
            headers=auth,
            json={
                "sku": sku,
                "barcode": barcode,
                "name": name,
                "category_id": ready["category_id"],
                "price_cents": price,
                "opening_store_id": ready["store_id"],
                "opening_quantity": 20,
            },
            timeout=20,
        )
        if response.status_code not in (200, 201):
            raise RuntimeError(f"{name} {response.status_code} {response.text[:180]}")
        return response.json()["id"]

    create("CAFE-WATER", "Mineral Water", 200, "281000000011")
    daal = create("CAFE-DAAL", "Daal Channa", 300, "281000000012")
    options = httpx.put(
        f"http://127.0.0.1:{PORT}/api/v1/menu/products/{daal}/price-options",
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
        raise RuntimeError(f"portions {options.status_code} {options.text[:180]}")


def act(op: str, text: str = "") -> None:
    (DIRECTORY / "zoom-action.json").write_text(json.dumps({"op": op, "text": text}), encoding="utf-8")
    deadline = time.time() + 8
    while time.time() < deadline and (DIRECTORY / "zoom-action.json").exists():
        time.sleep(0.2)


def see(needle: str, timeout: float = 15) -> dict:
    return wait_measured(
        DIRECTORY,
        lambda row, needle=needle: needle in (row.get("dialog") or "") or needle in (row.get("text") or ""),
        timeout,
    )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    seed = signing_seed()
    env = os.environ.copy()
    env.update({"PORTION_PROFILE": "cafe", "PORTION_SIGNING_SEED": seed, "PORTION_KEY_ID": "portion-accept-1"})
    log_path = TEMP / "server.log"
    TEMP.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("w", encoding="utf-8")
    server = subprocess.Popen(
        ["node", "scripts/python.mjs", "scripts/portion_acceptance_server.py"],
        cwd=REPO,
        env=env,
        stdout=handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    proc = None
    result: dict = {"profile": "cafe"}
    try:
        deadline = time.time() + 90
        while time.time() < deadline:
            text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
            if "PORTION_READY cafe" in text:
                break
            if server.poll() is not None:
                raise RuntimeError(text[-400:])
            time.sleep(0.4)
        else:
            raise RuntimeError("cafe api did not become ready")
        seed_products()
        exe = build()
        ready = json.loads((TEMP / "ready.json").read_text(encoding="utf-8"))
        result["identity"] = {
            "executable": str(exe),
            "sha256": sha256(exe),
            "size": exe.stat().st_size,
            "identifier_expected": "com.axizpos.cafe.portion",
            "api": ready.get("api"),
            "database": ready.get("database"),
            "store_code": ready.get("store_code"),
            "business_profile": ready.get("business_profile"),
            "currency": ready.get("currency"),
        }
        if DIRECTORY.exists():
            subprocess.check_call(["powershell", "-NoProfile", "-Command", f"Remove-Item -LiteralPath '{DIRECTORY}' -Recurse -Force"])
        DIRECTORY.mkdir(parents=True)
        (DIRECTORY / "zoom-profile.txt").write_text("cafe", encoding="utf-8")
        (DIRECTORY / "zoom-activate.json").write_text(
            json.dumps({"subdomain": ready["store_code"], "activation_key": ready["activation_key"]}),
            encoding="utf-8",
        )
        (DIRECTORY / "zoom-unlock.json").write_text(
            json.dumps({"username": ready["cashier_username"], "pin": ready["cashier_pin"]}),
            encoding="utf-8",
        )
        (DIRECTORY / "zoom-shift.json").write_text("{}", encoding="utf-8")
        (DIRECTORY / "zoom-factor.txt").write_text("1", encoding="utf-8")
        proc = subprocess.Popen([str(exe)])
        result["identity"]["pid"] = proc.pid
        window = {}
        deadline = time.time() + 120
        while time.time() < deadline and not window.get("hwnd"):
            window = read_json(DIRECTORY / "zoom-identity.json")
            if proc.poll() is not None:
                raise RuntimeError(f"cafe exited {proc.returncode}")
            time.sleep(0.4)
        hwnd = int(window.get("hwnd") or 0)
        result["identity"].update({key: window.get(key) for key in ("hwnd", "identifier", "title", "data_dir")})
        if window.get("identifier") != "com.axizpos.cafe.portion":
            raise RuntimeError(f"unexpected identity {window.get('identifier')}")
        seen = see("Daal Channa", 90)
        capture(hwnd, OUT / "cafe-catalogue.png")
        result["catalogue"] = "Daal Channa" in (seen.get("text") or "") and "Mineral Water" in (seen.get("text") or "")
        click(DIRECTORY, "Daal Channa")
        opened = see("No portion selected")
        capture(hwnd, OUT / "cafe-portion-dialog.png", move=False)
        result["no_default"] = "No portion selected" in (opened.get("dialog") or "")
        click(DIRECTORY, "Small Plate")
        act("fill", "2")
        small = see("6.00")
        result["small_qty2"] = "6.00" in (small.get("dialog") or "")
        click(DIRECTORY, "Medium Plate")
        medium = see("10.00")
        result["medium_keeps_qty"] = "10.00" in (medium.get("dialog") or "")
        act("fill", "3")
        click(DIRECTORY, "Full Plate")
        full = see("27.00")
        result["full_qty3"] = "27.00" in (full.get("dialog") or "")
        capture(hwnd, OUT / "cafe-full-qty3.png", move=False)
        click(DIRECTORY, "Add 3")
        time.sleep(0.8)
        click(DIRECTORY, "Daal Channa")
        see("No portion selected")
        click(DIRECTORY, "Small Plate")
        click(DIRECTORY, "Add 1")
        time.sleep(0.6)
        click(DIRECTORY, "Review & charge")
        time.sleep(0.4)
        cart = read_json(DIRECTORY / "zoom-measured.json")
        capture(hwnd, OUT / "cafe-two-portions.png", move=False)
        result["cart"] = ((cart.get("layout") or {}).get("cart") or "")[:600]
        click(DIRECTORY, "Mineral Water")
        water = see("How many are you selling?")
        capture(hwnd, OUT / "cafe-water.png", move=False)
        result["water_no_portion"] = "Portion size" not in (water.get("dialog") or "") and "How many are you selling?" in (water.get("dialog") or "")
        click(DIRECTORY, "Decrease quantity")
        time.sleep(0.4)
        result["minus_stays_one"] = "Add 1" in (read_json(DIRECTORY / "zoom-measured.json").get("dialog") or "")
        act("double-add")
        time.sleep(0.8)
        click(DIRECTORY, "Review & charge")
        time.sleep(0.4)
        after = read_json(DIRECTORY / "zoom-measured.json")
        result["water_cart"] = ((after.get("layout") or {}).get("cart") or "")[:400]
        result["modifier"] = "NOT RUN"
        result["recipe"] = "NOT RUN"
        result["status"] = "RECORDED"
        print("CAFE_NATIVE_DONE")
        return 0
    except Exception as exc:
        result["status"] = "FAILED"
        result["error"] = f"{type(exc).__name__}: {exc}"
        print("CAFE_NATIVE_FAILED", type(exc).__name__)
        return 1
    finally:
        (OUT / "cafe.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        if proc is not None and proc.poll() is None:
            proc.terminate()
        if server.poll() is None:
            server.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
