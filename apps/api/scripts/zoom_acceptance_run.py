"""Drive the four isolated zoom registers. Does not touch any other POS process."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

import ctypes
from ctypes import wintypes

REPO = Path(__file__).resolve().parents[3]
DESKTOP = REPO / "apps" / "desktop"
EVIDENCE = REPO / "docs" / "ui-ux" / "zoom-evidence"
TEMP = Path(os.environ["TEMP"]) / "axiz-zoom"
APPDATA = Path(os.environ["APPDATA"])
PROFILES = {
    "grocery": (18090, "com.axizpos.grocery.zoom", "AxizPOS Grocery Zoom"),
    "electronics": (18091, "com.axizpos.electronics.zoom", "AxizPOS Electronics Zoom"),
    "fashion": (18092, "com.axizpos.fashion.zoom", "AxizPOS Fashion Zoom"),
    "restaurant": (18093, "com.axizpos.restaurant.zoom", "AxizPOS Restaurant Zoom"),
}

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.c_void_p]
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
user32.GetWindowDC.argtypes = [wintypes.HWND]
user32.GetWindowDC.restype = wintypes.HDC
user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.c_uint]


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def ensure_key() -> str:
    TEMP.mkdir(parents=True, exist_ok=True)
    seed_path = TEMP / "seed.b64"
    if not seed_path.exists():
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        seed = os.urandom(32)
        key = Ed25519PrivateKey.from_private_bytes(seed)
        public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        (TEMP / "public.b64").write_text(base64.b64encode(public).decode("ascii"), encoding="ascii")
        (TEMP / "key-id.txt").write_text("zoom-accept-1", encoding="ascii")
        seed_path.write_text(base64.b64encode(seed).decode("ascii"), encoding="ascii")
    return seed_path.read_text(encoding="ascii").strip()


def build(profile: str, port: int) -> Path:
    target = DESKTOP / "src-tauri" / "target" / "zoom-shared"
    exe = target / "debug" / "ai-pos-desktop.exe"
    marker = target / "zoom-profile.txt"
    if exe.exists() and marker.exists() and marker.read_text(encoding="utf-8").strip() == profile:
        return exe
    env = os.environ.copy()
    env.update(
        {
            "POS_ENV": "acceptance",
            "ACCEPTANCE_PROFILE": f"zoom-{profile}",
            "ACCEPTANCE_TENANT_URL_TEMPLATE": f"http://127.0.0.1:{port}",
            "ACCEPTANCE_TENANT_BASE_DOMAIN": "acceptance.invalid",
            "CARGO_TARGET_DIR": str(target),
        }
    )
    pnpm = shutil.which("pnpm") or shutil.which("pnpm.cmd")
    if pnpm is None:
        raise SystemExit("pnpm was not found on PATH.")
    subprocess.check_call(
        [pnpm, "exec", "tauri", "build", "--debug", "--no-bundle", "--config", f"src-tauri/tauri.zoom.{profile}.conf.json"],
        cwd=DESKTOP,
        env=env,
    )
    if not exe.exists():
        raise SystemExit(f"Zoom executable was not produced for {profile}.")
    marker.write_text(profile, encoding="utf-8")
    return exe


def start_server(profile: str, seed: str, pin: str) -> tuple[subprocess.Popen, Path]:
    env = os.environ.copy()
    env.update({"ZOOM_PROFILE": profile, "ZOOM_SIGNING_SEED": seed, "ZOOM_KEY_ID": "zoom-accept-1", "ZOOM_CASHIER_PIN": pin})
    log_path = TEMP / profile / "server.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        ["node", "scripts/python.mjs", "scripts/zoom_profile_server.py"],
        cwd=REPO,
        env=env,
        stdout=handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return proc, log_path


def wait_ready(proc: subprocess.Popen, log_path: Path, profile: str) -> None:
    deadline = time.time() + 120
    while time.time() < deadline:
        text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
        if f"ZOOM_READY {profile}" in text:
            return
        if proc.poll() is not None:
            raise SystemExit(f"Zoom API for {profile} exited {proc.returncode}. {text[-500:]}")
        time.sleep(0.5)
    raise SystemExit(f"Zoom API for {profile} did not become ready.")


def capture(hwnd: int, path: Path, move: bool = True, width: int = 1400, height: int = 900) -> None:
    if move:
        user32.ShowWindow(hwnd, 9)
        user32.SetWindowPos(hwnd, 0, 40, 40, width, height, 0x0004)
        time.sleep(0.35)
    rect = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width = max(1, rect.right - rect.left)
    height = max(1, rect.bottom - rect.top)
    hwnd_dc = user32.GetWindowDC(hwnd)
    mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
    bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, width, height)
    gdi32.SelectObject(mem_dc, bitmap)
    user32.PrintWindow(hwnd, mem_dc, 2)
    user32.ReleaseDC(hwnd, hwnd_dc)
    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", ctypes.c_long),
            ("biHeight", ctypes.c_long),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", ctypes.c_long),
            ("biYPelsPerMeter", ctypes.c_long),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    header = BITMAPINFOHEADER()
    header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    header.biWidth = width
    header.biHeight = -height
    header.biPlanes = 1
    header.biBitCount = 32
    header.biCompression = 0
    buffer = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(mem_dc, bitmap, 0, height, buffer, ctypes.byref(header), 0)
    from struct import pack

    row = width * 4
    raw = b"".join(buffer[y * row : (y + 1) * row] for y in range(height))
    # BMP
    pixel_offset = 54
    size = pixel_offset + len(raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    bmp_path = path.with_suffix(".bmp")
    with bmp_path.open("wb") as handle:
        handle.write(b"BM" + pack("<IHHI", size, 0, 0, pixel_offset))
        handle.write(pack("<IiiHHIIiiII", 40, width, -height, 1, 32, 0, len(raw), 0, 0, 0, 0))
        handle.write(raw)
    subprocess.check_call(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"Add-Type -AssemblyName System.Drawing; $img=[System.Drawing.Image]::FromFile('{bmp_path}'); $img.Save('{path}', [System.Drawing.Imaging.ImageFormat]::Png); $img.Dispose()",
        ]
    )
    bmp_path.unlink(missing_ok=True)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(mem_dc)


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def wait_measured(directory: Path, predicate, timeout: float = 30) -> dict:
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        last = read_json(directory / "zoom-measured.json")
        if last and predicate(last):
            return last
        time.sleep(0.4)
    return last


def run_profile(profile: str, seed: str, pin: str) -> dict:
    port, identifier, title = PROFILES[profile]
    server, log_path = start_server(profile, seed, pin)
    result = {"profile": profile, "port": port, "identifier": identifier, "title": title, "levels": {}, "selector": {}}
    proc = None
    try:
        wait_ready(server, log_path, profile)
        ready = json.loads((TEMP / profile / "ready.json").read_text(encoding="utf-8"))
        exe = build(profile, port)
        directory = APPDATA / identifier
        if directory.exists():
            subprocess.check_call(["powershell", "-NoProfile", "-Command", f"Remove-Item -LiteralPath '{directory}' -Recurse -Force"])
        directory.mkdir(parents=True)
        (directory / "zoom-profile.txt").write_text(profile, encoding="utf-8")
        (directory / "zoom-activate.json").write_text(
            json.dumps({"subdomain": ready["store_code"], "activation_key": ready["activation_key"]}),
            encoding="utf-8",
        )
        (directory / "zoom-unlock.json").write_text(
            json.dumps({"username": ready["username"], "pin": ready["pin"]}),
            encoding="utf-8",
        )
        (directory / "zoom-shift.json").write_text("{}", encoding="utf-8")
        (directory / "zoom-factor.txt").write_text("1", encoding="utf-8")
        proc = subprocess.Popen([str(exe)])
        result["pid"] = proc.pid
        identity = {}
        deadline = time.time() + 90
        while time.time() < deadline and not identity:
            identity = read_json(directory / "zoom-identity.json")
            if proc.poll() is not None:
                result["status"] = "BLOCKED"
                result["reason"] = f"Process exited {proc.returncode} before the window opened. { (directory / 'zoom-status.txt').read_text(encoding='utf-8') if (directory / 'zoom-status.txt').exists() else '' }"
                return result
            time.sleep(0.4)
        result["identity"] = {key: identity.get(key) for key in ("pid", "hwnd", "identifier", "title", "data_dir", "profile")}
        hwnd = int(identity.get("hwnd") or 0)
        owner = wintypes.DWORD()
        if hwnd:
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if not hwnd or owner.value != proc.pid:
            result["status"] = "BLOCKED"
            result["reason"] = "The window handle does not belong to the zoom process."
            return result
        measured = wait_measured(directory, lambda row: any(name in row.get("text", "") for name in ready.get("expect", [])), 90)
        result["catalogue_seen"] = any(name in measured.get("text", "") for name in ready.get("expect", []))
        result["status_text"] = (directory / "zoom-status.txt").read_text(encoding="utf-8") if (directory / "zoom-status.txt").exists() else ""
        if not result["catalogue_seen"]:
            capture(hwnd, EVIDENCE / f"{profile}-blocked.png")
            result["status"] = "BLOCKED"
            result["reason"] = "The catalogue text was not visible."
            result["screen"] = measured.get("text", "")[:500]
            return result
        baseline = None
        font = None
        for label, factor in (("100", 1.0), ("125", 1.25), ("150", 1.5), ("200", 2.0)):
            (directory / "zoom-factor.txt").write_text(str(factor), encoding="utf-8")
            row = wait_measured(
                directory,
                lambda item, label=label: item.get("requested_percent") == int(label) and item.get("dpr"),
                20,
            )
            if baseline is None and row.get("dpr"):
                baseline = row["dpr"]
                font = row.get("font")
            ratio = (row.get("dpr") or 0) / baseline if baseline else 0
            if factor >= 1.5:
                (directory / "zoom-action.json").write_text(json.dumps({"op": "scroll"}), encoding="utf-8")
                time.sleep(0.8)
            shot = EVIDENCE / f"{profile}-{label}.png"
            capture(hwnd, shot)
            (EVIDENCE / f"{profile}-{label}.json").write_text(json.dumps({k: v for k, v in row.items() if k != "text"}, indent=2), encoding="utf-8")
            overflow = (row.get("scrollWidth") or 0) > (row.get("clientWidth") or 0) + 8
            result["levels"][label] = {
                "requested_percent": row.get("requested_percent"),
                "dpr": row.get("dpr"),
                "ratio": round(ratio, 3),
                "scale": row.get("scale"),
                "font": row.get("font"),
                "font_unchanged": row.get("font") == font,
                "well": row.get("wellHeight"),
                "footer": row.get("footerHeight"),
                "objectFit": row.get("objectFit"),
                "overflow": overflow,
                "screenshot": str(shot.relative_to(REPO)),
                "pass": abs(ratio - factor) < 0.08 and abs((row.get("scale") or 0) - 1) < 0.05 and row.get("font") == font and not overflow,
            }
        if profile == "restaurant":
            result["selector"] = restaurant_selector(directory, hwnd, ready)
        result["status"] = "PASS" if all(level["pass"] for level in result["levels"].values()) else "FAIL"
        return result
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
        if server.poll() is None:
            server.terminate()


def restaurant_selector(directory: Path, hwnd: int, ready: dict) -> dict:
    cases = {}
    for label, factor in (("100", 1.0), ("125", 1.25), ("150", 1.5), ("200", 2.0)):
        (directory / "zoom-factor.txt").write_text(str(factor), encoding="utf-8")
        wait_measured(directory, lambda item, label=label: item.get("requested_percent") == int(label), 15)
        for case, name, expect in (
            ("meal", "Grilled Chicken", "Breakfast"),
            ("plate", "Special Pasta", "Small Plate"),
            ("long", LONG_NAME if False else "Zoom Extra Long Product Name", "Family celebration"),
        ):
            click(directory, name)
            row = wait_measured(directory, lambda item, expect=expect: expect in item.get("dialog", ""), 12)
            shot = EVIDENCE / f"restaurant-{case}-{label}.png"
            capture(hwnd, shot)
            click(directory, "Cancel")
            wait_measured(directory, lambda item: "Choose an option" not in item.get("dialog", ""), 8)
            cases[f"{case}-{label}"] = {
                "opened": expect in row.get("dialog", ""),
                "default_selected": "No option selected" in row.get("dialog", ""),
                "screenshot": str(shot.relative_to(REPO)),
            }
    (directory / "zoom-factor.txt").write_text("1", encoding="utf-8")
    wait_measured(directory, lambda item: item.get("requested_percent") == 100, 15)
    click(directory, "Grilled Chicken")
    wait_measured(directory, lambda item: "Breakfast" in item.get("dialog", ""), 12)
    click(directory, "Breakfast")
    time.sleep(0.6)
    click(directory, "Extra cheese")
    time.sleep(0.4)
    click(directory, "Add to order")
    added = wait_measured(directory, lambda item: "Grilled Chicken" in item.get("text", "") and "Breakfast" in item.get("text", ""), 12)
    shot = EVIDENCE / "restaurant-line-100.png"
    capture(hwnd, shot)
    cases["line"] = {"added": "Breakfast" in added.get("text", ""), "screenshot": str(shot.relative_to(REPO))}
    return cases


LONG_WAIT = "Zoom Extra Long Product Name"


def click(directory: Path, text: str) -> None:
    (directory / "zoom-action.json").write_text(json.dumps({"op": "click", "text": text}), encoding="utf-8")
    deadline = time.time() + 8
    while time.time() < deadline and (directory / "zoom-action.json").exists():
        time.sleep(0.2)


def probe_dialog(profile: str, seed: str, pin: str) -> None:
    """Open one selector and record the dialog text. Does not settle a sale."""
    server, log_path = start_server(profile, seed, pin)
    proc = None
    try:
        wait_ready(server, log_path, profile)
        ready = json.loads((TEMP / profile / "ready.json").read_text(encoding="utf-8"))
        _port, identifier, _title = PROFILES[profile]
        exe = build(profile, PROFILES[profile][0])
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
        identity = {}
        deadline = time.time() + 90
        while time.time() < deadline and not identity:
            identity = read_json(directory / "zoom-identity.json")
            time.sleep(0.4)
        wait_measured(directory, lambda row: "From" in row.get("text", "") and "Grilled Chicken" in row.get("text", ""), 90)
        click(directory, "Grilled Chicken")
        row = wait_measured(directory, lambda item: "$8.00" in item.get("dialog", ""), 20)
        hwnd = int(identity.get("hwnd") or 0)
        if hwnd:
            capture(hwnd, EVIDENCE / "restaurant-dialog-live.png")
        (EVIDENCE / "restaurant-dialog.txt").write_text(
            (row.get("dialog", "") + "\n\n" + str(row.get("radios", "")) + "\n\n" + str(row.get("priceHit", ""))).strip(),
            encoding="utf-8",
        )
        print("ZOOM_DIALOG_READY", flush=True)
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
        if server.poll() is None:
            server.terminate()


def main() -> None:
    pin = f"{int.from_bytes(os.urandom(2), 'big') % 9000 + 1000}"
    seed = ensure_key()
    if len(sys.argv) > 1 and sys.argv[1] == "probe":
        probe_dialog("restaurant", seed, pin)
        return
    chosen = sys.argv[1:] or list(PROFILES)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    report = []
    for profile in chosen:
        print(f"ZOOM_PROFILE_START {profile}", flush=True)
        try:
            outcome = run_profile(profile, seed, pin)
        except Exception as exc:
            outcome = {"profile": profile, "status": "BLOCKED", "reason": traceback.format_exc()[-800:]}
        public = {key: value for key, value in outcome.items() if key not in {"pin"}}
        report.append(public)
        (EVIDENCE / f"{profile}-result.json").write_text(json.dumps(public, indent=2), encoding="utf-8")
        print(f"ZOOM_PROFILE_DONE {profile} {public.get('status')}", flush=True)
    (EVIDENCE / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
