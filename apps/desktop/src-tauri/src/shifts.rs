use std::collections::BTreeMap;

use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

use crate::auth::Session;
use crate::db::{insert_events, Db, QueuedEvent};

/// Shifts live on the register so a cashier can open, take cash, and close with the network down.
/// Every change is also queued as a `register_shift` / `cash_movement` sync event; the API recomputes the
/// Z report from what actually synced, so the figures here are the register's own view.
pub fn migrate(conn: &Connection) -> Result<(), String> {
    conn.execute_batch(
        "
        CREATE TABLE IF NOT EXISTS local_shifts (
            id TEXT PRIMARY KEY,
            opened_at TEXT NOT NULL,
            opened_by_id TEXT NOT NULL,
            opened_by_name TEXT NOT NULL,
            opening_float_cents INTEGER NOT NULL,
            currency TEXT NOT NULL,
            status TEXT NOT NULL,
            closed_at TEXT,
            closed_by_name TEXT,
            counted_cash_cents INTEGER,
            expected_cash_cents INTEGER,
            z_number TEXT
        );
        CREATE TABLE IF NOT EXISTS local_cash_movements (
            id TEXT PRIMARY KEY,
            shift_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            amount_cents INTEGER NOT NULL,
            reason TEXT NOT NULL,
            user_name TEXT NOT NULL,
            occurred_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS local_cash_movements_shift ON local_cash_movements (shift_id);
        ",
    )
    .map_err(|err| err.to_string())
}

#[derive(Clone, Serialize)]
pub struct LocalShift {
    pub id: String,
    pub opened_at: String,
    pub opened_by_name: String,
    pub opening_float_cents: i64,
    pub currency: String,
    pub status: String,
    pub closed_at: Option<String>,
    pub closed_by_name: Option<String>,
    pub counted_cash_cents: Option<i64>,
    pub expected_cash_cents: Option<i64>,
    pub z_number: Option<String>,
}

#[derive(Serialize)]
pub struct ShiftSummary {
    pub shift: LocalShift,
    pub sales_count: i64,
    pub sales_total_cents: i64,
    /// Tips taken on top of the sales (owed to staff); cash tips are in the drawer.
    pub tips_cents: i64,
    pub tenders: BTreeMap<String, i64>,
    pub returns_count: i64,
    pub refund_tenders: BTreeMap<String, i64>,
    pub pay_in_cents: i64,
    pub pay_out_cents: i64,
    pub drops_cents: i64,
    pub no_sale_count: i64,
    pub expected_cash_cents: i64,
    /// Foreign cash received per currency, in that currency's minor units.
    pub foreign_cash: BTreeMap<String, i64>,
}

#[derive(Deserialize)]
pub struct OpenShift {
    pub id: String,
    pub opened_at: String,
    pub opening_float_cents: i64,
    pub currency: String,
}

#[derive(Deserialize)]
pub struct CashMovementInput {
    pub id: String,
    pub kind: String,
    pub amount_cents: i64,
    pub reason: String,
    pub occurred_at: String,
}

#[derive(Deserialize)]
pub struct CloseShift {
    pub closed_at: String,
    pub counted_cash_cents: i64,
    pub z_number: Option<String>,
    pub notes: String,
    #[serde(default)]
    pub counted_foreign: BTreeMap<String, i64>,
}

const MAX_CASH: i64 = 100_000_000;

fn row_to_shift(row: &rusqlite::Row<'_>) -> rusqlite::Result<LocalShift> {
    Ok(LocalShift {
        id: row.get(0)?,
        opened_at: row.get(1)?,
        opened_by_name: row.get(2)?,
        opening_float_cents: row.get(3)?,
        currency: row.get(4)?,
        status: row.get(5)?,
        closed_at: row.get(6)?,
        closed_by_name: row.get(7)?,
        counted_cash_cents: row.get(8)?,
        expected_cash_cents: row.get(9)?,
        z_number: row.get(10)?,
    })
}

const SHIFT_COLUMNS: &str =
    "id, opened_at, opened_by_name, opening_float_cents, currency, status, closed_at, \
     closed_by_name, counted_cash_cents, expected_cash_cents, z_number";

fn open_shift_row(conn: &Connection) -> Result<Option<LocalShift>, String> {
    conn.query_row(
        &format!("SELECT {SHIFT_COLUMNS} FROM local_shifts WHERE status = 'OPEN' ORDER BY opened_at DESC LIMIT 1"),
        [],
        row_to_shift,
    )
    .optional()
    .map_err(|err| err.to_string())
}

pub fn current(db: &Db) -> Result<Option<LocalShift>, String> {
    db.read(open_shift_row)
}

pub fn recent(db: &Db, limit: i64) -> Result<Vec<LocalShift>, String> {
    db.read(|conn| {
        let mut statement = conn
            .prepare(&format!(
                "SELECT {SHIFT_COLUMNS} FROM local_shifts ORDER BY opened_at DESC LIMIT ?1"
            ))
            .map_err(|err| err.to_string())?;
        let rows = statement
            .query_map(params![limit], row_to_shift)
            .map_err(|err| err.to_string())?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|err| err.to_string());
        rows
    })
}

