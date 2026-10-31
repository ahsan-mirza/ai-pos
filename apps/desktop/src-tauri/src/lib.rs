mod audit;
mod auth;
mod checkout_approvals;
mod customers;
mod db;
mod documents;
mod erp;
mod held;
mod keyboard_detector;
mod margin;
mod media_cache;
mod menu;
mod payments;
mod printer;
mod quotes;
mod restaurant;
mod retail;
mod returns;
mod scale;
mod search_index;
mod serials;
mod settings;
mod shifts;
mod sync;
mod sync_center;
mod table_sessions;
mod terminal;
mod timeclock;
mod updates;

use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use serde::Serialize;
use tauri::{Emitter, Manager};
use tauri_plugin_opener::OpenerExt;

use crate::auth::Session;
use crate::db::Db;
use crate::sync::DesktopConfig;

pub struct AppState {
    db: Arc<Db>,
    config: DesktopConfig,
    media_dir: PathBuf,
    terminal: terminal::TerminalStatus,
    terminal_path: PathBuf,
    flush_lock: Arc<Mutex<()>>,
    session: Mutex<Option<Session>>,
    /// Bearer token from the last online unlock. Cleared on lock and on an offline unlock.
    user_token: Mutex<Option<String>>,
    approvals: Arc<returns::Approvals>,
    checkout_approvals: Arc<checkout_approvals::CheckoutApprovals>,
}

impl AppState {
    fn session(&self) -> Result<Option<Session>, String> {
        self.session
            .lock()
            .map(|guard| guard.clone())
            .map_err(|err| err.to_string())
    }
}

#[derive(Serialize)]
struct CatalogSnapshot {
    products: Vec<db::ProductRow>,
    source: &'static str,
    message: Option<String>,
}

#[tauri::command]
async fn list_cashiers(state: tauri::State<'_, AppState>) -> Result<Vec<auth::CashierCard>, String> {
    let db = state.db.clone();
    let config = state.config.clone();
    tauri::async_runtime::spawn_blocking(move || auth::cashier_directory(&db, &config))
        .await
        .map_err(|err| err.to_string())?
}

#[tauri::command]
async fn unlock_cashier(
    state: tauri::State<'_, AppState>,
    user_id: String,
    pin: String,
) -> Result<Session, String> {
    let db = state.db.clone();
    let config = state.config.clone();
    let (session, access_token) = tauri::async_runtime::spawn_blocking(move || {
        let unlocked = auth::unlock_by_id(&db, &config, &user_id, &pin)?;
        if unlocked.session.mode == "offline" {
            audit::record_offline_login(&db, &unlocked.session, &config.store_id)?;
        }
        Ok::<_, String>((unlocked.session, unlocked.access_token))
    })
    .await
    .map_err(|err| err.to_string())??;
    *state.session.lock().map_err(|err| err.to_string())? = Some(session.clone());
    *state.user_token.lock().map_err(|err| err.to_string())? = access_token;
    state
        .db
        .save_register_session(&session.user, session.mode, session.unlocked_at)?;
    Ok(session)
}

#[tauri::command]
async fn pin_login(
    state: tauri::State<'_, AppState>,
    username: String,
    pin: String,
) -> Result<Session, String> {
    let db = state.db.clone();
    let config = state.config.clone();
    let (session, access_token) = tauri::async_runtime::spawn_blocking(move || {
        let unlocked = auth::pin_login(&db, &config, &username, &pin)?;
        if unlocked.session.mode == "offline" {
            audit::record_offline_login(&db, &unlocked.session, &config.store_id)?;
        }
        Ok::<_, String>((unlocked.session, unlocked.access_token))
    })
    .await
    .map_err(|err| err.to_string())??;
    *state.session.lock().map_err(|err| err.to_string())? = Some(session.clone());
    *state.user_token.lock().map_err(|err| err.to_string())? = access_token;
    state
        .db
        .save_register_session(&session.user, session.mode, session.unlocked_at)?;
    Ok(session)
}

