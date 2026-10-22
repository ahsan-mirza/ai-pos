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
    /// The tenant subdomain (client1.qios.ae), sent as X-Tenant-Domain.
    pub tenant_domain: String,
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
}

#[derive(Serialize)]
pub struct SyncReport {
    pub pending: i64,
    pub applied: i64,
    pub duplicates: i64,
    pub message: String,
}

enum PushError {
    /// The server refused the batch. Retrying the same payload will fail the same way.
    Rejected(String),
    /// Network, auth, or server failure. The batch stays queued.
    Unavailable(String),
}

impl DesktopConfig {
    /// Debug builds read the repo-root `.env` (TENANT_URL_TEMPLATE, POS_DEV_ENV_CONFIG, ...).
    /// Release builds never read files from the build machine; build.rs bakes their settings in.
    pub fn load_env_file() -> Result<(), String> {
        if !cfg!(debug_assertions) {
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
        let opted_in = std::env::var("POS_DEV_ENV_CONFIG")
            .map(|value| matches!(value.trim().to_ascii_lowercase().as_str(), "1" | "true" | "yes"))
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
        let tenant_domain = std::env::var("TENANT_DOMAIN").map(|value| value.trim().to_string()).unwrap_or_default();
        Ok(Some(Self {
            api_base_url,
            api_key,
            device_id,
            store_id,
            tenant_domain,
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

    for _ in 0..MAX_BATCHES_PER_FLUSH {
        let Some((batch_id, events)) = db.next_pending_batch()? else {
            break;
        };
        match post_batch(config, &events) {
            Ok(response) => {
                db.mark_batch(&batch_id, "synced", None)?;
                synced += 1;
                applied += response.results.iter().filter(|result| result.status == "applied").count() as i64;
                duplicates += response
                    .results
                    .iter()
                    .filter(|result| result.status == "duplicate")
                    .count() as i64;
            }
            Err(PushError::Rejected(reason)) => {
                db.mark_batch(&batch_id, "rejected", Some(&reason))?;
                rejected += 1;
                last_rejection = Some(reason);
            }
            Err(PushError::Unavailable(reason)) => {
                db.record_failure(&batch_id, &reason)?;
                unavailable = Some(reason);
                break;
            }
        }
    }

    let message = match (unavailable, last_rejection) {
        (Some(reason), _) => format!("Not synced: {reason}"),
        (None, Some(reason)) => format!("{rejected} queued sale(s) rejected: {reason}"),
        (None, None) if synced > 0 => "Synced with the API.".to_string(),
        (None, None) => "Queue is empty.".to_string(),
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

const CATALOG_PAGE: usize = 1000;

/// The whole catalog, page by page (supermarkets carry tens of thousands of SKUs). The register sells from what
/// is free: stock held by open quotes is subtracted.
pub fn fetch_products(config: &DesktopConfig) -> Result<Vec<ProductRow>, String> {
    let client = client()?;
    let page_size = CATALOG_PAGE.to_string();
    let mut products = Vec::new();
    let mut after: Option<String> = None;
    loop {
        let mut query = vec![("limit", page_size.as_str()), ("store_id", config.store_id.as_str())];
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
        let page: Vec<RemoteProduct> = serde_json::from_str(&body).map_err(|err| err.to_string())?;
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

/// Server search adds what the local cache cannot answer: IMEI/serial lookups and other stores' live stock.
pub fn remote_search(config: &DesktopConfig, query: &str, limit: i64) -> Result<Vec<SearchHit>, String> {
    let response = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(4))
        .build()
        .map_err(|err| err.to_string())?
        .get(format!("{}/api/v1/products/search", config.api_base_url))
        .query(&[("q", query), ("limit", &limit.to_string()), ("store_id", &config.store_id)])
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
        .get(format!("{}/api/v1/inventory/availability", config.api_base_url))
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

fn post_batch(config: &DesktopConfig, events: &[QueuedEvent]) -> Result<PushResponse, PushError> {
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
        .map_err(PushError::Unavailable)?
        .post(format!("{}/api/v1/sync/push", config.api_base_url))
        .headers(config.auth_headers())
        .json(&payload)
        .send()
        .map_err(|err| PushError::Unavailable(err.to_string()))?;
    let status = response.status();
    let body = response
        .text()
        .map_err(|err| PushError::Unavailable(err.to_string()))?;
    if status.is_success() {
        return serde_json::from_str(&body).map_err(|err| PushError::Unavailable(err.to_string()));
    }
    let reason = error_message(&body, status.as_u16());
    match status.as_u16() {
        409 | 413 | 422 => Err(PushError::Rejected(reason)),
        _ => Err(PushError::Unavailable(reason)),
    }
}

fn client() -> Result<reqwest::blocking::Client, String> {
    reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(20))
        .build()
        .map_err(|err| err.to_string())
}

fn error_message(body: &str, status: u16) -> String {
    serde_json::from_str::<ErrorBody>(body)
        .map(|parsed| parsed.error.message)
        .unwrap_or_else(|_| format!("Request failed ({status})."))
        .chars()
        .take(500)
        .collect()
}

fn required(name: &str) -> Result<String, String> {
    let value = std::env::var(name).map_err(|_| format!("{name} is required."))?;
    let trimmed = value.trim().to_string();
    if trimmed.is_empty() {
        return Err(format!("{name} is required."));
    }
    Ok(trimmed)
}
