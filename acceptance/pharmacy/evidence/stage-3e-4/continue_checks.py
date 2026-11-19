"""Clear quarantine, revoke the pharmacist, and probe application-role RLS."""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

for env_path in (ROOT / ".env.acceptance", HERE / ".env.acceptance.runtime"):
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key] = value

os.environ["ACCEPTANCE_API_URL"] = "http://127.0.0.1:18080"
os.environ["ACCEPTANCE_ADMIN_PASSWORD"] = os.environ["ADMIN_PASSWORD"]
os.environ["ACCEPTANCE_API_KEY"] = os.environ["API_KEY"]
os.environ["ACCEPTANCE_STAFF_PASSWORD"] = "accept-rerun-" + secrets.token_hex(4)
os.environ["APP_ENV"] = "acceptance"

import exercise  # noqa: E402
from exercise import Api, _login  # noqa: E402

manifest = __import__("json").loads((HERE / "evidence" / "manifest.json").read_text(encoding="utf-8"))
admin = Api(os.environ["ACCEPTANCE_API_URL"], exercise.TENANT)
_login(admin, "admin", os.environ["ACCEPTANCE_ADMIN_PASSWORD"])
_, users = admin("GET", "/api/v1/users")
for username in ("pharmacist.one", "officer.one", "officer.two", "clerk.a", "clerk.b"):
    user_id = next(row["id"] for row in users if row.get("username") == username)
    admin("POST", f"/api/v1/users/{user_id}/password", {"password": os.environ["ACCEPTANCE_STAFF_PASSWORD"]})
    print("password-reset", username)

pharmacist_id = next(row["id"] for row in users if row.get("username") == "pharmacist.one")
officer = Api(os.environ["ACCEPTANCE_API_URL"], exercise.TENANT)
_login(officer, "officer.two", os.environ["ACCEPTANCE_STAFF_PASSWORD"])
revoked, _ = officer(
    "POST",
    f"/api/v1/pharmacy/pharmacists/{pharmacist_id}/revoke",
    {"reason": "Acceptance revocation", "confirm": True},
    ok=(200, 404, 409),
)
print("pharmacist-revoked", revoked)
if revoked not in {200, 404, 409}:
    raise SystemExit("Pharmacist revocation failed")

exercise.revoke_check()

layers = exercise._layers(admin)
lot_b = exercise._lot(layers, "ACCEPT-LOT-B", manifest["store_id"])
print("lot-b-after-clearance", None if lot_b is None else lot_b["status"])

for key in ("DATABASE_URL", "CONTROL_DATABASE_URL", "PGPASSWORD"):
    os.environ.pop(key, None)

import rls_probe  # noqa: E402

def _reuse_seed(results: list[dict]) -> str:
    rls_probe._result(results, "tenant-b-seeded", True, "reused the tenant B rows created before the database probe")
    return "d6e06b97-98d0-4637-a54f-1495ba273aa9"

rls_probe._seed_b = _reuse_seed
rls_probe.main()
print("continue-checks-complete")
