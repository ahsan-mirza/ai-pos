//! Tauri commands for the ERP features (document numbering, held carts, shifts, printing, sync center,
//! customer display). Each feature's storage lives in its own module; these are thin command wrappers.

use tauri::Manager;
use tauri_plugin_opener::OpenerExt;

use crate::documents;
use crate::held;
use crate::margin;
use crate::printer;
use crate::shifts;
use crate::sync_center;
use crate::timeclock;
use crate::AppState;

const SHIFT_MANAGE: &str = "pos:shift_manage";

#[tauri::command]
pub fn list_batches(
    state: tauri::State<AppState>,
    status: Option<String>,
    limit: Option<i64>,
) -> Result<Vec<sync_center::BatchRow>, String> {
    require_session(&state)?;
    sync_center::list(&state.db, status.as_deref(), limit.unwrap_or(50).clamp(1, 200))
}

#[tauri::command]
pub fn resolve_batch(state: tauri::State<AppState>, batch_id: String, action: String) -> Result<(), String> {
    let session = require_session(&state)?;
    sync_center::resolve(&state.db, &session, &batch_id, &action)
}

/// The loyalty programme's rules; offline the register treats the programme as off rather than guess a value.
#[tauri::command]
pub async fn loyalty_settings(state: tauri::State<'_, AppState>) -> Result<serde_json::Value, String> {
    let config = state.config.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let response = reqwest::blocking::Client::builder()
            .timeout(std::time::Duration::from_secs(6))
            .build()
            .map_err(|err| err.to_string())?
            .get(format!("{}/api/v1/loyalty/settings", config.api_base_url))
            .headers(config.auth_headers())
            .send();
        Ok(match response {
            Ok(response) if response.status().is_success() => {
                response.json().unwrap_or(serde_json::json!({ "enabled": false }))
            }
            _ => serde_json::json!({ "enabled": false }),
        })
    })
    .await
    .map_err(|err: tauri::Error| err.to_string())?
}

/// Promotions this register may apply. Returns null when offline so the register keeps its cached copy.
#[tauri::command]
pub async fn active_promotions(state: tauri::State<'_, AppState>) -> Result<serde_json::Value, String> {
    let config = state.config.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let response = reqwest::blocking::Client::builder()
            .timeout(std::time::Duration::from_secs(6))
            .build()
            .map_err(|err| err.to_string())?
            .get(format!("{}/api/v1/promotions/active", config.api_base_url))
            .query(&[("store_id", config.store_id.as_str())])
            .headers(config.auth_headers())
            .send();
        Ok(match response {
            Ok(response) if response.status().is_success() => response.json().unwrap_or(serde_json::Value::Null),
            _ => serde_json::Value::Null,
        })
    })
    .await
    .map_err(|err: tauri::Error| err.to_string())?
}

#[tauri::command]
pub async fn foreign_currencies(
    state: tauri::State<'_, AppState>,
) -> Result<Vec<crate::settings::ForeignCurrency>, String> {
    let db = state.db.clone();
    let config = state.config.clone();
    tauri::async_runtime::spawn_blocking(move || crate::settings::refresh_currencies(&db, &config))
        .await
        .map_err(|err| err.to_string())?
}

/// QR payments need the server: it issues the QR and learns from the acquirer when the customer has paid.
#[tauri::command]
pub async fn payment_intent(
    state: tauri::State<'_, AppState>,
    action: String,
    intent_id: Option<String>,
    amount_cents: Option<i64>,
) -> Result<serde_json::Value, String> {
    require_session(&state)?;
    let config = state.config.clone();
    let safe_id: String = intent_id
        .unwrap_or_default()
        .chars()
        .filter(|c| c.is_ascii_hexdigit() || *c == '-')
        .collect();
    tauri::async_runtime::spawn_blocking(move || {
        let client = reqwest::blocking::Client::builder()
            .timeout(std::time::Duration::from_secs(8))
            .build()
            .map_err(|err| err.to_string())?;
        let base = format!("{}/api/v1/payments/intents", config.api_base_url);
        let request = match action.as_str() {
            "create" => client.post(&base).json(&serde_json::json!({
                "amount_cents": amount_cents.ok_or("Amount is required.")?,
                "store_id": config.store_id,
            })),
            "get" if !safe_id.is_empty() => client.get(format!("{base}/{safe_id}")),
            "cancel" if !safe_id.is_empty() => client.post(format!("{base}/{safe_id}/cancel")),
            _ => return Err("Unknown payment action.".to_string()),
        };
        let response = request
            .headers(config.auth_headers())
            .send()
            .map_err(|err| format!("QR payments need a connection: {err}"))?;
        let status = response.status();
        let value: serde_json::Value = response.json().unwrap_or(serde_json::Value::Null);
        if !status.is_success() {
            return Err(value["error"]["message"].as_str().unwrap_or("The payment server refused.").to_string());
        }
        Ok(value)
    })
    .await
    .map_err(|err| err.to_string())?
}

