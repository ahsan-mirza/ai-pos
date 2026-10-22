use std::collections::HashMap;
use std::time::Duration;

use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

use crate::auth::Session;
use crate::db::{insert_events, Db, QueuedEvent};
use crate::sync::DesktopConfig;

const PRICE_TIERS: [&str; 4] = ["RETAIL", "TIER_1", "TIER_2", "DISTRIBUTOR"];
const PAYMENT_TERMS: [&str; 4] = ["DUE_ON_RECEIPT", "NET_15", "NET_30", "NET_60"];
const CUSTOMERS_MANAGE: &str = "customers:manage";

pub fn migrate(conn: &Connection) -> Result<(), String> {
    conn.execute_batch(
        "
        CREATE TABLE IF NOT EXISTS customers (
            id TEXT PRIMARY KEY,
            search_text TEXT NOT NULL,
            customer_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            fetched_at INTEGER NOT NULL
        );
        ",
    )
    .map_err(|err| err.to_string())?;
    // Customers added at this register stay in the cache until the server's list includes them.
    let has_local_flag = conn
        .query_row(
            "SELECT 1 FROM pragma_table_info('customers') WHERE name = 'local_only'",
            [],
            |_| Ok(()),
        )
        .optional()
        .map_err(|err| err.to_string())?
        .is_some();
    if !has_local_flag {
        conn.execute(
            "ALTER TABLE customers ADD COLUMN local_only INTEGER NOT NULL DEFAULT 0",
            [],
        )
        .map_err(|err| err.to_string())?;
    }
    Ok(())
}

#[derive(Deserialize)]
pub struct NewCustomer {
    pub id: String,
    pub name: String,
    pub phone: Option<String>,
    pub email: Option<String>,
    pub customer_type: String,
    pub company_name: Option<String>,
    pub trn_vat_number: Option<String>,
    pub price_tier: String,
    pub credit_limit_cents: i64,
    pub payment_terms: String,
    pub at: String,
    #[serde(default)]
    pub birthday: Option<String>,
    #[serde(default)]
    pub gender: Option<String>,
    #[serde(default)]
    pub notes: Option<String>,
}

fn cleaned(value: &Option<String>, max: usize) -> Option<String> {
    value
        .as_deref()
        .map(str::trim)
        .filter(|text| !text.is_empty())
        .map(|text| text.chars().take(max).collect())
}

