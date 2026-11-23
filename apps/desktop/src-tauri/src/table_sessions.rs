//! Open table and takeaway tickets kept on the register so a round can be sent to the kitchen
//! and the table stays occupied until the bill is paid, including while the server is unreachable.
//! Amounts are integer cents, matching every other money column on this register.

use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};

use crate::db::Db;

pub fn migrate(conn: &Connection) -> Result<(), String> {
    conn.execute_batch(
        "
        CREATE TABLE IF NOT EXISTS table_sessions (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            store_id TEXT NOT NULL,
            table_number TEXT NOT NULL,
            guest_count INTEGER NOT NULL DEFAULT 1,
            guest_name TEXT NOT NULL DEFAULT '',
            address TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',
            order_mode TEXT NOT NULL DEFAULT 'dine_in',
            status TEXT NOT NULL DEFAULT 'OPEN',
            total_cents INTEGER NOT NULL DEFAULT 0,
            server_order_id TEXT,
            server_revision INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS table_session_items (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            product_id TEXT NOT NULL,
            product_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price_cents INTEGER NOT NULL,
            modifiers_json TEXT NOT NULL DEFAULT '[]',
            kitchen_status TEXT NOT NULL DEFAULT 'PENDING',
            note TEXT,
            FOREIGN KEY(session_id) REFERENCES table_sessions(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS table_sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS ix_table_sync_log_store ON table_sync_log(store_id, id);
        CREATE TABLE IF NOT EXISTS order_tags (
            session_id TEXT PRIMARY KEY,
            store_id TEXT NOT NULL,
            order_mode TEXT NOT NULL,
            tag TEXT NOT NULL,
            UNIQUE(store_id, tag)
        );
        CREATE TABLE IF NOT EXISTS order_tag_counters (
            store_id TEXT NOT NULL,
            order_mode TEXT NOT NULL,
            last_value INTEGER NOT NULL,
            PRIMARY KEY (store_id, order_mode)
        );
        ",
    )
    .map_err(|err| err.to_string())?;
    add_note_column(conn)?;
    add_price_option_column(conn)?;
    add_skip_recipe_column(conn)
}

fn add_note_column(conn: &Connection) -> Result<(), String> {
    let mut info = conn
        .prepare("PRAGMA table_info(table_session_items)")
        .map_err(|err| err.to_string())?;
    let has_note = info
        .query_map([], |row| row.get::<_, String>(1))
        .map_err(|err| err.to_string())?
        .filter_map(Result::ok)
        .any(|name| name == "note");
    if has_note {
        return Ok(());
    }
    conn.execute("ALTER TABLE table_session_items ADD COLUMN note TEXT", [])
        .map_err(|err| err.to_string())?;
    Ok(())
}

fn add_price_option_column(conn: &Connection) -> Result<(), String> {
    let mut info = conn
        .prepare("PRAGMA table_info(table_session_items)")
        .map_err(|err| err.to_string())?;
    let present = info
        .query_map([], |row| row.get::<_, String>(1))
        .map_err(|err| err.to_string())?
        .filter_map(Result::ok)
        .any(|name| name == "price_option_json");
    if present {
        return Ok(());
    }
    conn.execute(
        "ALTER TABLE table_session_items ADD COLUMN price_option_json TEXT",
        [],
    )
    .map_err(|err| err.to_string())?;
    Ok(())
}

fn add_skip_recipe_column(conn: &Connection) -> Result<(), String> {
    let mut info = conn
        .prepare("PRAGMA table_info(table_session_items)")
        .map_err(|err| err.to_string())?;
    let present = info
        .query_map([], |row| row.get::<_, String>(1))
        .map_err(|err| err.to_string())?
        .filter_map(Result::ok)
        .any(|name| name == "skip_recipe");
    if present {
        return Ok(());
    }
    conn.execute(
        "ALTER TABLE table_session_items ADD COLUMN skip_recipe INTEGER NOT NULL DEFAULT 0",
        [],
    )
    .map_err(|err| err.to_string())?;
    Ok(())
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionItem {
    pub id: String,
    pub session_id: String,
    pub product_id: String,
    pub product_name: String,
    pub quantity: i64,
    pub unit_price_cents: i64,
    pub modifiers_json: String,
    pub kitchen_status: String,
    #[serde(default)]
    pub note: Option<String>,
    #[serde(default)]
    pub price_option_json: Option<String>,
    /// True only when this line was added without consuming its recipe.
    #[serde(default)]
    pub skip_recipe: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TableSession {
    pub id: String,
    pub tenant_id: String,
    pub store_id: String,
    pub table_number: String,
    pub guest_count: i64,
    pub guest_name: String,
    pub address: String,
    pub phone: String,
    pub order_mode: String,
    pub status: String,
    pub server_order_id: Option<String>,
    pub server_revision: i64,
    pub created_at: String,
    pub updated_at: String,
    pub items: Vec<SessionItem>,
}

pub fn list(db: &Db, store_id: &str) -> Result<Vec<TableSession>, String> {
    db.read(|conn| {
        let mut statement = conn
            .prepare(
                "SELECT id, tenant_id, store_id, table_number, guest_count, guest_name, address, phone, order_mode, status,
                        server_order_id, server_revision, created_at, updated_at
                 FROM table_sessions WHERE store_id = ?1 AND status != 'CLOSED' ORDER BY updated_at DESC",
            )
            .map_err(|err| err.to_string())?;
        let sessions = statement
            .query_map(params![store_id], session_row)
            .map_err(|err| err.to_string())?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|err| err.to_string())?;
        drop(statement);
        let mut with_items = Vec::with_capacity(sessions.len());
        for mut session in sessions {
            session.items = items(conn, &session.id)?;
            with_items.push(session);
        }
        Ok(with_items)
    })
}

pub fn tag_for(db: &Db, session_id: &str) -> Result<Option<String>, String> {
    db.read(|conn| {
        conn.query_row(
            "SELECT tag FROM order_tags WHERE session_id = ?1",
            params![session_id],
            |row| row.get(0),
        )
        .optional()
        .map_err(|err| err.to_string())
    })
}

/// Issues one tag for this session. A repeat returns the same tag. `presented` stores a tag the server already issued.
pub fn allocate(
    db: &Db,
    session_id: &str,
    store_id: &str,
    mode: &str,
    device_id: &str,
    presented: Option<&str>,
) -> Result<String, String> {
    let session_id = session_id.trim();
    let store_id = store_id.trim();
    if session_id.is_empty() || store_id.is_empty() {
        return Err("The order tag needs an order and a branch.".into());
    }
    let prefix = tag_prefix(mode)?;
    db.transaction(|tx| {
        if let Some(existing) = lookup_tag(tx, session_id)? {
            if let Some(wanted) = presented.map(str::trim).filter(|value| !value.is_empty()) {
                if wanted != existing {
                    return Err("The order tag cannot be changed.".into());
                }
            }
            return Ok(existing);
        }
        let tag = match presented.map(str::trim).filter(|value| !value.is_empty()) {
            Some(wanted) => {
                if !acceptable_tag(wanted) {
                    return Err("Order tags are assigned by the register. A typed tag is not accepted.".into());
                }
                if !wanted.starts_with(prefix) {
                    return Err("That tag belongs to a different order type.".into());
                }
                wanted.to_string()
            }
            None => {
                let value = next_local_value(tx, store_id, mode)?;
                format!("{prefix}-{}-{value:03}", device_suffix(device_id))
            }
        };
        tx.execute(
            "INSERT INTO order_tags (session_id, store_id, order_mode, tag) VALUES (?1, ?2, ?3, ?4)",
            params![session_id, store_id, mode, tag],
        )
        .map_err(|err| {
            if err.to_string().contains("UNIQUE") {
                "That order tag is already used.".to_string()
            } else {
                err.to_string()
            }
        })?;
        Ok(tag)
    })
}

fn tag_prefix(mode: &str) -> Result<&'static str, String> {
    match mode {
        "takeaway" => Ok("TW"),
        "delivery" => Ok("DL"),
        _ => Err("This order type keeps its table name.".into()),
    }
}

fn acceptable_tag(tag: &str) -> bool {
    let server = tag.len() >= 5
        && tag.len() <= 8
        && (tag.starts_with("TW") || tag.starts_with("DL"))
        && tag[2..].chars().all(|c| c.is_ascii_digit());
    if server {
        return true;
    }
    let mut parts = tag.split('-');
    let prefix = parts.next();
    let device = parts.next();
    let value = parts.next();
    prefix.is_some_and(|item| item == "TW" || item == "DL")
        && device.is_some_and(|item| {
            (2..=8).contains(&item.len()) && item.chars().all(|c| c.is_ascii_uppercase() || c.is_ascii_digit())
        })
        && value.is_some_and(|item| (3..=6).contains(&item.len()) && item.chars().all(|c| c.is_ascii_digit()))
        && parts.next().is_none()
}

fn device_suffix(device_id: &str) -> String {
    let mut chars: String = device_id
        .chars()
        .filter(|c| c.is_ascii_alphanumeric())
        .take(4)
        .collect();
    chars.make_ascii_uppercase();
    if chars.len() < 2 {
        "LOCAL".into()
    } else {
        chars
    }
}

fn lookup_tag(tx: &rusqlite::Transaction<'_>, session_id: &str) -> Result<Option<String>, String> {
    tx.query_row(
        "SELECT tag FROM order_tags WHERE session_id = ?1",
        params![session_id],
        |row| row.get(0),
    )
    .optional()
    .map_err(|err| err.to_string())
}

fn next_local_value(tx: &rusqlite::Transaction<'_>, store_id: &str, mode: &str) -> Result<i64, String> {
    tx.query_row(
        "INSERT INTO order_tag_counters (store_id, order_mode, last_value) VALUES (?1, ?2, 1)
         ON CONFLICT(store_id, order_mode) DO UPDATE SET last_value = last_value + 1
         RETURNING last_value",
        params![store_id, mode],
        |row| row.get(0),
    )
    .map_err(|err| err.to_string())
}

fn enforce_service_tag(tx: &rusqlite::Transaction<'_>, session: &TableSession) -> Result<(), String> {
    if session.order_mode != "takeaway" && session.order_mode != "delivery" {
        return Ok(());
    }
    let incoming = session.table_number.trim();
    if let Some(issued) = lookup_tag(tx, &session.id)? {
        if incoming != issued {
            return Err("The order tag cannot be changed.".into());
        }
        return Ok(());
    }
    let previous: Option<String> = tx
        .query_row(
            "SELECT table_number FROM table_sessions WHERE id = ?1",
            params![session.id],
            |row| row.get(0),
        )
        .optional()
        .map_err(|err| err.to_string())?;
    if let Some(previous) = previous {
        if incoming != previous.trim() {
            return Err("The order tag cannot be changed.".into());
        }
        return Ok(());
    }
    Err("Order tags are assigned by the register.".into())
}

pub fn save(db: &Db, session: &TableSession) -> Result<TableSession, String> {
    if session.table_number.trim().is_empty() {
        return Err("Choose a table or a guest name.".into());
    }
    db.transaction(|tx| {
        enforce_service_tag(tx, session)?;
        tx.execute(
            "INSERT INTO table_sessions (
                id, tenant_id, store_id, table_number, guest_count, guest_name, address, phone, order_mode, status,
                total_cents, server_order_id, server_revision, created_at, updated_at
             ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15)
             ON CONFLICT(id) DO UPDATE SET
                table_number = excluded.table_number,
                guest_count = excluded.guest_count,
                guest_name = excluded.guest_name,
                address = excluded.address,
                phone = excluded.phone,
                order_mode = excluded.order_mode,
                status = excluded.status,
                total_cents = excluded.total_cents,
                server_order_id = excluded.server_order_id,
                server_revision = excluded.server_revision,
                updated_at = excluded.updated_at",
            params![
                session.id,
                session.tenant_id,
                session.store_id,
                session.table_number.trim(),
                session.guest_count.max(1),
                session.guest_name,
                session.address,
                session.phone,
                session.order_mode,
                session.status,
                session.items.iter().map(|item| item.unit_price_cents * item.quantity).sum::<i64>(),
                session.server_order_id,
                session.server_revision,
                session.created_at,
                session.updated_at,
            ],
        )
        .map_err(|err| err.to_string())?;
        tx.execute("DELETE FROM table_session_items WHERE session_id = ?1", params![session.id])
            .map_err(|err| err.to_string())?;
        for item in &session.items {
            tx.execute(
                "INSERT INTO table_session_items (
                    id, session_id, product_id, product_name, quantity, unit_price_cents, modifiers_json, kitchen_status, note, price_option_json, skip_recipe
                 ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11)",
                params![
                    item.id,
                    session.id,
                    item.product_id,
                    item.product_name,
                    item.quantity,
                    item.unit_price_cents,
                    item.modifiers_json,
                    item.kitchen_status,
                    item.note,
                    item.price_option_json,
                    if item.skip_recipe { 1 } else { 0 },
                ],
            )
            .map_err(|err| err.to_string())?;
        }
        Ok(())
    })?;
    Ok(session.clone())
}

/// The cashier keeps the latest live frames so a dropped socket can be reconstructed from SQLite.
pub fn cache_event(db: &Db, store_id: &str, payload: &str) -> Result<(), String> {
    let event_type = serde_json::from_str::<serde_json::Value>(payload)
        .ok()
        .and_then(|value| {
            value
                .get("type")
                .and_then(|item| item.as_str())
                .map(str::to_string)
        })
        .unwrap_or_else(|| "UNKNOWN".to_string());
    db.transaction(|tx| {
        tx.execute(
            "INSERT INTO table_sync_log (store_id, event_type, payload) VALUES (?1, ?2, ?3)",
            params![store_id, event_type, payload],
        )
        .map_err(|err| err.to_string())?;
        tx.execute(
            "DELETE FROM table_sync_log WHERE store_id = ?1 AND id < COALESCE((
                SELECT MIN(id) FROM (
                    SELECT id FROM table_sync_log WHERE store_id = ?1 ORDER BY id DESC LIMIT 200
                )
            ), 0)",
            params![store_id],
        )
        .map_err(|err| err.to_string())?;
        Ok(())
    })
}