/// Live balance of a store-credit voucher. Online only: an offline register cannot know what other tills spent.
#[tauri::command]
pub async fn store_credit_lookup(
    state: tauri::State<'_, AppState>,
    code: String,
) -> Result<serde_json::Value, String> {
    require_session(&state)?;
    let config = state.config.clone();
    let safe_code: String = code
        .trim()
        .to_ascii_uppercase()
        .chars()
        .filter(|c| c.is_ascii_alphanumeric() || *c == '-')
        .collect();
    if safe_code.is_empty() {
        return Err("Enter the voucher code.".to_string());
    }
    tauri::async_runtime::spawn_blocking(move || {
        let response = reqwest::blocking::Client::builder()
            .timeout(std::time::Duration::from_secs(8))
            .build()
            .map_err(|err| err.to_string())?
            .get(format!("{}/api/v1/store-credits/{safe_code}", config.api_base_url))
            .headers(config.auth_headers())
            .send()
            .map_err(|err| format!("Store credit needs a connection: {err}"))?;
        let status = response.status();
        let value: serde_json::Value = response.json().unwrap_or(serde_json::Value::Null);
        if !status.is_success() {
            return Err(value["error"]["message"].as_str().unwrap_or("The server refused the voucher.").to_string());
        }
        Ok(value)
    })
    .await
    .map_err(|err| err.to_string())?
}

/// Trade-ins are online only: the IMEI check and pricing need the live stock ledger.
#[tauri::command]
pub async fn trade_in_request(
    state: tauri::State<'_, AppState>,
    action: String,
    body: Option<serde_json::Value>,
    trade_in_id: Option<String>,
) -> Result<serde_json::Value, String> {
    require_session(&state)?;
    let config = state.config.clone();
    let safe_id: String = trade_in_id
        .unwrap_or_default()
        .chars()
        .filter(|c| c.is_ascii_hexdigit() || *c == '-')
        .collect();
    tauri::async_runtime::spawn_blocking(move || {
        let client = reqwest::blocking::Client::builder()
            .timeout(std::time::Duration::from_secs(10))
            .build()
            .map_err(|err| err.to_string())?;
        let base = format!("{}/api/v1/trade-ins", config.api_base_url);
        let request = match action.as_str() {
            "check" => client.post(format!("{base}/check")).json(&body.unwrap_or_default()),
            "create" => client.post(&base).json(&body.unwrap_or_default()),
            "cancel" if !safe_id.is_empty() => client.post(format!("{base}/{safe_id}/cancel")),
            _ => return Err("Unknown trade-in action.".to_string()),
        };
        let response = request
            .headers(config.auth_headers())
            .send()
            .map_err(|err| format!("Trade-ins need a connection: {err}"))?;
        let status = response.status();
        let value: serde_json::Value = response.json().unwrap_or(serde_json::Value::Null);
        if !status.is_success() {
            return Err(value["error"]["message"].as_str().unwrap_or("The server refused the trade-in.").to_string());
        }
        Ok(value)
    })
    .await
    .map_err(|err| err.to_string())?
}

/// Remote manager approvals: the register asks, then polls until a manager answers from the portal or phone.
#[tauri::command]
pub async fn approval_request(
    state: tauri::State<'_, AppState>,
    action: String,
    body: Option<serde_json::Value>,
    request_id: Option<String>,
) -> Result<serde_json::Value, String> {
    require_session(&state)?;
    let config = state.config.clone();
    let safe_id: String = request_id
        .unwrap_or_default()
        .chars()
        .filter(|c| c.is_ascii_hexdigit() || *c == '-')
        .collect();
    tauri::async_runtime::spawn_blocking(move || {
        let client = reqwest::blocking::Client::builder()
            .timeout(std::time::Duration::from_secs(8))
            .build()
            .map_err(|err| err.to_string())?;
        let base = format!("{}/api/v1/approvals", config.api_base_url);
        let request = match action.as_str() {
            "create" => {
                let mut payload = body.unwrap_or_default();
                if payload.get("store_id").map_or(true, |value| value.is_null()) && !config.store_id.is_empty() {
                    payload["store_id"] = serde_json::Value::String(config.store_id.clone());
                }
                client.post(&base).json(&payload)
            }
            "get" if !safe_id.is_empty() => client.get(format!("{base}/{safe_id}")),
            "cancel" if !safe_id.is_empty() => client.post(format!("{base}/{safe_id}/cancel")),
            _ => return Err("Unknown approval action.".to_string()),
        };
        let response = request
            .headers(config.auth_headers())
            .send()
            .map_err(|err| format!("Remote approval needs a connection: {err}"))?;
        let status = response.status();
        let value: serde_json::Value = response.json().unwrap_or(serde_json::Value::Null);
        if !status.is_success() {
            return Err(value["error"]["message"].as_str().unwrap_or("The server refused the request.").to_string());
        }
        Ok(value)
    })
    .await
    .map_err(|err| err.to_string())?
}

