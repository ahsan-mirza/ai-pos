use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};

use crate::auth::Session;
use crate::db::Db;

/// Parked carts: a cashier holds one sale to serve the next customer and recalls it later. Local only;
/// nothing is reserved on the server, so stock is checked again when the recalled cart is charged.
pub fn migrate(conn: &Connection) -> Result<(), String> {
    conn.execute_batch(
        "
        CREATE TABLE IF NOT EXISTS held_carts (
            id TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            cashier_name TEXT NOT NULL,
            item_count INTEGER NOT NULL,
            total_cents INTEGER NOT NULL,
            payload TEXT NOT NULL,
            held_at TEXT NOT NULL
        );
        ",
    )
    .map_err(|err| err.to_string())
}

const MAX_HELD: i64 = 20;

#[derive(Deserialize)]
pub struct HoldInput {
    pub id: String,
    pub label: String,
    pub item_count: i64,
    pub total_cents: i64,
    pub payload: serde_json::Value,
    pub held_at: String,
}

#[derive(Serialize)]
pub struct HeldCart {
    pub id: String,
    pub label: String,
    pub cashier_name: String,
    pub item_count: i64,
    pub total_cents: i64,
    pub payload: serde_json::Value,
    pub held_at: String,
}

pub fn hold(db: &Db, session: &Session, input: &HoldInput) -> Result<(), String> {
    let label = input.label.trim();
    if label.is_empty() || label.chars().count() > 60 {
        return Err("Give the held sale a short name (up to 60 characters).".into());
    }
    if input.item_count <= 0 {
        return Err("There is nothing in the cart to hold.".into());
    }
    let payload = serde_json::to_string(&input.payload).map_err(|err| err.to_string())?;
    if payload.len() > 512 * 1024 {
        return Err("This cart is too large to hold.".into());
    }
    db.transaction(|tx| {
        let count: i64 = tx
            .query_row("SELECT COUNT(*) FROM held_carts", [], |row| row.get(0))
            .map_err(|err| err.to_string())?;
        if count >= MAX_HELD {
            return Err(format!("{MAX_HELD} sales are already on hold. Recall or discard one first."));
        }
        tx.execute(
            "INSERT INTO held_carts (id, label, cashier_name, item_count, total_cents, payload, held_at)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
            params![input.id, label, session.user.full_name, input.item_count, input.total_cents, payload, input.held_at],
        )
        .map_err(|err| err.to_string())?;
        Ok(())
    })
}

fn row_to_cart(row: &rusqlite::Row<'_>) -> rusqlite::Result<HeldCart> {
    let payload: String = row.get(5)?;
    Ok(HeldCart {
        id: row.get(0)?,
        label: row.get(1)?,
        cashier_name: row.get(2)?,
        item_count: row.get(3)?,
        total_cents: row.get(4)?,
        payload: serde_json::from_str(&payload).unwrap_or(serde_json::Value::Null),
        held_at: row.get(6)?,
    })
}

pub fn list(db: &Db) -> Result<Vec<HeldCart>, String> {
    db.read(|conn| {
        let mut statement = conn
            .prepare(
                "SELECT id, label, cashier_name, item_count, total_cents, payload, held_at FROM held_carts
                 ORDER BY held_at DESC",
            )
            .map_err(|err| err.to_string())?;
        let rows = statement
            .query_map([], row_to_cart)
            .map_err(|err| err.to_string())?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|err| err.to_string());
        rows
    })
}

/// Removes the held cart and returns it, so two registers' cashiers cannot both recall the same sale.
pub fn take(db: &Db, id: &str) -> Result<Option<HeldCart>, String> {
    db.transaction(|tx| {
        let cart = tx
            .query_row(
                "SELECT id, label, cashier_name, item_count, total_cents, payload, held_at FROM held_carts WHERE id = ?1",
                params![id],
                row_to_cart,
            )
            .optional()
            .map_err(|err| err.to_string())?;
        tx.execute("DELETE FROM held_carts WHERE id = ?1", params![id])
            .map_err(|err| err.to_string())?;
        Ok(cart)
    })
}

pub fn count(db: &Db) -> Result<i64, String> {
    db.read(|conn| {
        conn.query_row("SELECT COUNT(*) FROM held_carts", [], |row| row.get(0))
            .map_err(|err| err.to_string())
    })
}
