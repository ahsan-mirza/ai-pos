use std::path::Path;
use std::time::Duration;

use serde::Deserialize;
use serde_json::Value;

use crate::sync::DesktopConfig;

#[derive(Deserialize)]
struct ErrorBody {
    error: ErrorDetail,
}

#[derive(Deserialize)]
struct ErrorDetail {
    message: String,
}

fn client(seconds: u64) -> Result<reqwest::blocking::Client, String> {
    reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(seconds))
        .build()
        .map_err(|err| err.to_string())
}

fn failure(body: &str, status: u16) -> String {
    serde_json::from_str::<ErrorBody>(body)
        .map(|parsed| parsed.error.message)
        .unwrap_or_else(|_| format!("Request failed ({status})."))
}

/// Quotes reserve stock on the server, so they are never queued offline.
pub fn create(config: &DesktopConfig, payload: &Value) -> Result<Value, String> {
    let response = client(15)?
        .post(format!("{}/api/v1/quotes", config.api_base_url))
        .headers(config.auth_headers())
        .json(payload)
        .send()
        .map_err(|_| {
            "Quotes need a live connection to reserve stock. The server is unreachable.".to_string()
        })?;
    let status = response.status();
    let body = response.text().map_err(|err| err.to_string())?;
    if !status.is_success() {
        return Err(failure(&body, status.as_u16()));
    }
    serde_json::from_str(&body).map_err(|err| err.to_string())
}

/// Downloads the quotation PDF into `directory` and returns the saved file path.
pub fn download_pdf(
    config: &DesktopConfig,
    quote_id: &str,
    number: &str,
    directory: &Path,
) -> Result<String, String> {
    let safe_id: String = quote_id
        .chars()
        .filter(|c| c.is_ascii_hexdigit() || *c == '-')
        .collect();
    let safe_number: String = number
        .chars()
        .filter(|c| c.is_ascii_alphanumeric() || *c == '-')
        .collect();
    if safe_id.is_empty() {
        return Err("Unknown quote.".into());
    }
    let response = client(20)?
        .get(format!(
            "{}/api/v1/quotes/{safe_id}/pdf",
            config.api_base_url
        ))
        .headers(config.auth_headers())
        .send()
        .map_err(|err| format!("The server is unreachable: {err}"))?;
    let status = response.status();
    let bytes = response.bytes().map_err(|err| err.to_string())?;
    if !status.is_success() {
        return Err(failure(&String::from_utf8_lossy(&bytes), status.as_u16()));
    }
    std::fs::create_dir_all(directory).map_err(|err| err.to_string())?;
    let name = if safe_number.is_empty() {
        safe_id
    } else {
        safe_number
    };
    let path = directory.join(format!("{name}.pdf"));
    std::fs::write(&path, &bytes).map_err(|err| err.to_string())?;
    Ok(path.to_string_lossy().into_owned())
}
