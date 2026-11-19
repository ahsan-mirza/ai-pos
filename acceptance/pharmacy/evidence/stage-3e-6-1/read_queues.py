"""Queue and series counts for both acceptance tenants. No payloads or secrets."""
import os
import sqlite3
from pathlib import Path

root = Path(os.environ["APPDATA"]) / "com.axizpos.pharmacy.acceptance" / "tenants"
for slug in ("accept-grocery", "pharmacy-accept"):
    db = root / slug / "ai-pos.db"
    print("==", slug)
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    print("series", conn.execute("SELECT doc_type, prefix, next_value FROM document_series").fetchall())
    print("queue", conn.execute("SELECT entity_type, operation, status FROM sync_queue").fetchall())
    names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for name in ("sales", "sale_items", "sale_tenders", "payments", "local_sales", "outbox"):
        if name in names:
            count = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            print(name, count)
