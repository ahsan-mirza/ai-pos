//! Pass-through to the retail API (gift cards, customer history, holds, tax-free forms, alterations, online
//! orders) with the register's own credentials. Paths are whitelisted; errors come back as JSON
//! {status, code, message} so a screen can tell a refusal from being offline.

use std::time::Duration;

use serde_json::{json, Value};

use crate::AppState;

const PREFIXES: [&str; 26] = [
    "/api/v1/gift-cards",
    "/api/v1/customers",
    "/api/v1/quotes",
    "/api/v1/tax-free",
    "/api/v1/repairs",
    "/api/v1/reorders",
    "/api/v1/online-orders",
    "/api/v1/returns/receipts",
    "/api/v1/users/register-staff",
    "/api/v1/users/me/preferences",
    "/api/v1/catalog/attributes",
    "/api/v1/grocery",
    "/api/v1/rentals",
    "/api/v1/inventory",
    "/api/v1/products",
    "/api/v1/categories",
    "/api/v1/brands",
    "/api/v1/product-models",
    "/api/v1/units",
    "/api/v1/price-lists",
    "/api/v1/pricing",
    "/api/v1/serials",
    "/api/v1/replenishment",
    "/api/v1/pharmacy",
    "/api/v1/recipes",
    "/api/v1/stores",
];

fn safe(path: &str) -> bool {
    PREFIXES.iter().any(|prefix| {
        path == *prefix
            || path.starts_with(&format!("{prefix}/"))
            || path.starts_with(&format!("{prefix}?"))
    }) && !path.contains("..")
        && path
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || "/-_?=&:.%+".contains(c))
}

fn with_total(path: &str, body: Value, total: Option<&str>) -> Value {
    if !path.contains("offset=") {
        return body;
    }
    let Some(total) = total.and_then(|value| value.parse::<u64>().ok()) else {
        return body;
    };
    match body {
        Value::Array(rows) => json!({ "rows": rows, "total": total }),
        other => other,
    }
}

fn failure(status: u16, code: &str, message: &str) -> String {
    json!({ "status": status, "code": code, "message": message }).to_string()
}

#[tauri::command]
pub async fn retail_request(
    state: tauri::State<'_, AppState>,
    method: String,
    path: String,
    body: Option<Value>,
) -> Result<Value, String> {
    state
        .session()?
        .ok_or_else(|| failure(401, "locked", "Unlock the register first."))?;
    let user_token = state
        .user_token
        .lock()
        .map_err(|err| err.to_string())?
        .clone();
    if !safe(&path) {
        return Err(failure(
            400,
            "invalid_path",
            "That request is not allowed from the register.",
        ));
    }
    let config = state.config.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let client = reqwest::blocking::Client::builder()
            .timeout(Duration::from_secs(10))
            .build()
            .map_err(|err| failure(0, "offline", &err.to_string()))?;
        let url = format!("{}{}", config.api_base_url, path);
        let request = match method.as_str() {
            "GET" => client.get(&url),
            "POST" => client.post(&url).json(&body.unwrap_or_else(|| json!({}))),
            "PATCH" => client.patch(&url).json(&body.unwrap_or_else(|| json!({}))),
            "PUT" => client.put(&url).json(&body.unwrap_or_else(|| json!({}))),
            "DELETE" => client.delete(&url),
            _ => return Err(failure(400, "invalid_method", "Unsupported method.")),
        };
        let request = request.headers(config.auth_headers());
        let request = if let Some(token) = &user_token {
            request.header("Authorization", format!("Bearer {token}"))
        } else {
            request
        };
        let response = request
            .send()
            .map_err(|err| failure(0, "offline", &format!("The server is unreachable: {err}")))?;
        let status = response.status();
        let total = response
            .headers()
            .get("x-total-count")
            .and_then(|value| value.to_str().ok())
            .map(str::to_owned);
        let value: Value = response.json().unwrap_or(Value::Null);
        let value = with_total(&path, value, total.as_deref());
        if !status.is_success() {
            let code = value["error"]["code"].as_str().unwrap_or("rejected");
            let message = value["error"]["message"]
                .as_str()
                .unwrap_or("The server refused the request.");
            return Err(failure(status.as_u16(), code, message));
        }
        Ok(value)
    })
    .await
    .map_err(|err| failure(0, "offline", &err.to_string()))?
}

fn decode_base64(input: &str) -> Result<Vec<u8>, String> {
    fn value(byte: u8) -> Result<u8, String> {
        match byte {
            b'A'..=b'Z' => Ok(byte - b'A'),
            b'a'..=b'z' => Ok(byte - b'a' + 26),
            b'0'..=b'9' => Ok(byte - b'0' + 52),
            b'+' => Ok(62),
            b'/' => Ok(63),
            _ => Err(failure(400, "invalid_file", "The photo could not be read.")),
        }
    }
    let bytes: Vec<u8> = input.bytes().filter(|byte| !byte.is_ascii_whitespace()).collect();
    if bytes.is_empty() || bytes.len() % 4 != 0 {
        return Err(failure(400, "invalid_file", "The photo could not be read."));
    }
    let mut out = Vec::with_capacity(bytes.len() / 4 * 3);
    for chunk in bytes.chunks(4) {
        let padding = chunk.iter().filter(|byte| **byte == b'=').count();
        let first = value(chunk[0])?;
        let second = value(chunk[1])?;
        let third = if chunk[2] == b'=' { 0 } else { value(chunk[2])? };
        let fourth = if chunk[3] == b'=' { 0 } else { value(chunk[3])? };
        let packed = ((first as u32) << 18) | ((second as u32) << 12) | ((third as u32) << 6) | fourth as u32;
        out.push((packed >> 16) as u8);
        if padding < 2 {
            out.push((packed >> 8) as u8);
        }
        if padding < 1 {
            out.push(packed as u8);
        }
    }
    Ok(out)
}

