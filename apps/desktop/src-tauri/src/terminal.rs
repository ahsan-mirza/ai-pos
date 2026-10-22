//! First-run activation: subdomain + one-time key -> tenant, store, register, and device token.
//! The result is kept in `terminal.bin`, encrypted for the signed-in Windows account with DPAPI.

use std::path::{Path, PathBuf};
use std::time::Duration;

use serde::{Deserialize, Serialize};

pub const DEFAULT_TENANT_URL_TEMPLATE: &str = "https://{tenant}.qios.ae";
pub const DEFAULT_TENANT_BASE_DOMAIN: &str = "qios.ae";

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct TerminalConfig {
    pub tenant_slug: String,
    pub tenant_name: String,
    pub tenant_domain: String,
    /// Public portal address the server reported (https://client1.qios.ae).
    pub tenant_url: String,
    /// Where this register sends API calls; the address it was activated against.
    pub api_base_url: String,
    pub store_id: String,
    pub store_code: String,
    pub store_name: String,
    pub register_id: String,
    pub register_code: String,
    pub register_name: String,
    pub device_token: String,
    pub activated_at: i64,
}

/// What the UI may see: everything except the device token.
#[derive(Clone, Debug, Default, Serialize)]
pub struct TerminalStatus {
    pub activated: bool,
    /// "activation" (terminal.bin), "env" (developer .env), or "none".
    pub source: String,
    pub tenant_slug: String,
    pub tenant_name: String,
    pub tenant_domain: String,
    pub tenant_url: String,
    pub store_id: String,
    pub store_code: String,
    pub store_name: String,
    pub register_id: String,
    pub register_code: String,
    pub register_name: String,
}

impl TerminalStatus {
    pub fn none() -> Self {
        Self { source: "none".into(), ..Self::default() }
    }

    pub fn from_config(config: &TerminalConfig, source: &str) -> Self {
        Self {
            activated: true,
            source: source.into(),
            tenant_slug: config.tenant_slug.clone(),
            tenant_name: config.tenant_name.clone(),
            tenant_domain: config.tenant_domain.clone(),
            tenant_url: config.tenant_url.clone(),
            store_id: config.store_id.clone(),
            store_code: config.store_code.clone(),
            store_name: config.store_name.clone(),
            register_id: config.register_id.clone(),
            register_code: config.register_code.clone(),
            register_name: config.register_name.clone(),
        }
    }
}

#[derive(Deserialize)]
struct ActivationResponse {
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

#[derive(Deserialize)]
struct ErrorBody {
    error: ErrorDetail,
}

#[derive(Deserialize)]
struct ErrorDetail {
    message: String,
}

pub fn config_path(app_data_dir: &Path) -> PathBuf {
    app_data_dir.join("terminal.bin")
}

/// Each tenant's catalog, users, and unsynced sales live in their own database file.
pub fn database_path(app_data_dir: &Path, tenant_slug: &str) -> PathBuf {
    app_data_dir.join("tenants").join(tenant_slug).join("ai-pos.db")
}

pub fn load(path: &Path) -> Result<Option<TerminalConfig>, String> {
    if !path.exists() {
        return Ok(None);
    }
    let sealed = std::fs::read(path).map_err(|err| format!("Unable to read {}: {err}", path.display()))?;
    let plain = protect::unseal(&sealed)?;
    let config: TerminalConfig =
        serde_json::from_slice(&plain).map_err(|err| format!("The terminal configuration is damaged: {err}"))?;
    Ok(Some(config))
}

pub fn save(path: &Path, config: &TerminalConfig) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|err| err.to_string())?;
    }
    let plain = serde_json::to_vec(config).map_err(|err| err.to_string())?;
    let sealed = protect::seal(&plain)?;
    let staging = path.with_extension("bin.tmp");
    std::fs::write(&staging, sealed).map_err(|err| err.to_string())?;
    std::fs::rename(&staging, path).map_err(|err| err.to_string())
}

pub fn remove(path: &Path) -> Result<(), String> {
    if path.exists() {
        std::fs::remove_file(path).map_err(|err| err.to_string())?;
    }
    Ok(())
}

