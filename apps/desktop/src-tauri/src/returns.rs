use std::collections::{HashMap, HashSet};
use std::sync::Mutex;
use std::time::Duration;

use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::auth::{self, CashierProfile, Session};
use crate::db::{self, Db, QueuedEvent};
use crate::sync::DesktopConfig;

const POS_REFUND: &str = "pos:refund";
/// A manager approval covers one return started within this many seconds of the PIN entry.
const APPROVAL_TTL_SECS: i64 = 10 * 60;

/// Manager approvals verified on this register, keyed by approver id, valued by verification time.
pub type Approvals = Mutex<HashMap<String, i64>>;

pub fn migrate(conn: &Connection) -> Result<(), String> {
    conn.execute_batch(
        "
        CREATE TABLE IF NOT EXISTS receipt_cache (
            sale_id TEXT PRIMARY KEY,
            client_sale_id TEXT NOT NULL,
            invoice TEXT NOT NULL,
            payload TEXT NOT NULL,
            pending_return_ids TEXT NOT NULL DEFAULT '[]',
            fetched_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_receipt_cache_invoice ON receipt_cache (invoice);
        CREATE TABLE IF NOT EXISTS local_returns (
            id TEXT PRIMARY KEY,
            sale_id TEXT NOT NULL,
            batch_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_local_returns_sale ON local_returns (sale_id);
        ",
    )
    .map_err(|err| err.to_string())
}

#[derive(Debug, Clone, Serialize)]
pub struct LocalReturn {
    pub id: String,
    pub sale_id: String,
    pub batch_id: String,
    pub status: String,
    pub error: Option<String>,
    pub created_at: i64,
    pub payload: Value,
}

/// `receipt` comes from the API or the register cache; `queued_sale` is a sale rung up here that the API has not
/// seen yet. `local_returns` lists returns made on this register that the receipt does not reflect yet.
#[derive(Serialize)]
pub struct ReceiptLookup {
    source: &'static str,
    receipt: Option<Value>,
    queued_sale: Option<Value>,
    local_returns: Vec<LocalReturn>,
    message: Option<String>,
}

enum Remote {
    Found(Value),
    NotFound(String),
    Refused(String),
    Unavailable(String),
}

#[derive(Deserialize)]
struct ErrorBody {
    error: ErrorDetail,
}

#[derive(Deserialize)]
struct ErrorDetail {
    message: String,
}

pub fn lookup(db: &Db, config: &DesktopConfig, code: &str) -> Result<ReceiptLookup, String> {
    let code = code.trim();
    let valid = (8..=64).contains(&code.len())
        && code.chars().all(|c| c.is_ascii_alphanumeric() || c == '-');
    if !valid {
        return Err(
            "Enter a receipt barcode or an invoice number of at least 8 characters.".into(),
        );
    }
    match fetch_receipt(config, code) {
        Remote::Found(receipt) => {
            let sale_id = text(&receipt, "sale_id")?;
            let pending: Vec<LocalReturn> = local_returns_for(db, &sale_id)?
                .into_iter()
                .filter(|item| item.status == "pending")
                .collect();
            cache_receipt(db, &receipt, &pending)?;
            Ok(ReceiptLookup {
                source: "api",
                receipt: Some(receipt),
                queued_sale: None,
                local_returns: pending,
                message: None,
            })
        }
        Remote::Refused(message) => Err(message),
        Remote::NotFound(message) => offline_lookup(db, code, None)?.ok_or(message),
        Remote::Unavailable(reason) => offline_lookup(db, code, Some(reason))?.ok_or_else(|| {
            "The server is unreachable and this receipt is not cached on this register.".into()
        }),
    }
}

fn offline_lookup(
    db: &Db,
    code: &str,
    reason: Option<String>,
) -> Result<Option<ReceiptLookup>, String> {
    let lowered = code.to_lowercase();
    let prefix = format!("{lowered}%");
    let cached: Vec<(String, String, String, i64)> = db.read(|conn| {
        let mut statement = conn
            .prepare(
                "SELECT sale_id, payload, pending_return_ids, fetched_at FROM receipt_cache
                 WHERE sale_id = ?1 OR client_sale_id = ?1 OR invoice = upper(?1) OR client_sale_id LIKE ?2 LIMIT 2",
            )
            .map_err(|err| err.to_string())?;
        let rows = statement
            .query_map(params![lowered, prefix], |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)))
            .map_err(|err| err.to_string())?;
        rows.collect::<rusqlite::Result<Vec<_>>>().map_err(|err| err.to_string())
    })?;
    if cached.len() > 1 {
        return Err("More than one cached sale matches. Scan the full receipt barcode.".into());
    }
    if let Some((sale_id, payload, pending_ids, fetched_at)) = cached.into_iter().next() {
        let excluded: HashSet<String> =
            serde_json::from_str(&pending_ids).map_err(|err| err.to_string())?;
        let local = local_returns_for(db, &sale_id)?
            .into_iter()
            .filter(|item| {
                item.status != "rejected"
                    && (item.created_at > fetched_at || excluded.contains(&item.id))
            })
            .collect();
        return Ok(Some(ReceiptLookup {
            source: "cache",
            receipt: Some(serde_json::from_str(&payload).map_err(|err| err.to_string())?),
            queued_sale: None,
            local_returns: local,
            message: reason,
        }));
    }

    let queued: Vec<String> = db.read(|conn| {
        let mut statement = conn
            .prepare(
                "SELECT payload FROM sync_queue
                 WHERE entity_type = 'sale' AND status <> 'rejected'
                   AND (json_extract(payload, '$.id') = ?1 OR json_extract(payload, '$.client_sale_id') LIKE ?2)
                 LIMIT 2",
            )
            .map_err(|err| err.to_string())?;
        let rows = statement
            .query_map(params![lowered, prefix], |row| row.get(0))
            .map_err(|err| err.to_string())?;
        rows.collect::<rusqlite::Result<Vec<_>>>().map_err(|err| err.to_string())
    })?;
    if queued.len() > 1 {
        return Err(
            "More than one sale on this register matches. Scan the full receipt barcode.".into(),
        );
    }
    let Some(payload) = queued.into_iter().next() else {
        return Ok(None);
    };
    let sale: Value = serde_json::from_str(&payload).map_err(|err| err.to_string())?;
    let sale_id = text(&sale, "id")?;
    let local = local_returns_for(db, &sale_id)?
        .into_iter()
        .filter(|item| item.status != "rejected")
        .collect();
    Ok(Some(ReceiptLookup {
        source: "register",
        receipt: None,
        queued_sale: Some(sale),
        local_returns: local,
        message: reason,
    }))
}

