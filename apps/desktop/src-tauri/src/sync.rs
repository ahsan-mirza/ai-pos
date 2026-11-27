use std::path::PathBuf;
use std::time::Duration;

use reqwest::header::{HeaderMap, HeaderValue};
use serde::{Deserialize, Serialize};

use crate::db::{Db, ProductRow, QueuedEvent, SearchHit};
use crate::terminal::TerminalConfig;

const MAX_BATCHES_PER_FLUSH: usize = 25;

#[derive(Clone)]
pub struct DesktopConfig {
    pub api_base_url: String,
    /// The register's device token, sent as X-Terminal-Token.
    pub api_key: String,
    pub device_id: String,
    /// The branch this terminal sells from; its catalog and stock come from this store only.
    pub store_id: String,
    /// The tenant subdomain (client1.axizpos.com), sent as X-Tenant-Domain.
    pub tenant_domain: String,
    /// Store code returned by activation. Capability snapshots are accepted only for this tenant.
    pub tenant_slug: String,
}

const DEFAULT_STORE_ID: &str = "00000000-0000-4000-8000-000000000001";

#[derive(Debug, Deserialize)]
struct PushResult {
    status: String,
}

#[derive(Debug, Deserialize)]
struct PushResponse {
    results: Vec<PushResult>,
}

#[derive(Debug, Deserialize)]
struct ErrorBody {
    error: ErrorDetail,
}

#[derive(Debug, Deserialize)]
struct ErrorDetail {
    message: String,
    #[serde(default)]
    code: String,
}

#[derive(Serialize)]
pub struct SyncReport {
    pub pending: i64,
    pub applied: i64,
    pub duplicates: i64,
    pub message: String,
}

enum PushError {
    /// The server refused the batch. `server_time` is the Date header, when it could be read.
    Rejected { reason: String, server_time: Option<String> },
    /// The same key was stored with a different payload. The local event stays unchanged.
    Conflict { reason: String },
    /// Network, auth, or server failure. The batch stays queued.
    /// `halt` stops this flush: the connection or the login is down, so later batches would fail the same way.
    /// A server error on one batch does not halt. Later sales and cash movements still upload.
    Unavailable { reason: String, halt: bool },
}

/// Queue status for a push response. A lost response stays pending so the original key can be sent again.
pub fn queue_status_for(http_status: u16, error_code: &str) -> &'static str {
    if http_status == 409 && error_code == "idempotency_conflict" {
        return "conflict";
    }
    if matches!(http_status, 409 | 413 | 422) {
        return "rejected";
    }
    "pending"
}

impl DesktopConfig {
    /// Debug builds read the repo-root `.env` (TENANT_URL_TEMPLATE, POS_DEV_ENV_CONFIG, ...).
    /// Release builds never read files from the build machine; build.rs bakes their settings in.
    pub fn load_env_file() -> Result<(), String> {
        if env!("POS_ACCEPTANCE_BUILD") == "1" || !cfg!(debug_assertions) {
            return Ok(());
        }
        let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        let env_path = manifest_dir.join("..").join("..").join("..").join(".env");
        if env_path.exists() {
            dotenvy::from_path(&env_path)
                .map_err(|err| format!("Unable to load {}: {err}", env_path.display()))?;
        }
        Ok(())
    }

    pub fn from_terminal(terminal: &TerminalConfig) -> Self {
        Self {
            api_base_url: terminal.api_base_url.trim_end_matches('/').to_string(),
            api_key: terminal.device_token.clone(),
            device_id: terminal.register_id.clone(),
            store_id: terminal.store_id.clone(),
            tenant_domain: terminal.tenant_domain.clone(),
            tenant_slug: terminal.tenant_slug.clone(),
        }
    }

    /// Until activation nothing can reach a server; calls fail fast as "offline".
    pub fn unactivated() -> Self {
        Self {
            api_base_url: "http://not-activated.invalid".into(),
            api_key: String::new(),
            device_id: "unactivated".into(),
            store_id: DEFAULT_STORE_ID.into(),
            tenant_domain: String::new(),
            tenant_slug: String::new(),
        }
    }

