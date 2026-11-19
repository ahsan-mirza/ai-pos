import os
import sqlite3
from pathlib import Path

root = Path(os.environ["APPDATA"]) / "com.axizpos.pharmacy.acceptance"
print("root", root, root.exists())
for path in root.rglob("*.db"):
    print("DB", path.relative_to(root))
    conn = sqlite3.connect(path)
    tables = [row[0] for row in conn.execute("select name from sqlite_master where type='table'")]
    print(" tables", tables)
    if "document_series" in tables:
        print(" series", conn.execute("select doc_type, prefix, next_value from document_series").fetchall())
    if "business_settings" in tables:
        row = conn.execute("select profile_json from business_settings").fetchone()
        print(" profile", (row[0] or "")[:500])
    for name in tables:
        if "sync" in name or "queue" in name or name == "sales":
            count = conn.execute(f"select count(*) from {name}").fetchone()[0]
            print(" ", name, count)