/// Adds a customer at the register: cached at once so the sale can carry it offline, and queued as a `customer`
/// sync event. Credit terms and discounted tiers need customers:manage, as on the server.
pub fn create(db: &Db, session: &Session, input: &NewCustomer) -> Result<Value, String> {
    if input.id.len() != 36 || !input.id.chars().all(|c| c.is_ascii_hexdigit() || c == '-') {
        return Err("Customer id must be a UUID.".into());
    }
    let name: String = input.name.trim().chars().take(120).collect();
    if name.is_empty() {
        return Err("Enter the customer's name.".into());
    }
    let wholesale = input.customer_type == "WHOLESALE";
    if !wholesale && input.customer_type != "RETAIL" {
        return Err("Choose retail or wholesale.".into());
    }
    let company = cleaned(&input.company_name, 160);
    if wholesale && company.is_none() {
        return Err("Wholesale customers need a company name.".into());
    }
    let trusted = session
        .user
        .permissions
        .iter()
        .any(|item| item == CUSTOMERS_MANAGE);
    let (tier, credit, terms) = if wholesale && trusted {
        if !PRICE_TIERS.contains(&input.price_tier.as_str())
            || !PAYMENT_TERMS.contains(&input.payment_terms.as_str())
        {
            return Err("Choose a price tier and payment terms.".into());
        }
        (
            input.price_tier.clone(),
            input.credit_limit_cents.clamp(0, 10_000_000_000),
            input.payment_terms.clone(),
        )
    } else {
        ("RETAIL".to_string(), 0, "DUE_ON_RECEIPT".to_string())
    };
    let payload = json!({
        "id": input.id,
        "created_by_id": session.user.id,
        "name": name,
        "phone": cleaned(&input.phone, 40),
        "email": cleaned(&input.email, 254),
        "customer_type": input.customer_type,
        "company_name": if wholesale { company.clone() } else { None },
        "trn_vat_number": if wholesale { cleaned(&input.trn_vat_number, 32) } else { None },
        "price_tier": tier,
        "credit_limit_cents": credit,
        "payment_terms": terms,
        "birthday": cleaned(&input.birthday, 10),
        "gender": cleaned(&input.gender, 12),
        "notes": cleaned(&input.notes, 500),
    });
    let mut display = payload.clone();
    if let Some(object) = display.as_object_mut() {
        object.remove("created_by_id");
        for (key, value) in [
            ("code", json!("NEW")),
            ("current_balance_cents", json!(0)),
            ("available_credit_cents", json!(credit)),
            ("address", Value::Null),
            ("is_active", json!(true)),
            ("overdue_cents", json!(0)),
            ("open_invoice_count", json!(0)),
            ("cheque_exposure_cents", json!(0)),
            ("credit_hold", json!(false)),
            ("credit_hold_reason", Value::Null),
            ("whatsapp_opt_in", json!(false)),
            ("sms_opt_in", json!(false)),
            ("email_opt_in", json!(false)),
            ("loyalty_points", json!(0)),
            ("pending_on_account_cents", json!(0)),
            ("created_at", json!(input.at)),
            ("updated_at", json!(input.at)),
        ] {
            object.insert(key.into(), value);
        }
    }
    let key = format!("customer-{}", input.id);
    db.transaction(|tx| {
        tx.execute(
            "INSERT INTO customers (id, search_text, customer_type, payload, fetched_at, local_only)
             VALUES (?1, ?2, ?3, ?4, strftime('%s','now'), 1)",
            params![input.id, search_text(&display), input.customer_type, display.to_string()],
        )
        .map_err(|err| err.to_string())?;
        insert_events(
            tx,
            &key,
            &[QueuedEvent {
                id: key.clone(),
                idempotency_key: key.clone(),
                entity_type: "customer".into(),
                operation: "upsert".into(),
                payload,
                occurred_at: input.at.clone(),
            }],
        )
    })?;
    Ok(display)
}

#[derive(Serialize)]
pub struct CustomerSnapshot {
    pub customers: Vec<Value>,
    pub source: &'static str,
    pub message: Option<String>,
}

/// Replaces the offline customer cache from the API; falls back to the cache when the API is unreachable.
pub fn refresh(db: &Db, config: &DesktopConfig) -> Result<CustomerSnapshot, String> {
    match fetch(config) {
        Ok(customers) => {
            db.transaction(|tx| {
                tx.execute("DELETE FROM customers WHERE local_only = 0", []).map_err(|err| err.to_string())?;
                for customer in &customers {
                    let id = customer.get("id").and_then(Value::as_str).unwrap_or_default();
                    let kind = customer.get("customer_type").and_then(Value::as_str).unwrap_or("RETAIL");
                    tx.execute(
                        "INSERT OR REPLACE INTO customers (id, search_text, customer_type, payload, fetched_at, local_only)
                         VALUES (?1, ?2, ?3, ?4, strftime('%s','now'), 0)",
                        params![id, search_text(customer), kind, customer.to_string()],
                    )
                    .map_err(|err| err.to_string())?;
                }
                Ok(())
            })?;
            Ok(CustomerSnapshot {
                customers: with_pending(db, customers)?,
                source: "api",
                message: None,
            })
        }
        Err(reason) => Ok(CustomerSnapshot {
            customers: search(db, "", 500)?,
            source: "cache",
            message: Some(reason),
        }),
    }
}

