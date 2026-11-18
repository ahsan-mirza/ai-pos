//! Demo enrollment from a connection file the visitor opens after installation.
//!
//! The file holds one short-lived ticket. The server decides the tenant. The device token is
//! stored with the same DPAPI seal as a production activation. The raw ticket is not logged.

use std::path::{Path, PathBuf};
use std::time::Duration;

use serde::Deserialize;

use crate::auth::{self, PinUnlock, TokenResponse};
use crate::sync::DesktopConfig;
use crate::terminal::{self, TerminalConfig};

const MAX_HANDOFF_BYTES: u64 = 4096;

#[derive(Debug)]
pub enum DemoFault {
    /// The server refused the ticket or the demo register. Do not retry that ticket.
    Refused(String),
    /// The API could not be reached. The ticket may still be unused.
    Offline(String),
}

impl DemoFault {
    pub fn message(&self) -> &str {
        match self {
            Self::Refused(message) | Self::Offline(message) => message,
        }
    }
}

#[derive(Deserialize)]
struct HandoffFile {
    version: u8,
    enrollment_ticket: String,
}

#[derive(Deserialize)]
struct ExchangeBody {
    tenant_slug: String,
    tenant_name: String,
    tenant_domain: String,
    tenant_url: String,
    store_id: String,
    store_code: String,
    store_name: String,
    register_id: String,
    register_code: String,
    register_name: String,
    device_token: String,
}

/// The API origin this build already uses. A `{tenant}` template becomes the `api` host.
pub fn enrollment_api_base() -> String {
    let template = std::env::var("TENANT_URL_TEMPLATE")
        .ok()
        .map(|value| value.trim().trim_end_matches('/').to_string())
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| terminal::tenant_api_url("api"));
    if template.contains("{tenant}") {
        return template.replace("{tenant}", "api");
    }
    template
}

pub fn read_handoff(path: &Path) -> Result<String, String> {
    let canonical = path.canonicalize().map_err(|_| "The connection file could not be opened.".to_string())?;
    if !canonical.is_file() {
        return Err("Choose the AxizPOS connection file.".into());
    }
    let extension = canonical
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    if extension != "posdemo" {
        return Err("Choose a file that ends in .posdemo.".into());
    }
    if !inside_user_profile(&canonical) {
        return Err("Open a connection file from your own user folder.".into());
    }
    let meta = std::fs::metadata(&canonical).map_err(|_| "The connection file could not be opened.".to_string())?;
    if meta.len() == 0 || meta.len() > MAX_HANDOFF_BYTES {
        return Err("That connection file is not valid.".into());
    }
    let text = std::fs::read_to_string(&canonical).map_err(|_| "The connection file could not be read.".to_string())?;
    let parsed: HandoffFile = serde_json::from_str(&text).map_err(|_| "That connection file is not valid.".to_string())?;
    if parsed.version != 1 {
        return Err("That connection file is not valid.".into());
    }
    let ticket = parsed.enrollment_ticket.trim();
    if ticket.len() < 12 || ticket.len() > 180 || ticket.chars().any(char::is_whitespace) || !ticket.contains('.') {
        return Err("That connection file is not valid.".into());
    }
    Ok(ticket.to_string())
}

fn inside_user_profile(path: &Path) -> bool {
    let profile = std::env::var("USERPROFILE")
        .or_else(|_| std::env::var("HOME"))
        .ok()
        .map(PathBuf::from);
    let Some(profile) = profile else {
        return false;
    };
    let Ok(profile) = profile.canonicalize() else {
        return false;
    };
    path.starts_with(profile)
}

pub fn posdemo_argument(args: &[String]) -> Option<String> {
    args.iter()
        .find(|arg| {
            Path::new(arg)
                .extension()
                .and_then(|value| value.to_str())
                .is_some_and(|value| value.eq_ignore_ascii_case("posdemo"))
        })
        .cloned()
}

pub fn delete_handoff(path: &Path) -> Result<(), String> {
    if path.exists() {
        std::fs::remove_file(path).map_err(|_| "The connection file could not be removed.".to_string())?;
    }
    Ok(())
}

