import { DatabaseSync } from "node:sqlite";

const dbPath = process.argv[2];
const db = new DatabaseSync(dbPath, { readOnly: true });
const tables = db.prepare("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").all();
const out = { tables: tables.map((row) => row.name) };

function columns(table) {
  return db.prepare(`PRAGMA table_info(${table})`).all().map((row) => row.name);
}

if (out.tables.includes("sync_queue")) {
  out.sync_queue_columns = columns("sync_queue");
  out.sync_queue_by_status = db.prepare(
    "SELECT status, entity_type, operation, COUNT(*) AS n FROM sync_queue GROUP BY status, entity_type, operation ORDER BY status, entity_type"
  ).all();
  out.sync_queue_rows = db.prepare(
    "SELECT id, entity_type, operation, status, attempts, substr(COALESCE(last_error,''),1,180) AS last_error, length(payload) AS payload_bytes FROM sync_queue ORDER BY id"
  ).all();
}

const saleTables = ["sales", "sale_lines", "payments", "orders", "transactions", "stock_movements", "inventory"];
for (const table of saleTables) {
  if (out.tables.includes(table)) {
    out[`${table}_count`] = db.prepare(`SELECT COUNT(*) AS n FROM ${table}`).get();
  }
}

console.log(JSON.stringify(out, null, 2));
db.close();
