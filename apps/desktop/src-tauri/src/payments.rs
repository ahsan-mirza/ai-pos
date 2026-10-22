//! Integrated card terminals and buy-now-pay-later. The server talks to the providers; the register only asks it
//! to start a payment and polls until the terminal or the provider answers, so these calls need a connection.

use crate::AppState;

const PREFIX: &str = "/api/v1/payments/";

fn safe_path(path: &str) -> Result<String, String> {
    let allowed = path.starts_with(PREFIX)
        && !path.contains("..")
        && path
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || matches!(c, '/' | '-' | '_' | '?' | '=' | '&'));
    if allowed {
        Ok(path.to_string())
    } else {
        Err("That payment request is not allowed from the register.".to_string())
    }
}

/// GET or POST under /api/v1/payments/ with the register's credentials; returns the JSON body.
#[tauri::command]
pub async fn payments_request(
    state: tauri::State<'_, AppState>,
    method: String,
    path: String,
    body: Option<serde_json::Value>,
) -> Result<serde_json::Value, String> {
    state
        .session()?
        .ok_or_else(|| "Unlock the register first.".to_string())?;
    let path = safe_path(&path)?;
    let config = state.config.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let client = reqwest::blocking::Client::builder()
            .timeout(std::time::Duration::from_secs(20))
            .build()
            .map_err(|err| err.to_string())?;
        let url = format!("{}{}", config.api_base_url, path);
        let request = match method.as_str() {
            "GET" => client.get(&url),
            "POST" => client
                .post(&url)
                .json(&body.unwrap_or(serde_json::json!({}))),
            _ => return Err("Unknown payment request.".to_string()),
        };
        let response = request
            .headers(config.auth_headers())
            .send()
            .map_err(|err| format!("Card and pay-later payments need a connection: {err}"))?;
        let status = response.status();
        let value: serde_json::Value = response.json().unwrap_or(serde_json::Value::Null);
        if !status.is_success() {
            return Err(value["error"]["message"]
                .as_str()
                .unwrap_or("The payment server refused.")
                .to_string());
        }
        Ok(value)
    })
    .await
    .map_err(|err| err.to_string())?
}

#[cfg(test)]
mod tests {
    use super::safe_path;

    #[test]
    fn only_payment_paths_pass() {
        assert!(safe_path("/api/v1/payments/card-intents").is_ok());
        assert!(safe_path("/api/v1/payments/config?store_id=abc-1").is_ok());
        assert!(safe_path("/api/v1/sales").is_err());
        assert!(safe_path("/api/v1/payments/../users").is_err());
        assert!(safe_path("/api/v1/payments/x y").is_err());
    }
}