    /// Headers on every API call: the tenant subdomain and this register's token.
    pub fn auth_headers(&self) -> HeaderMap {
        let mut headers = HeaderMap::new();
        if let Ok(value) = HeaderValue::from_str(&self.api_key) {
            headers.insert("X-Terminal-Token", value);
        }
        if !self.tenant_domain.is_empty() {
            if let Ok(value) = HeaderValue::from_str(&self.tenant_domain) {
                headers.insert("X-Tenant-Domain", value);
            }
        }
        headers
    }

    /// Legacy developer setup from .env, used only when POS_DEV_ENV_CONFIG=true (skips activation).
    pub fn from_env() -> Result<Option<Self>, String> {
        if env!("POS_ACCEPTANCE_BUILD") == "1" {
            return Ok(None);
        }
        let opted_in = std::env::var("POS_DEV_ENV_CONFIG")
            .map(|value| {
                matches!(
                    value.trim().to_ascii_lowercase().as_str(),
                    "1" | "true" | "yes"
                )
            })
            .unwrap_or(false);
        if !opted_in {
            return Ok(None);
        }
        let api_base_url = required("API_BASE_URL")?.trim_end_matches('/').to_string();
        if !(api_base_url.starts_with("http://") || api_base_url.starts_with("https://")) {
            return Err("API_BASE_URL must be an absolute http(s) URL.".into());
        }
        // A registered register authenticates with its own DEVICE_KEY; API_KEY is the legacy shared key.
        let api_key = std::env::var("DEVICE_KEY")
            .ok()
            .map(|value| value.trim().to_string())
            .filter(|value| !value.is_empty())
            .map_or_else(|| required("API_KEY"), Ok)?;
        if api_key.len() < 16 {
            return Err("DEVICE_KEY / API_KEY must be at least 16 characters.".into());
        }
        let device_id = required("DEVICE_ID")?;
        let store_id = std::env::var("STORE_ID")
            .ok()
            .map(|value| value.trim().to_string())
            .filter(|value| !value.is_empty())
            .unwrap_or_else(|| DEFAULT_STORE_ID.to_string());
        let tenant_domain = std::env::var("TENANT_DOMAIN")
            .map(|value| value.trim().to_string())
            .unwrap_or_default();
        Ok(Some(Self {
            api_base_url,
            api_key,
            device_id,
            store_id,
            tenant_domain: tenant_domain.clone(),
            tenant_slug: tenant_domain,
        }))
    }
}

