//! Pass-through to the restaurant API (open orders, floor plan, kitchen display, delivery channels) with the
//! register's own credentials. Paths are whitelisted; errors come back as JSON {status, code, message} so the
//! screens can tell a stale order (409) from being offline.

use std::time::Duration;

use serde_json::{json, Value};

use crate::AppState;

const PREFIXES: [&str; 7] = [
    "/api/v1/orders",
    "/api/v1/dining",
    "/api/v1/kds",
    "/api/v1/channels",
    "/api/v1/sales-orders",
    "/api/v1/price-lists/customers",
    "/api/v1/reservations",
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

fn failure(status: u16, code: &str, message: &str) -> String {
    json!({ "status": status, "code": code, "message": message }).to_string()
}

#[tauri::command]
pub async fn restaurant_request(
    state: tauri::State<'_, AppState>,
    method: String,
    path: String,
    body: Option<Value>,
) -> Result<Value, String> {
    state
        .session()?
        .ok_or_else(|| failure(401, "locked", "Unlock the register first."))?;
    if !safe(&path) {
        return Err(failure(
            400,
            "invalid_path",
            "That restaurant request is not allowed.",
        ));
    }
    let config = state.config.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let client = reqwest::blocking::Client::builder()
            .timeout(Duration::from_secs(8))
            .build()
            .map_err(|err| failure(0, "offline", &err.to_string()))?;
        let url = format!("{}{}", config.api_base_url, path);
        let request = match method.as_str() {
            "GET" => client.get(&url),
            "POST" => client.post(&url).json(&body.unwrap_or_else(|| json!({}))),
            "PATCH" => client.patch(&url).json(&body.unwrap_or_else(|| json!({}))),
            "PUT" => client.put(&url).json(&body.unwrap_or_else(|| json!({}))),
            _ => return Err(failure(400, "invalid_method", "Unsupported method.")),
        };
        let response = request
            .headers(config.auth_headers())
            .send()
            .map_err(|err| failure(0, "offline", &format!("The server is unreachable: {err}")))?;
        let status = response.status();
        let value: Value = response.json().unwrap_or(Value::Null);
        if !status.is_success() {
            let code = value["error"]["code"].as_str().unwrap_or("rejected");
            let message = value["error"]["message"]
                .as_str()
                .unwrap_or("The server refused the request.");
            let mut body = serde_json::json!({ "status": status.as_u16(), "code": code, "message": message });
            if let Some(order_id) = value["error"]["details"]["order_id"].as_str() {
                body["order_id"] = serde_json::json!(order_id);
            }
            return Err(body.to_string());
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
    fn only_restaurant_paths_pass() {
        assert!(safe("/api/v1/orders?store_id=abc&status=OPEN"));
        assert!(safe(
            "/api/v1/orders/123e4567-e89b-12d3-a456-426614174000/send"
        ));
        assert!(safe("/api/v1/dining/floor?store_id=x"));
        assert!(safe("/api/v1/reservations?store_id=x"));
        assert!(!safe("/api/v1/users"));
        assert!(!safe("/api/v1/orders/../users"));
        assert!(!safe("/api/v1/ordersx"));
        assert!(safe("/api/v1/sales-orders"));
        assert!(!safe("/api/v1/sales-ordersx"));
    }
}