#[tauri::command]
fn current_session(state: tauri::State<AppState>) -> Result<Option<Session>, String> {
    {
        let guard = state.session.lock().map_err(|err| err.to_string())?;
        if guard.is_some() {
            return Ok(guard.clone());
        }
    }
    let Some((user, mode, unlocked_at)) = state.db.load_register_session()? else {
        return Ok(None);
    };
    let now = auth::now_secs();
    let same_store = user.store_id.as_ref().map(|id| id == &state.config.store_id).unwrap_or(true);
    let fresh = unlocked_at <= now && now - unlocked_at <= auth::REGISTER_SESSION_SECS;
    if !same_store || !fresh {
        state.db.clear_register_session()?;
        return Ok(None);
    }
    let session = Session {
        user,
        mode: if mode == "offline" { "offline" } else { "online" },
        unlocked_at,
    };
    *state.session.lock().map_err(|err| err.to_string())? = Some(session.clone());
    Ok(Some(session))
}

#[tauri::command]
fn lock_session(state: tauri::State<AppState>) -> Result<(), String> {
    *state.session.lock().map_err(|err| err.to_string())? = None;
    *state.user_token.lock().map_err(|err| err.to_string())? = None;
    state.db.clear_register_session()?;
    Ok(())
}

#[tauri::command]
fn search_products(
    state: tauri::State<AppState>,
    query: String,
    limit: Option<i64>,
) -> Result<Vec<db::SearchHit>, String> {
    state
        .db
        .search_products(&query, limit.unwrap_or(50).clamp(1, 100))
}

#[tauri::command]
async fn remote_search(
    state: tauri::State<'_, AppState>,
    query: String,
    limit: Option<i64>,
) -> Result<Vec<db::SearchHit>, String> {
    let config = state.config.clone();
    let limit = limit.unwrap_or(50).clamp(1, 100);
    tauri::async_runtime::spawn_blocking(move || sync::remote_search(&config, &query, limit))
        .await
        .map_err(|err| err.to_string())?
}

#[tauri::command]
fn enqueue_events(
    state: tauri::State<AppState>,
    batch_id: String,
    events: Vec<db::QueuedEvent>,
) -> Result<(), String> {
    let Some(session) = state.session()? else {
        return Err("Unlock the register before charging.".into());
    };
    if events
        .iter()
        .any(|event| event.entity_type == "sale_return")
    {
        return Err(
            "Returns are queued with enqueue_return so manager approval is checked.".into(),
        );
    }
    for event in events.iter().filter(|event| event.entity_type == "sale") {
        let cashier = event
            .payload
            .get("cashier_id")
            .and_then(serde_json::Value::as_str);
        if cashier != Some(session.user.id.as_str()) {
            return Err(
                "The sale must be attributed to the cashier who unlocked this register.".into(),
            );
        }
        let store = event
            .payload
            .get("store_id")
            .and_then(serde_json::Value::as_str);
        if store != Some(state.config.store_id.as_str()) {
            return Err("The sale must be booked to this terminal's branch (STORE_ID).".into());
        }
    }
    checkout_approvals::check_sale(&state.checkout_approvals, &session, &events)?;
    state.db.enqueue(&batch_id, &events)
}

#[tauri::command]
async fn approve_manager(
    state: tauri::State<'_, AppState>,
    username: String,
    pin: String,
    permission: String,
) -> Result<auth::CashierProfile, String> {
    let Some(session) = state.session()? else {
        return Err("Unlock the register before asking for approval.".into());
    };
    let db = state.db.clone();
    let config = state.config.clone();
    let approvals = state.checkout_approvals.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let approver = checkout_approvals::approve(
            &db,
            &config,
            &approvals,
            &session,
            &username,
            &pin,
            &permission,
        )?;
        audit::record_manager_override(
            &db,
            &session,
            &config.store_id,
            &approver.id,
            &approver.full_name,
            &permission,
        )?;
        Ok(approver)
    })
    .await
    .map_err(|err| err.to_string())?
}

#[tauri::command]
async fn refresh_customers(
    state: tauri::State<'_, AppState>,
) -> Result<customers::CustomerSnapshot, String> {
    let db = state.db.clone();
    let config = state.config.clone();
    tauri::async_runtime::spawn_blocking(move || customers::refresh(&db, &config))
        .await
        .map_err(|err| err.to_string())?
}

#[tauri::command]
fn search_customers(
    state: tauri::State<AppState>,
    query: String,
    limit: Option<i64>,
) -> Result<Vec<serde_json::Value>, String> {
    customers::search(&state.db, &query, limit.unwrap_or(20).clamp(1, 500))
}