pub fn exchange_ticket(ticket: &str) -> Result<TerminalConfig, DemoFault> {
    let api = enrollment_api_base();
    let response = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(20))
        .build()
        .map_err(|err| DemoFault::Offline(err.to_string()))?
        .post(format!("{api}/api/v1/demo-access/pos/exchange"))
        .json(&serde_json::json!({
            "enrollment_ticket": ticket,
            "machine_name": machine_name(),
        }))
        .send();
    let response = match response {
        Ok(response) => response,
        Err(_) => {
            return Err(DemoFault::Offline(
                "Unable to connect. Please check your internet connection.".into(),
            ))
        }
    };
    let status = response.status();
    let body = response.text().unwrap_or_default();
    if status.as_u16() == 404 || status.as_u16() == 401 || status.as_u16() == 403 {
        return Err(DemoFault::Refused(public_error(&body)));
    }
    if !status.is_success() {
        return Err(DemoFault::Offline(
            "The demo connection could not be completed. Please try again shortly.".into(),
        ));
    }
    let exchanged: ExchangeBody = serde_json::from_str(&body)
        .map_err(|_| DemoFault::Refused("The demo connection response was not valid.".into()))?;
    if exchanged.device_token.is_empty() || exchanged.tenant_slug.is_empty() || exchanged.tenant_domain.is_empty() {
        return Err(DemoFault::Refused("The demo connection response was not valid.".into()));
    }
    Ok(TerminalConfig {
        tenant_slug: exchanged.tenant_slug,
        tenant_name: exchanged.tenant_name,
        tenant_domain: exchanged.tenant_domain,
        tenant_url: exchanged.tenant_url,
        api_base_url: api,
        store_id: exchanged.store_id,
        store_code: exchanged.store_code,
        store_name: exchanged.store_name,
        register_id: exchanged.register_id,
        register_code: exchanged.register_code,
        register_name: exchanged.register_name,
        device_token: exchanged.device_token,
        activated_at: auth::now_secs(),
        demo: true,
    })
}

pub fn open_session(config: &DesktopConfig) -> Result<PinUnlock, DemoFault> {
    let response = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(15))
        .build()
        .map_err(|err| DemoFault::Offline(err.to_string()))?
        .post(format!("{}/api/v1/demo-access/pos/session", config.api_base_url.trim_end_matches('/')))
        .headers(config.auth_headers())
        .send();
    let response = match response {
        Ok(response) => response,
        Err(_) => return Err(DemoFault::Offline("Unable to connect. The saved demo can continue offline.".into())),
    };
    let status = response.status();
    let body = response.text().unwrap_or_default();
    if status.as_u16() == 401 || status.as_u16() == 403 {
        return Err(DemoFault::Refused(
            "This demo session is no longer available.".into(),
        ));
    }
    if !status.is_success() {
        return Err(DemoFault::Offline("The demo session could not be opened. Please try again shortly.".into()));
    }
    let parsed: TokenResponse = serde_json::from_str(&body)
        .map_err(|_| DemoFault::Refused("The demo session response was not valid.".into()))?;
    if !parsed.is_pos_scope() {
        return Err(DemoFault::Refused("The demo session response was not valid.".into()));
    }
    auth::accept_demo_session(parsed).map_err(DemoFault::Refused)
}

fn public_error(body: &str) -> String {
    #[derive(Deserialize)]
    struct Body {
        error: Detail,
    }
    #[derive(Deserialize)]
    struct Detail {
        message: String,
    }
    match serde_json::from_str::<Body>(body) {
        Ok(parsed) if !parsed.error.message.is_empty() && parsed.error.message.len() < 200 => parsed.error.message,
        _ => "This demo connection is no longer available. Download a new connection file.".into(),
    }
}

fn machine_name() -> String {
    std::env::var("COMPUTERNAME")
        .or_else(|_| std::env::var("HOSTNAME"))
        .unwrap_or_default()
        .chars()
        .take(120)
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_connection_file_in_the_user_profile_carries_one_ticket() {
        let dir = std::env::temp_dir().join("axizpos-handoff-test");
        std::fs::create_dir_all(&dir).unwrap();
        let file = dir.join("Harbor.posdemo");
        std::fs::write(&file, r#"{"version":1,"enrollment_ticket":"restaurant.ticket-value"}"#).unwrap();
        if !inside_user_profile(&file) {
            let _ = std::fs::remove_dir_all(&dir);
            return;
        }
        assert_eq!(
            posdemo_argument(&["register.exe".into(), file.display().to_string()]).as_deref(),
            Some(file.to_str().unwrap())
        );
        assert!(posdemo_argument(&["register.exe".into()]).is_none());
        assert_eq!(read_handoff(&file).unwrap(), "restaurant.ticket-value");
        std::fs::write(&file, r#"{"version":1,"enrollment_ticket":"no-separator"}"#).unwrap();
        assert!(read_handoff(&file).is_err());
        std::fs::write(&file, "not-json").unwrap();
        assert!(read_handoff(&file).is_err());
        let _ = std::fs::remove_dir_all(&dir);
    }
}
