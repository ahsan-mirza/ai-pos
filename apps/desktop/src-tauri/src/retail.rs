//! Pass-through to the retail API (gift cards, customer history, holds, tax-free forms, alterations, online
//! orders) with the register's own credentials. Paths are whitelisted; errors come back as JSON
//! {status, code, message} so a screen can tell a refusal from being offline.

use std::time::Duration;

use serde_json::{json, Value};

use crate::AppState;

const PREFIXES: [&str; 9] = [
    "/api/v1/gift-cards",
    "/api/v1/customers",
    "/api/v1/quotes",
    "/api/v1/tax-free",
    "/api/v1/repairs",
    "/api/v1/online-orders",
    "/api/v1/returns/receipts",
    "/api/v1/users/register-staff",
    "/api/v1/catalog/attributes",
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
pub async fn retail_request(
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
        assert!(safe("/api/v1/users/register-staff?store_id=s-1"));
        assert!(!safe("/api/v1/users"));
        assert!(!safe("/api/v1/users/123"));
        assert!(!safe("/api/v1/gift-cards/../users"));
        assert!(!safe("/api/v1/gift-cardsx"));
    }
}