#[tauri::command]
fn create_customer(
    state: tauri::State<AppState>,
    input: customers::NewCustomer,
) -> Result<serde_json::Value, String> {
    let Some(session) = state.session()? else {
        return Err("Unlock the register before adding a customer.".into());
    };
    customers::create(&state.db, &session, &input)
}

#[tauri::command]
async fn refresh_serials(
    state: tauri::State<'_, AppState>,
) -> Result<serials::SerialRefresh, String> {
    let db = state.db.clone();
    let config = state.config.clone();
    tauri::async_runtime::spawn_blocking(move || serials::refresh(&db, &config))
        .await
        .map_err(|err| err.to_string())?
}

#[tauri::command]
fn available_serials(
    state: tauri::State<AppState>,
    product_id: String,
    limit: Option<i64>,
    exclude: Option<Vec<String>>,
) -> Result<Vec<serials::SerialRow>, String> {
    serials::available(
        &state.db,
        &product_id,
        limit.unwrap_or(100).clamp(1, 1000),
        &exclude.unwrap_or_default(),
    )
}

#[tauri::command]
fn count_serials(state: tauri::State<AppState>, product_id: String) -> Result<i64, String> {
    serials::count_available(&state.db, &product_id)
}

#[tauri::command]
fn check_serials(
    state: tauri::State<AppState>,
    product_id: String,
    values: Vec<String>,
) -> Result<Vec<serials::SerialCheck>, String> {
    if values.len() > 1000 {
        return Err("Check at most 1000 identifiers at once.".into());
    }
    serials::check(&state.db, &product_id, &values)
}

#[tauri::command]
async fn create_quote(
    state: tauri::State<'_, AppState>,
    payload: serde_json::Value,
) -> Result<serde_json::Value, String> {
    let Some(session) = state.session()? else {
        return Err("Unlock the register before saving a quote.".into());
    };
    if payload
        .get("cashier_id")
        .and_then(serde_json::Value::as_str)
        != Some(session.user.id.as_str())
    {
        return Err(
            "The quote must be attributed to the cashier who unlocked this register.".into(),
        );
    }
    if payload.get("store_id").and_then(serde_json::Value::as_str)
        != Some(state.config.store_id.as_str())
    {
        return Err("The quote must be booked to this terminal's branch (STORE_ID).".into());
    }
    let event = db::QueuedEvent {
        id: String::new(),
        idempotency_key: String::new(),
        entity_type: "sale".into(),
        operation: "upsert".into(),
        payload: payload.clone(),
        occurred_at: String::new(),
    };
    checkout_approvals::check_sale(&state.checkout_approvals, &session, &[event])?;
    let config = state.config.clone();
    tauri::async_runtime::spawn_blocking(move || quotes::create(&config, &payload))
        .await
        .map_err(|err| err.to_string())?
}

#[tauri::command]
async fn open_quote_pdf(
    app: tauri::AppHandle,
    state: tauri::State<'_, AppState>,
    quote_id: String,
    number: String,
) -> Result<String, String> {
    let config = state.config.clone();
    let directory = app
        .path()
        .app_data_dir()
        .map_err(|err| err.to_string())?
        .join("quotes");
    let path = tauri::async_runtime::spawn_blocking(move || {
        quotes::download_pdf(&config, &quote_id, &number, &directory)
    })
    .await
    .map_err(|err| err.to_string())??;
    app.opener()
        .open_path(path.clone(), None::<&str>)
        .map_err(|err| format!("Saved to {path} but could not open it: {err}"))?;
    Ok(path)
}

#[tauri::command]
fn terminal_store(state: tauri::State<AppState>) -> String {
    state.config.store_id.clone()
}

#[tauri::command]
fn terminal_status(state: tauri::State<AppState>) -> terminal::TerminalStatus {
    state.terminal.clone()
}

/// The webview uses this to subscribe to table events. It is the same token the shell already sends.
#[tauri::command]
fn terminal_api_key(state: tauri::State<AppState>) -> String {
    state.config.api_key.clone()
}