fn event(
    key: String,
    entity_type: &str,
    payload: serde_json::Value,
    occurred_at: &str,
) -> QueuedEvent {
    QueuedEvent {
        id: key.clone(),
        idempotency_key: key,
        entity_type: entity_type.into(),
        operation: "upsert".into(),
        payload,
        occurred_at: occurred_at.into(),
    }
}

fn valid_id(value: &str) -> bool {
    value.len() == 36 && value.chars().all(|c| c.is_ascii_hexdigit() || c == '-')
}

/// Head office counts every shift in the business currency. Until that currency has been fetched, the
/// amount the cashier typed is kept under the code they were shown.
fn counted_currency(db: &Db, shown: &str) -> Result<String, String> {
    if let Some(code) = crate::settings::cached_currency(db)? {
        if code.len() == 3 {
            return Ok(code);
        }
    }
    Ok(shown.trim().to_ascii_uppercase())
}

pub fn open(
    db: &Db,
    session: &Session,
    store_id: &str,
    input: &OpenShift,
) -> Result<LocalShift, String> {
    if !valid_id(&input.id) {
        return Err("Shift id must be a UUID.".into());
    }
    if !(0..=MAX_CASH).contains(&input.opening_float_cents) {
        return Err("Enter an opening float between 0 and 1,000,000.".into());
    }
    let currency = counted_currency(db, &input.currency)?;
    db.transaction(|tx| {
        if open_shift_row(tx)?.is_some() {
            return Err("A shift is already open on this register. Close it first.".into());
        }
        tx.execute(
            "INSERT INTO local_shifts (id, opened_at, opened_by_id, opened_by_name, opening_float_cents, currency, status)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, 'OPEN')",
            params![
                input.id,
                input.opened_at,
                session.user.id,
                session.user.full_name,
                input.opening_float_cents,
                currency
            ],
        )
        .map_err(|err| err.to_string())?;
        let payload = json!({
            "id": input.id,
            "store_id": store_id,
            "opened_by_id": session.user.id,
            "opened_at": input.opened_at,
            "opening_float_cents": input.opening_float_cents,
            "currency": currency,
            "status": "OPEN",
            "blind_close": true,
        });
        insert_events(
            tx,
            &format!("shift-open-{}", input.id),
            &[event(format!("shift-open-{}", input.id), "register_shift", payload, &input.opened_at)],
        )?;
        open_shift_row(tx)?.ok_or_else(|| "The shift did not save.".to_string())
    })
}

pub fn record_movement(
    db: &Db,
    session: &Session,
    store_id: &str,
    input: &CashMovementInput,
) -> Result<(), String> {
    if !valid_id(&input.id) {
        return Err("Movement id must be a UUID.".into());
    }
    if !matches!(
        input.kind.as_str(),
        "PAY_IN" | "PAY_OUT" | "CASH_DROP" | "NO_SALE"
    ) {
        return Err("Unknown cash movement.".into());
    }
    let no_sale = input.kind == "NO_SALE";
    if no_sale && input.amount_cents != 0 {
        return Err("A no-sale open moves no cash.".into());
    }
    if !no_sale && !(1..=MAX_CASH).contains(&input.amount_cents) {
        return Err("Enter the amount of cash moved.".into());
    }
    if !no_sale && input.reason.trim().chars().count() < 3 {
        return Err("Give a reason for the cash movement.".into());
    }
    let currency = counted_currency(db, "")?;
    db.transaction(|tx| {
        let shift = open_shift_row(tx)?.ok_or_else(|| "Open a shift before moving cash.".to_string())?;
        tx.execute(
            "INSERT INTO local_cash_movements (id, shift_id, kind, amount_cents, reason, user_name, occurred_at)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
            params![
                input.id,
                shift.id,
                input.kind,
                input.amount_cents,
                input.reason.trim(),
                session.user.full_name,
                input.occurred_at
            ],
        )
        .map_err(|err| err.to_string())?;
        let payload = json!({
            "id": input.id,
            "shift_id": shift.id,
            "store_id": store_id,
            "user_id": session.user.id,
            "kind": input.kind,
            "amount_cents": input.amount_cents,
            "currency": if currency.len() == 3 { currency.clone() } else { shift.currency.clone() },
            "reason": input.reason.trim(),
            "occurred_at": input.occurred_at,
        });
        insert_events(
            tx,
            &format!("cash-{}", input.id),
            &[event(format!("cash-{}", input.id), "cash_movement", payload, &input.occurred_at)],
        )
    })
}