fn cache_receipt(db: &Db, receipt: &Value, pending: &[LocalReturn]) -> Result<(), String> {
    let sale_id = text(receipt, "sale_id")?;
    let invoice = text(receipt, "invoice")?;
    let client_sale_id = receipt
        .get("client_sale_id")
        .and_then(Value::as_str)
        .map(str::to_string)
        .unwrap_or_else(|| sale_id.clone());
    let payload = serde_json::to_string(receipt).map_err(|err| err.to_string())?;
    let pending_ids: Vec<&str> = pending.iter().map(|item| item.id.as_str()).collect();
    let pending_ids = serde_json::to_string(&pending_ids).map_err(|err| err.to_string())?;
    db.transaction(|tx| {
        tx.execute(
            "INSERT INTO receipt_cache (sale_id, client_sale_id, invoice, payload, pending_return_ids, fetched_at)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6)
             ON CONFLICT(sale_id) DO UPDATE SET
                payload = excluded.payload,
                pending_return_ids = excluded.pending_return_ids,
                fetched_at = excluded.fetched_at",
            params![sale_id, client_sale_id, invoice, payload, pending_ids, auth::now_secs()],
        )
        .map_err(|err| err.to_string())?;
        Ok(())
    })
}

const LOCAL_RETURN_COLUMNS: &str = "lr.id, lr.sale_id, lr.batch_id, lr.payload, lr.created_at,
    COALESCE((SELECT status FROM sync_queue q WHERE q.batch_id = lr.batch_id ORDER BY rowid DESC LIMIT 1), 'pending'),
    (SELECT last_error FROM sync_queue q WHERE q.batch_id = lr.batch_id ORDER BY rowid DESC LIMIT 1)";

fn read_local_return(row: &rusqlite::Row<'_>) -> rusqlite::Result<(LocalReturn, String)> {
    let payload: String = row.get(3)?;
    Ok((
        LocalReturn {
            id: row.get(0)?,
            sale_id: row.get(1)?,
            batch_id: row.get(2)?,
            created_at: row.get(4)?,
            status: row.get(5)?,
            error: row.get(6)?,
            payload: Value::Null,
        },
        payload,
    ))
}

fn hydrate(rows: Vec<(LocalReturn, String)>) -> Result<Vec<LocalReturn>, String> {
    rows.into_iter()
        .map(|(mut item, payload)| {
            item.payload = serde_json::from_str(&payload).map_err(|err| err.to_string())?;
            Ok(item)
        })
        .collect()
}

fn local_returns_for(db: &Db, sale_id: &str) -> Result<Vec<LocalReturn>, String> {
    let rows = db.read(|conn| {
        let mut statement = conn
            .prepare(&format!(
                "SELECT {LOCAL_RETURN_COLUMNS} FROM local_returns lr WHERE lr.sale_id = ?1 ORDER BY lr.created_at"
            ))
            .map_err(|err| err.to_string())?;
        let rows = statement
            .query_map(params![sale_id], read_local_return)
            .map_err(|err| err.to_string())?;
        rows.collect::<rusqlite::Result<Vec<_>>>().map_err(|err| err.to_string())
    })?;
    hydrate(rows)
}