/// Exchanges subdomain + activation key for this register's identity, stores it encrypted, and restarts
/// so the tenant's own local database is opened.
#[tauri::command]
async fn activate_terminal(
    app: tauri::AppHandle,
    state: tauri::State<'_, AppState>,
    subdomain: String,
    activation_key: String,
) -> Result<terminal::TerminalStatus, String> {
    if state.terminal.source == "activation" {
        return Err("This register is already activated. Deactivate it first.".into());
    }
    let path = state.terminal_path.clone();
    let activated = tauri::async_runtime::spawn_blocking(move || {
        let config = terminal::activate(&subdomain, &activation_key)?;
        terminal::save(&path, &config)?;
        Ok::<_, String>(config)
    })
    .await
    .map_err(|err| err.to_string())??;
    let status = terminal::TerminalStatus::from_config(&activated, "activation");
    // Give the UI a moment to show the confirmation before the window restarts.
    tauri::async_runtime::spawn_blocking(move || {
        std::thread::sleep(std::time::Duration::from_millis(1200));
        app.restart();
    });
    Ok(status)
}

/// A manager with devices:manage releases the register (e.g. to move it to another store).
#[tauri::command]
async fn deactivate_terminal(
    app: tauri::AppHandle,
    state: tauri::State<'_, AppState>,
    username: String,
    pin: String,
) -> Result<(), String> {
    if state.terminal.source != "activation" {
        return Err(
            "This register was configured from the developer .env and has no activation to remove."
                .into(),
        );
    }
    let pending = state.db.pending_count()?;
    if pending > 0 {
        return Err(format!(
            "{pending} sale(s) are still waiting to sync. Reconnect and sync before deactivating."
        ));
    }
    let db = state.db.clone();
    let config = state.config.clone();
    let path = state.terminal_path.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let manager = auth::pin_login(&db, &config, &username, &pin)?.session.user;
        if !manager
            .permissions
            .iter()
            .any(|item| item == "devices:manage")
        {
            return Err(format!(
                "{} cannot deactivate registers.",
                manager.full_name
            ));
        }
        terminal::remove(&path)
    })
    .await
    .map_err(|err| err.to_string())??;
    *state.session.lock().map_err(|err| err.to_string())? = None;
    app.restart();
}

#[tauri::command]
async fn check_branches(
    state: tauri::State<'_, AppState>,
    product_id: Option<String>,
    serial: Option<String>,
) -> Result<serde_json::Value, String> {
    let config = state.config.clone();
    tauri::async_runtime::spawn_blocking(move || {
        sync::branch_availability(&config, product_id.as_deref(), serial.as_deref())
    })
    .await
    .map_err(|err| err.to_string())?
}

#[tauri::command]
async fn lookup_receipt(
    state: tauri::State<'_, AppState>,
    code: String,
) -> Result<returns::ReceiptLookup, String> {
    let db = state.db.clone();
    let config = state.config.clone();
    tauri::async_runtime::spawn_blocking(move || returns::lookup(&db, &config, &code))
        .await
        .map_err(|err| err.to_string())?
}

#[tauri::command]
async fn approve_return(
    state: tauri::State<'_, AppState>,
    username: String,
    pin: String,
) -> Result<auth::CashierProfile, String> {
    let Some(session) = state.session()? else {
        return Err("Unlock the register before approving a return.".into());
    };
    let db = state.db.clone();
    let config = state.config.clone();
    let approvals = state.approvals.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let approver = returns::approve(&db, &config, &approvals, &session, &username, &pin)?;
        audit::record_manager_override(
            &db,
            &session,
            &config.store_id,
            &approver.id,
            &approver.full_name,
            "returns:refund",
        )?;
        Ok(approver)
    })
    .await
    .map_err(|err| err.to_string())?
}

#[tauri::command]
fn enqueue_return(
    state: tauri::State<AppState>,
    batch_id: String,
    events: Vec<db::QueuedEvent>,
) -> Result<(), String> {
    let Some(session) = state.session()? else {
        return Err("Unlock the register before refunding.".into());
    };
    returns::enqueue(&state.db, &state.approvals, &session, &batch_id, &events)
}

#[tauri::command]
fn recent_returns(
    state: tauri::State<AppState>,
    limit: Option<i64>,
) -> Result<Vec<returns::LocalReturn>, String> {
    returns::recent(&state.db, limit.unwrap_or(20).clamp(1, 100))
}

#[tauri::command]
fn pending_count(state: tauri::State<AppState>) -> Result<i64, String> {
    state.db.pending_count()
}

