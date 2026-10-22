use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use serde_json::json;

use crate::auth::Session;
use crate::db::{insert_events, Db, QueuedEvent};

/// Staff clock in and out on the register with their PIN session, network or not. Each change is queued as a
/// `time_entry` sync event (clock-in, then the same entry again at clock-out); managers approve on the portal.
pub fn migrate(conn: &Connection) -> Result<(), String> {
    conn.execute_batch(
        "
        CREATE TABLE IF NOT EXISTS local_time_entries (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            user_name TEXT NOT NULL,
            clock_in_at TEXT NOT NULL,
            clock_out_at TEXT,
            break_minutes INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS local_time_entries_user ON local_time_entries (user_id, clock_out_at);
        ",
    )
    .map_err(|err| err.to_string())
}

#[derive(Clone, Serialize)]
pub struct LocalTimeEntry {
    pub id: String,
    pub user_name: String,
    pub clock_in_at: String,
    pub clock_out_at: Option<String>,
    pub break_minutes: i64,
}

#[derive(Deserialize)]
pub struct ClockIn {
    pub id: String,
    pub at: String,
}

#[derive(Deserialize)]
pub struct ClockOut {
    pub at: String,
    pub break_minutes: i64,
}

fn row(row: &rusqlite::Row<'_>) -> rusqlite::Result<LocalTimeEntry> {
    Ok(LocalTimeEntry {
        id: row.get(0)?,
        user_name: row.get(1)?,
        clock_in_at: row.get(2)?,
        clock_out_at: row.get(3)?,
        break_minutes: row.get(4)?,
    })
}

const COLUMNS: &str = "id, user_name, clock_in_at, clock_out_at, break_minutes";

fn open_for(conn: &Connection, user_id: &str) -> Result<Option<LocalTimeEntry>, String> {
    conn.query_row(
        &format!(
            "SELECT {COLUMNS} FROM local_time_entries WHERE user_id = ?1 AND clock_out_at IS NULL
             ORDER BY clock_in_at DESC LIMIT 1"
        ),
        params![user_id],
        row,
    )
    .optional()
    .map_err(|err| err.to_string())
}

fn queue(tx: &rusqlite::Transaction<'_>, key: String, payload: serde_json::Value, at: &str) -> Result<(), String> {
    insert_events(
        tx,
        &key,
        &[QueuedEvent {
            id: key.clone(),
            idempotency_key: key.clone(),
            entity_type: "time_entry".into(),
            operation: "upsert".into(),
            payload,
            occurred_at: at.into(),
        }],
    )
}

pub fn status(db: &Db, session: &Session) -> Result<Option<LocalTimeEntry>, String> {
    db.read(|conn| open_for(conn, &session.user.id))
}

pub fn clock_in(db: &Db, session: &Session, store_id: &str, input: &ClockIn) -> Result<LocalTimeEntry, String> {
    if input.id.len() != 36 || !input.id.chars().all(|c| c.is_ascii_hexdigit() || c == '-') {
        return Err("Time entry id must be a UUID.".into());
    }
    db.transaction(|tx| {
        if open_for(tx, &session.user.id)?.is_some() {
            return Err(format!("{} is already clocked in.", session.user.full_name));
        }
        tx.execute(
            "INSERT INTO local_time_entries (id, user_id, user_name, clock_in_at) VALUES (?1, ?2, ?3, ?4)",
            params![input.id, session.user.id, session.user.full_name, input.at],
        )
        .map_err(|err| err.to_string())?;
        queue(
            tx,
            format!("clock-in-{}", input.id),
            json!({ "id": input.id, "user_id": session.user.id, "store_id": store_id, "clock_in_at": input.at }),
            &input.at,
        )?;
        open_for(tx, &session.user.id)?.ok_or_else(|| "The clock-in did not save.".to_string())
    })
}

pub fn clock_out(db: &Db, session: &Session, store_id: &str, input: &ClockOut) -> Result<LocalTimeEntry, String> {
    if !(0..=600).contains(&input.break_minutes) {
        return Err("Enter a break between 0 and 600 minutes.".into());
    }
    db.transaction(|tx| {
        let entry = open_for(tx, &session.user.id)?
            .ok_or_else(|| format!("{} is not clocked in.", session.user.full_name))?;
        tx.execute(
            "UPDATE local_time_entries SET clock_out_at = ?1, break_minutes = ?2 WHERE id = ?3",
            params![input.at, input.break_minutes, entry.id],
        )
        .map_err(|err| err.to_string())?;
        queue(
            tx,
            format!("clock-out-{}", entry.id),
            json!({
                "id": entry.id,
                "user_id": session.user.id,
                "store_id": store_id,
                "clock_in_at": entry.clock_in_at,
                "clock_out_at": input.at,
                "break_minutes": input.break_minutes,
            }),
            &input.at,
        )?;
        Ok(LocalTimeEntry { clock_out_at: Some(input.at.clone()), break_minutes: input.break_minutes, ..entry })
    })
}

/// Who is on the clock at this register right now.
pub fn on_duty(db: &Db) -> Result<Vec<LocalTimeEntry>, String> {
    db.read(|conn| {
        let mut statement = conn
            .prepare(&format!(
                "SELECT {COLUMNS} FROM local_time_entries WHERE clock_out_at IS NULL ORDER BY clock_in_at"
            ))
            .map_err(|err| err.to_string())?;
        let rows = statement
            .query_map([], row)
            .map_err(|err| err.to_string())?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|err| err.to_string());
        rows
    })
}