pub fn flush(db: &Db, config: &DesktopConfig) -> Result<SyncReport, String> {
    let mut applied = 0;
    let mut duplicates = 0;
    let mut synced = 0;
    let mut rejected = 0;
    let mut last_rejection: Option<String> = None;
    let mut unavailable: Option<String> = None;
    let mut skipped: Vec<String> = Vec::new();
    let mut blocked: Vec<String> = Vec::new();
    let attempt = sync_attempt_id();
    eprintln!(
        "sync attempt {attempt} host {} endpoint /api/v1/sync/push",
        sync_host(&config.api_base_url)
    );

    for _ in 0..MAX_BATCHES_PER_FLUSH {
        let Some((batch_id, events)) = db.next_pending_except(&skipped)? else {
            break;
        };
        let origin = db.preserved_device_id(&batch_id).unwrap_or_default();
        let mut posted = config.clone();
        if !origin.is_empty() {
            posted.device_id = origin;
        }
        match post_batch(&posted, &events, &attempt) {
            Ok(response) => {
                let queued = if response.results.iter().any(|result| result.status == "awaiting_review") {
                    "awaiting_review"
                } else {
                    "synced"
                };
                db.mark_batch(&batch_id, queued, None)?;
                synced += 1;
                applied += response
                    .results
                    .iter()
                    .filter(|result| result.status == "applied")
                    .count() as i64;
                duplicates += response
                    .results
                    .iter()
                    .filter(|result| result.status == "duplicate")
                    .count() as i64;
            }
            Err(PushError::Conflict { reason }) => {
                db.mark_batch(&batch_id, "conflict", Some(&reason))?;
                rejected += 1;
                last_rejection = Some(reason);
            }
            Err(PushError::Rejected { reason, server_time }) => {
                // A register clock ahead of head office keeps failing until the stamp is pulled back.
                // One correction per batch: a second rejection with the same stamp stays rejected.
                let realigned = server_time.as_deref().is_some_and(|stamp| {
                    reason.to_ascii_lowercase().contains("future")
                        && db.restamp_batch(&batch_id, stamp).unwrap_or(false)
                });
                if realigned {
                    continue;
                }
                // A shift opened before the business currency arrived is recounted in that currency and sent again.
                if let Some(code) = business_currency_in(&reason) {
                    if db.relabel_shift_currency(&batch_id, &code).unwrap_or(false) {
                        continue;
                    }
                }
                db.mark_batch(&batch_id, "rejected", Some(&reason))?;
                rejected += 1;
                last_rejection = Some(reason);
            }
            Err(PushError::Unavailable { reason, halt }) => {
                db.record_failure(&batch_id, &reason)?;
                if halt {
                    unavailable = Some(reason);
                    break;
                }
                blocked.push(batch_label(&events));
                skipped.push(batch_id);
            }
        }
    }

    // The sale queue is already marked. A missing first snapshot is reported.
    // A later pull miss stays on the cursor and retries on the next flush.
    let catalogue_note = if db.bootstrap_cursor()?.is_none() {
        refresh_catalogue(config, db).err()
    } else {
        let _ = refresh_catalogue(config, db);
        None
    };

    let still_waiting = {
        let mut seen = Vec::new();
        for label in &blocked {
            if !seen.contains(label) {
                seen.push(label.clone());
            }
        }
        seen.join(", ")
    };
    let message = match (unavailable, last_rejection, catalogue_note, blocked.is_empty(), synced > 0) {
        (Some(reason), _, _, _, _) => format!("Not synced: {reason}"),
        (None, _, _, false, true) => format!(
            "Some records synchronized. {still_waiting} still need attention. Reference: {attempt}."
        ),
        (None, _, _, false, false) => format!(
            "Not synced: The server failed while processing this synchronization batch. Your original records are still waiting. Reference: {attempt}."
        ),
        (None, Some(reason), _, _, _) => format!("{rejected} queued sale(s) rejected: {reason}"),
        (None, None, Some(reason), _, true) => {
            format!("Sales synced. Catalogue snapshot still incomplete: {reason}")
        }
        (None, None, Some(reason), _, false) => format!("Catalogue snapshot still incomplete: {reason}"),
        (None, None, None, _, true) => "Synced with the API.".to_string(),
        (None, None, None, _, false) => "Queue is empty.".to_string(),
    };

    Ok(SyncReport {
        pending: db.pending_count()?,
        applied,
        duplicates,
        message,
    })
}

#[derive(Deserialize)]
struct RemoteProduct {
    #[serde(flatten)]
    row: ProductRow,
    #[serde(default)]
    quantity_reserved: i64,
}

/// First contact takes the signed snapshot. Later flushes take the cursor page.
/// Both commit menu, floor, and the cursor in one database transaction.
fn refresh_catalogue(config: &DesktopConfig, db: &Db) -> Result<(), String> {
    if db.bootstrap_cursor()?.is_none() {
        bootstrap_catalogue(config, db)?;
    } else {
        pull_catalogue(config, db)?;
    }
    // The selling screen reads the assembled modifier document. Refresh it from the same API
    // after the signed rows commit, and keep the previous document if this call misses.
    let _ = crate::menu::refresh(db, config);
    Ok(())
}

const CATALOG_PAGE: usize = 1000;

#[derive(Deserialize)]
struct AllocationFeedItem {
    payload: String,
    signature: String,
    key_id: String,
}

#[derive(Deserialize)]
struct AllocationFeed {
    allocations: Vec<AllocationFeedItem>,
}

