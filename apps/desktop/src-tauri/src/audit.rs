//! Offline audit ledger for register activity. Events are written to SQLite first and pushed to
//! `/api/v1/audit-logs/sync` in batches whenever the API is reachable; the server de-duplicates on the event id.

use std::time::Duration;

use argon2::password_hash::rand_core::{OsRng, RngCore};
use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::auth::Session;
use crate::db::Db;
use crate::sync::DesktopConfig;

const BATCH_SIZE: i64 = 200;
const REASON_MIN_CHARS: usize = 3;
/// What the checkout UI may log directly. Logins and approvals are recorded by the shell itself.
const UI_ACTIONS: [&str; 3] = ["DRAWER_OPEN", "CASH_DROP", "ITEM_VOID"];
const REASON_REQUIRED: [&str; 3] = ["DRAWER_OPEN", "CASH_DROP", "PRICE_OVERRIDE"];

pub fn migrate(conn: &Connection) -> Result<(), String> {
    conn.execute_batch(
        "
        CREATE TABLE IF NOT EXISTS audit_events (
            id TEXT PRIMARY KEY,
            occurred_at TEXT NOT NULL,
            action_type TEXT NOT NULL,
            action TEXT NOT NULL,
            user_id TEXT NOT NULL,
            user_name TEXT NOT NULL,
            approver_id TEXT,
            store_id TEXT NOT NULL,
            target_entity TEXT NOT NULL,
            target_entity_id TEXT,
            reason_notes TEXT,
            old_values TEXT,
            new_values TEXT,
            details TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'synced', 'rejected')),
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_audit_events_status ON audit_events (status, occurred_at);
        CREATE TRIGGER IF NOT EXISTS audit_events_no_edit
        BEFORE UPDATE OF id, occurred_at, action_type, action, user_id, approver_id, store_id, target_entity,
            target_entity_id, reason_notes, old_values, new_values, details ON audit_events
        BEGIN
            SELECT RAISE(ABORT, 'audit events are append-only');
        END;
        CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
        BEFORE DELETE ON audit_events WHEN OLD.status = 'pending'
        BEGIN
            SELECT RAISE(ABORT, 'pending audit events cannot be deleted');
        END;
        ",
    )
    .map_err(|err| err.to_string())
}

/// What the checkout UI sends for a drawer open, cash drop, or item void.
#[derive(Debug, Deserialize)]
pub struct AuditInput {
    pub action_type: String,
    pub action: String,
    pub target_entity: String,
    pub target_entity_id: Option<String>,
    pub reason_notes: Option<String>,
    pub approver_id: Option<String>,
    pub old_values: Option<Value>,
    pub new_values: Option<Value>,
    #[serde(default)]
    pub details: Option<Value>,
}

#[derive(Serialize)]
pub struct LocalAuditEvent {
    id: String,
    occurred_at: String,
    action_type: String,
    action: String,
    user_name: String,
    reason_notes: Option<String>,
    details: Value,
    status: String,
    last_error: Option<String>,
}

#[derive(Serialize, Default)]
pub struct AuditStatus {
    pub pending: i64,
    pub rejected: i64,
    pub last_error: Option<String>,
}

#[derive(Deserialize)]
struct Rejection {
    id: String,
    reason: String,
}

#[derive(Deserialize)]
struct SyncResult {
    accepted: Vec<String>,
    duplicates: Vec<String>,
    rejected: Vec<Rejection>,
}

pub fn new_id() -> String {
    let mut bytes = [0u8; 16];
    OsRng.fill_bytes(&mut bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    let hex: String = bytes.iter().map(|byte| format!("{byte:02x}")).collect();
    format!("{}-{}-{}-{}-{}", &hex[0..8], &hex[8..12], &hex[12..16], &hex[16..20], &hex[20..32])
}

fn clean(text: Option<&str>) -> Option<String> {
    text.map(|value| value.split_whitespace().collect::<Vec<_>>().join(" "))
        .filter(|value| !value.is_empty())
}

fn valid_key(value: &str, max: usize, allowed: impl Fn(char) -> bool) -> bool {
    !value.is_empty() && value.len() <= max && value.chars().all(allowed)
}

/// Validates and stores one event. Mirrors the server's rules so a queued event is never rejected later.
pub fn record(db: &Db, session: &Session, store_id: &str, input: AuditInput) -> Result<String, String> {
    let reason = clean(input.reason_notes.as_deref());
    if REASON_REQUIRED.contains(&input.action_type.as_str())
        && reason.as_deref().map_or(0, |text| text.chars().count()) < REASON_MIN_CHARS
    {
        return Err("Enter a reason for this action.".into());
    }
    if reason.as_deref().is_some_and(|text| text.chars().count() > 1000) {
        return Err("Keep the reason under 1000 characters.".into());
    }
    if !valid_key(&input.action, 64, |c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_' || c == '.') {
        return Err("Invalid audit action key.".into());
    }
    if !valid_key(&input.target_entity, 40, |c| c.is_ascii_alphabetic()) {
        return Err("Invalid audit target.".into());
    }
    let id = new_id();
    let details = input.details.unwrap_or_else(|| Value::Object(Default::default()));
    if !details.is_object() {
        return Err("Audit details must be an object.".into());
    }
    let json = |value: Option<Value>| value.map(|item| item.to_string());
    db.transaction(|tx| {
        tx.execute(
            "INSERT INTO audit_events (id, occurred_at, action_type, action, user_id, user_name, approver_id, store_id,
                target_entity, target_entity_id, reason_notes, old_values, new_values, details)
             VALUES (?1, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13)",
            params![
                id,
                input.action_type,
                input.action,
                session.user.id,
                session.user.full_name,
                input.approver_id,
                store_id,
                input.target_entity,
                input.target_entity_id,
                reason,
                json(input.old_values),
                json(input.new_values),
                details.to_string(),
            ],
        )
        .map_err(|err| err.to_string())?;
        Ok(())
    })?;
    Ok(id)
}