fn sum_by_method(
    conn: &Connection,
    entity: &str,
    path: &str,
    shift_id: &str,
) -> Result<BTreeMap<String, i64>, String> {
    let mut statement = conn
        .prepare(&format!(
            "SELECT json_extract(t.value, '$.method'), SUM(json_extract(t.value, '$.amount_cents'))
             FROM sync_queue q, json_each(q.payload, '{path}') t
             WHERE q.entity_type = ?1 AND q.status != 'rejected' AND json_extract(q.payload, '$.shift_id') = ?2
             GROUP BY 1"
        ))
        .map_err(|err| err.to_string())?;
    let rows = statement
        .query_map(params![entity, shift_id], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, i64>(1)?))
        })
        .map_err(|err| err.to_string())?
        .collect::<Result<BTreeMap<_, _>, _>>()
        .map_err(|err| err.to_string());
    rows
}

fn summarize(conn: &Connection, shift: LocalShift) -> Result<ShiftSummary, String> {
    let (sales_count, sales_total_cents, tips_cents): (i64, i64, i64) = conn
        .query_row(
            "SELECT COUNT(*), COALESCE(SUM(json_extract(payload, '$.total_cents')), 0),
                    COALESCE(SUM(json_extract(payload, '$.tip_cents')), 0) FROM sync_queue
             WHERE entity_type = 'sale' AND status != 'rejected' AND json_extract(payload, '$.shift_id') = ?1",
            params![shift.id],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .map_err(|err| err.to_string())?;
    let returns_count: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM sync_queue
             WHERE entity_type = 'sale_return' AND status != 'rejected' AND json_extract(payload, '$.shift_id') = ?1",
            params![shift.id],
            |row| row.get(0),
        )
        .map_err(|err| err.to_string())?;
    let tenders = sum_by_method(conn, "sale", "$.tenders", &shift.id)?;
    let refund_tenders = sum_by_method(conn, "sale_return", "$.tenders", &shift.id)?;
    let mut movements: BTreeMap<String, (i64, i64)> = BTreeMap::new();
    let mut statement = conn
        .prepare("SELECT kind, SUM(amount_cents), COUNT(*) FROM local_cash_movements WHERE shift_id = ?1 GROUP BY kind")
        .map_err(|err| err.to_string())?;
    let rows = statement
        .query_map(params![shift.id], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, i64>(1)?,
                row.get::<_, i64>(2)?,
            ))
        })
        .map_err(|err| err.to_string())?;
    for row in rows {
        let (kind, amount, count) = row.map_err(|err| err.to_string())?;
        movements.insert(kind, (amount, count));
    }
    let moved = |kind: &str| movements.get(kind).map(|value| value.0).unwrap_or(0);
    // Foreign cash sits in its own drawer; the business-currency change handed back leaves this one.
    let mut foreign_cash: BTreeMap<String, i64> = BTreeMap::new();
    let (mut foreign_value, mut foreign_change) = (0i64, 0i64);
    let mut statement = conn
        .prepare(
            "SELECT json_extract(t.value, '$.currency'), SUM(json_extract(t.value, '$.foreign_amount_cents')),
                    SUM(json_extract(t.value, '$.amount_cents')), SUM(COALESCE(json_extract(t.value, '$.change_cents'), 0))
             FROM sync_queue q, json_each(q.payload, '$.tenders') t
             WHERE q.entity_type = 'sale' AND q.status != 'rejected' AND json_extract(q.payload, '$.shift_id') = ?1
               AND json_extract(t.value, '$.method') = 'cash' AND json_extract(t.value, '$.currency') IS NOT NULL
               AND json_extract(t.value, '$.currency') != ?2
             GROUP BY 1",
        )
        .map_err(|err| err.to_string())?;
    let rows = statement
        .query_map(params![shift.id, shift.currency], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, i64>(1)?,
                row.get::<_, i64>(2)?,
                row.get::<_, i64>(3)?,
            ))
        })
        .map_err(|err| err.to_string())?;
    for row in rows {
        let (code, received, value, change) = row.map_err(|err| err.to_string())?;
        foreign_cash.insert(code, received);
        foreign_value += value;
        foreign_change += change;
    }
    let expected = shift.opening_float_cents + tenders.get("cash").copied().unwrap_or(0)
        - foreign_value
        - foreign_change
        - refund_tenders.get("cash").copied().unwrap_or(0)
        + moved("PAY_IN")
        - moved("PAY_OUT")
        - moved("CASH_DROP");
    Ok(ShiftSummary {
        sales_count,
        sales_total_cents,
        tips_cents,
        returns_count,
        pay_in_cents: moved("PAY_IN"),
        pay_out_cents: moved("PAY_OUT"),
        drops_cents: moved("CASH_DROP"),
        no_sale_count: movements.get("NO_SALE").map(|value| value.1).unwrap_or(0),
        expected_cash_cents: expected,
        tenders,
        refund_tenders,
        foreign_cash,
        shift,
    })
}