pub fn recent(db: &Db, limit: i64) -> Result<Vec<LocalReturn>, String> {
    let rows = db.read(|conn| {
        let mut statement = conn
            .prepare(&format!(
                "SELECT {LOCAL_RETURN_COLUMNS} FROM local_returns lr ORDER BY lr.created_at DESC LIMIT ?1"
            ))
            .map_err(|err| err.to_string())?;
        let rows = statement
            .query_map(params![limit], read_local_return)
            .map_err(|err| err.to_string())?;
        rows.collect::<rusqlite::Result<Vec<_>>>().map_err(|err| err.to_string())
    })?;
    hydrate(rows)
}

/// Verifies a manager PIN (online first, then the register's Argon2 cache) without switching the session.
pub fn approve(
    db: &Db,
    config: &DesktopConfig,
    approvals: &Approvals,
    session: &Session,
    username: &str,
    pin: &str,
) -> Result<CashierProfile, String> {
    let approver = auth::pin_login(db, config, username, pin)?.user;
    if approver.id == session.user.id {
        return Err("Approval must come from a different staff member.".into());
    }
    if !approver.permissions.iter().any(|item| item == POS_REFUND) {
        return Err(format!("{} cannot approve refunds.", approver.full_name));
    }
    if let (Some(store), Some(own)) = (&session.user.store_id, &approver.store_id) {
        if store != own {
            return Err(format!(
                "{} is not assigned to this store.",
                approver.full_name
            ));
        }
    }
    approvals
        .lock()
        .map_err(|err| err.to_string())?
        .insert(approver.id.clone(), auth::now_secs());
    Ok(approver)
}

/// Queues one return and mirrors it in `local_returns` in the same transaction.
pub fn enqueue(
    db: &Db,
    approvals: &Approvals,
    session: &Session,
    batch_id: &str,
    events: &[QueuedEvent],
) -> Result<(), String> {
    let [event] = events else {
        return Err("A return is queued as exactly one event.".into());
    };
    if event.entity_type != "sale_return" {
        return Err("Only returns can be queued here.".into());
    }
    let payload = &event.payload;
    if payload.get("cashier_id").and_then(Value::as_str) != Some(session.user.id.as_str()) {
        return Err(
            "The return must be attributed to the cashier who unlocked this register.".into(),
        );
    }
    if let Some(store) = &session.user.store_id {
        if payload.get("store_id").and_then(Value::as_str) != Some(store.as_str()) {
            return Err("Returns can only be processed for this cashier's store.".into());
        }
    }
    let approver = match payload.get("override").filter(|value| !value.is_null()) {
        None => None,
        Some(value) => Some(text(value, "approved_by_id")?),
    };
    let mut guard = approvals.lock().map_err(|err| err.to_string())?;
    if let Some(approver) = &approver {
        let fresh = guard
            .get(approver)
            .is_some_and(|verified| auth::now_secs() - verified <= APPROVAL_TTL_SECS);
        if !fresh {
            return Err(
                "Manager approval expired. Ask the manager to enter their PIN again.".into(),
            );
        }
    }

    let return_id = text(payload, "id")?;
    let sale_id = text(payload, "original_sale_id")?;
    let serialized = serde_json::to_string(payload).map_err(|err| err.to_string())?;
    db.transaction(|tx| {
        db::insert_events(tx, batch_id, events)?;
        tx.execute(
            "INSERT INTO local_returns (id, sale_id, batch_id, payload, created_at) VALUES (?1, ?2, ?3, ?4, ?5)",
            params![return_id, sale_id, batch_id, serialized, auth::now_secs()],
        )
        .map_err(|err| err.to_string())?;
        Ok(())
    })?;
    if let Some(approver) = approver {
        guard.remove(&approver);
    }
    Ok(())
}

fn fetch_receipt(config: &DesktopConfig, code: &str) -> Remote {
    let Ok(client) = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(8))
        .build()
    else {
        return Remote::Unavailable("Could not start the HTTP client.".into());
    };
    let response = client
        .get(format!(
            "{}/api/v1/returns/receipts/{code}",
            config.api_base_url
        ))
        .headers(config.auth_headers())
        .send();
    let response = match response {
        Ok(response) => response,
        Err(err) => return Remote::Unavailable(err.to_string()),
    };
    let status = response.status().as_u16();
    let body = match response.text() {
        Ok(body) => body,
        Err(err) => return Remote::Unavailable(err.to_string()),
    };
    let message = || {
        serde_json::from_str::<ErrorBody>(&body)
            .map(|parsed| parsed.error.message)
            .unwrap_or_else(|_| format!("Request failed ({status})."))
    };
    match status {
        200 => serde_json::from_str(&body)
            .map(Remote::Found)
            .unwrap_or_else(|err| Remote::Unavailable(err.to_string())),
        404 => Remote::NotFound(message()),
        401 | 403 | 409 | 422 => Remote::Refused(message()),
        _ => Remote::Unavailable(message()),
    }
}

fn text(value: &Value, field: &str) -> Result<String, String> {
    value
        .get(field)
        .and_then(Value::as_str)
        .map(str::to_string)
        .ok_or_else(|| format!("Payload is missing {field}."))
}