/// Installs this register's signed grants. A manifest that fails verification is left out.
pub fn install_allocations(
    config: &DesktopConfig,
    db: &Db,
    expected: &crate::entitlement::ExpectedBinding,
) -> Result<usize, String> {
    let response = client()?
        .get(format!("{}/api/v1/inventory/allocation-feed", config.api_base_url))
        .headers(config.auth_headers())
        .send()
        .map_err(|err| err.to_string())?;
    let status = response.status();
    let body = response.text().map_err(|err| err.to_string())?;
    if !status.is_success() {
        return Err(error_message(&body, status.as_u16()));
    }
    let feed: AllocationFeed = serde_json::from_str(&body).map_err(|err| err.to_string())?;
    let mut installed = 0usize;
    for item in feed.allocations {
        if crate::allocation::install(db, &item.payload, &item.signature, &item.key_id, expected).is_ok() {
            installed += 1;
        }
    }
    Ok(installed)
}

/// The whole catalog, page by page (supermarkets carry tens of thousands of SKUs). The register sells from what
/// is free: stock held by open quotes is subtracted.
pub fn fetch_products(config: &DesktopConfig) -> Result<Vec<ProductRow>, String> {
    let client = client()?;
    let page_size = CATALOG_PAGE.to_string();
    let mut products = Vec::new();
    let mut after: Option<String> = None;
    loop {
        let mut query = vec![
            ("limit", page_size.as_str()),
            ("store_id", config.store_id.as_str()),
        ];
        if let Some(last) = after.as_deref() {
            query.push(("after", last));
        }
        let response = client
            .get(format!("{}/api/v1/products", config.api_base_url))
            .query(&query)
            .headers(config.auth_headers())
            .send()
            .map_err(|err| err.to_string())?;
        let status = response.status();
        let body = response.text().map_err(|err| err.to_string())?;
        if !status.is_success() {
            return Err(error_message(&body, status.as_u16()));
        }
        let page: Vec<RemoteProduct> =
            serde_json::from_str(&body).map_err(|err| err.to_string())?;
        let full = page.len() == CATALOG_PAGE;
        after = page.last().map(|item| item.row.id.clone());
        products.extend(page.into_iter().map(|item| {
            let mut row = item.row;
            row.stock_quantity = (row.stock_quantity - item.quantity_reserved).max(0);
            row.origin = "api".to_string();
            row
        }));
        if !full || after.is_none() {
            return Ok(products);
        }
    }
}

#[derive(Deserialize)]
struct CatalogRevisionBody {
    updated_at: Option<String>,
    count: i64,
}

/// `updated_at:count`. Callers download the catalog only when the string changes.
pub fn catalog_revision(config: &DesktopConfig) -> Result<String, String> {
    let response = client()?
        .get(format!("{}/api/v1/products/revision", config.api_base_url))
        .headers(config.auth_headers())
        .send()
        .map_err(|err| err.to_string())?;
    let status = response.status();
    let body = response.text().map_err(|err| err.to_string())?;
    if !status.is_success() {
        return Err(error_message(&body, status.as_u16()));
    }
    let parsed: CatalogRevisionBody = serde_json::from_str(&body).map_err(|err| err.to_string())?;
    Ok(format!("{}:{}", parsed.updated_at.unwrap_or_default(), parsed.count))
}

/// Server search adds what the local cache cannot answer: IMEI/serial lookups and other stores' live stock.
pub fn remote_search(
    config: &DesktopConfig,
    query: &str,
    limit: i64,
) -> Result<Vec<SearchHit>, String> {
    let response = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(4))
        .build()
        .map_err(|err| err.to_string())?
        .get(format!("{}/api/v1/products/search", config.api_base_url))
        .query(&[
            ("q", query),
            ("limit", &limit.to_string()),
            ("store_id", &config.store_id),
        ])
        .headers(config.auth_headers())
        .send()
        .map_err(|err| err.to_string())?;
    let status = response.status();
    let body = response.text().map_err(|err| err.to_string())?;
    if !status.is_success() {
        return Err(error_message(&body, status.as_u16()));
    }
    serde_json::from_str(&body).map_err(|err| err.to_string())
}