#[tauri::command]
fn batch_status(
    state: tauri::State<AppState>,
    batch_id: String,
) -> Result<Option<db::BatchStatus>, String> {
    state.db.batch_status(&batch_id)
}

#[tauri::command]
async fn flush_sync(state: tauri::State<'_, AppState>) -> Result<sync::SyncReport, String> {
    let db = state.db.clone();
    let config = state.config.clone();
    let lock = state.flush_lock.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let _guard = lock.lock().map_err(|err| err.to_string())?;
        let report = sync::flush(&db, &config);
        // The audit ledger syncs on the same cadence; its failures surface through audit_status.
        let _ = audit::flush(&db, &config);
        report
    })
    .await
    .map_err(|err| err.to_string())?
}

#[tauri::command]
async fn refresh_products(
    app: tauri::AppHandle,
    state: tauri::State<'_, AppState>,
) -> Result<CatalogSnapshot, String> {
    let db = state.db.clone();
    let config = state.config.clone();
    let media_dir = state.media_dir.clone();
    let snapshot =
        tauri::async_runtime::spawn_blocking(move || -> Result<CatalogSnapshot, String> {
            match sync::fetch_products(&config) {
                Ok(products) => {
                    db.replace_products(&products)?;
                    Ok(CatalogSnapshot {
                        products,
                        source: "api",
                        message: None,
                    })
                }
                Err(reason) => Ok(CatalogSnapshot {
                    products: db.list_products()?,
                    source: "cache",
                    message: Some(reason),
                }),
            }
        })
        .await
        .map_err(|err| err.to_string())??;
    if snapshot.source == "api" {
        let urls = media_cache::urls(&snapshot.products);
        tauri::async_runtime::spawn(async move {
            let saved = tauri::async_runtime::spawn_blocking(move || {
                media_cache::download_missing(&media_dir, &urls)
            })
            .await
            .unwrap_or(false);
            if saved {
                let _ = app.emit("product-images-cached", ());
            }
        });
    }
    Ok(snapshot)
}

#[tauri::command]
async fn catalog_revision(state: tauri::State<'_, AppState>) -> Result<String, String> {
    let config = state.config.clone();
    tauri::async_runtime::spawn_blocking(move || sync::catalog_revision(&config))
        .await
        .map_err(|err| err.to_string())?
}

#[tauri::command]
fn local_product_image(state: tauri::State<AppState>, url: String) -> Option<String> {
    media_cache::local_path(&state.media_dir, &url).map(|path| path.to_string_lossy().into_owned())
}

#[tauri::command]
async fn business_currency(
    state: tauri::State<'_, AppState>,
) -> Result<settings::CurrencySnapshot, String> {
    let db = state.db.clone();
    let config = state.config.clone();
    tauri::async_runtime::spawn_blocking(move || settings::refresh(&db, &config))
        .await
        .map_err(|err| err.to_string())?
}

#[tauri::command]
fn log_audit_event(
    state: tauri::State<AppState>,
    event: audit::AuditInput,
) -> Result<String, String> {
    let Some(session) = state.session()? else {
        return Err("Unlock the register first.".into());
    };
    audit::record_from_ui(&state.db, &session, &state.config.store_id, event)
}

#[tauri::command]
fn audit_status(state: tauri::State<AppState>) -> Result<audit::AuditStatus, String> {
    audit::status(&state.db)
}

#[tauri::command]
async fn check_app_update(
    app: tauri::AppHandle,
    state: tauri::State<'_, AppState>,
) -> Result<Option<updates::AppUpdate>, String> {
    let config = state.config.clone();
    Ok(updates::check(&config, &app.package_info().version.to_string()).await)
}

#[tauri::command]
async fn install_app_update(app: tauri::AppHandle, state: tauri::State<'_, AppState>) -> Result<(), String> {
    let config = state.config.clone();
    updates::install(&app, &config, &app.package_info().version.to_string()).await
}