/// Multipart photo upload. The catalogue service re-encodes the file; the register does not store the bytes itself.
#[tauri::command]
pub async fn retail_upload(
    state: tauri::State<'_, AppState>,
    path: String,
    filename: String,
    content_type: String,
    data_base64: String,
) -> Result<Value, String> {
    state
        .session()?
        .ok_or_else(|| failure(401, "locked", "Unlock the register first."))?;
    let user_token = state
        .user_token
        .lock()
        .map_err(|err| err.to_string())?
        .clone();
    if !safe(&path) || !path.contains("/images") {
        return Err(failure(400, "invalid_path", "That upload is not allowed from the register."));
    }
    if data_base64.len() > 7_000_000 {
        return Err(failure(413, "file_too_large", "Photos are limited to 5 MB."));
    }
    let bytes = decode_base64(&data_base64)?;
    if bytes.len() > 5 * 1024 * 1024 {
        return Err(failure(413, "file_too_large", "Photos are limited to 5 MB."));
    }
    let config = state.config.clone();
    let safe_name: String = filename
        .chars()
        .map(|char| if char.is_ascii_alphanumeric() || ".-_".contains(char) { char } else { '-' })
        .take(80)
        .collect();
    tauri::async_runtime::spawn_blocking(move || {
        let client = reqwest::blocking::Client::builder()
            .timeout(Duration::from_secs(30))
            .build()
            .map_err(|err| failure(0, "offline", &err.to_string()))?;
        let part = reqwest::blocking::multipart::Part::bytes(bytes)
            .file_name(if safe_name.is_empty() { "photo.webp".to_string() } else { safe_name })
            .mime_str(&content_type)
            .map_err(|_| failure(415, "unsupported_file", "Upload a JPEG, PNG or WebP photo."))?;
        let form = reqwest::blocking::multipart::Form::new().part("file", part);
        let url = format!("{}{}", config.api_base_url, path);
        let request = client.post(&url).multipart(form).headers(config.auth_headers());
        let request = if let Some(token) = &user_token {
            request.header("Authorization", format!("Bearer {token}"))
        } else {
            request
        };
        let response = request
            .send()
            .map_err(|err| failure(0, "offline", &format!("The server is unreachable: {err}")))?;
        let status = response.status();
        let value: Value = response.json().unwrap_or(Value::Null);
        if !status.is_success() {
            let code = value["error"]["code"].as_str().unwrap_or("rejected");
            let message = value["error"]["message"]
                .as_str()
                .unwrap_or("The server refused the photo.");
            return Err(failure(status.as_u16(), code, message));
        }
        Ok(value)
    })
    .await
    .map_err(|err| failure(0, "offline", &err.to_string()))?
}

#[cfg(test)]
mod tests {
    use super::safe;

    #[test]
    fn only_retail_paths_pass() {
        assert!(safe("/api/v1/gift-cards/GC-AAAA-BBBB-CCCC"));
        assert!(safe("/api/v1/gift-cards/product"));
        assert!(safe(
            "/api/v1/customers/123e4567-e89b-12d3-a456-426614174000/history?limit=10"
        ));
        assert!(safe("/api/v1/online-orders?status=NEW"));
        assert!(safe("/api/v1/reorders/occurrences?view=due"));
        assert!(!safe("/api/v1/reordersx"));
        assert!(safe("/api/v1/inventory/stock?store_id=s-1&status=low"));
        assert!(safe("/api/v1/products"));
        assert!(safe("/api/v1/pharmacy/lots/123/release"));
        assert!(safe("/api/v1/users/register-staff?store_id=s-1"));
        assert!(safe("/api/v1/users/me/preferences"));
        assert!(safe("/api/v1/users/me/preferences/product-catalogue-view"));
        assert!(!safe("/api/v1/users"));
        assert!(!safe("/api/v1/users/123"));
        assert!(!safe("/api/v1/users/me"));
        assert!(!safe("/api/v1/gift-cards/../users"));
        assert!(!safe("/api/v1/gift-cardsx"));
    }

    #[test]
    fn offset_lists_keep_their_total() {
        let body = serde_json::json!([{"id": "a"}]);
        let wrapped = super::with_total("/api/v1/repairs?offset=0&limit=25", body, Some("4"));
        assert_eq!(wrapped["total"], 4);
        assert_eq!(wrapped["rows"][0]["id"], "a");
        let plain = serde_json::json!([{"id": "a"}]);
        assert!(super::with_total("/api/v1/repairs?limit=30", plain, Some("4")).is_array());
    }
}