/// Entry point for the checkout UI; only register-floor actions are accepted from it.
pub fn record_from_ui(db: &Db, session: &Session, store_id: &str, input: AuditInput) -> Result<String, String> {
    if !UI_ACTIONS.contains(&input.action_type.as_str()) {
        return Err("This action cannot be logged from the register screen.".into());
    }
    if input.approver_id.is_some() {
        return Err("Approvals are recorded when the manager enters their PIN.".into());
    }
    record(db, session, store_id, input)
}

/// An unlock the server never saw: the register checked the PIN against its cached verifier.
pub fn record_offline_login(db: &Db, session: &Session, store_id: &str) -> Result<(), String> {
    record(
        db,
        session,
        store_id,
        AuditInput {
            action_type: "LOGIN_PIN".into(),
            action: "auth.pin_offline".into(),
            target_entity: "User".into(),
            target_entity_id: Some(session.user.id.clone()),
            reason_notes: None,
            approver_id: None,
            old_values: None,
            new_values: None,
            details: Some(serde_json::json!({ "mode": "offline", "role": session.user.role_name })),
        },
    )
    .map(|_| ())
}

/// A manager authorised something on this register without taking it over.
pub fn record_manager_override(
    db: &Db,
    session: &Session,
    store_id: &str,
    approver_id: &str,
    approver_name: &str,
    permission: &str,
) -> Result<(), String> {
    let scope = match permission {
        "pos:price_override" => "price_override",
        "pos:below_floor_override" => "below_floor",
        "pos:discount" => "discount",
        "customers:manage" => "credit_limit",
        "returns:refund" => "refund",
        _ => "other",
    };
    record(
        db,
        session,
        store_id,
        AuditInput {
            action_type: "MANAGER_OVERRIDE".into(),
            action: format!("approval.{scope}"),
            target_entity: "Register".into(),
            target_entity_id: None,
            reason_notes: None,
            approver_id: Some(approver_id.to_string()),
            old_values: None,
            new_values: None,
            details: Some(serde_json::json!({ "permission": permission, "approver_name": approver_name })),
        },
    )
    .map(|_| ())
}

pub fn recent(db: &Db, limit: i64) -> Result<Vec<LocalAuditEvent>, String> {
    db.read(|conn| {
        let mut statement = conn
            .prepare(
                "SELECT id, occurred_at, action_type, action, user_name, reason_notes, details, status, last_error
                 FROM audit_events ORDER BY occurred_at DESC LIMIT ?1",
            )
            .map_err(|err| err.to_string())?;
        let rows = statement
            .query_map(params![limit], |row| {
                let details: String = row.get(6)?;
                Ok(LocalAuditEvent {
                    id: row.get(0)?,
                    occurred_at: row.get(1)?,
                    action_type: row.get(2)?,
                    action: row.get(3)?,
                    user_name: row.get(4)?,
                    reason_notes: row.get(5)?,
                    details: serde_json::from_str(&details).unwrap_or(Value::Null),
                    status: row.get(7)?,
                    last_error: row.get(8)?,
                })
            })
            .map_err(|err| err.to_string())?;
        rows.collect::<rusqlite::Result<Vec<_>>>().map_err(|err| err.to_string())
    })
}

pub fn status(db: &Db) -> Result<AuditStatus, String> {
    db.read(|conn| {
        conn.query_row(
            "SELECT
                COALESCE(SUM(status = 'pending'), 0),
                COALESCE(SUM(status = 'rejected'), 0),
                (SELECT last_error FROM audit_events WHERE last_error IS NOT NULL ORDER BY occurred_at DESC LIMIT 1)
             FROM audit_events",
            [],
            |row| {
                Ok(AuditStatus {
                    pending: row.get(0)?,
                    rejected: row.get(1)?,
                    last_error: row.get(2)?,
                })
            },
        )
        .map_err(|err| err.to_string())
    })
}

