use std::path::Path;
use std::sync::Mutex;

use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};

use crate::auth::CashierProfile;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProductRow {
    pub id: String,
    pub store_id: String,
    pub sku: String,
    pub barcode: String,
    pub name: String,
    #[serde(default)]
    pub model_number: Option<String>,
    #[serde(default)]
    pub brand: Option<String>,
    pub category: String,
    pub price_cents: i64,
    pub currency: String,
    pub is_serialized: bool,
    pub stock_quantity: i64,
    #[serde(default = "one")]
    pub min_order_quantity: i64,
    #[serde(default = "piece_only")]
    pub sellable_units: Vec<String>,
    /// product_prices rows (tier, price, MOQ, volume breaks) exactly as the API returns them.
    #[serde(default = "empty_list")]
    pub prices: serde_json::Value,
    #[serde(default = "standard_tax")]
    pub tax_category: String,
    #[serde(default)]
    pub is_open_price: bool,
    #[serde(default)]
    pub is_service: bool,
    /// Parent model (size x colour grid) and this variant's attributes, for the register's variant picker.
    #[serde(default)]
    pub product_model_id: Option<String>,
    #[serde(default)]
    pub model_name: Option<String>,
    #[serde(default = "empty_object")]
    pub variant_attributes: serde_json::Value,
    /// "api" once the row came from the server; registers only sync product rows the server lacks.
    #[serde(default = "seed_origin")]
    pub origin: String,
    /// Weighed goods: stock and sale quantities count grams and price_cents is per kilogram.
    #[serde(default)]
    pub sold_by_weight: bool,
    #[serde(default)]
    pub plu_code: Option<String>,
    #[serde(default)]
    pub tare_grams: i64,
    /// Soonest batch expiry at this branch (expiry-first stock module), as YYYY-MM-DD.
    #[serde(default)]
    pub nearest_expiry: Option<String>,
    /// The packs in sellable_units with names and factors (built-in and the business's own units of measure).
    #[serde(default = "empty_list")]
    pub unit_options: serde_json::Value,
    /// Recipes module: a dish drawn from its ingredients (no stock check), and ingredients the register never sells.
    #[serde(default)]
    pub has_recipe: bool,
    #[serde(default)]
    pub is_ingredient: bool,
    /// Business-wide and this branch's price-list entries, as the API returns them.
    #[serde(default = "empty_list")]
    pub price_lists: serde_json::Value,
    /// Cover photo; product cards fall back to the category icon when it is missing or offline.
    #[serde(default)]
    pub image_url: Option<String>,
    #[serde(default)]
    pub thumb_url: Option<String>,
    /// Fashion attributes, for search and the product card.
    #[serde(default)]
    pub season: Option<String>,
    #[serde(default)]
    pub collection: Option<String>,
    #[serde(default)]
    pub gender: Option<String>,
    /// Price before the active markdown; the card strikes it through.
    #[serde(default)]
    pub compare_at_cents: Option<i64>,
}

fn standard_tax() -> String {
    "STANDARD".to_string()
}

fn seed_origin() -> String {
    "seed".to_string()
}

fn one() -> i64 {
    1
}

fn piece_only() -> Vec<String> {
    vec!["PIECE".to_string()]
}

fn empty_list() -> serde_json::Value {
    serde_json::Value::Array(Vec::new())
}