/// "Check other branches": what every active branch and warehouse holds for a product or one IMEI.
pub fn branch_availability(
    config: &DesktopConfig,
    product_id: Option<&str>,
    serial: Option<&str>,
) -> Result<serde_json::Value, String> {
    let mut params: Vec<(&str, &str)> = Vec::new();
    if let Some(product_id) = product_id {
        params.push(("product_id", product_id));
    }
    if let Some(serial) = serial {
        params.push(("serial", serial));
    }
    let response = client()?
        .get(format!(
            "{}/api/v1/inventory/availability",
            config.api_base_url
        ))
        .query(&params)
        .headers(config.auth_headers())
        .send()
        .map_err(|err| format!("The server is unreachable: {err}"))?;
    let status = response.status();
    let body = response.text().map_err(|err| err.to_string())?;
    if !status.is_success() {
        return Err(error_message(&body, status.as_u16()));
    }
    serde_json::from_str(&body).map_err(|err| err.to_string())
}

fn post_batch(config: &DesktopConfig, events: &[QueuedEvent], attempt: &str) -> Result<PushResponse, PushError> {
    let payload = serde_json::json!({
        "device_id": config.device_id,
        "events": events.iter().map(|event| serde_json::json!({
            "idempotency_key": event.idempotency_key,
            "entity_type": event.entity_type,
            "operation": event.operation,
            "payload": event.payload,
            "occurred_at": event.occurred_at,
        })).collect::<Vec<_>>()
    });
    let response = client()
        .map_err(|_| PushError::Unavailable { reason: connection_failure(), halt: true })?
        .post(format!("{}/api/v1/sync/push", config.api_base_url))
        .headers(config.auth_headers())
        .header("X-Sync-Attempt", attempt)
        .json(&payload)
        .send()
        .map_err(|_| PushError::Unavailable { reason: connection_failure(), halt: true })?;
    let server_time = response
        .headers()
        .get(reqwest::header::DATE)
        .and_then(|value| value.to_str().ok())
        .and_then(http_date_to_iso);
    let status = response.status();
    let body = response.text().map_err(|_| PushError::Unavailable {
        reason: server_failure(attempt),
        halt: false,
    })?;
    if status.is_success() {
        return serde_json::from_str(&body).map_err(|_| PushError::Unavailable {
            reason: server_failure(attempt),
            halt: false,
        });
    }
    let code = error_code(&body);
    let reason = failure_message(status.as_u16(), &code, &error_message(&body, status.as_u16()), attempt);
    match queue_status_for(status.as_u16(), &code) {
        "conflict" => Err(PushError::Conflict { reason }),
        "rejected" => Err(PushError::Rejected { reason, server_time }),
        _ => Err(PushError::Unavailable {
            reason,
            halt: halts_flush(status.as_u16(), &code),
        }),
    }
}

fn sync_attempt_id() -> String {
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|value| value.as_nanos())
        .unwrap_or(0);
    format!("sync-{nanos:x}")
}

fn sync_host(url: &str) -> String {
    url.trim_start_matches("https://")
        .trim_start_matches("http://")
        .split('/')
        .next()
        .unwrap_or("configured-server")
        .to_string()
}

fn batch_label(events: &[QueuedEvent]) -> String {
    events
        .iter()
        .find(|event| event.entity_type != "store" && event.entity_type != "product")
        .or_else(|| events.first())
        .map(|event| match event.entity_type.as_str() {
            "sale" => "Sales",
            "sale_return" => "Returns",
            "cash_movement" => "Cash movements",
            "register_shift" => "Shifts",
            "customer" => "Customers",
            other => other,
        })
        .unwrap_or("Records")
        .to_string()
}

