//! Register-local expenses. They are not sale events and they are not in `sync_queue`.
//! A row stays pending until the expenses API accepts the original payload.

use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

use crate::db::Db;

pub fn migrate(conn: &Connection) -> Result<(), String> {
    conn.execute_batch(
        "
        CREATE TABLE IF NOT EXISTS local_expenses (
            id TEXT PRIMARY KEY,
            idempotency_key TEXT NOT NULL UNIQUE,
            store_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            status TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '',
            attempts INTEGER NOT NULL DEFAULT 0,
            server_id TEXT NOT NULL DEFAULT '',
            total_cents INTEGER NOT NULL,
            paid_from TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS petty_cash_cache (
            store_id TEXT PRIMARY KEY,
            balance_cents INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        ",
    )
    .map_err(|err| err.to_string())
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Admission {
    pub status: &'static str,
    pub detail: &'static str,
    pub reserves_petty: bool,
}

pub fn admit(paid_from: &str, total_cents: i64, cached_petty_cents: Option<i64>) -> Admission {
    if paid_from != "PETTY_CASH" {
        return Admission {
            status: "pending_sync",
            detail: "Pending Sync. This is not posted in the accounting ledger until the server accepts it.",
            reserves_petty: false,
        };
    }
    match cached_petty_cents {
        None => Admission {
            status: "pending_review",
            detail: "Pending Review. Petty cash on this register is not known, so this is not a settled petty-cash posting.",
            reserves_petty: false,
        },
        Some(balance) if balance < total_cents => Admission {
            status: "pending_review",
            detail: "Pending Review. The downloaded petty-cash balance does not cover this amount, so it is not posted.",
            reserves_petty: false,
        },
        Some(_) => Admission {
            status: "pending_sync",
            detail: "Pending Sync. The downloaded petty-cash balance covers this amount. The ledger updates only after the server accepts it.",
            reserves_petty: true,
        },
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LocalExpense {
    pub id: String,
    pub idempotency_key: String,
    pub store_id: String,
    pub payload: Value,
    pub status: String,
    pub detail: String,
    pub error: String,
    pub attempts: i64,
    pub server_id: String,
    pub total_cents: i64,
    pub paid_from: String,
    pub created_at: i64,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LocalExpenseDraft {
    pub store_id: String,
    pub payload: Value,
    pub total_cents: i64,
    pub paid_from: String,
    pub idempotency_key: String,
}

fn now_secs() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|elapsed| elapsed.as_secs() as i64)
        .unwrap_or(0)
}

fn row(row: &rusqlite::Row<'_>) -> rusqlite::Result<LocalExpense> {
    let payload: String = row.get(3)?;
    Ok(LocalExpense {
        id: row.get(0)?,
        idempotency_key: row.get(1)?,
        store_id: row.get(2)?,
        payload: serde_json::from_str(&payload).unwrap_or(Value::Null),
        status: row.get(4)?,
        detail: row.get(5)?,
        error: row.get(6)?,
        attempts: row.get(7)?,
        server_id: row.get(8)?,
        total_cents: row.get(9)?,
        paid_from: row.get(10)?,
        created_at: row.get(11)?,
    })
}

const SELECT_ROW: &str = "SELECT id, idempotency_key, store_id, payload, status, detail, error, attempts, server_id, total_cents, paid_from, created_at FROM local_expenses";

pub fn cached_petty(db: &Db, store_id: &str) -> Result<Option<i64>, String> {
    let store_id = store_id.to_string();
    db.read(move |conn| {
        conn.query_row(
            "SELECT balance_cents FROM petty_cash_cache WHERE store_id = ?1",
            params![store_id],
            |row| row.get(0),
        )
        .optional()
        .map_err(|err| err.to_string())
    })
}

pub fn remember_petty(db: &Db, store_id: &str, balance_cents: i64) -> Result<(), String> {
    let store_id = store_id.trim().to_string();
    if store_id.is_empty() {
        return Err("A branch is required.".into());
    }
    let now = now_secs();
    db.transaction(move |tx| {
        tx.execute(
            "INSERT INTO petty_cash_cache (store_id, balance_cents, updated_at) VALUES (?1, ?2, ?3)
             ON CONFLICT(store_id) DO UPDATE SET balance_cents = excluded.balance_cents, updated_at = excluded.updated_at",
            params![store_id, balance_cents, now],
        )
        .map_err(|err| err.to_string())?;
        Ok(())
    })
}

pub fn save(db: &Db, draft: &LocalExpenseDraft) -> Result<LocalExpense, String> {
    let key = draft.idempotency_key.trim();
    if key.len() < 8 || !key.chars().all(|c| c.is_ascii_alphanumeric() || "._:-".contains(c)) {
        return Err("The expense needs a stable idempotency key.".into());
    }
    let store_id = draft.store_id.trim();
    if store_id.is_empty() {
        return Err("Choose a branch before saving an expense.".into());
    }
    if draft.total_cents < 1 {
        return Err("Enter the amount paid.".into());
    }
    let key = key.to_string();
    let store_id = store_id.to_string();
    let paid_from = draft.paid_from.trim().to_string();
    let total = draft.total_cents;
    let mut payload = draft.payload.clone();
    if let Some(object) = payload.as_object_mut() {
        object.insert("client_key".into(), json!(key));
        object.insert("store_id".into(), json!(store_id));
        object.insert("total_cents".into(), json!(total));
        object.insert("paid_from".into(), json!(paid_from));
    }
    let payload_text = payload.to_string();
    let cached = cached_petty(db, &store_id)?;
    let decision = admit(&paid_from, total, cached);
    let now = now_secs();
    db.transaction(move |tx| {
        let existing = tx
            .query_row(&format!("{SELECT_ROW} WHERE idempotency_key = ?1"), params![key], row)
            .optional()
            .map_err(|err| err.to_string())?;
        if let Some(existing) = existing {
            return Ok(existing);
        }
        let id = format!("local-{now}-{key}");
        if decision.reserves_petty {
            let updated = tx
                .execute(
                    "UPDATE petty_cash_cache SET balance_cents = balance_cents - ?1, updated_at = ?2
                     WHERE store_id = ?3 AND balance_cents >= ?1",
                    params![total, now, store_id, ],
                )
                .map_err(|err| err.to_string())?;
            if updated != 1 {
                return Err("The downloaded petty-cash balance changed. Save this expense again.".into());
            }
        }
        tx.execute(
            "INSERT INTO local_expenses (
                id, idempotency_key, store_id, payload, status, detail, error, attempts, server_id, total_cents, paid_from, created_at
             ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, '', 0, '', ?7, ?8, ?9)",
            params![id, key, store_id, payload_text, decision.status, decision.detail, total, paid_from, now],
        )
        .map_err(|err| err.to_string())?;
        tx.query_row(&format!("{SELECT_ROW} WHERE id = ?1"), params![id], row)
            .map_err(|err| err.to_string())
    })
}

pub fn list(db: &Db, store_id: &str) -> Result<Vec<LocalExpense>, String> {
    let store_id = store_id.trim().to_string();
    db.read(move |conn| {
        let mut statement = conn
            .prepare(&format!("{SELECT_ROW} WHERE store_id = ?1 OR ?1 = '' ORDER BY created_at DESC"))
            .map_err(|err| err.to_string())?;
        let rows = statement
            .query_map(params![store_id], row)
            .map_err(|err| err.to_string())?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|err| err.to_string())?;
        Ok(rows)
    })
}

pub fn pending(db: &Db) -> Result<Vec<LocalExpense>, String> {
    db.read(|conn| {
        let mut statement = conn
            .prepare(&format!("{SELECT_ROW} WHERE status = 'pending_sync' ORDER BY created_at"))
            .map_err(|err| err.to_string())?;
        let rows = statement
            .query_map([], row)
            .map_err(|err| err.to_string())?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|err| err.to_string())?;
        Ok(rows)
    })
}

pub fn mark_uploaded(db: &Db, id: &str, server_id: &str) -> Result<(), String> {
    let id = id.to_string();
    let server_id = server_id.to_string();
    db.transaction(move |tx| {
        tx.execute(
            "UPDATE local_expenses SET status = 'synced', server_id = ?2, error = '', detail = 'Synced. The server accepted this expense.'
             WHERE id = ?1 AND status = 'pending_sync'",
            params![id, server_id],
        )
        .map_err(|err| err.to_string())?;
        Ok(())
    })
}

pub fn mark_failed(db: &Db, id: &str, error: &str) -> Result<(), String> {
    let id = id.to_string();
    let error = error.to_string();
    db.transaction(move |tx| {
        tx.execute(
            "UPDATE local_expenses SET attempts = attempts + 1, error = ?2, status = 'failed'
             WHERE id = ?1 AND status = 'pending_sync'",
            params![id, error],
        )
        .map_err(|err| err.to_string())?;
        Ok(())
    })
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ExpenseFlush {
    pub uploaded: i64,
    pub pending: i64,
    pub failed: i64,
    pub message: String,
}

pub fn flush(db: &Db, config: &crate::sync::DesktopConfig, user_token: Option<&str>) -> Result<ExpenseFlush, String> {
    let kind = crate::connectivity::endpoint_kind(&config.api_base_url, !cfg!(debug_assertions));
    if !crate::connectivity::may_probe(kind) {
        let waiting = pending(db)?.len() as i64;
        return Ok(ExpenseFlush {
            uploaded: 0,
            pending: waiting,
            failed: 0,
            message: crate::connectivity::link_message(crate::connectivity::link_state(config.api_base_url.contains("not-activated") == false && !config.api_key.is_empty(), false, false), kind).into(),
        });
    }
    let rows = pending(db)?;
    let mut uploaded = 0i64;
    let mut failed = 0i64;
    for row in &rows {
        match post_expense(config, user_token, &row.payload) {
            Ok(server_id) => {
                mark_uploaded(db, &row.id, &server_id)?;
                uploaded += 1;
            }
            Err(UploadFault::Later(message)) => keep_pending(db, &row.id, &message)?,
            Err(UploadFault::Rejected(message)) => {
                mark_failed(db, &row.id, &message)?;
                failed += 1;
            }
        }
    }
    let waiting = pending(db)?.len() as i64;
    Ok(ExpenseFlush {
        uploaded,
        pending: waiting,
        failed,
        message: if uploaded > 0 {
            "The server accepted the pending expenses.".into()
        } else if waiting > 0 {
            crate::connectivity::OFFLINE_NOTICE.into()
        } else {
            "No expenses are waiting to sync.".into()
        },
    })
}

enum UploadFault {
    Later(String),
    Rejected(String),
}

fn post_expense(config: &crate::sync::DesktopConfig, user_token: Option<&str>, payload: &Value) -> Result<String, UploadFault> {
    let client = reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(20))
        .build()
        .map_err(|err| UploadFault::Later(err.to_string()))?;
    let mut request = client
        .post(format!("{}/api/v1/expenses", config.api_base_url.trim_end_matches('/')))
        .headers(config.auth_headers())
        .json(payload);
    if let Some(token) = user_token {
        if !token.is_empty() {
            request = request.header("Authorization", format!("Bearer {token}"));
        }
    }
    let response = request.send().map_err(|err| UploadFault::Later(format!("The server is unreachable: {err}")))?;
    let status = response.status();
    let body: Value = response.json().unwrap_or(Value::Null);
    if status.is_success() {
        return Ok(body["id"].as_str().unwrap_or("").to_string());
    }
    let message = body["error"]["message"].as_str().unwrap_or("The server refused the expense.").to_string();
    if status.is_server_error() || status.as_u16() == 401 || status.as_u16() == 429 {
        return Err(UploadFault::Later(message));
    }
    Err(UploadFault::Rejected(message))
}

pub fn keep_pending(db: &Db, id: &str, error: &str) -> Result<(), String> {
    let id = id.to_string();
    let error = error.to_string();
    db.transaction(move |tx| {
        tx.execute(
            "UPDATE local_expenses SET attempts = attempts + 1, error = ?2 WHERE id = ?1 AND status = 'pending_sync'",
            params![id, error],
        )
        .map_err(|err| err.to_string())?;
        Ok(())
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn db() -> Db {
        let path = std::env::temp_dir().join(format!(
            "aipos-expense-{}.sqlite",
            std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos()
        ));
        Db::open(&path).unwrap()
    }

    #[test]
    fn petty_cash_without_a_downloaded_balance_is_not_a_posting() {
        assert_eq!(admit("BANK", 100, None).status, "pending_sync");
        assert!(!admit("BANK", 100, None).reserves_petty);
        assert_eq!(admit("PETTY_CASH", 100, None).status, "pending_review");
        assert_eq!(admit("PETTY_CASH", 100, Some(50)).status, "pending_review");
        assert!(admit("PETTY_CASH", 100, Some(100)).reserves_petty);
    }

    #[test]
    fn a_local_expense_survives_and_a_repeat_does_not_create_another_row() {
        let db = db();
        remember_petty(&db, "store-1", 500).unwrap();
        let draft = LocalExpenseDraft {
            store_id: "store-1".into(),
            payload: json!({"description": "Tea", "spent_on": "2026-11-25", "category": "OFFICE"}),
            total_cents: 200,
            paid_from: "PETTY_CASH".into(),
            idempotency_key: "expense-key-1".into(),
        };
        let saved = save(&db, &draft).unwrap();
        assert_eq!(saved.status, "pending_sync");
        assert_eq!(cached_petty(&db, "store-1").unwrap(), Some(300));
        let again = save(&db, &draft).unwrap();
        assert_eq!(again.id, saved.id);
        assert_eq!(cached_petty(&db, "store-1").unwrap(), Some(300));
        assert_eq!(list(&db, "store-1").unwrap().len(), 1);
        assert_eq!(pending(&db).unwrap().len(), 1);
        mark_uploaded(&db, &saved.id, "server-1").unwrap();
        assert!(pending(&db).unwrap().is_empty());
        assert_eq!(list(&db, "store-1").unwrap()[0].status, "synced");
        let unknown = LocalExpenseDraft {
            paid_from: "PETTY_CASH".into(),
            store_id: "store-2".into(),
            idempotency_key: "expense-key-2".into(),
            ..draft
        };
        assert_eq!(save(&db, &unknown).unwrap().status, "pending_review");
        assert!(pending(&db).unwrap().is_empty());
    }
}