pub fn close(db: &Db, id: &str) -> Result<(), String> {
    db.transaction(|tx| {
        tx.execute(
            "UPDATE table_sessions SET status = 'CLOSED', updated_at = datetime('now') WHERE id = ?1",
            params![id],
        )
        .map_err(|err| err.to_string())?;
        Ok(())
    })
}

fn session_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<TableSession> {
    Ok(TableSession {
        id: row.get(0)?,
        tenant_id: row.get(1)?,
        store_id: row.get(2)?,
        table_number: row.get(3)?,
        guest_count: row.get(4)?,
        guest_name: row.get(5)?,
        address: row.get(6)?,
        phone: row.get(7)?,
        order_mode: row.get(8)?,
        status: row.get(9)?,
        server_order_id: row.get(10)?,
        server_revision: row.get(11)?,
        created_at: row.get(12)?,
        updated_at: row.get(13)?,
        items: Vec::new(),
    })
}

fn items(conn: &Connection, session_id: &str) -> Result<Vec<SessionItem>, String> {
    let mut statement = conn
        .prepare(
            "SELECT id, session_id, product_id, product_name, quantity, unit_price_cents, modifiers_json, kitchen_status, note, price_option_json, skip_recipe
             FROM table_session_items WHERE session_id = ?1",
        )
        .map_err(|err| err.to_string())?;
    let mapped = statement
        .query_map(params![session_id], |row| {
            Ok(SessionItem {
                id: row.get(0)?,
                session_id: row.get(1)?,
                product_id: row.get(2)?,
                product_name: row.get(3)?,
                quantity: row.get(4)?,
                unit_price_cents: row.get(5)?,
                modifiers_json: row.get(6)?,
                kitchen_status: row.get(7)?,
                note: row.get(8)?,
                price_option_json: row.get(9)?,
                skip_recipe: row.get::<_, i64>(10)? != 0,
            })
        })
        .map_err(|err| err.to_string())?;
    mapped
        .collect::<Result<Vec<_>, _>>()
        .map_err(|err| err.to_string())
}