pub fn failure_message(status: u16, code: &str, server_message: &str, attempt: &str) -> String {
    if status == 401 || status == 403 || code == "unauthorized" || code == "invalid_token" {
        return "This register could not authenticate with the server. No pending records were removed.".into();
    }
    if status >= 500 || code == "internal_error" || code == "database_unavailable" {
        return server_failure(attempt);
    }
    if server_message.trim().is_empty() {
        return server_failure(attempt);
    }
    server_message.to_string()
}

fn connection_failure() -> String {
    "Cannot connect to the configured server. Your records remain saved on this register and will retry when the connection returns.".into()
}

fn server_failure(attempt: &str) -> String {
    format!(
        "The server failed while processing this synchronization batch. Your original records are still waiting. Reference: {attempt}."
    )
}

/// A dead connection or a refused login stops the flush. One bad record does not.
pub fn halts_flush(status: u16, code: &str) -> bool {
    matches!(status, 401 | 403) || code == "database_unavailable" || code == "database_outdated" || status == 503
}

fn error_code(body: &str) -> String {
    serde_json::from_str::<ErrorBody>(body)
        .map(|parsed| parsed.error.code)
        .unwrap_or_default()
}

/// `Fri, 23 Oct 2026 16:38:59 GMT` → `2026-10-23T16:38:59Z`.
fn http_date_to_iso(value: &str) -> Option<String> {
    let comma = value.find(',')?;
    let mut parts = value[comma + 1..].split_whitespace();
    let day: u32 = parts.next()?.parse().ok()?;
    let month = match parts.next()? {
        "Jan" => 1,
        "Feb" => 2,
        "Mar" => 3,
        "Apr" => 4,
        "May" => 5,
        "Jun" => 6,
        "Jul" => 7,
        "Aug" => 8,
        "Sep" => 9,
        "Oct" => 10,
        "Nov" => 11,
        "Dec" => 12,
        _ => return None,
    };
    let year: i32 = parts.next()?.parse().ok()?;
    let mut clock = parts.next()?.split(':');
    let hour: u32 = clock.next()?.parse().ok()?;
    let minute: u32 = clock.next()?.parse().ok()?;
    let second: u32 = clock.next()?.parse().ok()?;
    if !(1..=31).contains(&day) || hour > 23 || minute > 59 || second > 59 {
        return None;
    }
    Some(format!("{year:04}-{month:02}-{day:02}T{hour:02}:{minute:02}:{second:02}Z"))
}

pub(crate) fn client() -> Result<reqwest::blocking::Client, String> {
    reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(20))
        .build()
        .map_err(|err| err.to_string())
}

fn checkout_settings_page(
    http: &reqwest::blocking::Client,
    config: &DesktopConfig,
    session_id: &str,
) -> Result<Option<String>, String> {
    let response = http
        .get(format!(
            "{}/api/v1/terminals/bootstrap/sessions/{session_id}/pages",
            config.api_base_url
        ))
        .headers(config.auth_headers())
        .query(&[
            ("dataset", "checkout_settings"),
            ("after_position", "-1"),
            ("limit", "1"),
        ])
        .send()
        .map_err(|err| err.to_string())?;
    let status = response.status();
    let body = response.text().map_err(|err| err.to_string())?;
    if !status.is_success() {
        return Err(error_message(&body, status.as_u16()));
    }
    let page: serde_json::Value = serde_json::from_str(&body).map_err(|err| err.to_string())?;
    let Some(records) = page["records"].as_array() else {
        return Err("The checkout settings page has no records.".into());
    };
    let Some(first) = records.first() else {
        return Ok(None);
    };
    if first.get("record").is_none_or(|item| item.is_null()) {
        return Ok(None);
    }
    serde_json::to_string(&first["record"]).map(Some).map_err(|err| err.to_string())
}

