import { DatabaseSync } from "node:sqlite";

const db = new DatabaseSync(process.argv[2], { readOnly: true });
const sale = db.prepare("SELECT status, payload FROM sync_queue WHERE entity_type = 'sale'").all().map((row) => {
  const payload = JSON.parse(row.payload);
  return {
    queue_status: row.status,
    invoice: payload.invoice_number ?? payload.number ?? payload.reference ?? null,
    keys: Object.keys(payload).sort(),
    total: payload.total ?? payload.grand_total ?? null,
    status: payload.status ?? null,
    payment_count: Array.isArray(payload.payments) ? payload.payments.length : null,
    line_count: Array.isArray(payload.lines) ? payload.lines.length : (Array.isArray(payload.items) ? payload.items.length : null),
  };
});
const counts = {};
for (const table of ["held_carts", "local_cash_movements", "local_returns", "receipt_cache", "local_shifts", "sync_queue"]) {
  counts[table] = db.prepare(`SELECT COUNT(*) AS n FROM ${table}`).get().n;
}
const pending = db.prepare("SELECT COUNT(*) AS n FROM sync_queue WHERE status != 'synced'").get().n;
const products = db.prepare("SELECT name FROM pragma_table_info('products')").all().map((row) => row.name);
const product = db.prepare("SELECT * FROM products WHERE sku = 'ACCEPT-TILL' OR barcode = '6291000000099' OR name LIKE '%Till Medicine%'").all().map((row) => {
  const keep = {};
  for (const key of Object.keys(row)) {
    if (/token|secret|password|pin|key/i.test(key)) continue;
    const value = row[key];
    if (typeof value === "string" && value.length > 200) keep[key] = `${value.slice(0, 80)}…`;
    else keep[key] = value;
  }
  return keep;
});
const sessionCols = db.prepare("SELECT name FROM pragma_table_info('register_session')").all().map((row) => row.name);
const session = db.prepare("SELECT * FROM register_session").all().map((row) => {
  const keep = {};
  for (const [key, value] of Object.entries(row)) {
    if (/token|secret|password|pin|key/i.test(key)) continue;
    keep[key] = typeof value === "string" && value.length > 240 ? `${value.slice(0, 80)}…` : value;
  }
  return keep;
});
console.log(JSON.stringify({ sale, counts, pending, product_columns: products, product, session_columns: sessionCols, session }, null, 2));
db.close();
