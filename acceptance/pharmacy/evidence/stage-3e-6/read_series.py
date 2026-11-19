import os
import sqlite3
from pathlib import Path

root = Path(os.environ["APPDATA"]) / "com.axizpos.pharmacy.acceptance" / "tenants"
for db in sorted(root.glob("*/ai-pos.db")):
    con = sqlite3.connect(db)
    names = [row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY 1")]
    print(db.parent.name, "tables", ",".join(names))
    if "document_series" in names:
        rows = con.execute("SELECT doc_type, prefix, next_value FROM document_series").fetchall()
        print(" series", rows or "empty")
    if "sync_queue" in names:
        count = con.execute("SELECT COUNT(*) FROM sync_queue").fetchone()[0]
        print(" queue", count)
