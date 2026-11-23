"""Drive the isolated order-tag acceptance register. It does not open another register's database."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import time
from pathlib import Path

from quantity_modal_native import sha256
from zoom_acceptance_run import REPO, capture, click, read_json, wait_measured

DESKTOP = REPO / "apps" / "desktop"
TARGET = Path(r"D:\Work\ai-pos\acceptance\ordertags\target")
EXE = TARGET / "debug" / "ai-pos-desktop.exe"
IDENTIFIER = "com.axizpos.ordertags.acceptance"
DIRECTORY = Path(os.environ["APPDATA"]) / IDENTIFIER
OUT = REPO / "docs" / "orders" / "evidence"
PORT = 18096
TEMP = Path(os.environ["TEMP"]) / "axiz-ordertags"
QUEUE = "OneNote (Desktop) - Protected"


def signing_seed() -> str:
    TEMP.mkdir(parents=True, exist_ok=True)
    seed_path = TEMP / "seed.b64"
    if not seed_path.exists():
        import base64

        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        raw = os.urandom(32)
        key = Ed25519PrivateKey.from_private_bytes(raw)
        public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        (TEMP / "public.b64").write_text(base64.b64encode(public).decode("ascii"), encoding="ascii")
        (TEMP / "key-id.txt").write_text("ordertags-accept-1", encoding="ascii")
        seed_path.write_text(base64.b64encode(raw).decode("ascii"), encoding="ascii")
    return seed_path.read_text(encoding="ascii").strip()


def build() -> Path:
    if os.environ.get("ORDERTAGS_SKIP_BUILD") == "1" and EXE.exists():
        return EXE
    env = os.environ.copy()
    env.update(
        {
            "POS_ENV": "acceptance",
            "ACCEPTANCE_PROFILE": "ordertags",
            "ACCEPTANCE_TENANT_URL_TEMPLATE": f"http://127.0.0.1:{PORT}",
            "ACCEPTANCE_TENANT_BASE_DOMAIN": "acceptance.invalid",
            "CARGO_TARGET_DIR": str(TARGET),
        }
    )
    pnpm = "pnpm.cmd" if os.name == "nt" else "pnpm"
    subprocess.check_call(
        [pnpm, "exec", "tauri", "build", "--debug", "--no-bundle", "--no-sign", "--config", "src-tauri/tauri.ordertags.conf.json"],
        cwd=DESKTOP,
        env=env,
    )
    return EXE


def act(op: str, text: str = "") -> None:
    (DIRECTORY / "zoom-action.json").write_text(json.dumps({"op": op, "text": text}), encoding="utf-8")
    deadline = time.time() + 8
    while time.time() < deadline and (DIRECTORY / "zoom-action.json").exists():
        time.sleep(0.2)


def see(predicate, timeout: float = 25) -> dict:
    return wait_measured(DIRECTORY, predicate, timeout)


def field_value(row: dict, name: str) -> str:
    for part in str(row.get("fields") or "").split(" | "):
        if part.startswith(name + "="):
            return part.split("=", 1)[1]
    return ""


def tag_of(row: dict) -> str:
    raw = field_value(row, "Order tag")
    return raw.removesuffix(":ro").removesuffix(":off")


def register_db() -> Path | None:
    root = DIRECTORY / "tenants"
    if not root.exists():
        return None
    matches = list(root.glob("*/ai-pos.db"))
    return matches[0] if matches else None


def read_register() -> dict:
    path = register_db()
    if path is None:
        return {}
    conn = sqlite3.connect(path)
    try:
        tags = conn.execute("SELECT session_id, tag FROM order_tags ORDER BY tag").fetchall()
        sessions = conn.execute(
            "SELECT id, order_mode, table_number, guest_name, phone, status FROM table_sessions ORDER BY updated_at"
        ).fetchall()
        printer = conn.execute(
            "SELECT transport, address, paper_dots, copies, drawer_kick, auto_discover, user_selected, previous_address FROM printer_settings WHERE id = 1"
        ).fetchone()
        audits = conn.execute(
            "SELECT action, action_type FROM audit_events WHERE action = 'register.printer_settings'"
        ).fetchall()
    except sqlite3.Error as exc:
        return {"error": str(exc), "path": str(path)}
    finally:
        conn.close()
    return {
        "path": str(path),
        "tags": [{"session_id": row[0], "tag": row[1]} for row in tags],
        "sessions": [
            {"id": row[0], "mode": row[1], "table_number": row[2], "guest": row[3], "phone": row[4], "status": row[5]}
            for row in sessions
        ],
        "printer": None
        if printer is None
        else {
            "transport": printer[0],
            "address": printer[1],
            "paper_dots": printer[2],
            "copies": printer[3],
            "drawer_kick": printer[4],
            "auto_discover": printer[5],
            "user_selected": printer[6],
            "previous_address": printer[7],
        },
        "settings_audits": [{"action": row[0], "action_type": row[1]} for row in audits],
    }


def start_takeaway(name: str, phone: str, pickup: str) -> dict:
    click(DIRECTORY, "Change Order Type")
    time.sleep(0.4)
    click(DIRECTORY, "Takeaway")
    time.sleep(0.5)
    act("fill-label", f"Customer name|{name}")
    time.sleep(0.6)
    act("fill-label", f"Phone|{phone}")
    act("fill-label", f"Pickup time|{pickup}")
    time.sleep(0.4)
    click(DIRECTORY, "Add & start")
    return see(lambda row: tag_of(row).startswith("TW"), 40)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    seed = signing_seed()
    env = os.environ.copy()
    env.update({"ORDERTAGS_SIGNING_SEED": seed, "ORDERTAGS_KEY_ID": "ordertags-accept-1"})
    log_path = TEMP / "server.log"
    handle = log_path.open("w", encoding="utf-8")
    server = subprocess.Popen(
        ["node", "scripts/python.mjs", "scripts/ordertags_acceptance_server.py"],
        cwd=REPO,
        env=env,
        stdout=handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    proc = None
    result: dict = {"profile": "ordertags"}
    try:
        deadline = time.time() + 90
        while time.time() < deadline:
            text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
            if "ORDERTAGS_READY" in text:
                break
            if server.poll() is not None:
                raise RuntimeError(text[-500:])
            time.sleep(0.4)
        else:
            raise RuntimeError("order-tag api did not become ready")
        exe = build()
        ready = json.loads((TEMP / "ready.json").read_text(encoding="utf-8"))
        result["identity"] = {
            "executable": str(exe),
            "sha256": sha256(exe),
            "size": exe.stat().st_size,
            "identifier_expected": IDENTIFIER,
            "api": ready.get("api"),
            "database": ready.get("database"),
            "store_code": ready.get("store_code"),
        }
        if DIRECTORY.exists():
            subprocess.check_call(["powershell", "-NoProfile", "-Command", f"Remove-Item -LiteralPath '{DIRECTORY}' -Recurse -Force"])
        DIRECTORY.mkdir(parents=True)
        (DIRECTORY / "zoom-profile.txt").write_text("ordertags", encoding="utf-8")
        (DIRECTORY / "zoom-activate.json").write_text(
            json.dumps({"subdomain": ready["store_code"], "activation_key": ready["activation_key"]}),
            encoding="utf-8",
        )
        (DIRECTORY / "zoom-unlock.json").write_text(
            json.dumps({"username": ready["owner_username"], "pin": ready["owner_pin"]}),
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
                raise RuntimeError(f"acceptance app exited {proc.returncode}")
            time.sleep(0.4)
        hwnd = int(window.get("hwnd") or 0)
        result["identity"].update({key: window.get(key) for key in ("hwnd", "identifier", "title", "data_dir")})
        if window.get("identifier") != IDENTIFIER:
            raise RuntimeError(f"unexpected identity {window.get('identifier')}")
        see(lambda row: "Takeaway" in (row.get("text") or ""), 90)
        first = start_takeaway("Amina", "0501111111", "14:30")
        first_tag = tag_of(first)
        result["first_tag"] = first_tag
        result["first_readonly"] = field_value(first, "Order tag").endswith(":ro")
        capture(hwnd, OUT / "takeaway-tag.png")
        act("fill-label", "Customer name|Bilal")
        act("fill-label", "Phone|0502222222")
        act("fill-label", "Pickup time|15:45")
        click(DIRECTORY, "Update")
        updated = see(lambda row: "Bilal" in field_value(row, "Customer name") and tag_of(row) == first_tag, 20)
        result["tag_after_edit"] = tag_of(updated)
        result["guest_after_edit"] = field_value(updated, "Customer name")
        result["phone_after_edit"] = field_value(updated, "Phone")
        result["pickup_after_edit"] = field_value(updated, "Pickup time")
        result["fields_after_edit"] = updated.get("fields")
        if not first_tag.startswith("TW") or tag_of(updated) != first_tag:
            raise RuntimeError(f"tag was not issued or changed: {first_tag} -> {tag_of(updated)}")
        click(DIRECTORY, "Mineral Water")
        added = see(lambda row: "How many" in (row.get("dialog") or "") or "1 item" in (row.get("text") or ""), 20)
        if "How many" in (added.get("dialog") or ""):
            click(DIRECTORY, "Add 1")
            see(lambda row: "1 item" in (row.get("text") or ""), 15)
        click(DIRECTORY, "Card")
        time.sleep(0.3)
        click(DIRECTORY, "Pay")
        paid = see(
            lambda row: "No, Skip" in (row.get("dialog") or "") or "Sale not recorded" in (row.get("text") or ""),
            30,
        )
        result["payment_dialog"] = (paid.get("dialog") or "")[:400]
        if "No, Skip" not in (paid.get("dialog") or ""):
            raise RuntimeError("the first takeaway was not settled, so a second tag was not requested")
        click(DIRECTORY, "No, Skip")
        time.sleep(0.8)
        second = start_takeaway("Noor", "0503333333", "16:00")
        second_tag = tag_of(second)
        result["second_tag"] = second_tag
        result["tags_differ"] = bool(first_tag) and first_tag != second_tag and second_tag.startswith("TW")
        if not result["tags_differ"]:
            raise RuntimeError(f"second tag was not the next reference: {first_tag} then {second_tag}")
        click(DIRECTORY, "Restaurant settings")
        time.sleep(0.6)
        click(DIRECTORY, "Printer & drawer")
        see(lambda row: "Change printer" in (row.get("text") or ""), 20)
        click(DIRECTORY, "Change printer")
        opened = see(lambda row: "Windows printer" in (row.get("dialog") or ""), 20)
        result["settings_opened"] = "Windows printer" in (opened.get("dialog") or "")
        click(DIRECTORY, "Windows printer")
        time.sleep(0.6)
        click(DIRECTORY, "Select a printer")
        time.sleep(0.5)
        act("click-option", QUEUE)
        time.sleep(0.4)
        click(DIRECTORY, "58 mm")
        click(DIRECTORY, "Copies")
        time.sleep(0.3)
        act("click-option", "2")
        time.sleep(0.3)
        click(DIRECTORY, "Save")
        saved = see(lambda row: "virtual printer" in (row.get("text") or "").lower() or "Register settings saved" in (row.get("text") or ""), 25)
        result["save_text"] = (saved.get("text") or "")[:800]
        result["sqlite_after_save"] = read_register()
        click(DIRECTORY, "Change printer")
        reopened = see(lambda row: "58 mm" in (row.get("pressed") or "") or QUEUE in (row.get("dialog") or ""), 20)
        result["reopened_pressed"] = reopened.get("pressed")
        result["reopened_dialog"] = (reopened.get("dialog") or "")[:500]
        result["reopened_selects"] = reopened.get("selects")
        act("escape")
        time.sleep(0.4)
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=20)
        identity = DIRECTORY / "zoom-identity.json"
        if identity.exists():
            identity.unlink()
        measured = DIRECTORY / "zoom-measured.json"
        if measured.exists():
            measured.unlink()
        proc = subprocess.Popen([str(exe)])
        result["restart_pid"] = proc.pid
        time.sleep(2)
        window = {}
        deadline = time.time() + 90
        while time.time() < deadline and not window.get("hwnd"):
            window = read_json(DIRECTORY / "zoom-identity.json")
            time.sleep(0.4)
        hwnd = int(window.get("hwnd") or 0)
        see(lambda row: "Takeaway" in (row.get("text") or "") or "Settings" in (row.get("text") or ""), 90)
        click(DIRECTORY, "Restaurant settings")
        time.sleep(0.5)
        click(DIRECTORY, "Printer & drawer")
        see(lambda row: "Change printer" in (row.get("text") or ""), 20)
        click(DIRECTORY, "Change printer")
        restored = see(lambda row: QUEUE in (row.get("dialog") or "") or "58 mm" in (row.get("pressed") or ""), 25)
        result["restart_pressed"] = restored.get("pressed")
        result["restart_dialog"] = (restored.get("dialog") or "")[:500]
        result["restart_selects"] = restored.get("selects")
        result["sqlite_after_restart"] = read_register()
        capture(hwnd, OUT / "settings-after-restart.png")
        result["status"] = "RECORDED"
        print("ORDERTAGS_NATIVE_DONE")
        return 0
    except Exception as exc:
        result["status"] = "FAILED"
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["sqlite"] = read_register()
        print("ORDERTAGS_NATIVE_FAILED", type(exc).__name__, exc)
        return 1
    finally:
        (OUT / "ordertags.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        if proc is not None and proc.poll() is None:
            proc.terminate()
        if server.poll() is None:
            server.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
