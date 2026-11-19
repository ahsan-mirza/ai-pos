import { DatabaseSync } from "node:sqlite";

const root = process.env.APPDATA + "/com.axizpos.pharmacy.acceptance/tenants/";
for (const slug of ["pharmacy-accept", "accept-grocery"]) {
  const db = new DatabaseSync(root + slug + "/ai-pos.db", { readOnly: true });
  const skus = db.prepare("SELECT sku FROM products ORDER BY sku").all().map((row) => row.sku);
  const users = db.prepare("SELECT username FROM cached_users ORDER BY username").all().map((row) => row.username);
  const session = db.prepare("SELECT mode, json_extract(user_json, '$.username') AS username FROM register_session").all();
  console.log(JSON.stringify({ slug, skus, users, session }));
}
