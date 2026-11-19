"""Local invoice sequence and sale counts. No payloads, tokens, or PINs."""
import os
import sqlite3
from pathlib import Path

db = Path(os.environ["APPDATA"]) / "com.axizpos.pharmacy.acceptance" / "tenants" / "pharmacy-accept" / "ai-pos.db"
conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
print("series", conn.execute("SELECT doc_type, prefix, next_value FROM document_series").fetchall())
print("queue", conn.execute("SELECT entity_type, operation, status FROM sync_queue").fetchall())
names = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
for name in names:
    if name in {"sales", "sale_items", "sale_tenders", "payments", "local_sales", "outbox"}:
        count = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        print(name, count)