#[cfg(test)]
mod tests {
    use std::time::{SystemTime, UNIX_EPOCH};

    use super::*;
    use crate::db::Db;

    #[test]
    fn skip_recipe_survives_save_and_reload() {
        let path = std::env::temp_dir().join(format!(
            "aipos-skip-recipe-{}.sqlite",
            SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos()
        ));
        let db = Db::open(&path).expect("open");
        let session = TableSession {
            id: "sess".into(),
            tenant_id: "tenant".into(),
            store_id: "store".into(),
            table_number: "5".into(),
            guest_count: 2,
            guest_name: String::new(),
            address: String::new(),
            phone: String::new(),
            order_mode: "dine_in".into(),
            status: "OPEN".into(),
            server_order_id: None,
            server_revision: 0,
            created_at: "2026-11-22T00:00:00Z".into(),
            updated_at: "2026-11-22T00:00:00Z".into(),
            items: vec![
                SessionItem {
                    id: "required".into(),
                    session_id: "sess".into(),
                    product_id: "dish".into(),
                    product_name: "Grilled Chicken".into(),
                    quantity: 1,
                    unit_price_cents: 1200,
                    modifiers_json: "[]".into(),
                    kitchen_status: "PENDING".into(),
                    note: None,
                    price_option_json: None,
                    skip_recipe: false,
                },
                SessionItem {
                    id: "skipped".into(),
                    session_id: "sess".into(),
                    product_id: "dish".into(),
                    product_name: "Grilled Chicken".into(),
                    quantity: 2,
                    unit_price_cents: 1200,
                    modifiers_json: "[]".into(),
                    kitchen_status: "PENDING".into(),
                    note: None,
                    price_option_json: None,
                    skip_recipe: true,
                },
            ],
        };
        save(&db, &session).expect("save");
        let loaded = list(&db, "store").expect("list");
        let _ = std::fs::remove_file(&path);
        assert_eq!(loaded.len(), 1);
        let skipped = loaded[0]
            .items
            .iter()
            .find(|item| item.id == "skipped")
            .expect("skipped line");
        let required = loaded[0]
            .items
            .iter()
            .find(|item| item.id == "required")
            .expect("required line");
        assert!(!required.skip_recipe);
        assert!(skipped.skip_recipe);
        assert_eq!(skipped.unit_price_cents, 1200);
        assert_eq!(skipped.quantity, 2);
    }

