"""Write non-secret acceptance identity. Does not print credentials."""

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from stage import API, ENV_FILE, EVIDENCE, PHARM, TENANT, Api, _login

for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
    if line and not line.startswith("#") and "=" in line:
        key, value = line.split("=", 1)
        os.environ.setdefault(key, value)

admin = Api(API, TENANT)
_login(admin, "admin", os.environ["ADMIN_PASSWORD"])
_, stores = admin("GET", "/api/v1/stores?limit=20")
_, products = admin("GET", "/api/v1/products?limit=20")
pharm = Api(API, PHARM)
_login(pharm, "admin", os.environ["ADMIN_PASSWORD"])
_, pharmacy_stores = pharm("GET", "/api/v1/stores?limit=20")
report = {
    "api": API,
    "database": "127.0.0.1:55433/axizpos_inventory_acceptance",
    "role": "ai_pos_app",
    "tenant": TENANT,
    "store_code": TENANT,
    "stores": [{"code": row.get("code"), "name": row.get("name")} for row in stores],
    "products": [{"sku": row.get("sku"), "name": row.get("name"), "barcode": row.get("barcode")} for row in products],
    "pharmacy_tenant": PHARM,
    "pharmacy_stores": [{"code": row.get("code"), "name": row.get("name")} for row in pharmacy_stores],
    "manager": "floor.mgr",
    "cashier": "cashier.inv",
    "admin": "admin",
    "profile": "grocery",
}
(EVIDENCE / "ready.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print("ready", len(stores), "stores", len(products), "products")