fn dataset_page(
    http: &reqwest::blocking::Client,
    config: &DesktopConfig,
    session_id: &str,
    dataset: &str,
) -> Result<Vec<(String, String)>, String> {
    let mut after = -1_i64;
    let mut rows = Vec::new();
    loop {
        let after_text = after.to_string();
        let response = http
            .get(format!(
                "{}/api/v1/terminals/bootstrap/sessions/{session_id}/pages",
                config.api_base_url
            ))
            .headers(config.auth_headers())
            .query(&[
                ("dataset", dataset),
                ("after_position", after_text.as_str()),
                ("limit", "50"),
            ])
            .send()
            .map_err(|err| err.to_string())?;
        let status = response.status();
        let body = response.text().map_err(|err| err.to_string())?;
        if !status.is_success() {
            return Err(error_message(&body, status.as_u16()));
        }
        let page: serde_json::Value = serde_json::from_str(&body).map_err(|err| err.to_string())?;
        for record in page["records"].as_array().ok_or("The config page has no records.")? {
            let id = record["id"].as_str().unwrap_or_default().to_string();
            if id.is_empty() {
                continue;
            }
            let payload = serde_json::to_string(&record["record"]).map_err(|err| err.to_string())?;
            rows.push((id, payload));
        }
        if page["done"].as_bool().unwrap_or(false) {
            return Ok(rows);
        }
        let next = page["next_position"].as_i64().unwrap_or(after);
        if next == after {
            return Err("The config page did not advance.".into());
        }
        after = next;
    }
}

/// Downloads the frozen catalogue and the checkout settings, then activates both together.
pub fn bootstrap_catalogue(config: &DesktopConfig, db: &crate::db::Db) -> Result<i64, String> {
    let http = client()?;
    let response = http
        .post(format!("{}/api/v1/terminals/bootstrap/sessions", config.api_base_url))
        .headers(config.auth_headers())
        .send()
        .map_err(|err| err.to_string())?;
    let status = response.status();
    let body = response.text().map_err(|err| err.to_string())?;
    if !status.is_success() {
        return Err(error_message(&body, status.as_u16()));
    }
    let started: serde_json::Value = serde_json::from_str(&body).map_err(|err| err.to_string())?;
    let session_id = started["session_id"].as_str().ok_or("The bootstrap session id is missing.")?;
    let expected = started["product_count"].as_i64().unwrap_or(0);
    let generation = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|duration| duration.as_secs() as i64)
        .unwrap_or(1);
    let settings = checkout_settings_page(&http, config, session_id)?;
    let menu = dataset_page(&http, config, session_id, "menu")?;
    let floor = dataset_page(&http, config, session_id, "floor")?;
        let mut after = -1_i64;
        let mut cursor = String::new();
        loop {
            let after_text = after.to_string();
            let response = http
                .get(format!(
                    "{}/api/v1/terminals/bootstrap/sessions/{session_id}/pages",
                    config.api_base_url
                ))
                .headers(config.auth_headers())
                .query(&[
                    ("dataset", "products"),
                    ("after_position", after_text.as_str()),
                    ("limit", "50"),
                ])
            .send()
            .map_err(|err| err.to_string())?;
        let status = response.status();
        let body = response.text().map_err(|err| err.to_string())?;
        if !status.is_success() {
            return Err(error_message(&body, status.as_u16()));
        }
        let page: serde_json::Value = serde_json::from_str(&body).map_err(|err| err.to_string())?;
        let records = page["records"].as_array().ok_or("The bootstrap page has no records.")?;
        let mut rows = Vec::new();
        for record in records {
            let id = record["id"].as_str().unwrap_or_default().to_string();
            let payload = serde_json::to_string(&record["record"]).map_err(|err| err.to_string())?;
            rows.push((id, payload));
        }
        db.stage_products(generation, &rows)?;
        if let Some(value) = page["cursor"].as_str() {
            cursor = value.to_string();
        }
        if page["done"].as_bool().unwrap_or(false) {
            db.finish_bootstrap(generation, expected, &cursor, settings.as_deref(), &menu, &floor)?;
            return Ok(expected);
        }
        after = page["next_position"].as_i64().unwrap_or(after);
    }
}