/// "client1", "client1.qios.ae", or "https://client1.qios.ae/" -> ("client1", "client1.qios.ae").
pub fn normalize_subdomain(input: &str) -> Result<(String, String), String> {
    normalize_subdomain_for(input, &base_domain())
}

fn normalize_subdomain_for(input: &str, base: &str) -> Result<(String, String), String> {
    let mut host = input.trim().to_lowercase();
    if let Some((_, rest)) = host.split_once("://") {
        host = rest.to_string();
    }
    let host = host.split(['/', ':']).next().unwrap_or("").trim_end_matches('.').to_string();
    let slug = match host.split_once('.') {
        None => host.clone(),
        Some((label, rest)) if rest == base || rest == "localhost" => label.to_string(),
        Some(_) => return Err(format!("Enter your store subdomain, e.g. client1 or client1.{base}.")),
    };
    let valid = !slug.is_empty()
        && slug.len() <= 32
        && slug.chars().all(|ch| ch.is_ascii_lowercase() || ch.is_ascii_digit() || ch == '-')
        && !slug.starts_with('-')
        && !slug.ends_with('-');
    if !valid {
        return Err("Subdomains use lowercase letters, digits, and dashes.".into());
    }
    Ok((slug.clone(), format!("{slug}.{base}")))
}

/// A runtime environment variable wins (LAN testing), then the value build.rs baked in from
/// the repo-root env file (`.env`, `.env.dev`, or `.env.production`), then the production default.
fn setting(name: &str, baked: &str, default: &str) -> String {
    std::env::var(name)
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .or_else(|| Some(baked.trim().to_string()).filter(|value| !value.is_empty()))
        .unwrap_or_else(|| default.to_string())
}

fn base_domain() -> String {
    setting("TENANT_BASE_DOMAIN", env!("POS_TENANT_BASE_DOMAIN"), DEFAULT_TENANT_BASE_DOMAIN)
        .trim_start_matches('.')
        .to_lowercase()
}

/// https://{tenant}.qios.ae in production, https://{tenant}.dev.qios.ae in the dev build; developers point
/// TENANT_URL_TEMPLATE at a local API.
pub fn tenant_api_url(slug: &str) -> String {
    setting("TENANT_URL_TEMPLATE", env!("POS_TENANT_URL_TEMPLATE"), DEFAULT_TENANT_URL_TEMPLATE)
        .replace("{tenant}", slug)
        .trim_end_matches('/')
        .to_string()
}

fn machine_name() -> String {
    std::env::var("COMPUTERNAME")
        .or_else(|_| std::env::var("HOSTNAME"))
        .unwrap_or_default()
        .chars()
        .take(120)
        .collect()
}

pub fn activate(subdomain: &str, activation_key: &str) -> Result<TerminalConfig, String> {
    let (slug, domain) = normalize_subdomain(subdomain)?;
    let key: String = activation_key.chars().filter(|ch| ch.is_ascii_alphanumeric()).collect();
    if key.len() < 8 {
        return Err("Enter the activation key from the admin portal (e.g. ABCD-EFGH-JKLM).".into());
    }
    let api_base_url = tenant_api_url(&slug);
    let response = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(15))
        .build()
        .map_err(|err| err.to_string())?
        .post(format!("{api_base_url}/api/v1/terminals/activate"))
        .header("X-Tenant-Domain", &domain)
        .json(&serde_json::json!({ "activation_key": key, "machine_name": machine_name() }))
        .send()
        .map_err(|err| format!("Could not reach {api_base_url}. Check the subdomain and the internet connection. ({err})"))?;
    let status = response.status();
    let body = response.text().map_err(|err| err.to_string())?;
    if !status.is_success() {
        let message = serde_json::from_str::<ErrorBody>(&body)
            .map(|parsed| parsed.error.message)
            .unwrap_or_else(|_| format!("Activation failed ({}).", status.as_u16()));
        return Err(message);
    }
    let activated: ActivationResponse =
        serde_json::from_str(&body).map_err(|err| format!("Unexpected activation response: {err}"))?;
    Ok(TerminalConfig {
        tenant_slug: activated.tenant_slug,
        tenant_name: activated.tenant_name,
        tenant_domain: if activated.tenant_domain.is_empty() { domain } else { activated.tenant_domain },
        tenant_url: activated.tenant_url,
        api_base_url,
        store_id: activated.store_id,
        store_code: activated.store_code,
        store_name: activated.store_name,
        register_id: activated.register_id,
        register_code: activated.register_code,
        register_name: activated.register_name,
        device_token: activated.device_token,
        activated_at: crate::auth::now_secs(),
    })
}

