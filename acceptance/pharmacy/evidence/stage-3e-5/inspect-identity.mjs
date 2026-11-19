import { DatabaseSync } from "node:sqlite";

const db = new DatabaseSync(process.argv[2], { readOnly: true });
const session = db.prepare("SELECT mode, user_json FROM register_session").get();
const user = JSON.parse(session.user_json);
const settings = db.prepare("SELECT currency, profile_json FROM business_settings").get();
const profile = settings?.profile_json ? JSON.parse(settings.profile_json) : null;
const products = db.prepare("SELECT store_id, sku, name, stock_quantity FROM products ORDER BY sku").all();
const stores = [...new Set(products.map((row) => row.store_id))];
console.log(
  JSON.stringify(
    {
      mode: session.mode,
      username: user.username ?? null,
      role: user.role_name ?? user.role ?? null,
      user_store_id: user.store_id ?? null,
      currency: settings?.currency ?? null,
      profile: profile?.profile ?? profile?.business_profile ?? profile?.name ?? null,
      profile_keys: profile ? Object.keys(profile) : [],
      store_ids: stores,
      product_count: products.length,
      products: products.map((row) => ({ sku: row.sku, name: row.name, stock_quantity: row.stock_quantity })),
    },
    null,
    2,
  ),
);