    fn temp_db(name: &str) -> (Db, std::path::PathBuf) {
        let path = std::env::temp_dir().join(format!(
            "aipos-{name}-{}.sqlite",
            SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos()
        ));
        let db = Db::open(&path).expect("open");
        (db, path)
    }

    fn takeaway(id: &str, tag: &str) -> TableSession {
        TableSession {
            id: id.into(),
            tenant_id: "tenant".into(),
            store_id: "store".into(),
            table_number: tag.into(),
            guest_count: 1,
            guest_name: "Amina".into(),
            address: String::new(),
            phone: "0500000000".into(),
            order_mode: "takeaway".into(),
            status: "OPEN".into(),
            server_order_id: None,
            server_revision: 0,
            created_at: "2026-11-23T00:00:00Z".into(),
            updated_at: "2026-11-23T00:00:00Z".into(),
            items: vec![],
        }
    }

    #[test]
    fn order_tags_are_unique_stable_and_reject_a_typed_replacement() {
        let (db, path) = temp_db("order-tags");
        let first = allocate(&db, "order-1", "store", "takeaway", "device-aaaa", None).unwrap();
        let second = allocate(&db, "order-2", "store", "takeaway", "device-aaaa", None).unwrap();
        assert_ne!(first, second);
        assert!(first.starts_with("TW-DEVI-"), "{first}");
        assert_eq!(allocate(&db, "order-1", "store", "takeaway", "device-aaaa", None).unwrap(), first);
        let mut session = takeaway("order-1", &first);
        save(&db, &session).unwrap();
        session.guest_name = "Noura".into();
        session.phone = "0501111111".into();
        session.address = "\u{1f}18:30".into();
        save(&db, &session).unwrap();
        let loaded = list(&db, "store").unwrap();
        assert_eq!(loaded[0].table_number, first);
        assert_eq!(loaded[0].guest_name, "Noura");
        session.table_number = "TW999".into();
        assert!(save(&db, &session).unwrap_err().contains("cannot be changed"));
        assert!(allocate(&db, "order-1", "store", "takeaway", "device-aaaa", Some("TW002"))
            .unwrap_err()
            .contains("cannot be changed"));
        assert!(allocate(&db, "order-3", "store", "takeaway", "device-aaaa", Some("TW1"))
            .unwrap_err()
            .contains("not accepted"));
        let remembered = allocate(&db, "order-4", "store", "delivery", "device-bbbb", Some("DL001")).unwrap();
        assert_eq!(remembered, "DL001");
        assert_eq!(tag_for(&db, "order-4").unwrap().as_deref(), Some("DL001"));
        let _ = std::fs::remove_file(path);
    }
}
