"""Start the register preview against the disposable laundry API. Prints no secrets."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
vals: dict[str, str] = {}
for line in (ROOT / ".env.laundry-acceptance").read_text(encoding="utf-8").splitlines():
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    vals[key.strip()] = value.strip()

env = os.environ.copy()
env["VITE_API_BASE_URL"] = "http://127.0.0.1:18082"
env["VITE_API_KEY"] = vals["API_KEY"]
env["VITE_DEVICE_ID"] = "laundry-acceptance-01"
env["VITE_SYNC_INTERVAL_MS"] = "15000"
env["VITE_STORE_ID"] = "f817cdaa-3706-4083-81cc-21c4fe801a77"
env["VITE_TENANT_DOMAIN"] = "laundry-a"
env["VITE_SHOW_DEMO_ACCOUNTS"] = "false"
print("register preview http://127.0.0.1:1421", flush=True)
raise SystemExit(
    subprocess.call(
        ["node", "node_modules/vite/bin/vite.js", "--port", "1421", "--strictPort", "--host", "127.0.0.1"],
        cwd=ROOT / "apps" / "desktop",
        env=env,
    )
)