/// The X report: a mid-shift snapshot. Blind close means the UI hides expected cash until the count is in.
#[derive(Serialize)]
pub struct ShiftSaleLine {
    pub id: String,
    pub name: String,
    pub sku: String,
    pub quantity: i64,
    pub returned_quantity: i64,
    pub unit_price_cents: i64,
    pub discount_cents: i64,
    pub tax_cents: i64,
    pub line_total_cents: i64,
}

#[derive(Serialize)]
pub struct ShiftTender {
    pub method: String,
    pub amount_cents: i64,
}

#[derive(Serialize)]
pub struct ShiftSale {
    pub id: String,
    pub invoice_number: String,
    pub sold_at: String,
    pub customer_name: String,
    pub item_count: i64,
    pub quantity: i64,
    pub returned_quantity: i64,
    pub gross_cents: i64,
    pub discount_cents: i64,
    pub tax_cents: i64,
    pub total_cents: i64,
    pub refunded_cents: i64,
    pub payment: String,
    pub status: String,
    pub sync_status: String,
    pub lines: Vec<ShiftSaleLine>,
    pub tenders: Vec<ShiftTender>,
}

#[derive(Serialize)]
pub struct ShiftReturn {
    pub id: String,
    pub credit_note_number: String,
    pub original_sale_id: String,
    pub original_invoice: String,
    pub processed_at: String,
    pub total_refund_cents: i64,
    pub sync_status: String,
    pub item_count: i64,
}

#[derive(Serialize)]
pub struct ShiftHistory {
    pub sales: Vec<ShiftSale>,
    pub returns: Vec<ShiftReturn>,
}

fn text_of(value: &Value, key: &str) -> String {
    value.get(key).and_then(|item| item.as_str()).unwrap_or("").trim().to_string()
}

fn cents_of(value: &Value, key: &str) -> i64 {
    value.get(key).and_then(|item| item.as_i64()).unwrap_or(0)
}

/// Sales and returns stored on this register for one shift. Names fall back to the local catalogue when the
/// queued sale did not keep a product-name snapshot. Return quantities come from queued return events.
pub fn history(db: &Db, shift_id: &str) -> Result<ShiftHistory, String> {
    db.read(|conn| read_history(conn, shift_id))
}

