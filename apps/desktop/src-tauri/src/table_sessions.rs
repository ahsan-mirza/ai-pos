//! Open table and takeaway tickets kept on the register so a round can be sent to the kitchen
//! and the table stays occupied until the bill is paid, including while the server is unreachable.
//! Amounts are integer cents, matching every other money column on this register.

use rusqlite::{params, Connection};
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
        ",
    )
    .map_err(|err| err.to_string())
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

pub fn save(db: &Db, session: &TableSession) -> Result<TableSession, String> {
    if session.table_number.trim().is_empty() {
        return Err("Choose a table or a guest name.".into());
    }
    db.transaction(|tx| {
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
                    id, session_id, product_id, product_name, quantity, unit_price_cents, modifiers_json, kitchen_status
                 ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)",
                params![
                    item.id,
                    session.id,
                    item.product_id,
                    item.product_name,
                    item.quantity,
                    item.unit_price_cents,
                    item.modifiers_json,
                    item.kitchen_status,
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
        .and_then(|value| value.get("type").and_then(|item| item.as_str()).map(str::to_string))
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
            "SELECT id, session_id, product_id, product_name, quantity, unit_price_cents, modifiers_json, kitchen_status
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
            })
        })
        .map_err(|err| err.to_string())?;
    mapped
        .collect::<Result<Vec<_>, _>>()
        .map_err(|err| err.to_string())
}