/// Applies the next product changes and stores the continuation cursor in the same local transaction.
pub fn pull_catalogue(config: &DesktopConfig, db: &crate::db::Db) -> Result<usize, String> {
    let Some(cursor) = db.bootstrap_cursor()? else {
        return Err("Download the catalogue before pulling changes.".into());
    };
    let http = client()?;
    let response = http
        .get(format!("{}/api/v1/terminals/bootstrap/pull", config.api_base_url))
        .headers(config.auth_headers())
        .query(&[("cursor", cursor.as_str()), ("limit", "50")])
        .send()
        .map_err(|err| err.to_string())?;
    let status = response.status();
    let body = response.text().map_err(|err| err.to_string())?;
    if !status.is_success() {
        return Err(error_message(&body, status.as_u16()));
    }
    let page: serde_json::Value = serde_json::from_str(&body).map_err(|err| err.to_string())?;
    let next = page["cursor"].as_str().unwrap_or(&cursor).to_string();
    let mut changes = Vec::new();
    for change in page["changes"].as_array().ok_or("The pull response has no changes.")? {
        let seq = change["seq"].as_i64().ok_or("A pull change has no sequence.")?;
        let dataset = change["dataset"].as_str().unwrap_or("products").to_string();
        let operation = change["operation"].as_str().unwrap_or("upsert").to_string();
        let id = change["record_id"].as_str().unwrap_or_default().to_string();
        let payload = if change["record"].is_null() {
            None
        } else {
            Some(serde_json::to_string(&change["record"]).map_err(|err| err.to_string())?)
        };
        changes.push((seq, dataset, operation, id, payload));
    }
    db.apply_catalogue_pull(&config.store_id, &changes, &next)?;
    Ok(changes.len())
}

fn error_message(body: &str, status: u16) -> String {
    serde_json::from_str::<ErrorBody>(body)
        .map(|parsed| parsed.error.message)
        .unwrap_or_else(|_| format!("Request failed ({status})."))
        .chars()
        .take(500)
        .collect()
}

#[cfg(test)]
mod tests {
    use super::{failure_message, halts_flush, http_date_to_iso, queue_status_for};

    #[test]
    fn a_server_error_names_the_attempt_and_does_not_stop_later_batches() {
        let message = failure_message(500, "internal_error", "The server hit an unexpected error.", "sync-abc");
        assert!(message.contains("Reference: sync-abc"));
        assert!(!halts_flush(500, "internal_error"));
        assert!(halts_flush(401, "unauthorized"));
        assert!(halts_flush(503, "database_unavailable"));
        assert_eq!(
            failure_message(401, "unauthorized", "Sign in again.", "sync-abc"),
            "This register could not authenticate with the server. No pending records were removed."
        );
    }

    #[test]
    fn a_payload_collision_is_not_a_successful_sync() {
        assert_eq!(queue_status_for(409, "idempotency_conflict"), "conflict");
        assert_eq!(queue_status_for(422, "sync_rejected"), "rejected");
        assert_eq!(queue_status_for(409, "conflict"), "rejected");
        assert_eq!(queue_status_for(503, ""), "pending");
        assert_eq!(queue_status_for(200, ""), "pending");
    }

    #[test]
    fn http_date_becomes_utc_iso() {
        assert_eq!(
            http_date_to_iso("Fri, 23 Oct 2026 16:38:59 GMT").as_deref(),
            Some("2026-10-23T16:38:59Z")
        );
        assert_eq!(http_date_to_iso("not a date"), None);
    }
}

/// "… business currency AED." → `AED`. Other refusals return nothing.
fn business_currency_in(reason: &str) -> Option<String> {
    let marker = "business currency ";
    let start = reason.to_ascii_lowercase().find(marker)? + marker.len();
    let code: String = reason[start..].chars().take(3).collect();
    if code.len() == 3 && code.chars().all(|item| item.is_ascii_alphabetic()) {
        Some(code.to_ascii_uppercase())
    } else {
        None
    }
}

fn required(name: &str) -> Result<String, String> {
    let value = std::env::var(name).map_err(|_| format!("{name} is required."))?;
    let trimmed = value.trim().to_string();
    if trimmed.is_empty() {
        return Err(format!("{name} is required."));
    }
    Ok(trimmed)
}