fn read_history(conn: &Connection, shift_id: &str) -> Result<ShiftHistory, String> {
    let mut returns_by_item: BTreeMap<String, i64> = BTreeMap::new();
    let mut refunds_by_sale: BTreeMap<String, i64> = BTreeMap::new();
    let mut return_rows: Vec<(String, String, String, String, i64, String, i64)> = Vec::new();
    let mut statement = conn
        .prepare(
            "SELECT payload, status, occurred_at FROM sync_queue
             WHERE entity_type = 'sale_return' AND status != 'rejected'",
        )
        .map_err(|err| err.to_string())?;
    let queued_returns = statement
        .query_map([], |row| Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?, row.get::<_, String>(2)?)))
        .map_err(|err| err.to_string())?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|err| err.to_string())?;
    drop(statement);
    for (payload, status, occurred_at) in queued_returns {
        let value: Value = serde_json::from_str(&payload).map_err(|err| err.to_string())?;
        let sale_id = text_of(&value, "original_sale_id");
        if sale_id.is_empty() {
            continue;
        }
        let refund = cents_of(&value, "total_refund_cents");
        *refunds_by_sale.entry(sale_id.clone()).or_insert(0) += refund;
        let mut count = 0;
        if let Some(items) = value.get("items").and_then(|item| item.as_array()) {
            for item in items {
                count += 1;
                let line_id = text_of(item, "sale_item_id");
                if !line_id.is_empty() {
                    *returns_by_item.entry(line_id).or_insert(0) += cents_of(item, "quantity");
                }
            }
        }
        if text_of(&value, "shift_id") == shift_id {
            return_rows.push((
                text_of(&value, "id"),
                text_of(&value, "credit_note_number"),
                sale_id,
                if text_of(&value, "processed_at").is_empty() { occurred_at } else { text_of(&value, "processed_at") },
                refund,
                status,
                count,
            ));
        }
    }

    let mut statement = conn
        .prepare(
            "SELECT payload, occurred_at, status FROM sync_queue
             WHERE entity_type = 'sale' AND status != 'rejected'
               AND json_extract(payload, '$.shift_id') = ?1
             ORDER BY occurred_at DESC",
        )
        .map_err(|err| err.to_string())?;
    let queued_sales = statement
        .query_map(params![shift_id], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?, row.get::<_, String>(2)?))
        })
        .map_err(|err| err.to_string())?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|err| err.to_string())?;
    drop(statement);

    let mut invoices: BTreeMap<String, String> = BTreeMap::new();
    let mut sales = Vec::new();
    for (payload, occurred_at, sync_status) in queued_sales {
        let value: Value = serde_json::from_str(&payload).map_err(|err| err.to_string())?;
        let id = text_of(&value, "id");
        let invoice = {
            let number = text_of(&value, "invoice_number");
            if number.is_empty() { id.clone() } else { number }
        };
        invoices.insert(id.clone(), invoice.clone());
        let mut lines = Vec::new();
        let mut quantity = 0;
        let mut returned_quantity = 0;
        let mut discount = 0;
        if let Some(items) = value.get("items").and_then(|item| item.as_array()) {
            for item in items {
                let line_id = text_of(item, "id");
                let sold = cents_of(item, "quantity");
                let returned = returns_by_item.get(&line_id).copied().unwrap_or(0).min(sold.max(0));
                quantity += sold;
                returned_quantity += returned;
                let line_discount = cents_of(item, "discount_cents") + cents_of(item, "manual_discount_cents");
                discount += line_discount;
                let (name, sku) = line_label(conn, item);
                lines.push(ShiftSaleLine {
                    id: line_id,
                    name,
                    sku,
                    quantity: sold,
                    returned_quantity: returned,
                    unit_price_cents: cents_of(item, "unit_price_cents"),
                    discount_cents: line_discount,
                    tax_cents: cents_of(item, "tax_cents"),
                    line_total_cents: cents_of(item, "line_total_cents"),
                });
            }
        }
        let mut tenders = Vec::new();
        if let Some(rows) = value.get("tenders").and_then(|item| item.as_array()) {
            for tender in rows {
                tenders.push(ShiftTender {
                    method: text_of(tender, "method"),
                    amount_cents: cents_of(tender, "amount_cents"),
                });
            }
        }
        let payment = if tenders.is_empty() {
            text_of(&value, "payment_method")
        } else {
            tenders.iter().map(|tender| tender.method.clone()).collect::<Vec<_>>().join(" + ")
        };
        let status = if quantity > 0 && returned_quantity >= quantity {
            "returned"
        } else if returned_quantity > 0 {
            "partially_returned"
        } else {
            "completed"
        };
        let sold_at = {
            let stamp = text_of(&value, "sold_at");
            if stamp.is_empty() { occurred_at } else { stamp }
        };
        sales.push(ShiftSale {
            id: id.clone(),
            invoice_number: invoice,
            sold_at,
            customer_name: customer_label(conn, &text_of(&value, "customer_id")),
            item_count: lines.len() as i64,
            quantity,
            returned_quantity,
            gross_cents: cents_of(&value, "subtotal_cents"),
            discount_cents: discount,
            tax_cents: cents_of(&value, "tax_cents"),
            total_cents: cents_of(&value, "total_cents"),
            refunded_cents: refunds_by_sale.get(&id).copied().unwrap_or(0),
            payment,
            status: status.into(),
            sync_status,
            lines,
            tenders,
        });
    }
    let returns = return_rows
        .into_iter()
        .map(|(id, number, sale_id, processed_at, refund, sync_status, item_count)| ShiftReturn {
            id,
            credit_note_number: if number.is_empty() { "Pending number".into() } else { number },
            original_invoice: invoices.get(&sale_id).cloned().unwrap_or_else(|| sale_id.clone()),
            original_sale_id: sale_id,
            processed_at,
            total_refund_cents: refund,
            sync_status,
            item_count,
        })
        .collect();
    Ok(ShiftHistory { sales, returns })
}

