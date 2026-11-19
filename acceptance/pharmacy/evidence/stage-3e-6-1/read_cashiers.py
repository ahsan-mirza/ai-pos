"""Print cashier directory names only. Never print PIN hashes or tokens."""
import os
import sqlite3
from pathlib import Path

db = Path(os.environ["APPDATA"]) / "com.axizpos.pharmacy.acceptance" / "tenants" / "pharmacy-accept" / "ai-pos.db"
conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
names = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print("tables", [name for name in names if "cash" in name or "user" in name or "pin" in name])
for name in names:
    if "cash" not in name and "user" not in name:
        continue
    columns = [row[1] for row in conn.execute(f"PRAGMA table_info({name})")]
    safe = [column for column in columns if not any(word in column for word in ("pin", "hash", "token", "secret"))]
    print(name, safe)
    if safe:
        rows = conn.execute(f"SELECT {', '.join(safe)} FROM {name}").fetchall()
        print("count", len(rows))
        for row in rows[:6]:
            print(row)
