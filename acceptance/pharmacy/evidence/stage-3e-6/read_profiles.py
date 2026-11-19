import json
import os
import sqlite3
from pathlib import Path

root = Path(os.environ["APPDATA"]) / "com.axizpos.pharmacy.acceptance" / "tenants"
for db in sorted(root.glob("*/ai-pos.db")):
    con = sqlite3.connect(db)
    try:
        row = con.execute("SELECT profile_json FROM business_settings WHERE id = 1").fetchone()
    except sqlite3.Error as error:
        print(db.parent.name, "error", error)
        continue
    if not row or not row[0]:
        currency = con.execute("SELECT currency FROM business_settings WHERE id = 1").fetchone()
        print(db.parent.name, "no profile", "currency", currency[0] if currency else None)
        continue
    payload = json.loads(row[0])
    print(
        db.parent.name,
        "tenant", payload.get("tenant_id"),
        "profile", payload.get("business_profile") or payload.get("profile"),
        "revision", payload.get("entitlement_revision"),
        "keys", sorted(payload.keys()),
    )
