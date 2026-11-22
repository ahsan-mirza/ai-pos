mod acceptance;
mod zoom;
mod allocation;
mod staff;
mod audit;
mod auth;
mod checkout_approvals;
mod customers;
mod bootstrap;
mod demo;
mod entitlement;
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
mod printer_discovery;
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
    /// The access token that received HTTP 401 for staff provisioning. The same token is not sent again.
    provision_auth_block: Mutex<Option<String>>,
    demo_notice: Mutex<Option<String>>,
    demo_launch: Mutex<Option<String>>,
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
    if state.user_token.lock().map_err(|err| err.to_string())?.is_some() {
        let _ = deliver_staff_provisioning(&state);
    }
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
    if state.user_token.lock().map_err(|err| err.to_string())?.is_some() {
        let _ = deliver_staff_provisioning(&state);
    }
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
    // The access token is memory-only. Restoring an online cashier without it
    // makes the register look signed in while retail calls authenticate as the
    // terminal, and user-only routes answer that a signed-in user is required.
    if mode != "offline" {
        let signed_in = state
            .user_token
            .lock()
            .map_err(|err| err.to_string())?
            .is_some();
        if !signed_in {
            state.db.clear_register_session()?;
            return Ok(None);
        }
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

fn register_tenant(config: &sync::DesktopConfig) -> String {
    let trimmed = config.tenant_domain.trim();
    if trimmed.is_empty() {
        "local".to_string()
    } else {
        trimmed.to_string()
    }
}

fn preference_tenant(config: &sync::DesktopConfig, requested: &str) -> Result<(), String> {
    if requested != register_tenant(config) {
        return Err("This preference belongs to another store.".into());
    }
    Ok(())
}

#[tauri::command]
fn read_catalogue_preference(
    state: tauri::State<AppState>,
    tenant_id: String,
    user_id: String,
) -> Result<Option<db::StoredPreference>, String> {
    preference_tenant(&state.config, &tenant_id)?;
    state.db.read_catalogue_preference(&tenant_id, &user_id)
}

#[tauri::command]
fn write_catalogue_preference(
    state: tauri::State<AppState>,
    tenant_id: String,
    user_id: String,
    value: String,
    updated_at: String,
    revision: i64,
    dirty: bool,
) -> Result<db::StoredPreference, String> {
    preference_tenant(&state.config, &tenant_id)?;
    state
        .db
        .write_catalogue_preference(&tenant_id, &user_id, &value, &updated_at, revision, dirty)
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
    // Online checkout does not draw the local grant. The server sells unreserved
    // branch stock and leaves other terminals' reservations in place.
    if session.mode == "offline" {
        match saved_terminal(&state) {
            Ok(saved) => {
                return allocation::commit_queued(&state.db, &expected_binding(&saved), &batch_id, &events);
            }
            Err(message) => {
                if allocation::requires_grant(&state.db, &events)? {
                    return Err(message);
                }
            }
        }
    }
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
    if let Some(blocked) = terminal::replacement_block(&state.terminal.source, state.db.pending_count()?) {
        return Err(blocked);
    }
    let path = state.terminal_path.clone();
    let activated = tauri::async_runtime::spawn_blocking(move || {
        let existing = match terminal::load(&path) {
            Ok(value) => value,
            // An activation key is the authorized replacement. Save keeps a backup and does not run at startup.
            Err(_) if path.exists() => None,
            Err(message) => return Err(message),
        };
        let (public_key, private_key) = match existing.as_ref() {
            Some(saved) if !saved.device_public_key.is_empty() && !saved.device_private_key.is_empty() => {
                (saved.device_public_key.clone(), saved.device_private_key.clone())
            }
            _ => entitlement::generate_device_key()?,
        };
        let outcome = terminal::activate(&subdomain, &activation_key, &public_key)?;
        let binding = entitlement::device_binding(&public_key)
            .ok_or_else(|| "The device key could not be prepared.".to_string())?;
        let mut stored = terminal::TerminalState {
            storage_version: 2,
            config: outcome.config,
            device_public_key: public_key,
            device_private_key: private_key,
            entitlement_payload: String::new(),
            entitlement_signature: String::new(),
            entitlement_key_id: String::new(),
        };
        let Some(signed) = outcome.entitlement else {
            return Err("The server did not return a permanent entitlement. The register was not saved.".into());
        };
        let expected = entitlement::ExpectedBinding {
            tenant_id: if stored.config.tenant_id.is_empty() {
                stored.config.tenant_slug.clone()
            } else {
                stored.config.tenant_id.clone()
            },
            branch_id: stored.config.store_id.clone(),
            terminal_id: stored.config.register_id.clone(),
            device_binding: binding,
        };
        let code = entitlement::code_for(
            &signed.payload,
            &signed.signature,
            &signed.key_id,
            &expected,
            crate::auth::now_secs(),
        );
        if code != entitlement::VALID {
            return Err(entitlement::verification_message(code).into());
        }
        stored.entitlement_payload = signed.payload;
        stored.entitlement_signature = signed.signature;
        stored.entitlement_key_id = signed.key_id;
        terminal::save(&path, &stored)?;
        Ok::<_, String>(stored)
    })
    .await
    .map_err(|err| err.to_string())??;
    let status = terminal::TerminalStatus::from_config(&activated.config, "activation");
    // Give the UI a moment to show the confirmation before the window restarts.
    tauri::async_runtime::spawn_blocking(move || {
        std::thread::sleep(std::time::Duration::from_millis(1200));
        app.restart();
    });
    Ok(status)
}

fn open_posdemo_from_args(app: &tauri::AppHandle, args: &[String]) {
    let Some(path) = demo::posdemo_argument(args) else {
        return;
    };
    let state = app.state::<AppState>();
    {
        let mut launch = match state.demo_launch.lock() {
            Ok(guard) => guard,
            Err(_) => return,
        };
        if launch.is_some() {
            return;
        }
        *launch = Some(path.clone());
    }
    let app = app.clone();
    tauri::async_runtime::spawn(async move {
        if let Err(message) = enroll_demo_path(app.clone(), path).await {
            if let Some(state) = app.try_state::<AppState>() {
                if let Ok(mut notice) = state.demo_notice.lock() {
                    *notice = Some(message);
                }
                if let Ok(mut launch) = state.demo_launch.lock() {
                    *launch = None;
                }
            }
        }
    });
}

/// Opens a demo connection file, exchanges it once, and stores the device token with DPAPI.
async fn enroll_demo_path(app: tauri::AppHandle, path: String) -> Result<terminal::TerminalStatus, String> {
    let state = app.state::<AppState>();
    if state.terminal.activated && !state.terminal.demo {
        return Err("This register is already activated.".into());
    }
    if let Some(blocked) = terminal::replacement_block(&state.terminal.source, state.db.pending_count()?) {
        return Err(blocked);
    }
    let file = PathBuf::from(&path);
    let config_path = state.terminal_path.clone();
    let status = tauri::async_runtime::spawn_blocking(move || {
        let ticket = demo::read_handoff(&file)?;
        let config = match demo::exchange_ticket(&ticket) {
            Ok(config) => config,
            Err(fault) => {
                if matches!(fault, demo::DemoFault::Refused(_)) {
                    let _ = demo::delete_handoff(&file);
                }
                return Err(fault.message().to_string());
            }
        };
        if let Err(message) = terminal::save(&config_path, &terminal::TerminalState::from_config(config.clone())) {
            let _ = demo::delete_handoff(&file);
            return Err(format!("{message} Download a new connection file."));
        }
        let _ = demo::delete_handoff(&file);
        Ok(terminal::TerminalStatus::from_config(&config, "activation"))
    })
    .await
    .map_err(|err| err.to_string())??;
    tauri::async_runtime::spawn_blocking(move || {
        std::thread::sleep(std::time::Duration::from_millis(400));
        app.restart();
    });
    Ok(status)
}

#[tauri::command]
async fn enroll_demo_file(app: tauri::AppHandle, path: String) -> Result<terminal::TerminalStatus, String> {
    enroll_demo_path(app, path).await
}

#[tauri::command]
fn take_demo_notice(state: tauri::State<AppState>) -> Result<Option<String>, String> {
    state
        .demo_notice
        .lock()
        .map(|mut guard| guard.take())
        .map_err(|err| err.to_string())
}

/// Asks the server for the demo POS session. A revoked demo clears the local device token.
#[tauri::command]
async fn open_demo_session(app: tauri::AppHandle, state: tauri::State<'_, AppState>) -> Result<Session, String> {
    if !state.terminal.demo {
        return Err("This register is not running a demo.".into());
    }
    let config = state.config.clone();
    let opened = tauri::async_runtime::spawn_blocking(move || demo::open_session(&config))
        .await
        .map_err(|err| err.to_string())?;
    match opened {
        Ok(unlocked) => {
            let session = unlocked.session.clone();
            *state.session.lock().map_err(|err| err.to_string())? = Some(session.clone());
            *state.user_token.lock().map_err(|err| err.to_string())? = unlocked.access_token;
            state
                .db
                .save_register_session(&session.user, session.mode, session.unlocked_at)?;
            Ok(session)
        }
        Err(demo::DemoFault::Offline(message)) => match current_session(state)? {
            Some(session) => Ok(session),
            None => Err(message),
        },
        Err(demo::DemoFault::Refused(message)) => {
            let path = state.terminal_path.clone();
            state.db.clear_register_session()?;
            terminal::remove(&path)?;
            tauri::async_runtime::spawn_blocking(move || {
                std::thread::sleep(std::time::Duration::from_millis(1200));
                app.restart();
            });
            Err(message)
        }
    }
}

/// Leaves the demo. Shared server data stays. Unsynced local sales must sync first.
#[tauri::command]
async fn exit_demo(app: tauri::AppHandle, state: tauri::State<'_, AppState>) -> Result<(), String> {
    if !state.terminal.demo {
        return Err("This register is not running a demo.".into());
    }
    let pending = state.db.pending_count()?;
    if pending > 0 {
        return Err(format!(
            "{pending} sale(s) are still waiting to sync. Reconnect and sync before leaving the demo."
        ));
    }
    let slug = state.terminal.tenant_slug.clone();
    if slug.is_empty() || slug.contains("..") || slug.contains('/') || slug.contains('\\') {
        return Err("This demo register could not be closed.".into());
    }
    let path = state.terminal_path.clone();
    let directory = path
        .parent()
        .map(|parent| parent.join("tenants").join(slug))
        .unwrap_or_default();
    state.db.clear_register_session()?;
    *state.session.lock().map_err(|err| err.to_string())? = None;
    *state.user_token.lock().map_err(|err| err.to_string())? = None;
    terminal::remove(&path)?;
    if directory.exists() {
        let _ = std::fs::remove_dir_all(&directory);
    }
    tauri::async_runtime::spawn_blocking(move || {
        std::thread::sleep(std::time::Duration::from_millis(400));
        app.restart();
    });
    Ok(())
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
fn note_remote_return(state: tauri::State<AppState>, notice: serde_json::Value) -> Result<(), String> {
    returns::note_remote(&state.db, &notice)
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

#[derive(serde::Serialize)]
struct ReadinessReport {
    entitlement_code: String,
    readiness: String,
    /// `valid` ignores the 24-hour lease. `legacy` keeps it. `blocked` refuses ordinary selling.
    selling: String,
    message: String,
    single_terminal_offline_stock: bool,
}

fn catalogue_facts(db: &db::Db) -> String {
    let (products, staff) = db.readiness_counts().unwrap_or((0, 0));
    let menu = db.config_count("menu").unwrap_or(0);
    let floor = db.config_count("floor").unwrap_or(0);
    let cursor = match db.bootstrap_cursor() {
        Ok(Some(_)) => "committed",
        _ => "missing",
    };
    format!("Datasets: products {products}, staff {staff}, menu {menu}, floor {floor}, cursor {cursor}.")
}

/// Local baseline only. `OFFLINE_READY` does not mean this terminal has its own stock allocation.
#[tauri::command]
fn bootstrap_readiness(
    state: tauri::State<AppState>,
    capability_snapshot: bool,
    server_subscription_blocked: bool,
) -> Result<ReadinessReport, String> {
    let loaded = match terminal::load(&state.terminal_path) {
        Ok(value) => value,
        Err(message) => {
            return Ok(ReadinessReport {
                entitlement_code: if message.contains("another Windows account") {
                    entitlement::STORAGE_DECRYPTION_FAILED.into()
                } else {
                    entitlement::MALFORMED.into()
                },
                readiness: entitlement::REQUIRES_ONLINE_RECOVERY.into(),
                selling: "blocked".into(),
                message,
                single_terminal_offline_stock: false,
            });
        }
    };
    let Some(saved) = loaded else {
        return Ok(ReadinessReport {
            entitlement_code: entitlement::MISSING.into(),
            readiness: entitlement::NOT_ACTIVATED.into(),
            selling: if state.terminal.source == "env" { "legacy" } else { "blocked" }.into(),
            message: if state.terminal.source == "env" {
                "Developer configuration keeps the subscription lease.".into()
            } else {
                entitlement::verification_message(entitlement::MISSING).into()
            },
            single_terminal_offline_stock: false,
        });
    };
    let binding = entitlement::device_binding(&saved.device_public_key).unwrap_or_default();
    let code = entitlement::code_for(
        &saved.entitlement_payload,
        &saved.entitlement_signature,
        &saved.entitlement_key_id,
        &entitlement::ExpectedBinding {
            tenant_id: if saved.config.tenant_id.is_empty() {
                saved.config.tenant_slug.clone()
            } else {
                saved.config.tenant_id.clone()
            },
            branch_id: saved.config.store_id.clone(),
            terminal_id: saved.config.register_id.clone(),
            device_binding: binding,
        },
        auth::now_secs(),
    );
    let (products, staff) = state.db.readiness_counts().unwrap_or((0, 0));
    let pending = state.db.pending_count().unwrap_or(0);
    let queue_readable = state.db.pending_count().is_ok();
    let stored_bootstrap = state.db.bootstrap_label();
    let bootstrap_status = if stored_bootstrap.is_empty() {
        "incomplete".to_string()
    } else {
        stored_bootstrap
    };
    Ok(ReadinessReport {
        entitlement_code: code.into(),
        readiness: entitlement::readiness(
            code,
            &entitlement::LocalBaseline {
                activated: true,
                storage_damaged: false,
                sqlite_open: Some(true),
                queue_readable,
                products,
                staff,
                pending,
                capability_snapshot,
                server_subscription_blocked,
                bootstrap_status: bootstrap_status.clone(),
                pull_failed: bootstrap_status == "pull_failed",
            },
        )
        .into(),
        selling: if code == entitlement::VALID {
            "valid"
        } else if code == entitlement::MISSING {
            "legacy"
        } else {
            "blocked"
        }
        .into(),
        message: format!(
            "{} {} {}",
            entitlement::verification_message(code),
            entitlement::describe_bootstrap(&bootstrap_status),
            catalogue_facts(&state.db)
        ),
        single_terminal_offline_stock: entitlement::single_terminal_offline_stock_enabled(),
    })
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
async fn bootstrap_catalogue(state: tauri::State<'_, AppState>) -> Result<i64, String> {
    let db = state.db.clone();
    let config = state.config.clone();
    tauri::async_runtime::spawn_blocking(move || sync::bootstrap_catalogue(&config, &db))
        .await
        .map_err(|err| err.to_string())?
}

#[tauri::command]
async fn pull_catalogue(state: tauri::State<'_, AppState>) -> Result<usize, String> {
    let db = state.db.clone();
    let config = state.config.clone();
    tauri::async_runtime::spawn_blocking(move || sync::pull_catalogue(&config, &db))
        .await
        .map_err(|err| err.to_string())?
}

/// Floor plan from the signed register_floor rows for this terminal's branch.
/// Live table occupancy stays on the server. Offline, every stored table is free.
#[tauri::command]
fn local_dining_floor(state: tauri::State<AppState>) -> Result<serde_json::Value, String> {
    let payloads = state.db.config_payloads("floor")?;
    Ok(assemble_local_floor(&state.config.store_id, &payloads))
}

fn assemble_local_floor(store_id: &str, payloads: &[String]) -> serde_json::Value {
    let mut areas = Vec::new();
    let mut tables = Vec::new();
    for text in payloads {
        let Ok(value) = serde_json::from_str::<serde_json::Value>(text) else {
            continue;
        };
        let row_store = value.get("store_id").and_then(|item| item.as_str()).unwrap_or("");
        if !store_id.is_empty() && !row_store.is_empty() && row_store != store_id {
            continue;
        }
        match value.get("kind").and_then(|item| item.as_str()).unwrap_or("") {
            "area" => areas.push(value),
            "table" => tables.push(value),
            _ => {}
        }
    }
    let mut assembled = Vec::new();
    for area in areas {
        if !area.get("is_active").and_then(|item| item.as_bool()).unwrap_or(true) {
            continue;
        }
        let id = area.get("id").and_then(|item| item.as_str()).unwrap_or("").to_string();
        let mut rows = Vec::new();
        for table in &tables {
            if table.get("area_id").and_then(|item| item.as_str()) != Some(id.as_str()) {
                continue;
            }
            if !table.get("is_active").and_then(|item| item.as_bool()).unwrap_or(true) {
                continue;
            }
            let shape = table.get("shape").and_then(|item| item.as_str()).unwrap_or("square");
            let shape = if shape == "round" || shape == "rect" { shape } else { "square" };
            rows.push(serde_json::json!({
                "id": table.get("id").cloned().unwrap_or(serde_json::Value::Null),
                "area_id": id,
                "label": table.get("label").cloned().unwrap_or(serde_json::json!("")),
                "seats": table.get("seats").cloned().unwrap_or(serde_json::json!(0)),
                "shape": shape,
                "x": table.get("x").cloned().unwrap_or(serde_json::json!(0)),
                "y": table.get("y").cloned().unwrap_or(serde_json::json!(0)),
                "w": table.get("w").cloned().unwrap_or(serde_json::json!(0)),
                "h": table.get("h").cloned().unwrap_or(serde_json::json!(0)),
                "is_active": true,
                "status": "free",
                "order_id": null,
                "order_number": null,
                "covers": 0,
                "seated_at": null,
                "open_cents": 0,
            }));
        }
        assembled.push(serde_json::json!({
            "id": id,
            "store_id": area.get("store_id").cloned().unwrap_or(serde_json::json!(store_id)),
            "name": area.get("name").cloned().unwrap_or(serde_json::json!("")),
            "position": area.get("position").cloned().unwrap_or(serde_json::json!(0)),
            "is_active": true,
            "tables": rows,
        }));
    }
    serde_json::json!({ "store_id": store_id, "areas": assembled })
}

#[tauri::command]
fn cached_products(state: tauri::State<AppState>) -> Result<Vec<db::ProductRow>, String> {
    state.db.list_products()
}

#[tauri::command]
async fn refresh_products(
    app: tauri::AppHandle,
    state: tauri::State<'_, AppState>,
) -> Result<CatalogSnapshot, String> {
    let db = state.db.clone();
    let config = state.config.clone();
    let media_dir = state.media_dir.clone();
    let expected = saved_terminal(&state).ok().map(|saved| expected_binding(&saved));
    let snapshot =
        tauri::async_runtime::spawn_blocking(move || -> Result<CatalogSnapshot, String> {
            match sync::fetch_products(&config) {
                Ok(products) => {
                    db.replace_products(&products)?;
                    if let Some(expected) = expected.as_ref() {
                        // A feed error leaves the catalogue in place. An invalid manifest is not installed.
                        let _ = sync::install_allocations(&config, &db, expected);
                    }
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
#[derive(Serialize)]
struct AllocationBalanceOut {
    product_id: String,
    allocation_id: String,
    remaining: i64,
}

#[derive(Serialize)]
struct RegisterStaffRow {
    user_id: String,
    username: String,
    full_name: String,
    role_name: String,
    store_id: String,
    provisioning_status: String,
    is_active: i64,
}

#[derive(Serialize)]
struct StaffSeatReport {
    trusted: bool,
    limit: Option<i64>,
    active: i64,
}

fn saved_terminal(state: &AppState) -> Result<terminal::TerminalState, String> {
    terminal::load(&state.terminal_path)?.ok_or_else(|| "This register is not activated.".to_string())
}

fn expected_binding(saved: &terminal::TerminalState) -> entitlement::ExpectedBinding {
    let binding = entitlement::device_binding(&saved.device_public_key).unwrap_or_default();
    entitlement::ExpectedBinding {
        tenant_id: if saved.config.tenant_id.is_empty() {
            saved.config.tenant_slug.clone()
        } else {
            saved.config.tenant_id.clone()
        },
        branch_id: saved.config.store_id.clone(),
        terminal_id: saved.config.register_id.clone(),
        device_binding: binding,
    }
}

/// Staff cap from the signed entitlement. A missing or invalid document is not a cap of zero and is not unlimited.
fn staff_cap(saved: &terminal::TerminalState) -> (Option<i64>, bool) {
    let binding = expected_binding(saved);
    let code = entitlement::code_for(
        &saved.entitlement_payload,
        &saved.entitlement_signature,
        &saved.entitlement_key_id,
        &binding,
        auth::now_secs(),
    );
    if code != entitlement::VALID {
        return (None, false);
    }
    let Ok(document) = serde_json::from_str::<serde_json::Value>(&saved.entitlement_payload) else {
        return (None, false);
    };
    let Some(limits) = document.get("limits") else {
        return (None, false);
    };
    match limits.get("staff") {
        Some(serde_json::Value::Null) => (None, true),
        Some(serde_json::Value::Number(number)) => match number.as_i64() {
            Some(limit) if limit >= 0 => (Some(limit), true),
            _ => (None, false),
        },
        _ => (None, false),
    }
}

fn staff_actor(state: &tauri::State<AppState>) -> Result<auth::CashierProfile, String> {
    let session = current_session(state.clone())?.ok_or("Unlock the register before managing staff.")?;
    let allowed = session.user.role_name == "Store Manager" || session.user.role_name == "Super Admin";
    if !allowed || !session.user.permissions.iter().any(|item| item == "users:create") {
        return Err("You cannot manage staff.".into());
    }
    Ok(session.user)
}

fn fresh_staff_id(prefix: &str) -> String {
    use rand::RngCore;
    let mut bytes = [0_u8; 16];
    rand::thread_rng().fill_bytes(&mut bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    let id = format!(
        "{:02x}{:02x}{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}{:02x}{:02x}{:02x}{:02x}",
        bytes[0], bytes[1], bytes[2], bytes[3], bytes[4], bytes[5], bytes[6], bytes[7], bytes[8], bytes[9], bytes[10], bytes[11], bytes[12], bytes[13], bytes[14], bytes[15]
    );
    if prefix == "staff" {
        id
    } else {
        format!("{prefix}-{id}")
    }
}

#[tauri::command]
fn terminal_allocation_balances(state: tauri::State<AppState>) -> Result<Vec<AllocationBalanceOut>, String> {
    let saved = saved_terminal(&state)?;
    let rows = allocation::verified_balances(&state.db, &expected_binding(&saved))?;
    Ok(rows
        .into_iter()
        .map(|(product_id, allocation_id, remaining)| AllocationBalanceOut {
            product_id,
            allocation_id,
            remaining,
        })
        .collect())
}

#[tauri::command]
fn register_staff_seats(state: tauri::State<AppState>) -> Result<StaffSeatReport, String> {
    let _actor = staff_actor(&state)?;
    let saved = saved_terminal(&state)?;
    let (limit, trusted) = staff_cap(&saved);
    let active: i64 = state.db.read(|conn| {
        conn.query_row(
            "SELECT COUNT(*) FROM cached_users WHERE is_active = 1 AND provisioning_status != 'rejected'",
            [],
            |row| row.get(0),
        )
        .map_err(|err| err.to_string())
    })?;
    Ok(StaffSeatReport { trusted, limit, active })
}

#[tauri::command]
fn list_register_staff(state: tauri::State<AppState>) -> Result<Vec<RegisterStaffRow>, String> {
    let _actor = staff_actor(&state)?;
    state.db.read(|conn| {
        let mut statement = conn
            .prepare(
                "SELECT user_id, username, full_name, COALESCE(store_id, ''), role_name, provisioning_status, is_active
                 FROM cached_users ORDER BY full_name",
            )
            .map_err(|err| err.to_string())?;
        let rows = statement
            .query_map([], |row| {
                Ok(RegisterStaffRow {
                    user_id: row.get(0)?,
                    username: row.get(1)?,
                    full_name: row.get(2)?,
                    store_id: row.get(3)?,
                    role_name: row.get(4)?,
                    provisioning_status: row.get(5)?,
                    is_active: row.get(6)?,
                })
            })
            .map_err(|err| err.to_string())?;
        rows.collect::<Result<Vec<_>, _>>().map_err(|err| err.to_string())
    })
}

#[tauri::command]
fn create_register_staff(
    state: tauri::State<AppState>,
    username: String,
    full_name: String,
    role_name: String,
    pin: String,
) -> Result<String, String> {
    let actor = staff_actor(&state)?;
    let saved = saved_terminal(&state)?;
    let (limit, trusted) = staff_cap(&saved);
    let store_id = actor.store_id.clone().filter(|item| !item.is_empty()).unwrap_or_else(|| saved.config.store_id.clone());
    staff::create_local(
        &state.db,
        staff::NewStaff {
            actor_id: actor.id,
            actor_role: actor.role_name,
            actor_store_id: store_id.clone(),
            seat_limit: limit,
            seat_trusted: trusted,
            tenant_id: expected_binding(&saved).tenant_id,
            terminal_id: saved.config.register_id.clone(),
            user_id: fresh_staff_id("staff"),
            username,
            full_name,
            store_id,
            role_name,
            pin,
            event_id: fresh_staff_id("event"),
        },
    )
}

#[tauri::command]
fn edit_register_staff(
    state: tauri::State<AppState>,
    user_id: String,
    full_name: String,
    role_name: String,
) -> Result<(), String> {
    let actor = staff_actor(&state)?;
    let saved = saved_terminal(&state)?;
    let store_id = actor.store_id.clone().filter(|item| !item.is_empty()).unwrap_or_else(|| saved.config.store_id.clone());
    staff::edit_local(
        &state.db,
        &actor.id,
        &actor.role_name,
        &store_id,
        &user_id,
        &full_name,
        &role_name,
        &fresh_staff_id("event"),
        &expected_binding(&saved).tenant_id,
        &saved.config.register_id,
    )
}

#[tauri::command]
fn reset_register_staff_pin(state: tauri::State<AppState>, user_id: String, pin: String) -> Result<(), String> {
    let actor = staff_actor(&state)?;
    let saved = saved_terminal(&state)?;
    staff::reset_pin_local(
        &state.db,
        &actor.id,
        &actor.role_name,
        &user_id,
        &pin,
        &fresh_staff_id("event"),
        &expected_binding(&saved).tenant_id,
        &saved.config.register_id,
    )
}

#[tauri::command]
fn disable_register_staff(state: tauri::State<AppState>, user_id: String) -> Result<(), String> {
    let actor = staff_actor(&state)?;
    staff::disable_local(
        &state.db,
        &actor.id,
        &actor.role_name,
        &user_id,
        &fresh_staff_id("event"),
    )
}

#[tauri::command]
fn submit_staff_provisioning(state: tauri::State<AppState>) -> Result<String, String> {
    deliver_staff_provisioning(&state)
}

fn deliver_staff_provisioning(state: &tauri::State<AppState>) -> Result<String, String> {
    let _actor = staff_actor(state)?;
    let token = state.user_token.lock().map_err(|err| err.to_string())?.clone();
    let Some(token) = token else {
        staff::hold_for_authentication(&state.db)?;
        return Err("This register has no online access token. The staff change stays here until an authorized online session is available.".into());
    };
    let blocked = state.provision_auth_block.lock().map_err(|err| err.to_string())?.clone();
    if blocked.as_deref() == Some(token.as_str()) {
        return Err("This online session was refused. Sign in again before the same staff change is sent. It stays on this register.".into());
    }
    let events = staff::pending_outbox(&state.db)?;
    let config = state.config.clone();
    let client = reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(10))
        .build()
        .map_err(|err| err.to_string())?;
    let mut accepted = 0_i64;
    for event in events {
        let mut body: serde_json::Value = serde_json::from_str(&event.payload).unwrap_or_else(|_| serde_json::json!({}));
        body["event_id"] = serde_json::Value::String(event.id.clone());
        body["operation"] = serde_json::Value::String(event.operation.clone());
        body["origin_terminal_id"] = serde_json::Value::String(event.origin_terminal_id.clone());
        if !event.base_version.is_empty() {
            body["base_version"] = serde_json::Value::String(event.base_version.clone());
        }
        let response = client
            .post(format!("{}/api/v1/users/provision", config.api_base_url))
            .headers(config.auth_headers())
            .header("Authorization", format!("Bearer {token}"))
            .json(&body)
            .send();
        let response = match response {
            Ok(response) => response,
            Err(_) => {
                let _ = staff::mark_provisioning(&state.db, &event.id, "retryable", Some("The server could not be reached."));
                return Err("The server could not be reached. The staff change stays pending.".into());
            }
        };
        let status = response.status();
        let value: serde_json::Value = response.json().unwrap_or(serde_json::Value::Null);
        let code = value
            .get("error")
            .and_then(|item| item.get("code"))
            .and_then(|item| item.as_str())
            .unwrap_or("");
        let message = value
            .get("error")
            .and_then(|item| item.get("message"))
            .and_then(|item| item.as_str())
            .unwrap_or("The server did not accept this staff change.");
        let body_status = value.get("status").and_then(|item| item.as_str()).unwrap_or("");
        match staff::classify_provision_response(status.as_u16(), code, body_status) {
            "accepted" => {
                staff::mark_provisioning(&state.db, &event.id, "accepted", None)?;
                accepted += 1;
            }
            "conflict" => {
                staff::mark_provisioning(&state.db, &event.id, "conflict", Some(message))?;
            }
            "rejected" => {
                staff::mark_provisioning(&state.db, &event.id, "rejected", Some(message))?;
            }
            "permission_denied" => {
                staff::mark_provisioning(&state.db, &event.id, "permission_denied", Some(message))?;
                return Err("The signed-in user cannot provision staff. This event will not be retried, and the person stays on this register.".into());
            }
            "awaiting_authentication" => {
                *state.provision_auth_block.lock().map_err(|err| err.to_string())? = Some(token);
                staff::mark_provisioning(
                    &state.db,
                    &event.id,
                    "awaiting_authentication",
                    Some("The online session was refused. This change stays on this register until you sign in again."),
                )?;
                return Err("The online session was refused. The staff change stays on this register until you sign in again.".into());
            }
            _ => {
                staff::mark_provisioning(&state.db, &event.id, "retryable", Some("The server could not be reached. The same event will be sent again."))?;
                return Err("The server could not be reached. The staff change stays pending.".into());
            }
        }
    }
    if let Ok(response) = client
        .get(format!("{}/api/v1/users/staff-feed", config.api_base_url))
        .headers(config.auth_headers())
        .send()
    {
        if response.status().is_success() {
            if let Ok(feed) = response.json::<serde_json::Value>() {
                if let Some(rows) = feed.get("staff").and_then(|item| item.as_array()) {
                    for row in rows {
                        let verifier = row.get("pin_verifier").and_then(|item| item.as_str()).unwrap_or("");
                        let user_id = row.get("user_id").and_then(|item| item.as_str()).unwrap_or("");
                        let username = row.get("username").and_then(|item| item.as_str()).unwrap_or("");
                        let store_id = row.get("store_id").and_then(|item| item.as_str()).unwrap_or("");
                        let role_name = row.get("role_name").and_then(|item| item.as_str()).unwrap_or("");
                        let active = row.get("is_active").and_then(|item| item.as_bool()).unwrap_or(false);
                        if user_id.is_empty() || store_id.is_empty() {
                            continue;
                        }
                        if staff::import_accepted(&state.db, user_id, username, verifier, store_id, role_name, active).is_err() {
                            continue;
                        }
                    }
                }
            }
        }
    }
    Ok(format!("{accepted} staff changes were accepted."))
}


pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, args, _cwd| {
            open_posdemo_from_args(app, &args);
        }))
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            DesktopConfig::load_env_file().map_err(std::io::Error::other)?;
            let directory = app.path().app_data_dir()?;
            let identifier = app.config().identifier.clone();
            acceptance::assert_isolated(&identifier, &directory).map_err(std::io::Error::other)?;
            std::fs::create_dir_all(&directory)?;
            zoom::prepare_activation(&directory).map_err(std::io::Error::other)?;
            let terminal_path = terminal::config_path(&directory);
            // Activated: that tenant's own database. Developer .env: the legacy shared file. Neither: activation.
            let (config, status, database) = match terminal::load(&terminal_path) {
                Ok(Some(activated)) => {
                    let mut status = terminal::TerminalStatus::from_config(&activated.config, "activation");
                    let binding = entitlement::device_binding(&activated.device_public_key).unwrap_or_default();
                    let expected = entitlement::ExpectedBinding {
                        tenant_id: if activated.config.tenant_id.is_empty() {
                            activated.config.tenant_slug.clone()
                        } else {
                            activated.config.tenant_id.clone()
                        },
                        branch_id: activated.config.store_id.clone(),
                        terminal_id: activated.config.register_id.clone(),
                        device_binding: binding,
                    };
                    let code = entitlement::code_for(
                        &activated.entitlement_payload,
                        &activated.entitlement_signature,
                        &activated.entitlement_key_id,
                        &expected,
                        auth::now_secs(),
                    );
                    status.entitlement_code = code.to_string();
                    status.readiness = entitlement::readiness(
                        code,
                        &entitlement::LocalBaseline {
                            activated: true,
                            storage_damaged: false,
                            sqlite_open: None,
                            queue_readable: false,
                            products: 0,
                            staff: 0,
                            pending: 0,
                            capability_snapshot: false,
                            server_subscription_blocked: false,
                            bootstrap_status: String::new(),
                            pull_failed: false,
                        },
                    )
                    .to_string();
                    (
                        DesktopConfig::from_terminal(&activated.config),
                        status,
                        terminal::database_path(&directory, &activated.config.tenant_slug),
                    )
                }
                Ok(None) => match DesktopConfig::from_env().map_err(std::io::Error::other)? {
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
                },
                Err(message) => {
                    eprintln!("ai-pos: terminal configuration could not be read: {message}");
                    let mut status = terminal::TerminalStatus::none();
                    status.source = "recovery".into();
                    status.activated = false;
                    status.entitlement_code = if message.contains("another Windows account") {
                        entitlement::STORAGE_DECRYPTION_FAILED.into()
                    } else {
                        entitlement::MALFORMED.into()
                    };
                    status.readiness = entitlement::REQUIRES_ONLINE_RECOVERY.into();
                    (DesktopConfig::unactivated(), status, directory.join("ai-pos.db"))
                }
            };
            acceptance::assert_database(&identifier, &directory, &database, &config.api_base_url)
                .map_err(std::io::Error::other)?;
            acceptance::write_diagnostics(&directory, &database, &identifier, &config.api_base_url, &status.source)
                .map_err(std::io::Error::other)?;
            if let Some(parent) = database.parent() {
                std::fs::create_dir_all(parent)?;
            }
            let db = std::sync::Arc::new(Db::open(&database).map_err(std::io::Error::other)?);
            printer::watch(app.handle().clone(), db.clone());
            let unlocked = zoom::sign_in(&db, &config, &directory).unwrap_or_else(|message| {
                let _ = std::fs::write(directory.join("zoom-status.txt"), message);
                None
            });
            if let Some((session, _)) = &unlocked {
                if let Err(message) = zoom::open_shift(&db, session, &config.store_id, &directory) {
                    let _ = std::fs::write(directory.join("zoom-status.txt"), message);
                }
            }
            let media_dir = directory.join("media");
            updates::watch(app.handle().clone(), config.clone());
            app.manage(AppState {
                db,
                config,
                media_dir,
                terminal: status,
                terminal_path,
                flush_lock: Arc::new(Mutex::new(())),
                session: Mutex::new(unlocked.as_ref().map(|(session, _)| session.clone())),
                user_token: Mutex::new(unlocked.and_then(|(_, token)| token)),
                provision_auth_block: Mutex::new(None),
                demo_notice: Mutex::new(None),
                demo_launch: Mutex::new(None),
                approvals: Arc::new(Mutex::new(Default::default())),
                checkout_approvals: Arc::new(Mutex::new(Default::default())),
            });
            keyboard_detector::start(app.handle().clone());
            zoom::start(app.handle().clone());
            open_posdemo_from_args(app.handle(), &std::env::args().skip(1).collect::<Vec<_>>());
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            pin_login,
            unlock_cashier,
            list_cashiers,
            current_session,
            lock_session,
            read_catalogue_preference,
            write_catalogue_preference,
            search_products,
            remote_search,
            terminal_store,
            terminal_status,
            terminal_api_key,
            activate_terminal,
            enroll_demo_file,
            take_demo_notice,
            open_demo_session,
            exit_demo,
            deactivate_terminal,
            check_branches,
            enqueue_events,
            lookup_receipt,
            approve_return,
            note_remote_return,
            enqueue_return,
            recent_returns,
            pending_count,
            bootstrap_readiness,
            batch_status,
            flush_sync,
            cached_products,
            terminal_allocation_balances,
            list_register_staff,
            create_register_staff,
            edit_register_staff,
            reset_register_staff_pin,
            disable_register_staff,
            submit_staff_provisioning,
            register_staff_seats,
            refresh_products,
            bootstrap_catalogue,
            pull_catalogue,
            local_dining_floor,
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
            erp::list_windows_printers,
            erp::save_printer_settings,
            erp::print_receipt,
            erp::open_cash_drawer,
            erp::open_document_pdf,
            erp::current_shift,
            erp::open_shift,
            erp::record_cash_movement,
            erp::shift_history,
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
            erp::conflict_count,
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
            zoom::acceptance_zoom_report,
            restaurant::restaurant_request,
            retail::retail_request,
            retail::retail_upload,
            check_app_update,
            install_app_update
        ])
        .run(tauri::generate_context!())
        .expect("ai-pos desktop failed to start");
}
