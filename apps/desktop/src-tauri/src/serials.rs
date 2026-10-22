use std::collections::HashSet;
use std::time::Duration;

use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};

use crate::db::Db;
use crate::sync::DesktopConfig;

pub fn migrate(conn: &Connection) -> Result<(), String> {
    conn.execute_batch(
        "
        CREATE TABLE IF NOT EXISTS register_serials (
            id TEXT PRIMARY KEY,
            product_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            value TEXT NOT NULL UNIQUE
        );
        CREATE INDEX IF NOT EXISTS ix_register_serials_product ON register_serials (product_id);
        CREATE TABLE IF NOT EXISTS register_serials_meta (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            fetched_at INTEGER NOT NULL,
            queue_mark INTEGER NOT NULL
        );
        ",
    )
    .map_err(|err| err.to_string())
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SerialRow {
    pub id: String,
    pub product_id: String,
    pub kind: String,
    pub value: String,
}

#[derive(Serialize)]
pub struct SerialRefresh {
    pub count: i64,
    pub source: &'static str,
    pub message: Option<String>,
}

#[derive(Serialize)]
pub struct SerialCheck {
    pub value: String,
    /// "available", "taken" (already in a queued sale), "other_product", or "unknown" (not in the cache).
    pub status: &'static str,
    pub product_id: Option<String>,
    pub kind: Option<String>,
}

/// Downloads this branch's free in-stock IMEIs. Queue rows after `queue_mark` are sales the cache predates.
pub fn refresh(db: &Db, config: &DesktopConfig) -> Result<SerialRefresh, String> {
    match fetch(config) {
        Ok(rows) => {
            let count = rows.len() as i64;
            db.transaction(|tx| {
                tx.execute("DELETE FROM register_serials", []).map_err(|err| err.to_string())?;
                for row in &rows {
                    tx.execute(
                        "INSERT OR REPLACE INTO register_serials (id, product_id, kind, value) VALUES (?1, ?2, ?3, ?4)",
                        params![row.id, row.product_id, row.kind, row.value],
                    )
                    .map_err(|err| err.to_string())?;
                }
                // Everything after the oldest still-pending row may be missing from the server's snapshot.
                let mark: i64 = tx
                    .query_row(
                        "SELECT IFNULL((SELECT MIN(rowid) - 1 FROM sync_queue WHERE status = 'pending'),
                                       (SELECT IFNULL(MAX(rowid), 0) FROM sync_queue))",
                        [],
                        |row| row.get(0),
                    )
                    .map_err(|err| err.to_string())?;
                tx.execute(
                    "INSERT INTO register_serials_meta (id, fetched_at, queue_mark) VALUES (1, strftime('%s','now'), ?1)
                     ON CONFLICT(id) DO UPDATE SET fetched_at = excluded.fetched_at, queue_mark = excluded.queue_mark",
                    params![mark],
                )
                .map_err(|err| err.to_string())?;
                Ok(())
            })?;
            Ok(SerialRefresh {
                count,
                source: "api",
                message: None,
            })
        }
        Err(reason) => Ok(SerialRefresh {
            count: db.read(|conn| {
                conn.query_row("SELECT COUNT(*) FROM register_serials", [], |row| row.get(0))
                    .map_err(|err| err.to_string())
            })?,
            source: "cache",
            message: Some(reason),
        }),
    }
}

/// Up to `limit` cached units of a product that no queued sale on this register has claimed.
pub fn available(db: &Db, product_id: &str, limit: i64, exclude: &[String]) -> Result<Vec<SerialRow>, String> {
    let claimed = claimed_values(db)?;
    let skip: HashSet<&str> = exclude.iter().map(String::as_str).collect();
    let rows: Vec<SerialRow> = db.read(|conn| {
        let mut statement = conn
            .prepare("SELECT id, product_id, kind, value FROM register_serials WHERE product_id = ?1 ORDER BY rowid")
            .map_err(|err| err.to_string())?;
        let rows = statement
            .query_map(params![product_id], read_row)
            .map_err(|err| err.to_string())?;
        rows.collect::<rusqlite::Result<Vec<_>>>().map_err(|err| err.to_string())
    })?;
    Ok(rows
        .into_iter()
        .filter(|row| !claimed.contains(&row.value) && !skip.contains(row.value.as_str()))
        .take(limit.max(0) as usize)
        .collect())
}

pub fn count_available(db: &Db, product_id: &str) -> Result<i64, String> {
    Ok(available(db, product_id, i64::MAX, &[])?.len() as i64)
}

/// Classifies scanned or pasted identifiers against the cache for one product.
pub fn check(db: &Db, product_id: &str, values: &[String]) -> Result<Vec<SerialCheck>, String> {
    let claimed = claimed_values(db)?;
    values
        .iter()
        .map(|value| {
            let found: Option<SerialRow> = db.read(|conn| {
                conn.query_row(
                    "SELECT id, product_id, kind, value FROM register_serials WHERE UPPER(value) = UPPER(?1)",
                    params![value],
                    read_row,
                )
                .optional()
                .map_err(|err| err.to_string())
            })?;
            Ok(match found {
                None => SerialCheck {
                    value: value.clone(),
                    status: if claimed.contains(value) { "taken" } else { "unknown" },
                    product_id: None,
                    kind: None,
                },
                Some(row) => SerialCheck {
                    value: row.value.clone(),
                    status: if row.product_id != product_id {
                        "other_product"
                    } else if claimed.contains(&row.value) {
                        "taken"
                    } else {
                        "available"
                    },
                    product_id: Some(row.product_id),
                    kind: Some(row.kind),
                },
            })
        })
        .collect()
}

/// Serial values in queued sales that are either still pending or synced after the cache was downloaded.
fn claimed_values(db: &Db) -> Result<HashSet<String>, String> {
    db.read(|conn| {
        let mark: i64 = conn
            .query_row("SELECT queue_mark FROM register_serials_meta WHERE id = 1", [], |row| row.get(0))
            .optional()
            .map_err(|err| err.to_string())?
            .unwrap_or(0);
        let mut statement = conn
            .prepare(
                "SELECT json_extract(i.value, '$.serial_value')
                 FROM sync_queue q, json_each(q.payload, '$.items') i
                 WHERE q.entity_type = 'sale' AND q.status <> 'rejected'
                   AND (q.status = 'pending' OR q.rowid > ?1)
                   AND json_extract(i.value, '$.serial_value') IS NOT NULL",
            )
            .map_err(|err| err.to_string())?;
        let rows = statement
            .query_map(params![mark], |row| row.get::<_, String>(0))
            .map_err(|err| err.to_string())?;
        rows.collect::<rusqlite::Result<HashSet<_>>>().map_err(|err| err.to_string())
    })
}

fn read_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<SerialRow> {
    Ok(SerialRow {
        id: row.get(0)?,
        product_id: row.get(1)?,
        kind: row.get(2)?,
        value: row.get(3)?,
    })
}

fn fetch(config: &DesktopConfig) -> Result<Vec<SerialRow>, String> {
    let response = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(15))
        .build()
        .map_err(|err| err.to_string())?
        .get(format!("{}/api/v1/inventory/register-serials", config.api_base_url))
        .query(&[("store_id", config.store_id.as_str())])
        .headers(config.auth_headers())
        .send()
        .map_err(|err| format!("The server is unreachable: {err}"))?;
    let status = response.status();
    if !status.is_success() {
        return Err(format!("IMEI sync failed ({}).", status.as_u16()));
    }
    response.json().map_err(|err| err.to_string())
}