#[tauri::command]
fn recent_audit_events(
    state: tauri::State<AppState>,
    limit: Option<i64>,
) -> Result<Vec<audit::LocalAuditEvent>, String> {
    audit::recent(&state.db, limit.unwrap_or(20).clamp(1, 200))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            DesktopConfig::load_env_file().map_err(std::io::Error::other)?;
            let directory = app.path().app_data_dir()?;
            std::fs::create_dir_all(&directory)?;
            let terminal_path = terminal::config_path(&directory);
            // Activated: that tenant's own database. Developer .env: the legacy shared file. Neither: activation.
            let (config, status, database) = match terminal::load(&terminal_path) {
                Ok(Some(activated)) => (
                    DesktopConfig::from_terminal(&activated),
                    terminal::TerminalStatus::from_config(&activated, "activation"),
                    terminal::database_path(&directory, &activated.tenant_slug),
                ),
                other => {
                    if let Err(message) = other {
                        eprintln!("ai-pos: ignoring terminal configuration: {message}");
                    }
                    match DesktopConfig::from_env().map_err(std::io::Error::other)? {
                        Some(config) => {
                            let status = terminal::TerminalStatus {
                                activated: true,
                                source: "env".into(),
                                tenant_domain: config.tenant_domain.clone(),
                                store_id: config.store_id.clone(),
                                register_code: config.device_id.clone(),
                                ..terminal::TerminalStatus::none()
                            };
                            (config, status, directory.join("ai-pos.db"))
                        }
                        None => (
                            DesktopConfig::unactivated(),
                            terminal::TerminalStatus::none(),
                            directory.join("ai-pos.db"),
                        ),
                    }
                }
            };
            if let Some(parent) = database.parent() {
                std::fs::create_dir_all(parent)?;
            }
            let db = Db::open(&database).map_err(std::io::Error::other)?;
            let media_dir = directory.join("media");
            updates::watch(app.handle().clone(), config.clone());
            app.manage(AppState {
                db: Arc::new(db),
                config,
                media_dir,
                terminal: status,
                terminal_path,
                flush_lock: Arc::new(Mutex::new(())),
                session: Mutex::new(None),
                user_token: Mutex::new(None),
                approvals: Arc::new(Mutex::new(Default::default())),
                checkout_approvals: Arc::new(Mutex::new(Default::default())),
            });
            keyboard_detector::start(app.handle().clone());
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            pin_login,
            unlock_cashier,
            list_cashiers,
            current_session,
            lock_session,
            search_products,
            remote_search,
            terminal_store,
            terminal_status,
            terminal_api_key,
            activate_terminal,
            deactivate_terminal,
            check_branches,
            enqueue_events,
            lookup_receipt,
            approve_return,
            enqueue_return,
            recent_returns,
            pending_count,
            batch_status,
            flush_sync,
            refresh_products,
            catalog_revision,
            local_product_image,
            business_currency,
            approve_manager,
            refresh_customers,
            search_customers,
            create_customer,
            refresh_serials,
            available_serials,
            count_serials,
            check_serials,
            create_quote,
            open_quote_pdf,
            log_audit_event,
            audit_status,
            recent_audit_events,
            erp::refresh_series,
            erp::next_document_number,
            erp::printer_settings,
            erp::probe_printer,
            erp::save_printer_settings,
            erp::print_receipt,
            erp::open_cash_drawer,
            erp::open_document_pdf,
            erp::current_shift,
            erp::open_shift,
            erp::record_cash_movement,
            erp::shift_summary,
            erp::close_shift,
            erp::recent_shifts,
            erp::list_table_sessions,
            erp::save_table_session,
            erp::cache_table_event,
            erp::close_table_session,
            erp::hold_cart,
            erp::held_carts,
            erp::recall_cart,
            erp::held_count,
            erp::add_layaway_payment,
            erp::list_batches,
            erp::resolve_batch,
            erp::rejected_count,
            erp::refresh_floors,
            erp::payment_intent,
            payments::payments_request,
            erp::store_credit_lookup,
            erp::trade_in_request,
            erp::approval_request,
            erp::active_promotions,
            erp::clock_status,
            erp::clock_in,
            erp::clock_out,
            erp::on_duty,
            erp::foreign_currencies,
            erp::loyalty_settings,
            keyboard_detector::check_hardware_keyboard_status,
            scale::scale_ports,
            scale::read_scale,
            menu::refresh_menu,
            restaurant::restaurant_request,
            retail::retail_request,
            check_app_update,
            install_app_update
        ])
        .run(tauri::generate_context!())
        .expect("ai-pos desktop failed to start");
}