fn empty_object() -> serde_json::Value {
    serde_json::Value::Object(serde_json::Map::new())
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchHit {
    pub product: ProductRow,
    #[serde(rename = "match")]
    pub match_kind: String,
    #[serde(default)]
    pub serial_kind: Option<String>,
    #[serde(default)]
    pub serial_status: Option<String>,
}

const MAX_SEARCH_TOKENS: usize = 6;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QueuedEvent {
    pub id: String,
    pub idempotency_key: String,
    pub entity_type: String,
    pub operation: String,
    pub payload: serde_json::Value,
    pub occurred_at: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct BatchStatus {
    pub status: String,
    pub error: Option<String>,
}

#[derive(Debug, Clone)]
pub struct CachedUser {
    pub user_id: String,
    pub username: String,
    pub full_name: String,
    pub store_id: Option<String>,
    pub role_name: String,
    pub permissions: String,
    pub pin_hash: String,
    pub failed_attempts: i64,
    pub locked_until: Option<i64>,
    pub max_discount_bps: Option<i64>,
}

#[derive(Deserialize)]
struct SeedFile {
    products: Vec<ProductRow>,
    #[serde(default)]
    wholesale: Option<SeedWholesale>,
}

#[derive(Deserialize)]
struct SeedWholesale {
    #[serde(default)]
    pricing: Vec<SeedPricing>,
}

#[derive(Deserialize)]
struct SeedPricing {
    sku: String,
    #[serde(default = "piece_only")]
    sellable_units: Vec<String>,
    #[serde(default = "one")]
    min_order_quantity: i64,
    #[serde(default = "empty_list")]
    tiers: serde_json::Value,
}

const PRODUCT_COLUMNS: &str = "id, store_id, sku, barcode, name, category, price_cents, currency, is_serialized, \
     stock_quantity, model_number, brand, min_order_quantity, sellable_units, prices_json, tax_category, \
     is_open_price, origin, is_service, product_model_id, model_name, variant_json, sold_by_weight, plu_code, \
     tare_grams, nearest_expiry, units_json, has_recipe, is_ingredient, price_lists_json, image_url, thumb_url, \
     season, collection, gender, compare_at_cents";
const PRODUCT_COLUMN_COUNT: usize = 36;

pub struct Db {
    conn: Mutex<Connection>,
}

impl Db {
    pub fn open(path: &Path) -> Result<Self, String> {
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent).map_err(|err| err.to_string())?;
        }
        let conn = Connection::open(path).map_err(|err| err.to_string())?;
        conn.execute_batch("PRAGMA foreign_keys = ON;")
            .map_err(|err| err.to_string())?;
        migrate(&conn)?;
        crate::search_index::migrate(&conn)?;
        crate::returns::migrate(&conn)?;
        crate::settings::migrate(&conn)?;
        crate::customers::migrate(&conn)?;
        crate::serials::migrate(&conn)?;
        crate::audit::migrate(&conn)?;
        crate::documents::migrate(&conn)?;
        crate::printer::migrate(&conn)?;
        crate::shifts::migrate(&conn)?;
        crate::held::migrate(&conn)?;
        crate::table_sessions::migrate(&conn)?;
        crate::margin::migrate(&conn)?;
        crate::timeclock::migrate(&conn)?;
        crate::menu::migrate(&conn)?;
        seed(&conn)?;
        Ok(Self {
            conn: Mutex::new(conn),
        })
    }

    /// Every whitespace-separated token must appear (case-insensitive, partial) in name, model, barcode,
    /// SKU, category, or brand. Model, SKU, and barcode also match with separators removed. Words of three or
    /// more characters go through the trigram index (search_index); shorter ones are LIKE-filtered.
    pub fn search_products(&self, query: &str, limit: i64) -> Result<Vec<SearchHit>, String> {
        let lowered = query.trim().to_lowercase();
        let tokens: Vec<&str> = lowered.split_whitespace().take(MAX_SEARCH_TOKENS).collect();
        if tokens.is_empty() {
            return Ok(Vec::new());
        }
        let mut values: Vec<String> = vec![lowered.clone(), format!("{}%", like_escape(tokens[0]))];
        let mut clauses = Vec::new();
        let mut indexed = Vec::new();
        for token in &tokens {
            if token.chars().count() >= crate::search_index::MIN_CHARS {
                indexed.push(crate::search_index::term(token, &compact(token)));
                continue;
            }
            values.push(format!("%{}%", like_escape(token)));
            let plain = values.len();
            let compact = compact(token);
            let mut ors: Vec<String> = [
                "name",
                "IFNULL(model_number, '')",
                "barcode",
                "sku",
                "category",
                "IFNULL(brand, '')",
                "IFNULL(season, '')",
                "IFNULL(collection, '')",
            ]
            .iter()
                .map(|field| format!("{field} LIKE ?{plain} ESCAPE '\\'"))
                .collect();
            if !compact.is_empty() {
                values.push(format!("%{}%", like_escape(&compact)));
                let squeezed = values.len();
                for field in ["IFNULL(model_number, '')", "sku", "barcode"] {
                    ors.push(format!(
                        "REPLACE(REPLACE({field}, '-', ''), ' ', '') LIKE ?{squeezed} ESCAPE '\\'"
                    ));
                }
            }
            clauses.push(format!("({})", ors.join(" OR ")));
        }
        if !indexed.is_empty() {
            values.push(indexed.join(" AND "));
            clauses.push(format!(
                "rowid IN (SELECT rowid FROM products_fts WHERE products_fts MATCH ?{})",
                values.len()
            ));
        }
        values.push(limit.to_string());
        let limit_param = values.len();
        let sql = format!(
            "SELECT {PRODUCT_COLUMNS}, (LOWER(barcode) = ?1 OR LOWER(sku) = ?1) AS is_exact FROM products
             WHERE {}
             ORDER BY CASE WHEN LOWER(barcode) = ?1 OR LOWER(sku) = ?1 THEN 0
                           WHEN LOWER(name) LIKE ?2 ESCAPE '\\' THEN 1 ELSE 2 END, name
             LIMIT ?{limit_param}",
            clauses.join(" AND ")
        );
        let conn = self.lock()?;
        let mut statement = conn.prepare(&sql).map_err(|err| err.to_string())?;
        let rows = statement
            .query_map(rusqlite::params_from_iter(values.iter()), |row| {
                Ok(SearchHit {
                    product: read_product(row)?,
                    match_kind: if row.get::<_, bool>(PRODUCT_COLUMN_COUNT)? { "exact".into() } else { "text".into() },
                    serial_kind: None,
                    serial_status: None,
                })
            })
            .map_err(|err| err.to_string())?;
        rows.collect::<rusqlite::Result<Vec<_>>>()
            .map_err(|err| err.to_string())
    }

    pub fn list_products(&self) -> Result<Vec<ProductRow>, String> {
        let conn = self.lock()?;
        let mut statement = conn
            .prepare(&format!("SELECT {PRODUCT_COLUMNS} FROM products ORDER BY name"))
            .map_err(|err| err.to_string())?;
        let rows = statement
            .query_map([], read_product)
            .map_err(|err| err.to_string())?;
        rows.collect::<rusqlite::Result<Vec<_>>>()
            .map_err(|err| err.to_string())
    }

    /// Replaces the local catalog with the server's rows so stock and prices mirror Postgres.
    pub fn replace_products(&self, products: &[ProductRow]) -> Result<(), String> {
        let mut conn = self.lock()?;
        let tx = conn.transaction().map_err(|err| err.to_string())?;
        tx.execute("DELETE FROM products", [])
            .map_err(|err| err.to_string())?;
        for product in products {
            let mut row = product.clone();
            row.origin = "api".to_string();
            insert_product(&tx, &row)?;
        }
        tx.commit().map_err(|err| err.to_string())
    }

    pub fn enqueue(&self, batch_id: &str, events: &[QueuedEvent]) -> Result<(), String> {
        self.transaction(|tx| insert_events(tx, batch_id, events))
    }

    /// Runs `work` in one SQLite transaction so feature modules can write alongside the sync queue atomically.
    pub fn transaction<T>(&self, work: impl FnOnce(&rusqlite::Transaction<'_>) -> Result<T, String>) -> Result<T, String> {
        let mut conn = self.lock()?;
        let tx = conn.transaction().map_err(|err| err.to_string())?;
        let value = work(&tx)?;
        tx.commit().map_err(|err| err.to_string())?;
        Ok(value)
    }

    pub fn read<T>(&self, work: impl FnOnce(&Connection) -> Result<T, String>) -> Result<T, String> {
        let conn = self.lock()?;
        work(&conn)
    }

    /// Oldest pending batch. A batch is one checkout and is pushed as one server transaction.
    pub fn next_pending_batch(&self) -> Result<Option<(String, Vec<QueuedEvent>)>, String> {
        let conn = self.lock()?;
        let batch_id: Option<String> = conn
            .query_row(
                "SELECT batch_id FROM sync_queue WHERE status = 'pending'
                 GROUP BY batch_id ORDER BY MIN(rowid) LIMIT 1",
                [],
                |row| row.get(0),
            )
            .map(Some)
            .or_else(|err| match err {
                rusqlite::Error::QueryReturnedNoRows => Ok(None),
                other => Err(other),
            })
            .map_err(|err| err.to_string())?;
        let Some(batch_id) = batch_id else {
            return Ok(None);
        };
        let mut statement = conn
            .prepare(
                "SELECT id, idempotency_key, entity_type, operation, payload, occurred_at
                 FROM sync_queue WHERE batch_id = ?1 AND status = 'pending' ORDER BY rowid",
            )
            .map_err(|err| err.to_string())?;
        let rows = statement
            .query_map(params![batch_id], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, String>(3)?,
                    row.get::<_, String>(4)?,
                    row.get::<_, String>(5)?,
                ))
            })
            .map_err(|err| err.to_string())?;
        let mut events = Vec::new();
        for row in rows {
            let (id, idempotency_key, entity_type, operation, payload, occurred_at) =
                row.map_err(|err| err.to_string())?;
            events.push(QueuedEvent {
                id,
                idempotency_key,
                entity_type,
                operation,
                payload: serde_json::from_str(&payload).map_err(|err| err.to_string())?,
                occurred_at,
            });
        }
        Ok(Some((batch_id, events)))
    }

    pub fn pending_count(&self) -> Result<i64, String> {
        let conn = self.lock()?;
        conn.query_row(
            "SELECT COUNT(DISTINCT batch_id) FROM sync_queue WHERE status = 'pending'",
            [],
            |row| row.get(0),
        )
        .map_err(|err| err.to_string())
    }

    pub fn batch_status(&self, batch_id: &str) -> Result<Option<BatchStatus>, String> {
        let conn = self.lock()?;
        conn.query_row(
            "SELECT status, last_error FROM sync_queue WHERE batch_id = ?1 ORDER BY rowid DESC LIMIT 1",
            params![batch_id],
            |row| {
                Ok(BatchStatus {
                    status: row.get(0)?,
                    error: row.get(1)?,
                })
            },
        )
        .map(Some)
        .or_else(|err| match err {
            rusqlite::Error::QueryReturnedNoRows => Ok(None),
            other => Err(other),
        })
        .map_err(|err| err.to_string())
    }

    pub fn mark_batch(&self, batch_id: &str, status: &str, error: Option<&str>) -> Result<(), String> {
        let conn = self.lock()?;
        conn.execute(
            "UPDATE sync_queue SET status = ?1, last_error = ?2 WHERE batch_id = ?3",
            params![status, error, batch_id],
        )
        .map_err(|err| err.to_string())?;
        Ok(())
    }

    pub fn record_failure(&self, batch_id: &str, message: &str) -> Result<(), String> {
        let conn = self.lock()?;
        conn.execute(
            "UPDATE sync_queue SET attempts = attempts + 1, last_error = ?1 WHERE batch_id = ?2",
            params![message, batch_id],
        )
        .map_err(|err| err.to_string())?;
        Ok(())
    }

    pub fn upsert_cached_user(&self, profile: &CashierProfile, pin_hash: &str, now: i64) -> Result<(), String> {
        let permissions = serde_json::to_string(&profile.permissions).map_err(|err| err.to_string())?;
        let mut conn = self.lock()?;
        let tx = conn.transaction().map_err(|err| err.to_string())?;
        tx.execute(
            "DELETE FROM cached_users WHERE username = ?1 AND user_id <> ?2",
            params![profile.username, profile.id],
        )
        .map_err(|err| err.to_string())?;
        tx.execute(
            "INSERT INTO cached_users (user_id, username, full_name, store_id, role_name, permissions, pin_hash, failed_attempts, locked_until, updated_at, max_discount_bps)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, 0, NULL, ?8, ?9)
             ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name,
                store_id = excluded.store_id,
                role_name = excluded.role_name,
                permissions = excluded.permissions,
                pin_hash = excluded.pin_hash,
                failed_attempts = 0,
                locked_until = NULL,
                updated_at = excluded.updated_at,
                max_discount_bps = excluded.max_discount_bps",
            params![
                profile.id,
                profile.username,
                profile.full_name,
                profile.store_id,
                profile.role_name,
                permissions,
                pin_hash,
                now,
                profile.max_discount_bps
            ],
        )
        .map_err(|err| err.to_string())?;
        tx.commit().map_err(|err| err.to_string())
    }

    pub fn cached_user(&self, username: &str) -> Result<Option<CachedUser>, String> {
        let conn = self.lock()?;
        conn.query_row(
            "SELECT user_id, username, full_name, store_id, role_name, permissions, pin_hash, failed_attempts, locked_until,
                    max_discount_bps
             FROM cached_users WHERE username = ?1",
            params![username],
            |row| {
                Ok(CachedUser {
                    user_id: row.get(0)?,
                    username: row.get(1)?,
                    full_name: row.get(2)?,
                    store_id: row.get(3)?,
                    role_name: row.get(4)?,
                    permissions: row.get(5)?,
                    pin_hash: row.get(6)?,
                    failed_attempts: row.get(7)?,
                    locked_until: row.get(8)?,
                    max_discount_bps: row.get(9)?,
                })
            },
        )
        .map(Some)
        .or_else(|err| match err {
            rusqlite::Error::QueryReturnedNoRows => Ok(None),
            other => Err(other),
        })
        .map_err(|err| err.to_string())
    }

    pub fn record_cached_failure(&self, username: &str, attempts: i64, locked_until: Option<i64>) -> Result<(), String> {
        let conn = self.lock()?;
        conn.execute(
            "UPDATE cached_users SET failed_attempts = ?1, locked_until = ?2 WHERE username = ?3",
            params![attempts, locked_until, username],
        )
        .map_err(|err| err.to_string())?;
        Ok(())
    }

    pub fn remove_cached_user(&self, username: &str) -> Result<(), String> {
        let conn = self.lock()?;
        conn.execute("DELETE FROM cached_users WHERE username = ?1", params![username])
            .map_err(|err| err.to_string())?;
        Ok(())
    }

    fn lock(&self) -> Result<std::sync::MutexGuard<'_, Connection>, String> {
        self.conn.lock().map_err(|err| err.to_string())
    }
}