#[cfg(windows)]
mod protect {
    use std::ptr::{null, null_mut};

    use windows_sys::Win32::Foundation::{LocalFree, HLOCAL};
    use windows_sys::Win32::Security::Cryptography::{
        CryptProtectData, CryptUnprotectData, CRYPTPROTECT_UI_FORBIDDEN, CRYPT_INTEGER_BLOB,
    };

    const ENTROPY: &[u8] = b"ai-pos-terminal-config-v1";

    fn blob(data: &[u8]) -> CRYPT_INTEGER_BLOB {
        CRYPT_INTEGER_BLOB { cbData: data.len() as u32, pbData: data.as_ptr() as *mut u8 }
    }

    fn take(output: CRYPT_INTEGER_BLOB) -> Vec<u8> {
        // SAFETY: DPAPI allocated `cbData` bytes at `pbData` with LocalAlloc; they are copied, then freed once.
        unsafe {
            let bytes = std::slice::from_raw_parts(output.pbData, output.cbData as usize).to_vec();
            LocalFree(output.pbData as HLOCAL);
            bytes
        }
    }

    pub fn seal(plain: &[u8]) -> Result<Vec<u8>, String> {
        let input = blob(plain);
        let entropy = blob(ENTROPY);
        let mut output = CRYPT_INTEGER_BLOB { cbData: 0, pbData: null_mut() };
        // SAFETY: every pointer refers to a live blob for the duration of the call.
        let ok = unsafe {
            CryptProtectData(&input, null(), &entropy, null(), null(), CRYPTPROTECT_UI_FORBIDDEN, &mut output)
        };
        if ok == 0 {
            return Err("Windows could not encrypt the terminal configuration.".into());
        }
        Ok(take(output))
    }

    pub fn unseal(sealed: &[u8]) -> Result<Vec<u8>, String> {
        let input = blob(sealed);
        let entropy = blob(ENTROPY);
        let mut output = CRYPT_INTEGER_BLOB { cbData: 0, pbData: null_mut() };
        // SAFETY: as in `seal`.
        let ok = unsafe {
            CryptUnprotectData(&input, null_mut(), &entropy, null(), null(), CRYPTPROTECT_UI_FORBIDDEN, &mut output)
        };
        if ok == 0 {
            return Err("This terminal was activated under another Windows account. Activate it again.".into());
        }
        Ok(take(output))
    }
}

#[cfg(not(windows))]
mod protect {
    // Development builds on macOS/Linux keep the file readable only by the user; release builds target Windows.
    pub fn seal(plain: &[u8]) -> Result<Vec<u8>, String> {
        Ok(plain.to_vec())
    }

    pub fn unseal(sealed: &[u8]) -> Result<Vec<u8>, String> {
        Ok(sealed.to_vec())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn subdomains_normalise() {
        let live = |input: &str| normalize_subdomain_for(input, "qios.ae");
        assert_eq!(live("Client1").unwrap(), ("client1".into(), "client1.qios.ae".into()));
        assert_eq!(live("https://client1.qios.ae/login").unwrap().0, "client1");
        assert_eq!(live("demo.localhost:5173").unwrap().0, "demo");
        assert!(live("client1.example.com").is_err());
        assert!(live("bad_name").is_err());
        let dev = |input: &str| normalize_subdomain_for(input, "dev.qios.ae");
        assert_eq!(dev("client1").unwrap(), ("client1".into(), "client1.dev.qios.ae".into()));
        assert_eq!(dev("https://client1.dev.qios.ae/").unwrap().0, "client1");
        assert!(dev("client1.qios.ae").is_err());
    }

    #[test]
    fn sealed_config_round_trips() {
        let sealed = protect::seal(b"{\"a\":1}").unwrap();
        assert_eq!(protect::unseal(&sealed).unwrap(), b"{\"a\":1}");
    }
}