#[tauri::command]
pub async fn refresh_floors(state: tauri::State<'_, AppState>) -> Result<margin::FloorSnapshot, String> {
    let db = state.db.clone();
    let config = state.config.clone();
    tauri::async_runtime::spawn_blocking(move || margin::refresh(&db, &config))
        .await
        .map_err(|err| err.to_string())?
}

#[tauri::command]
pub fn rejected_count(state: tauri::State<AppState>) -> Result<i64, String> {
    sync_center::rejected_count(&state.db)
}

#[tauri::command]
pub fn list_table_sessions(state: tauri::State<AppState>, store_id: String) -> Result<Vec<crate::table_sessions::TableSession>, String> {
    require_session(&state)?;
    crate::table_sessions::list(&state.db, &store_id)
}

#[tauri::command]
pub fn save_table_session(
    state: tauri::State<AppState>,
    session: crate::table_sessions::TableSession,
) -> Result<crate::table_sessions::TableSession, String> {
    require_session(&state)?;
    crate::table_sessions::save(&state.db, &session)
}

#[tauri::command]
pub fn cache_table_event(state: tauri::State<AppState>, store_id: String, payload: String) -> Result<(), String> {
    require_session(&state)?;
    crate::table_sessions::cache_event(&state.db, &store_id, &payload)
}

#[tauri::command]
pub fn close_table_session(state: tauri::State<AppState>, id: String) -> Result<bool, String> {
    require_session(&state)?;
    crate::table_sessions::close(&state.db, &id)?;
    Ok(true)
}

#[tauri::command]
pub fn hold_cart(state: tauri::State<AppState>, input: held::HoldInput) -> Result<(), String> {
    let session = require_session(&state)?;
    held::hold(&state.db, &session, &input)
}

#[tauri::command]
pub fn held_carts(state: tauri::State<AppState>) -> Result<Vec<held::HeldCart>, String> {
    require_session(&state)?;
    held::list(&state.db)
}

#[tauri::command]
pub fn recall_cart(state: tauri::State<AppState>, id: String) -> Result<Option<held::HeldCart>, String> {
    require_session(&state)?;
    held::take(&state.db, &id)
}

#[tauri::command]
pub fn held_count(state: tauri::State<AppState>) -> Result<i64, String> {
    held::count(&state.db)
}

/// Takes a further deposit on a layaway. Layaways hold stock on the server, so this needs a connection.
#[tauri::command]
pub async fn add_layaway_payment(
    state: tauri::State<'_, AppState>,
    quote_id: String,
    payment: serde_json::Value,
) -> Result<serde_json::Value, String> {
    let session = require_session(&state)?;
    let safe_id: String = quote_id.chars().filter(|c| c.is_ascii_hexdigit() || *c == '-').collect();
    let mut body = payment;
    body["cashier_id"] = serde_json::Value::String(session.user.id.clone());
    let config = state.config.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let response = reqwest::blocking::Client::builder()
            .timeout(std::time::Duration::from_secs(15))
            .build()
            .map_err(|err| err.to_string())?
            .post(format!("{}/api/v1/quotes/{safe_id}/payments", config.api_base_url))
            .headers(config.auth_headers())
            .json(&body)
            .send()
            .map_err(|err| format!("The server is unreachable: {err}"))?;
        let status = response.status();
        let value: serde_json::Value = response.json().unwrap_or(serde_json::Value::Null);
        if !status.is_success() {
            let message = value["error"]["message"].as_str().unwrap_or("The server rejected the deposit.");
            return Err(message.to_string());
        }
        Ok(value)
    })
    .await
    .map_err(|err| err.to_string())?
}

#[tauri::command]
pub fn current_shift(state: tauri::State<AppState>) -> Result<Option<shifts::LocalShift>, String> {
    shifts::current(&state.db)
}

#[tauri::command]
pub fn open_shift(state: tauri::State<AppState>, input: shifts::OpenShift) -> Result<shifts::LocalShift, String> {
    let session = require_session(&state)?;
    shifts::open(&state.db, &session, &state.config.store_id, &input)
}

#[tauri::command]
pub fn clock_status(state: tauri::State<AppState>) -> Result<Option<timeclock::LocalTimeEntry>, String> {
    let session = require_session(&state)?;
    timeclock::status(&state.db, &session)
}