fn migrate(conn: &Connection) -> Result<(), String> {
    conn.execute_batch(
        "
        CREATE TABLE IF NOT EXISTS products (
            id TEXT PRIMARY KEY,
            store_id TEXT NOT NULL,
            sku TEXT NOT NULL UNIQUE,
            barcode TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            price_cents INTEGER NOT NULL,
            currency TEXT NOT NULL,
            is_serialized INTEGER NOT NULL,
            stock_quantity INTEGER NOT NULL,
            model_number TEXT,
            brand TEXT
        );
        CREATE TABLE IF NOT EXISTS sync_queue (
            id TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL,
            idempotency_key TEXT NOT NULL UNIQUE,
            entity_type TEXT NOT NULL,
            operation TEXT NOT NULL,
            payload TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            status TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cached_users (
            user_id TEXT PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            full_name TEXT NOT NULL,
            store_id TEXT,
            role_name TEXT NOT NULL,
            permissions TEXT NOT NULL,
            pin_hash TEXT NOT NULL,
            failed_attempts INTEGER NOT NULL DEFAULT 0,
            locked_until INTEGER,
            updated_at INTEGER NOT NULL
        );
        ",
    )
    .map_err(|err| err.to_string())?;

    for column in ["model_number", "brand"] {
        if !has_column(conn, "products", column)? {
            conn.execute_batch(&format!("ALTER TABLE products ADD COLUMN {column} TEXT;"))
                .map_err(|err| err.to_string())?;
        }
    }
    for (column, definition) in [
        ("min_order_quantity", "INTEGER NOT NULL DEFAULT 1"),
        ("sellable_units", "TEXT NOT NULL DEFAULT '[\"PIECE\"]'"),
        ("prices_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("tax_category", "TEXT NOT NULL DEFAULT 'STANDARD'"),
        ("is_open_price", "INTEGER NOT NULL DEFAULT 0"),
        ("origin", "TEXT NOT NULL DEFAULT 'seed'"),
        ("is_service", "INTEGER NOT NULL DEFAULT 0"),
        ("product_model_id", "TEXT"),
        ("model_name", "TEXT"),
        ("variant_json", "TEXT NOT NULL DEFAULT '{}'"),
        ("sold_by_weight", "INTEGER NOT NULL DEFAULT 0"),
        ("plu_code", "TEXT"),
        ("tare_grams", "INTEGER NOT NULL DEFAULT 0"),
        ("nearest_expiry", "TEXT"),
        ("units_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("has_recipe", "INTEGER NOT NULL DEFAULT 0"),
        ("is_ingredient", "INTEGER NOT NULL DEFAULT 0"),
        ("price_lists_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("image_url", "TEXT"),
        ("thumb_url", "TEXT"),
        ("season", "TEXT"),
        ("collection", "TEXT"),
        ("gender", "TEXT"),
        ("compare_at_cents", "INTEGER"),
    ] {
        if !has_column(conn, "products", column)? {
            conn.execute_batch(&format!("ALTER TABLE products ADD COLUMN {column} {definition};"))
                .map_err(|err| err.to_string())?;
        }
    }
    if !has_column(conn, "cached_users", "max_discount_bps")? {
        conn.execute_batch("ALTER TABLE cached_users ADD COLUMN max_discount_bps INTEGER;")
            .map_err(|err| err.to_string())?;
    }
    if !has_column(conn, "sync_queue", "batch_id")? {
        conn.execute_batch(
            "ALTER TABLE sync_queue ADD COLUMN batch_id TEXT;
             UPDATE sync_queue SET batch_id = id WHERE batch_id IS NULL;",
        )
        .map_err(|err| err.to_string())?;
    }
    conn.execute_batch("CREATE INDEX IF NOT EXISTS ix_sync_queue_batch ON sync_queue (batch_id, status);")
        .map_err(|err| err.to_string())
}

pub fn insert_events(tx: &rusqlite::Transaction<'_>, batch_id: &str, events: &[QueuedEvent]) -> Result<(), String> {
    let created_at = events
        .first()
        .map(|event| event.occurred_at.clone())
        .unwrap_or_else(|| "1970-01-01T00:00:00Z".to_string());
    for event in events {
        let payload = serde_json::to_string(&event.payload).map_err(|err| err.to_string())?;
        tx.execute(
            "INSERT INTO sync_queue (id, batch_id, idempotency_key, entity_type, operation, payload, occurred_at, status, attempts, created_at)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, 'pending', 0, ?8)",
            params![
                event.id,
                batch_id,
                event.idempotency_key,
                event.entity_type,
                event.operation,
                payload,
                event.occurred_at,
                created_at
            ],
        )
        .map_err(|err| err.to_string())?;
    }
    Ok(())
}

fn has_column(conn: &Connection, table: &str, column: &str) -> Result<bool, String> {
    conn.prepare(&format!("SELECT 1 FROM pragma_table_info('{table}') WHERE name = ?1"))
        .and_then(|mut statement| statement.exists(params![column]))
        .map_err(|err| err.to_string())
}

fn like_escape(value: &str) -> String {
    value.replace('\\', "\\\\").replace('%', "\\%").replace('_', "\\_")
}

fn compact(value: &str) -> String {
    value
        .chars()
        .filter(|c| !matches!(c, ' ' | '-' | '_' | '.' | '/'))
        .collect()
}

fn seed(conn: &Connection) -> Result<(), String> {
    let count: i64 = conn
        .query_row("SELECT COUNT(*) FROM products", [], |row| row.get(0))
        .map_err(|err| err.to_string())?;
    if count > 0 {
        return Ok(());
    }
    let seed: SeedFile = serde_json::from_str(include_str!("../../../../packages/catalog/seed.json"))
        .map_err(|err| err.to_string())?;
    let pricing = seed.wholesale.map(|wholesale| wholesale.pricing).unwrap_or_default();
    for product in seed.products {
        let mut product = product;
        if let Some(spec) = pricing.iter().find(|spec| spec.sku == product.sku) {
            product.sellable_units = spec.sellable_units.clone();
            product.min_order_quantity = spec.min_order_quantity;
            product.prices = spec.tiers.clone();
        }
        insert_product(conn, &product)?;
    }
    Ok(())
}

fn insert_product(conn: &Connection, product: &ProductRow) -> Result<(), String> {
    let units = serde_json::to_string(&product.sellable_units).map_err(|err| err.to_string())?;
    let prices = serde_json::to_string(&product.prices).map_err(|err| err.to_string())?;
    let variant = serde_json::to_string(&product.variant_attributes).map_err(|err| err.to_string())?;
    let unit_options = serde_json::to_string(&product.unit_options).map_err(|err| err.to_string())?;
    let price_lists = serde_json::to_string(&product.price_lists).map_err(|err| err.to_string())?;
    conn.execute(
        &format!(
            "INSERT INTO products ({PRODUCT_COLUMNS})
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16, ?17, ?18, ?19, ?20, ?21, ?22,
                     ?23, ?24, ?25, ?26, ?27, ?28, ?29, ?30, ?31, ?32, ?33, ?34, ?35, ?36)"
        ),
        params![
            product.id,
            product.store_id,
            product.sku,
            product.barcode,
            product.name,
            product.category,
            product.price_cents,
            product.currency,
            if product.is_serialized { 1 } else { 0 },
            product.stock_quantity,
            product.model_number,
            product.brand,
            product.min_order_quantity,
            units,
            prices,
            product.tax_category,
            if product.is_open_price { 1 } else { 0 },
            product.origin,
            if product.is_service { 1 } else { 0 },
            product.product_model_id,
            product.model_name,
            variant,
            if product.sold_by_weight { 1 } else { 0 },
            product.plu_code,
            product.tare_grams,
            product.nearest_expiry,
            unit_options,
            if product.has_recipe { 1 } else { 0 },
            if product.is_ingredient { 1 } else { 0 },
            price_lists,
            product.image_url,
            product.thumb_url,
            product.season,
            product.collection,
            product.gender,
            product.compare_at_cents
        ],
    )
    .map_err(|err| err.to_string())?;
    Ok(())
}

fn json_column<T: serde::de::DeserializeOwned>(row: &rusqlite::Row<'_>, index: usize, fallback: T) -> rusqlite::Result<T> {
    let raw: String = row.get(index)?;
    Ok(serde_json::from_str(&raw).unwrap_or(fallback))
}

fn read_product(row: &rusqlite::Row<'_>) -> rusqlite::Result<ProductRow> {
    Ok(ProductRow {
        id: row.get(0)?,
        store_id: row.get(1)?,
        sku: row.get(2)?,
        barcode: row.get(3)?,
        name: row.get(4)?,
        category: row.get(5)?,
        price_cents: row.get(6)?,
        currency: row.get(7)?,
        is_serialized: row.get::<_, i64>(8)? != 0,
        stock_quantity: row.get(9)?,
        model_number: row.get(10)?,
        brand: row.get(11)?,
        min_order_quantity: row.get(12)?,
        sellable_units: json_column(row, 13, piece_only())?,
        prices: json_column(row, 14, empty_list())?,
        tax_category: row.get(15)?,
        is_open_price: row.get::<_, i64>(16)? != 0,
        origin: row.get(17)?,
        is_service: row.get::<_, i64>(18)? != 0,
        product_model_id: row.get(19)?,
        model_name: row.get(20)?,
        variant_attributes: json_column(row, 21, empty_object())?,
        sold_by_weight: row.get::<_, i64>(22)? != 0,
        plu_code: row.get(23)?,
        tare_grams: row.get(24)?,
        nearest_expiry: row.get(25)?,
        unit_options: json_column(row, 26, empty_list())?,
        has_recipe: row.get::<_, i64>(27)? != 0,
        is_ingredient: row.get::<_, i64>(28)? != 0,
        price_lists: json_column(row, 29, empty_list())?,
        image_url: row.get(30)?,
        thumb_url: row.get(31)?,
        season: row.get(32)?,
        collection: row.get(33)?,
        gender: row.get(34)?,
        compare_at_cents: row.get(35)?,
    })
}
