import os
import sqlite3

path = os.path.expandvars(r"%APPDATA%\com.axizpos.restaurant.portion\tenants\portionr\ai-pos.db")
conn = sqlite3.connect(path)
tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY 1")]
print("products", conn.execute("select count(*) from products").fetchone()[0])
cols = [row[1] for row in conn.execute("pragma table_info(products)")]
print("sell_without_recipe", "sell_without_recipe" in cols)
if "sync_queue" in tables:
    print("queue")
    for row in conn.execute("select status, entity_type, substr(coalesce(last_error,''),1,160) from sync_queue order by rowid desc limit 10"):
        print(row)
print("names")
for row in conn.execute("select name, price_cents, sell_without_recipe, is_ingredient from products"):
    print(row)