/// Matches name, company, code, phone, or TRN. Balances include on-account sales still waiting to sync.
pub fn search(db: &Db, query: &str, limit: i64) -> Result<Vec<Value>, String> {
    let like = format!(
        "%{}%",
        query
            .trim()
            .to_lowercase()
            .replace('%', "")
            .replace('_', "")
    );
    let rows: Vec<String> = db.read(|conn| {
        let mut statement = conn
            .prepare(
                "SELECT payload FROM customers WHERE search_text LIKE ?1
                 ORDER BY customer_type DESC, search_text LIMIT ?2",
            )
            .map_err(|err| err.to_string())?;
        let rows = statement
            .query_map(params![like, limit], |row| row.get::<_, String>(0))
            .map_err(|err| err.to_string())?;
        rows.collect::<rusqlite::Result<Vec<_>>>()
            .map_err(|err| err.to_string())
    })?;
    let customers = rows
        .iter()
        .filter_map(|raw| serde_json::from_str::<Value>(raw).ok())
        .collect();
    with_pending(db, customers)
}

fn with_pending(db: &Db, customers: Vec<Value>) -> Result<Vec<Value>, String> {
    let pending = pending_on_account(db)?;
    Ok(customers
        .into_iter()
        .map(|mut customer| {
            let id = customer
                .get("id")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_string();
            let extra = pending.get(&id).copied().unwrap_or(0);
            if let Some(object) = customer.as_object_mut() {
                let balance = object
                    .get("current_balance_cents")
                    .and_then(Value::as_i64)
                    .unwrap_or(0)
                    + extra;
                let limit = object
                    .get("credit_limit_cents")
                    .and_then(Value::as_i64)
                    .unwrap_or(0);
                object.insert("current_balance_cents".into(), Value::from(balance));
                object.insert(
                    "available_credit_cents".into(),
                    Value::from(limit - balance),
                );
                object.insert("pending_on_account_cents".into(), Value::from(extra));
            }
            customer
        })
        .collect())
}

/// On-account amounts per customer in sales queued on this register but not yet accepted by the API.
fn pending_on_account(db: &Db) -> Result<HashMap<String, i64>, String> {
    db.read(|conn| {
        let mut statement = conn
            .prepare(
                "SELECT json_extract(q.payload, '$.customer_id'), SUM(json_extract(t.value, '$.amount_cents'))
                 FROM sync_queue q, json_each(q.payload, '$.tenders') t
                 WHERE q.entity_type = 'sale' AND q.status = 'pending'
                   AND json_extract(t.value, '$.method') = 'on_account'
                   AND json_extract(q.payload, '$.customer_id') IS NOT NULL
                 GROUP BY 1",
            )
            .map_err(|err| err.to_string())?;
        let rows = statement
            .query_map([], |row| Ok((row.get::<_, String>(0)?, row.get::<_, i64>(1)?)))
            .map_err(|err| err.to_string())?;
        rows.collect::<rusqlite::Result<HashMap<_, _>>>().map_err(|err| err.to_string())
    })
}

fn search_text(customer: &Value) -> String {
    [
        "name",
        "company_name",
        "code",
        "phone",
        "trn_vat_number",
        "email",
    ]
    .iter()
    .filter_map(|field| customer.get(*field).and_then(Value::as_str))
    .collect::<Vec<_>>()
    .join(" ")
    .to_lowercase()
}

fn fetch(config: &DesktopConfig) -> Result<Vec<Value>, String> {
    let response = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(8))
        .build()
        .map_err(|err| err.to_string())?
        .get(format!("{}/api/v1/customers/sync", config.api_base_url))
        .headers(config.auth_headers())
        .send()
        .map_err(|err| format!("The server is unreachable: {err}"))?;
    let status = response.status();
    if !status.is_success() {
        return Err(format!("Customer sync failed ({}).", status.as_u16()));
    }
    response.json().map_err(|err| err.to_string())
}
