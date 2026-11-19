import { DatabaseSync } from "node:sqlite";

const db = new DatabaseSync(process.argv[2], { readOnly: true });
const session = db.prepare(
  "SELECT mode, json_extract(user_json, '$.username') AS username FROM register_session",
).all();
const queue = db.prepare(
  "SELECT status, entity_type, COUNT(*) AS n FROM sync_queue GROUP BY status, entity_type ORDER BY status, entity_type",
).all();
const pending = db.prepare("SELECT COUNT(*) AS n FROM sync_queue WHERE status = 'pending'").get();
console.log(JSON.stringify({ session, queue, pending }, null, 2));
