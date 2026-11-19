"""Receive and release medicine A, then rerun the existing pharmacy API checks."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

for env_path in (ROOT / ".env.acceptance", HERE / ".env.acceptance.runtime"):
    if not env_path.exists():
        raise SystemExit(f"missing {env_path.name}")
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key] = value

os.environ["ACCEPTANCE_API_URL"] = "http://127.0.0.1:18080"
os.environ["ACCEPTANCE_ADMIN_PASSWORD"] = os.environ["ADMIN_PASSWORD"]
os.environ["ACCEPTANCE_API_KEY"] = os.environ["API_KEY"]
os.environ["ACCEPTANCE_PHASE"] = "finish"

import secrets  # noqa: E402

import exercise  # noqa: E402
from exercise import Api, _login  # noqa: E402

staff_password = "accept-rerun-" + secrets.token_hex(4)
os.environ["ACCEPTANCE_STAFF_PASSWORD"] = staff_password

manifest_path = HERE / "evidence" / "manifest.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
admin = Api(os.environ["ACCEPTANCE_API_URL"], exercise.TENANT)
_login(admin, "admin", os.environ["ACCEPTANCE_ADMIN_PASSWORD"])
_, users = admin("GET", "/api/v1/users")
for username in ("pharmacist.one", "manager.plain", "officer.one"):
    user_id = next(row["id"] for row in users if row.get("username") == username)
    status, _ = admin("POST", f"/api/v1/users/{user_id}/password", {"password": staff_password})
    print("password-reset", username, status)
    if status not in {200, 204}:
        raise SystemExit("Password reset failed")
_, order = admin("GET", f"/api/v1/inventory/purchase-orders/{manifest['order_a_id']}")
line_id = order["lines"][0]["id"]
_, received = admin(
    "POST",
    f"/api/v1/inventory/purchase-orders/{order['id']}/receive",
    {
        "note": "Acceptance till receipt A",
        "lines": [
            {
                "purchase_order_line_id": line_id,
                "quantity": 10,
                "manufacturer_lot": "ACCEPT-LOT-A",
                "expiry_date": "2027-06-01",
            }
        ],
    },
)
lot = next(item for item in received["receipts"][-1]["lots"] if item.get("manufacturer_lot") == "ACCEPT-LOT-A")
lot_id = str(lot["batch_item_id"])
print("lot-a-received", lot.get("status"), lot_id[:8])

pharmacist = Api(os.environ["ACCEPTANCE_API_URL"], exercise.TENANT)
_login(pharmacist, "pharmacist.one", os.environ["ACCEPTANCE_STAFF_PASSWORD"])
status, body = pharmacist(
    "POST",
    f"/api/v1/pharmacy/lots/{lot_id}/release",
    {"reason": "Acceptance release of lot A", "confirm": True},
)
print("lot-a-release", status)
if status != 200:
    raise SystemExit("Lot A release failed")

exercise.finish()

cleared, clear_body = pharmacist(
    "POST",
    f"/api/v1/pharmacy/lots/{manifest['lots']['B']}/clear-quarantine",
    {"reason": "Acceptance quarantine clearance", "confirm": True},
)
print("lot-b-clearance", cleared)
if cleared != 200:
    raise SystemExit("Quarantine clearance failed")

os.environ["ACCEPTANCE_PHASE"] = "revoke"
exercise.revoke_check()
print("regression-api-complete")
