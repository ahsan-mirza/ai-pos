import { DatabaseSync } from "node:sqlite";

const db = new DatabaseSync(process.argv[2], { readOnly: true });
const rows = db
  .prepare("SELECT status, entity_type, operation, length(payload) AS bytes FROM sync_queue ORDER BY created_at")
  .all();
const stock = db.prepare("SELECT sku, name, stock_quantity FROM products ORDER BY sku").all();
const sales = db
  .prepare(
    "SELECT status, json_extract(payload, '$.invoice_number') AS invoice, json_extract(payload, '$.total_cents') AS total FROM sync_queue WHERE entity_type = 'sale'",
  )
  .all();
console.log(JSON.stringify({ rows, stock, sales }, null, 2));