fn customer_label(conn: &Connection, id: &str) -> String {
    if id.is_empty() {
        return "Walk-in".into();
    }
    let payload: Option<String> = conn
        .query_row("SELECT payload FROM customers WHERE id = ?1", params![id], |row| row.get(0))
        .optional()
        .ok()
        .flatten();
    let Some(payload) = payload else {
        return "Customer".into();
    };
    let Ok(value) = serde_json::from_str::<Value>(&payload) else {
        return "Customer".into();
    };
    let company = text_of(&value, "company_name");
    if !company.is_empty() {
        return company;
    }
    let name = text_of(&value, "name");
    if name.is_empty() { "Customer".into() } else { name }
}

fn line_label(conn: &Connection, item: &Value) -> (String, String) {
    let description = text_of(item, "description");
    let product_id = text_of(item, "product_id");
    let found: Option<(String, String)> = conn
        .query_row(
            "SELECT name, sku FROM products WHERE id = ?1",
            params![product_id],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .optional()
        .ok()
        .flatten();
    match found {
        Some((name, sku)) if description.is_empty() => (name, sku),
        Some((_, sku)) => (description, sku),
        None if description.is_empty() => ("Item".into(), String::new()),
        None => (description, String::new()),
    }
}

pub fn summary(db: &Db, shift_id: Option<&str>) -> Result<Option<ShiftSummary>, String> {
    db.read(|conn| {
        let shift = match shift_id {
            Some(id) => conn
                .query_row(
                    &format!("SELECT {SHIFT_COLUMNS} FROM local_shifts WHERE id = ?1"),
                    params![id],
                    row_to_shift,
                )
                .optional()
                .map_err(|err| err.to_string())?,
            None => open_shift_row(conn)?,
        };
        shift.map(|shift| summarize(conn, shift)).transpose()
    })
}

pub fn close(
    db: &Db,
    session: &Session,
    store_id: &str,
    input: &CloseShift,
) -> Result<ShiftSummary, String> {
    if !(0..=MAX_CASH).contains(&input.counted_cash_cents) {
        return Err("Enter the counted cash.".into());
    }
    let business = counted_currency(db, "")?;
    db.transaction(|tx| {
        let shift = open_shift_row(tx)?.ok_or_else(|| "No shift is open on this register.".to_string())?;
        let expected = summarize(tx, shift.clone())?.expected_cash_cents;
        let currency = if business.len() == 3 { business.clone() } else { shift.currency.clone() };
        tx.execute(
            "UPDATE local_shifts SET status = 'CLOSED', closed_at = ?2, closed_by_name = ?3, counted_cash_cents = ?4,
                expected_cash_cents = ?5, z_number = ?6, currency = ?7 WHERE id = ?1",
            params![
                shift.id,
                input.closed_at,
                session.user.full_name,
                input.counted_cash_cents,
                expected,
                input.z_number,
                currency
            ],
        )
        .map_err(|err| err.to_string())?;
        let opened_by: String = tx
            .query_row("SELECT opened_by_id FROM local_shifts WHERE id = ?1", params![shift.id], |row| row.get(0))
            .map_err(|err| err.to_string())?;
        let payload = json!({
            "id": shift.id,
            "store_id": store_id,
            "opened_by_id": opened_by,
            "opened_at": shift.opened_at,
            "opening_float_cents": shift.opening_float_cents,
            "currency": currency,
            "status": "CLOSED",
            "closed_by_id": session.user.id,
            "closed_at": input.closed_at,
            "counted_cash_cents": input.counted_cash_cents,
            "z_number": input.z_number,
            "blind_close": true,
            "notes": input.notes.chars().take(500).collect::<String>(),
            "counted_foreign": input.counted_foreign,
        });
        insert_events(
            tx,
            &format!("shift-close-{}", shift.id),
            &[event(format!("shift-close-{}", shift.id), "register_shift", payload, &input.closed_at)],
        )?;
        let closed = tx
            .query_row(&format!("SELECT {SHIFT_COLUMNS} FROM local_shifts WHERE id = ?1"), params![shift.id], row_to_shift)
            .map_err(|err| err.to_string())?;
        summarize(tx, closed)
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn session() -> Session {
        Session {
            user: crate::auth::CashierProfile {
                id: "00000000-0000-4000-8000-000000000002".into(),
                username: "cashier".into(),
                full_name: "Cashier".into(),
                store_id: None,
                role_name: "Cashier".into(),
                permissions: vec![],
                max_discount_bps: None,
                addon_modules: vec![],
                addon_synced_at: 0,
                avatar_url: None,
            },
            mode: "offline",
            unlocked_at: 0,
        }
    }

    #[test]
    fn expected_cash_follows_tenders_and_movements() {
        let directory = std::env::temp_dir().join(format!("aipos-shift-{}", std::process::id()));
        std::fs::create_dir_all(&directory).unwrap();
        let db = Db::open(&directory.join("shift.db")).unwrap();
        let session = session();
        let shift_id = "11111111-1111-4111-8111-111111111111";
        open(
            &db,
            &session,
            "store",
            &OpenShift {
                id: shift_id.into(),
                opened_at: "2026-10-19T08:00:00Z".into(),
                opening_float_cents: 10_000,
                currency: "AED".into(),
            },
        )
        .unwrap();
        assert!(open(
            &db,
            &session,
            "store",
            &OpenShift {
                id: "22222222-2222-4222-8222-222222222222".into(),
                opened_at: "x".into(),
                opening_float_cents: 0,
                currency: "AED".into()
            },
        )
        .is_err());
        let sale = QueuedEvent {
            id: "sale-1".into(),
            idempotency_key: "sale-key-1".into(),
            entity_type: "sale".into(),
            operation: "upsert".into(),
            payload: json!({"shift_id": shift_id, "total_cents": 2500, "tenders": [{"method": "cash", "amount_cents": 2500}]}),
            occurred_at: "2026-10-19T09:00:00Z".into(),
        };
        db.enqueue("batch-1", &[sale]).unwrap();
        record_movement(
            &db,
            &session,
            "store",
            &CashMovementInput {
                id: "33333333-3333-4333-8333-333333333333".into(),
                kind: "CASH_DROP".into(),
                amount_cents: 5_000,
                reason: "Safe drop".into(),
                occurred_at: "2026-10-19T10:00:00Z".into(),
            },
        )
        .unwrap();
        let closed = close(
            &db,
            &session,
            "store",
            &CloseShift {
                closed_at: "2026-10-19T18:00:00Z".into(),
                counted_cash_cents: 7_400,
                z_number: None,
                notes: String::new(),
                counted_foreign: BTreeMap::new(),
            },
        )
        .unwrap();
        assert_eq!(closed.expected_cash_cents, 7_500);
        assert_eq!(closed.shift.status, "CLOSED");
        assert!(current(&db).unwrap().is_none());
        let _ = std::fs::remove_dir_all(&directory);
    }

    #[test]
    fn a_shift_queued_in_the_seed_currency_is_recounted_in_the_business_currency() {
        let directory = std::env::temp_dir().join(format!("aipos-shift-currency-{}", std::process::id()));
        std::fs::create_dir_all(&directory).unwrap();
        let db = Db::open(&directory.join("shift.db")).unwrap();
        db.transaction(|tx| {
            tx.execute(
                "INSERT INTO business_settings (id, currency, fetched_at) VALUES (1, 'AED', 1)",
                [],
            )
            .map_err(|err| err.to_string())?;
            Ok(())
        })
        .unwrap();
        let shift_id = "11111111-1111-4111-8111-111111111111";
        open(
            &db,
            &session(),
            "store",
            &OpenShift {
                id: shift_id.into(),
                opened_at: "2026-10-26T08:11:00Z".into(),
                opening_float_cents: 0,
                currency: "USD".into(),
            },
        )
        .unwrap();
        let payload: String = db
            .read(|conn| {
                conn.query_row(
                    "SELECT payload FROM sync_queue WHERE entity_type = 'register_shift'",
                    [],
                    |row| row.get(0),
                )
                .map_err(|err| err.to_string())
            })
            .unwrap();
        assert!(payload.contains("\"currency\":\"AED\""), "{payload}");
        db.transaction(|tx| {
            tx.execute("UPDATE sync_queue SET payload = replace(payload, 'AED', 'USD')", [])
                .map_err(|err| err.to_string())?;
            Ok(())
        })
        .unwrap();
        let batch: String = db
            .read(|conn| {
                conn.query_row("SELECT batch_id FROM sync_queue LIMIT 1", [], |row| row.get(0))
                    .map_err(|err| err.to_string())
            })
            .unwrap();
        assert!(db.relabel_shift_currency(&batch, "AED").unwrap());
        assert!(!db.relabel_shift_currency(&batch, "AED").unwrap());
        let _ = std::fs::remove_dir_all(&directory);
    }

    #[test]
    fn shift_history_links_a_partial_return_to_the_original_invoice() {
        let directory = std::env::temp_dir().join(format!("aipos-shift-history-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&directory);
        std::fs::create_dir_all(&directory).unwrap();
        let db = Db::open(&directory.join("shift.db")).unwrap();
        let shift_id = "11111111-1111-4111-8111-111111111111";
        let sale_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
        db.enqueue(
            "batch-sale",
            &[QueuedEvent {
                id: "sale-1".into(),
                idempotency_key: "sale-key".into(),
                entity_type: "sale".into(),
                operation: "upsert".into(),
                payload: json!({
                    "id": sale_id,
                    "shift_id": shift_id,
                    "invoice_number": "DT-01-S-000125",
                    "sold_at": "2026-10-19T09:00:00Z",
                    "payment_method": "cash",
                    "subtotal_cents": 3000,
                    "tax_cents": 150,
                    "total_cents": 3150,
                    "items": [{
                        "id": "line-1",
                        "product_id": "cable",
                        "description": "Cotton Suit",
                        "quantity": 3,
                        "unit_price_cents": 1000,
                        "discount_cents": 0,
                        "manual_discount_cents": 0,
                        "tax_cents": 150,
                        "line_total_cents": 3150
                    }],
                    "tenders": [{"method": "cash", "amount_cents": 3150}]
                }),
                occurred_at: "2026-10-19T09:00:00Z".into(),
            }],
        )
        .unwrap();
        db.enqueue(
            "batch-return",
            &[QueuedEvent {
                id: "return-1".into(),
                idempotency_key: "return-key".into(),
                entity_type: "sale_return".into(),
                operation: "upsert".into(),
                payload: json!({
                    "id": "return-1",
                    "original_sale_id": sale_id,
                    "shift_id": shift_id,
                    "credit_note_number": "RET-000018",
                    "processed_at": "2026-10-19T11:00:00Z",
                    "total_refund_cents": 1050,
                    "items": [{"sale_item_id": "line-1", "quantity": 1}]
                }),
                occurred_at: "2026-10-19T11:00:00Z".into(),
            }],
        )
        .unwrap();
        let history = history(&db, shift_id).unwrap();
        assert_eq!(history.sales.len(), 1);
        let sale = &history.sales[0];
        assert_eq!(sale.invoice_number, "DT-01-S-000125");
        assert_eq!(sale.lines[0].name, "Cotton Suit");
        assert_eq!(sale.lines[0].quantity, 3);
        assert_eq!(sale.lines[0].returned_quantity, 1);
        assert_eq!(sale.status, "partially_returned");
        assert_eq!(sale.refunded_cents, 1050);
        assert_eq!(sale.total_cents, 3150);
        assert_eq!(history.returns[0].credit_note_number, "RET-000018");
        assert_eq!(history.returns[0].original_invoice, "DT-01-S-000125");
        let _ = std::fs::remove_dir_all(&directory);
    }
}
