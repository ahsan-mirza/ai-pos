use rusqlite::params;
use serde::Serialize;

use crate::auth::Session;
use crate::db::Db;

/// What a manager sees in the register's Sync Center: each queued checkout, return, shift, or cash movement,
/// and why the server refused it. Rejected batches stay rejected until a manager retries or discards them.
#[derive(Serialize)]
pub struct BatchRow {
    pub batch_id: String,
    pub status: String,
    pub entity_types: Vec<String>,
    pub event_count: i64,
    pub attempts: i64,
    pub last_error: Option<String>,
    pub created_at: String,
    /// Invoice / credit-note number, or a total, so the cashier can recognise the transaction.
    pub summary: String,
}

const RESOLVE_PERMISSION: &str = "pos:shift_manage";

pub fn list(db: &Db, status: Option<&str>, limit: i64) -> Result<Vec<BatchRow>, String> {
    db.read(|conn| {
        let mut statement = conn
            .prepare(
                "SELECT batch_id, MAX(status), GROUP_CONCAT(DISTINCT entity_type), COUNT(*), MAX(attempts),
                        MAX(last_error), MIN(created_at),
                        MAX(COALESCE(json_extract(payload, '$.invoice_number'), json_extract(payload, '$.credit_note_number'),
                                     json_extract(payload, '$.z_number'))),
                        MAX(json_extract(payload, '$.total_cents')), MAX(json_extract(payload, '$.total_refund_cents')),
                        MAX(json_extract(payload, '$.amount_cents'))
                 FROM sync_queue
                 WHERE (?1 IS NULL OR status = ?1)
                 GROUP BY batch_id ORDER BY MIN(rowid) DESC LIMIT ?2",
            )
            .map_err(|err| err.to_string())?;
        let rows = statement
            .query_map(params![status, limit], |row| {
                let types: String = row.get::<_, Option<String>>(2)?.unwrap_or_default();
                let number: Option<String> = row.get(7)?;
                let total: Option<i64> = row.get(8)?;
                let refund: Option<i64> = row.get(9)?;
                let moved: Option<i64> = row.get(10)?;
                let amount = total.or(refund).or(moved);
                let summary = match (number, amount) {
                    (Some(number), Some(cents)) => format!("{number} · {:.2}", cents as f64 / 100.0),
                    (Some(number), None) => number,
                    (None, Some(cents)) => format!("{:.2}", cents as f64 / 100.0),
                    (None, None) => String::new(),
                };
                Ok(BatchRow {
                    batch_id: row.get(0)?,
                    status: row.get(1)?,
                    entity_types: types.split(',').filter(|item| !item.is_empty()).map(str::to_string).collect(),
                    event_count: row.get(3)?,
                    attempts: row.get(4)?,
                    last_error: row.get(5)?,
                    created_at: row.get(6)?,
                    summary,
                })
            })
            .map_err(|err| err.to_string())?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|err| err.to_string());
        rows
    })
}

/// Retry puts a rejected batch back in the queue (after the cause was fixed on the server); discard drops it
/// for good and is reserved for managers, since a discarded sale never reaches the books.
pub fn resolve(db: &Db, session: &Session, batch_id: &str, action: &str) -> Result<(), String> {
    let (from, to) = match action {
        "retry" => ("rejected", "pending"),
        "discard" => ("rejected", "discarded"),
        _ => return Err("Unknown action.".into()),
    };
    if action == "discard"
        && !session
            .user
            .permissions
            .iter()
            .any(|item| item == RESOLVE_PERMISSION)
    {
        return Err("Only a manager can discard a rejected transaction.".into());
    }
    db.transaction(|tx| {
        let changed = tx
            .execute(
                "UPDATE sync_queue SET status = ?1, attempts = 0,
                    last_error = CASE WHEN ?1 = 'discarded' THEN 'Discarded by ' || ?4 ELSE last_error END
                 WHERE batch_id = ?2 AND status = ?3",
                params![to, batch_id, from, session.user.full_name],
            )
            .map_err(|err| err.to_string())?;
        if changed == 0 {
            return Err("Only rejected transactions can be retried or discarded.".into());
        }
        Ok(())
    })
}

pub fn rejected_count(db: &Db) -> Result<i64, String> {
    db.read(|conn| {
        conn.query_row(
            "SELECT COUNT(DISTINCT batch_id) FROM sync_queue WHERE status = 'rejected'",
            [],
            |row| row.get(0),
        )
        .map_err(|err| err.to_string())
    })
}