fn pending(conn: &Connection) -> Result<Vec<(String, Value)>, String> {
    let mut statement = conn
        .prepare(
            "SELECT id, occurred_at, action_type, action, user_id, approver_id, store_id, target_entity,
                    target_entity_id, reason_notes, old_values, new_values, details
             FROM audit_events WHERE status = 'pending' ORDER BY occurred_at LIMIT ?1",
        )
        .map_err(|err| err.to_string())?;
    let parse = |text: Option<String>| text.and_then(|value| serde_json::from_str::<Value>(&value).ok());
    let rows = statement
        .query_map(params![BATCH_SIZE], |row| {
            let id: String = row.get(0)?;
            let event = serde_json::json!({
                "id": id,
                "occurred_at": row.get::<_, String>(1)?,
                "action_type": row.get::<_, String>(2)?,
                "action": row.get::<_, String>(3)?,
                "user_id": row.get::<_, String>(4)?,
                "approver_id": row.get::<_, Option<String>>(5)?,
                "store_id": row.get::<_, String>(6)?,
                "target_entity": row.get::<_, String>(7)?,
                "target_entity_id": row.get::<_, Option<String>>(8)?,
                "reason_notes": row.get::<_, Option<String>>(9)?,
                "old_values": parse(row.get(10)?),
                "new_values": parse(row.get(11)?),
                "details": parse(row.get(12)?).unwrap_or_else(|| serde_json::json!({})),
            });
            Ok((id, event))
        })
        .map_err(|err| err.to_string())?;
    rows.collect::<rusqlite::Result<Vec<_>>>().map_err(|err| err.to_string())
}

fn mark(db: &Db, ids: &[String], state: &str, error: Option<&str>) -> Result<(), String> {
    db.transaction(|tx| {
        for id in ids {
            tx.execute(
                "UPDATE audit_events SET status = ?2, last_error = ?3, attempts = attempts + 1 WHERE id = ?1",
                params![id, state, error],
            )
            .map_err(|err| err.to_string())?;
        }
        Ok(())
    })
}

fn error_message(body: &str, status: u16) -> String {
    serde_json::from_str::<Value>(body)
        .ok()
        .and_then(|value| value.pointer("/error/message").and_then(Value::as_str).map(str::to_string))
        .unwrap_or_else(|| format!("Audit sync failed ({status})."))
}

/// Pushes pending events oldest-first. Stops at the first network or server failure so order is kept.
pub fn flush(db: &Db, config: &DesktopConfig) -> Result<AuditStatus, String> {
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(15))
        .build()
        .map_err(|err| err.to_string())?;
    for _ in 0..10 {
        let batch = db.read(pending)?;
        if batch.is_empty() {
            break;
        }
        let ids: Vec<String> = batch.iter().map(|(id, _)| id.clone()).collect();
        let payload = serde_json::json!({
            "device_id": config.device_id,
            "events": batch.into_iter().map(|(_, event)| event).collect::<Vec<_>>(),
        });
        let response = match client
            .post(format!("{}/api/v1/audit-logs/sync", config.api_base_url))
            .headers(config.auth_headers())
            .json(&payload)
            .send()
        {
            Ok(response) => response,
            Err(err) => {
                mark(db, &ids, "pending", Some(&format!("Offline: {err}")))?;
                break;
            }
        };
        let code = response.status().as_u16();
        let body = response.text().unwrap_or_default();
        if code == 422 {
            mark(db, &ids, "rejected", Some(&error_message(&body, code)))?;
            continue;
        }
        if !(200..300).contains(&code) {
            mark(db, &ids, "pending", Some(&error_message(&body, code)))?;
            break;
        }
        let result: SyncResult = serde_json::from_str(&body).map_err(|err| err.to_string())?;
        let mut done = result.accepted;
        done.extend(result.duplicates);
        mark(db, &done, "synced", None)?;
        for rejection in result.rejected {
            mark(db, &[rejection.id], "rejected", Some(&rejection.reason))?;
        }
    }
    status(db)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ids_are_v4_uuids() {
        let id = new_id();
        assert_eq!(id.len(), 36);
        assert_eq!(&id[14..15], "4");
        assert!(matches!(&id[19..20], "8" | "9" | "a" | "b"));
        assert_ne!(id, new_id());
    }

    #[test]
    fn events_are_append_only_until_synced() {
        let conn = Connection::open_in_memory().unwrap();
        migrate(&conn).unwrap();
        conn.execute(
            "INSERT INTO audit_events (id, occurred_at, action_type, action, user_id, user_name, store_id, target_entity)
             VALUES ('e1', '2026-10-19T10:00:00Z', 'DRAWER_OPEN', 'drawer.no_sale', 'u1', 'Cashier', 's1', 'CashDrawer')",
            [],
        )
        .unwrap();
        assert!(conn.execute("UPDATE audit_events SET reason_notes = 'edited' WHERE id = 'e1'", []).is_err());
        assert!(conn.execute("DELETE FROM audit_events WHERE id = 'e1'", []).is_err());
        conn.execute("UPDATE audit_events SET status = 'synced', attempts = 1 WHERE id = 'e1'", [])
            .unwrap();
        assert_eq!(conn.execute("DELETE FROM audit_events WHERE id = 'e1'", []).unwrap(), 1);
    }
}