#[tauri::command]
pub fn clock_in(state: tauri::State<AppState>, input: timeclock::ClockIn) -> Result<timeclock::LocalTimeEntry, String> {
    let session = require_session(&state)?;
    timeclock::clock_in(&state.db, &session, &state.config.store_id, &input)
}

#[tauri::command]
pub fn clock_out(state: tauri::State<AppState>, input: timeclock::ClockOut) -> Result<timeclock::LocalTimeEntry, String> {
    let session = require_session(&state)?;
    timeclock::clock_out(&state.db, &session, &state.config.store_id, &input)
}

#[tauri::command]
pub fn on_duty(state: tauri::State<AppState>) -> Result<Vec<timeclock::LocalTimeEntry>, String> {
    require_session(&state)?;
    timeclock::on_duty(&state.db)
}

#[tauri::command]
pub fn record_cash_movement(state: tauri::State<AppState>, input: shifts::CashMovementInput) -> Result<(), String> {
    let session = require_session(&state)?;
    shifts::record_movement(&state.db, &session, &state.config.store_id, &input)
}

/// X report. Expected cash is withheld from cashiers without shift management until the shift is closed.
#[tauri::command]
pub fn shift_summary(
    state: tauri::State<AppState>,
    shift_id: Option<String>,
) -> Result<Option<shifts::ShiftSummary>, String> {
    let session = require_session(&state)?;
    let mut summary = shifts::summary(&state.db, shift_id.as_deref())?;
    if let Some(found) = summary.as_mut() {
        if found.shift.status == "OPEN" && !session.user.permissions.iter().any(|item| item == SHIFT_MANAGE) {
            found.expected_cash_cents = 0;
        }
    }
    Ok(summary)
}

#[tauri::command]
pub fn close_shift(state: tauri::State<AppState>, input: shifts::CloseShift) -> Result<shifts::ShiftSummary, String> {
    let session = require_session(&state)?;
    shifts::close(&state.db, &session, &state.config.store_id, &input)
}

#[tauri::command]
pub fn recent_shifts(state: tauri::State<AppState>, limit: Option<i64>) -> Result<Vec<shifts::LocalShift>, String> {
    shifts::recent(&state.db, limit.unwrap_or(10).clamp(1, 50))
}

fn require_session(state: &AppState) -> Result<crate::auth::Session, String> {
    state.session()?.ok_or_else(|| "Unlock the register first.".to_string())
}

#[tauri::command]
pub fn printer_settings(state: tauri::State<AppState>) -> Result<printer::PrinterSettings, String> {
    printer::load(&state.db)
}

#[tauri::command]
pub fn save_printer_settings(
    state: tauri::State<AppState>,
    settings: printer::PrinterSettings,
) -> Result<printer::PrinterSettings, String> {
    require_session(&state)?;
    printer::save(&state.db, &settings)
}

#[tauri::command]
pub async fn print_receipt(state: tauri::State<'_, AppState>, job: printer::RasterJob) -> Result<(), String> {
    require_session(&state)?;
    let db = state.db.clone();
    tauri::async_runtime::spawn_blocking(move || printer::print_raster(&db, &job))
        .await
        .map_err(|err| err.to_string())?
}

#[tauri::command]
pub async fn open_cash_drawer(state: tauri::State<'_, AppState>) -> Result<(), String> {
    require_session(&state)?;
    let db = state.db.clone();
    tauri::async_runtime::spawn_blocking(move || printer::kick_drawer(&db))
        .await
        .map_err(|err| err.to_string())?
}

#[tauri::command]
pub async fn open_document_pdf(
    app: tauri::AppHandle,
    state: tauri::State<'_, AppState>,
    kind: String,
    id: String,
    number: String,
) -> Result<String, String> {
    let config = state.config.clone();
    let directory = app.path().app_data_dir().map_err(|err| err.to_string())?.join("documents");
    let path = tauri::async_runtime::spawn_blocking(move || {
        printer::download_document(&config, &kind, &id, &number, &directory)
    })
    .await
    .map_err(|err| err.to_string())??;
    app.opener()
        .open_path(path.clone(), None::<&str>)
        .map_err(|err| format!("Saved to {path} but could not open it: {err}"))?;
    Ok(path)
}

#[tauri::command]
pub async fn refresh_series(state: tauri::State<'_, AppState>) -> Result<documents::SeriesStatus, String> {
    let db = state.db.clone();
    let config = state.config.clone();
    tauri::async_runtime::spawn_blocking(move || documents::refresh(&db, &config))
        .await
        .map_err(|err| err.to_string())?
}

#[tauri::command]
pub fn next_document_number(state: tauri::State<AppState>, doc_type: String) -> Result<Option<String>, String> {
    if !matches!(doc_type.as_str(), "INV" | "CN" | "Z") {
        return Err("Unknown document type.".into());
    }
    documents::next_number(&state.db, &doc_type)
}
