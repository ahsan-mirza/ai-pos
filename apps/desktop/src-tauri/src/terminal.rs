//! First-run activation: subdomain + one-time key -> tenant, store, register, and device token.
//! The result is kept in `terminal.bin`, encrypted for the signed-in Windows account with DPAPI.

use std::path::{Path, PathBuf};
use std::time::Duration;

use serde::{Deserialize, Serialize};

pub const DEFAULT_TENANT_URL_TEMPLATE: &str = "https://{tenant}.axizpos.com";
pub const DEFAULT_TENANT_BASE_DOMAIN: &str = "axizpos.com";

#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq)]
pub struct TerminalConfig {
    pub tenant_slug: String,
    pub tenant_name: String,
    pub tenant_domain: String,
    /// Public portal address the server reported (https://client1.axizpos.com).
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
    /// Tenant uuid from the activation response. Empty on registers activated before permanent entitlements.
    #[serde(default)]
    pub tenant_id: String,
    /// True only after a demo enrollment exchange. Existing files without the field stay production registers.
    #[serde(default)]
    pub demo: bool,
    /// Last local verification code. Empty until the register reads the sealed file.
    #[serde(default)]
    pub entitlement_code: String,
    /// Bootstrap readiness. This does not mean stock is partitioned between tills.
    #[serde(default)]
    pub readiness: String,
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
    #[serde(default)]
    pub demo: bool,
    /// Last permanent-entitlement result. Empty means this status was not assessed.
    #[serde(default)]
    pub entitlement_code: String,
    /// Bootstrap readiness. This is not a claim that stock is allocated to this terminal.
    #[serde(default)]
    pub readiness: String,
    /// Isolated acceptance switch. The default is false, including on production registers.
    #[serde(default)]
    pub single_terminal_offline_stock: bool,
}

impl TerminalStatus {
    pub fn none() -> Self {
        Self {
            source: "none".into(),
            entitlement_code: crate::entitlement::MISSING.into(),
            readiness: crate::entitlement::NOT_ACTIVATED.into(),
            ..Self::default()
        }
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
            demo: config.demo,
            entitlement_code: crate::entitlement::MISSING.into(),
            readiness: crate::entitlement::MISSING.into(),
            single_terminal_offline_stock: false,
        }
    }
}

/// Versioned sealed state. Version 1 is a bare `TerminalConfig` from O1.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct TerminalState {
    pub storage_version: u32,
    pub config: TerminalConfig,
    #[serde(default)]
    pub device_public_key: String,
    #[serde(default)]
    pub device_private_key: String,
    #[serde(default)]
    pub entitlement_payload: String,
    #[serde(default)]
    pub entitlement_signature: String,
    #[serde(default)]
    pub entitlement_key_id: String,
}

impl TerminalState {
    pub fn from_config(config: TerminalConfig) -> Self {
        Self {
            storage_version: 2,
            config,
            device_public_key: String::new(),
            device_private_key: String::new(),
            entitlement_payload: String::new(),
            entitlement_signature: String::new(),
            entitlement_key_id: String::new(),
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
    #[serde(default)]
    tenant_id: String,
    #[serde(default)]
    entitlement: Option<crate::entitlement::SignedEntitlement>,
}

#[derive(Deserialize)]
struct ErrorBody {
    error: ErrorDetail,
}

#[derive(Deserialize)]
struct ErrorDetail {
    message: String,
    #[serde(default)]
    code: String,
}

pub fn config_path(app_data_dir: &Path) -> PathBuf {
    app_data_dir.join("terminal.bin")
}

/// Each tenant's catalog, users, and unsynced sales live in their own database file.
pub fn database_path(app_data_dir: &Path, tenant_slug: &str) -> PathBuf {
    app_data_dir
        .join("tenants")
        .join(tenant_slug)
        .join("ai-pos.db")
}

pub fn load(path: &Path) -> Result<Option<TerminalState>, String> {
    let Some(plain) = read_plain(path)? else {
        return Ok(None);
    };
    parse_state(&plain).map(Some)
}

pub fn parse_state(plain: &[u8]) -> Result<TerminalState, String> {
    let value: serde_json::Value = serde_json::from_slice(plain)
        .map_err(|err| format!("The terminal configuration is damaged: {err}"))?;
    if value.get("storage_version").and_then(|item| item.as_u64()) == Some(2) {
        return serde_json::from_value(value)
            .map_err(|err| format!("The terminal configuration is damaged: {err}"));
    }
    if value.get("tenant_slug").and_then(|item| item.as_str()).is_some() {
        let config: TerminalConfig = serde_json::from_value(value)
            .map_err(|err| format!("The terminal configuration is damaged: {err}"))?;
        return Ok(TerminalState::from_config(config));
    }
    Err("The terminal configuration is damaged: unrecognized storage.".into())
}

pub(crate) fn read_plain(path: &Path) -> Result<Option<Vec<u8>>, String> {
    if !path.exists() {
        return Ok(None);
    }
    let sealed = std::fs::read(path).map_err(|err| format!("Unable to read {}: {err}", path.display()))?;
    let plain = protect::unseal(&sealed)?;
    Ok(Some(plain))
}

pub fn save(path: &Path, state: &TerminalState) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|err| err.to_string())?;
    }
    let plain = serde_json::to_vec(state).map_err(|err| err.to_string())?;
    let sealed = protect::seal(&plain)?;
    let staging = path.with_extension("bin.tmp");
    {
        use std::io::Write;
        let mut file = std::fs::OpenOptions::new()
            .create(true)
            .write(true)
            .truncate(true)
            .open(&staging)
            .map_err(|err| err.to_string())?;
        file.write_all(&sealed).map_err(|err| err.to_string())?;
        file.sync_all().map_err(|err| err.to_string())?;
    }
    let checked = std::fs::read(&staging).map_err(|err| err.to_string())?;
    let opened = parse_state(&protect::unseal(&checked)?)?;
    if opened.config.register_id != state.config.register_id || opened.storage_version != 2 {
        let _ = std::fs::remove_file(&staging);
        return Err("The saved terminal state could not be read back.".into());
    }
    if path.exists() {
        let backup = path.with_extension("bin.bak");
        std::fs::copy(path, &backup).map_err(|err| err.to_string())?;
    }
    if path.exists() {
        std::fs::remove_file(path).map_err(|err| err.to_string())?;
    }
    if let Err(err) = std::fs::rename(&staging, path) {
        let backup = path.with_extension("bin.bak");
        if backup.exists() && !path.exists() {
            let _ = std::fs::rename(&backup, path);
        }
        return Err(err.to_string());
    }
    let _ = std::fs::remove_file(path.with_extension("bin.tmp"));
    Ok(())
}

pub fn remove(path: &Path) -> Result<(), String> {
    if path.exists() {
        std::fs::remove_file(path).map_err(|err| err.to_string())?;
    }
    Ok(())
}

/// "client1", "client1.axizpos.com", or "https://client1.axizpos.com/" -> ("client1", "client1").
/// The second value is the store code sent as X-Tenant-Domain. Stores share one host, so it is not a subdomain.
pub fn normalize_subdomain(input: &str) -> Result<(String, String), String> {
    normalize_subdomain_for(input, &base_domain())
}

fn normalize_subdomain_for(input: &str, base: &str) -> Result<(String, String), String> {
    let mut host = input.trim().to_lowercase();
    if let Some((_, rest)) = host.split_once("://") {
        host = rest.to_string();
    }
    let host = host
        .split(['/', ':'])
        .next()
        .unwrap_or("")
        .trim_end_matches('.')
        .to_string();
    let slug = match host.split_once('.') {
        None => host.clone(),
        Some((label, rest)) if rest == base || rest == "localhost" => label.to_string(),
        Some(_) => return Err("Enter your store code, e.g. client1.".into()),
    };
    let valid = !slug.is_empty()
        && slug.len() <= 32
        && slug
            .chars()
            .all(|ch| ch.is_ascii_lowercase() || ch.is_ascii_digit() || ch == '-')
        && !slug.starts_with('-')
        && !slug.ends_with('-');
    if !valid {
        return Err("Store codes use lowercase letters, digits, and dashes.".into());
    }
    Ok((slug.clone(), slug))
}

/// A runtime environment variable wins (LAN testing), then the value build.rs baked in from
/// the repo-root env file (`.env`, `.env.dev`, or `.env.production`), then the production default.
fn acceptance_build() -> bool {
    env!("POS_ACCEPTANCE_BUILD") == "1"
}

fn setting(name: &str, baked: &str, default: &str) -> String {
    if acceptance_build() {
        return baked.trim().to_string();
    }
    std::env::var(name)
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .or_else(|| Some(baked.trim().to_string()).filter(|value| !value.is_empty()))
        .unwrap_or_else(|| default.to_string())
}

fn base_domain() -> String {
    setting(
        "TENANT_BASE_DOMAIN",
        env!("POS_TENANT_BASE_DOMAIN"),
        DEFAULT_TENANT_BASE_DOMAIN,
    )
    .trim_start_matches('.')
    .to_lowercase()
}

/// https://{tenant}.axizpos.com in production, https://{tenant}.dev.axizpos.com in the dev build; developers point
/// TENANT_URL_TEMPLATE at a local API.
pub fn tenant_api_url(slug: &str) -> String {
    setting(
        "TENANT_URL_TEMPLATE",
        env!("POS_TENANT_URL_TEMPLATE"),
        DEFAULT_TENANT_URL_TEMPLATE,
    )
    .replace("{tenant}", slug)
    .trim_end_matches('/')
    .to_string()
}

/// The only API address an acceptance build may call. Process environment cannot replace it.
pub fn acceptance_api_base() -> Result<String, String> {
    let url = tenant_api_url("acceptance");
    if url == env!("POS_ACCEPTANCE_API_BASE") && !url.is_empty() {
        return Ok(url);
    }
    Err("Acceptance API URL is not the dedicated loopback endpoint.".into())
}

fn machine_name() -> String {
    std::env::var("COMPUTERNAME")
        .or_else(|_| std::env::var("HOSTNAME"))
        .unwrap_or_default()
        .chars()
        .take(120)
        .collect()
}

pub const SIGNING_UNAVAILABLE: &str =
    "The server cannot currently issue a permanent device entitlement. Contact your administrator.";
#[cfg_attr(not(test), allow(dead_code))]
pub const SAME_STORE_PENDING: &str =
    "Existing store detected. Your pending records will remain associated with this store and register.";
pub const DIFFERENT_STORE_PENDING: &str =
    "This device contains transactions belonging to another store. Sync or export them before changing stores.";
pub const API_UNAVAILABLE: &str =
    "Your records are محفوظ locally. Reconnect to the original store to synchronize before migration.";
pub const SERVER_UNREACHABLE: &str =
    "Cannot reach the server. Check the store code and the internet connection.";

pub fn sync_before_retire(sales: i64) -> String {
    if sales == 1 {
        "1 sale is waiting to sync. Synchronize it before retiring the previous register identity.".into()
    } else {
        format!("{sales} sales are waiting to sync. Synchronize them before retiring the previous register identity.")
    }
}

/// Same-store pending records are not a reason to refuse a key. A different store still is.
pub fn replacement_block(decision: &str, pending: i64) -> Option<String> {
    if pending <= 0 {
        return None;
    }
    match decision {
        "different_store" => Some(DIFFERENT_STORE_PENDING.into()),
        "same_store_replacement" => Some(sync_before_retire(pending)),
        "same_store" | "same_store_additional" => None,
        "signing" => Some(SIGNING_UNAVAILABLE.into()),
        "offline" => Some(API_UNAVAILABLE.into()),
        _ => None,
    }
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct ActivationDecision {
    pub decision: String,
    pub kind: String,
    #[serde(default)]
    pub same_tenant: bool,
    #[serde(default)]
    pub same_store: bool,
    #[serde(default)]
    pub blocked: bool,
    pub code: String,
    pub message: String,
    #[serde(default)]
    pub signing_ready: bool,
    #[serde(default)]
    pub pending_sales: i64,
    #[serde(default)]
    pub pending_returns: i64,
    #[serde(default)]
    pub pending_cash_movements: i64,
}

#[derive(Clone, Debug, Default)]
pub struct LocalActivationContext {
    pub tenant_id: String,
    pub store_id: String,
    pub register_id: String,
    pub device_public_key: String,
    pub pending_sales: i64,
    pub pending_returns: i64,
    pub pending_cash_movements: i64,
}

impl LocalActivationContext {
    pub fn pending_total(&self) -> i64 {
        self.pending_sales + self.pending_returns + self.pending_cash_movements
    }
}

pub fn preflight(
    subdomain: &str,
    activation_key: &str,
    local: &LocalActivationContext,
) -> Result<ActivationDecision, String> {
    let (slug, domain) = normalize_subdomain(subdomain)?;
    let key: String = activation_key.chars().filter(|ch| ch.is_ascii_alphanumeric()).collect();
    let api_base_url = tenant_api_url(&slug);
    let response = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(15))
        .build()
        .map_err(|err| err.to_string())?
        .post(format!("{api_base_url}/api/v1/terminals/activation-preflight"))
        .header("X-Tenant-Domain", &domain)
        .json(&serde_json::json!({
            "store_code": slug,
            "activation_key": key,
            "local": {
                "tenant_id": local.tenant_id,
                "store_id": local.store_id,
                "register_id": local.register_id,
                "device_public_key": local.device_public_key,
                "pending_sales": local.pending_sales,
                "pending_returns": local.pending_returns,
                "pending_cash_movements": local.pending_cash_movements,
            }
        }))
        .send()
        .map_err(|_| {
            if local.pending_total() > 0 {
                API_UNAVAILABLE.to_string()
            } else {
                SERVER_UNREACHABLE.to_string()
            }
        })?;
    let status = response.status();
    let body = response.text().map_err(|err| err.to_string())?;
    if !status.is_success() {
        let message = serde_json::from_str::<ErrorBody>(&body)
            .map(|parsed| {
                if parsed.error.code.is_empty() {
                    parsed.error.message
                } else {
                    format!("[{}] {}", parsed.error.code, parsed.error.message)
                }
            })
            .unwrap_or_else(|_| format!("Activation could not be checked ({}).", status.as_u16()));
        return Err(message);
    }
    serde_json::from_str(&body).map_err(|err| format!("Unexpected activation check: {err}"))
}

/// Stops activation only when the decision says it must stop. Same-store notices are not a stop.
pub fn activation_block(decision: &ActivationDecision, archived: bool) -> Option<String> {
    if decision.code == "pending_different_store" && archived {
        return None;
    }
    if decision.blocked {
        return Some(if decision.code == "entitlement_unconfigured" {
            SIGNING_UNAVAILABLE.to_string()
        } else if decision.message.trim().is_empty() {
            "Activation could not be completed. Contact your administrator.".to_string()
        } else {
            decision.message.clone()
        });
    }
    None
}

pub struct ActivationOutcome {
    pub config: TerminalConfig,
    pub entitlement: Option<crate::entitlement::SignedEntitlement>,
}

pub fn activate(
    subdomain: &str,
    activation_key: &str,
    device_public_key: &str,
) -> Result<ActivationOutcome, String> {
    let (slug, domain) = normalize_subdomain(subdomain)?;
    let key: String = activation_key
        .chars()
        .filter(|ch| ch.is_ascii_alphanumeric())
        .collect();
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
        .json(&serde_json::json!({
            "activation_key": key,
            "machine_name": machine_name(),
            "device_public_key": device_public_key,
        }))
        .send()
        .map_err(|_| SERVER_UNREACHABLE.to_string())?;
    let status = response.status();
    let body = response.text().map_err(|err| err.to_string())?;
    if !status.is_success() {
        let message = serde_json::from_str::<ErrorBody>(&body)
            .map(|parsed| {
                if parsed.error.code.is_empty() {
                    parsed.error.message
                } else {
                    format!("[{}] {}", parsed.error.code, parsed.error.message)
                }
            })
            .unwrap_or_else(|_| format!("Activation failed ({}).", status.as_u16()));
        return Err(message);
    }
    let activated: ActivationResponse = serde_json::from_str(&body)
        .map_err(|err| format!("Unexpected activation response: {err}"))?;
    if !device_public_key.is_empty() && activated.entitlement.is_none() {
        return Err("The server did not return a permanent entitlement. The register was not saved.".into());
    }
    Ok(ActivationOutcome {
        config: TerminalConfig {
            tenant_slug: activated.tenant_slug,
            tenant_name: activated.tenant_name,
            tenant_domain: if activated.tenant_domain.is_empty() {
                domain
            } else {
                activated.tenant_domain
            },
            tenant_url: activated.tenant_url,
            tenant_id: activated.tenant_id,
            api_base_url,
            store_id: activated.store_id,
            store_code: activated.store_code,
            store_name: activated.store_name,
            register_id: activated.register_id,
            register_code: activated.register_code,
            register_name: activated.register_name,
            device_token: activated.device_token,
            activated_at: crate::auth::now_secs(),
            entitlement_code: String::new(),
            readiness: String::new(),
            demo: false,
        },
        entitlement: activated.entitlement,
    })
}

#[cfg(windows)]
pub(crate) mod protect {
    use std::ptr::{null, null_mut};

    use windows_sys::Win32::Foundation::{LocalFree, HLOCAL};
    use windows_sys::Win32::Security::Cryptography::{
        CryptProtectData, CryptUnprotectData, CRYPTPROTECT_UI_FORBIDDEN, CRYPT_INTEGER_BLOB,
    };

    const ENTROPY: &[u8] = b"ai-pos-terminal-config-v1";

    fn blob(data: &[u8]) -> CRYPT_INTEGER_BLOB {
        CRYPT_INTEGER_BLOB {
            cbData: data.len() as u32,
            pbData: data.as_ptr() as *mut u8,
        }
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
        let mut output = CRYPT_INTEGER_BLOB {
            cbData: 0,
            pbData: null_mut(),
        };
        // SAFETY: every pointer refers to a live blob for the duration of the call.
        let ok = unsafe {
            CryptProtectData(
                &input,
                null(),
                &entropy,
                null(),
                null(),
                CRYPTPROTECT_UI_FORBIDDEN,
                &mut output,
            )
        };
        if ok == 0 {
            return Err("Windows could not encrypt the terminal configuration.".into());
        }
        Ok(take(output))
    }

    pub fn unseal(sealed: &[u8]) -> Result<Vec<u8>, String> {
        let input = blob(sealed);
        let entropy = blob(ENTROPY);
        let mut output = CRYPT_INTEGER_BLOB {
            cbData: 0,
            pbData: null_mut(),
        };
        // SAFETY: as in `seal`.
        let ok = unsafe {
            CryptUnprotectData(
                &input,
                null_mut(),
                &entropy,
                null(),
                null(),
                CRYPTPROTECT_UI_FORBIDDEN,
                &mut output,
            )
        };
        if ok == 0 {
            return Err(
                "This terminal was activated under another Windows account. Activate it again."
                    .into(),
            );
        }
        Ok(take(output))
    }
}

#[cfg(not(windows))]
pub(crate) mod protect {
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
        let live = |input: &str| normalize_subdomain_for(input, "axizpos.com");
        assert_eq!(live("Client1").unwrap(), ("client1".into(), "client1".into()));
        assert_eq!(
            live("https://client1.axizpos.com/login").unwrap(),
            ("client1".into(), "client1".into())
        );
        assert_eq!(live("demo.localhost:5173").unwrap(), ("demo".into(), "demo".into()));
        assert!(live("client1.example.com").is_err());
        assert!(live("bad_name").is_err());
        let dev = |input: &str| normalize_subdomain_for(input, "dev.axizpos.com");
        assert_eq!(dev("client1").unwrap(), ("client1".into(), "client1".into()));
        assert_eq!(
            dev("https://client1.dev.axizpos.com/").unwrap(),
            ("client1".into(), "client1".into())
        );
        assert!(dev("client1.axizpos.com").is_err());
        assert!(SAME_STORE_PENDING.contains("Existing store detected"));
        assert!(replacement_block("same_store_additional", 2).is_none());
        assert!(replacement_block("different_store", 0).is_none());
        assert!(replacement_block("different_store", 1)
            .unwrap()
            .contains("another store"));
        assert!(replacement_block("same_store_replacement", 1)
            .unwrap()
            .contains("1 sale is waiting to sync"));
        assert!(replacement_block("signing", 1).unwrap().contains("permanent device entitlement"));
        assert!(replacement_block("offline", 1).unwrap().contains("محفوظ"));
        let different = ActivationDecision {
            code: "pending_different_store".into(),
            blocked: true,
            message: DIFFERENT_STORE_PENDING.into(),
            ..ActivationDecision::default()
        };
        assert!(activation_block(&different, false).unwrap().contains("another store"));
        assert!(activation_block(&different, true).is_none());
        let unsigned = ActivationDecision {
            code: "entitlement_unconfigured".into(),
            blocked: true,
            message: "Traceback (most recent call last)".into(),
            ..ActivationDecision::default()
        };
        assert!(activation_block(&unsigned, false).unwrap().contains("permanent device entitlement"));
        let ip = |input: &str| normalize_subdomain_for(input, "130.210.53.214");
        assert_eq!(ip("Client1").unwrap(), ("client1".into(), "client1".into()));
        assert_eq!(
            ip("client1.130.210.53.214").unwrap(),
            ("client1".into(), "client1".into())
        );
        assert!(ip("client1.axizpos.com").is_err());
    }

    #[test]
    fn sealed_config_round_trips() {
        let sealed = protect::seal(b"{\"a\":1}").unwrap();
        assert_eq!(protect::unseal(&sealed).unwrap(), b"{\"a\":1}");
    }

    fn sample_config() -> TerminalConfig {
        TerminalConfig {
            tenant_slug: "tenant-a".into(),
            tenant_name: "Tenant A".into(),
            tenant_domain: "tenant-a".into(),
            tenant_url: "http://127.0.0.1".into(),
            api_base_url: "http://127.0.0.1:9".into(),
            store_id: "branch-a".into(),
            store_code: "A".into(),
            store_name: "Branch A".into(),
            register_id: "till-a".into(),
            register_code: "T1".into(),
            register_name: "Till 1".into(),
            device_token: "aipos_test_token".into(),
            activated_at: 1,
            tenant_id: "tenant-a".into(),
            entitlement_code: String::new(),
            readiness: String::new(),
            demo: false,
        }
    }

    #[test]
    fn o1_storage_upgrades_without_replacing_the_identity() {
        let dir = std::env::temp_dir().join(format!("axiz-o2-legacy-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        let path = config_path(&dir);
        let legacy = sample_config();
        let plain = serde_json::to_vec(&legacy).unwrap();
        std::fs::write(&path, protect::seal(&plain).unwrap()).unwrap();
        let loaded = load(&path).unwrap().unwrap();
        assert_eq!(loaded.config.register_id, "till-a");
        assert!(loaded.entitlement_payload.is_empty());
        save(&path, &loaded).unwrap();
        let again = load(&path).unwrap().unwrap();
        assert_eq!(again.storage_version, 2);
        assert_eq!(again.config.device_token, legacy.device_token);
        assert_eq!(again.config.register_id, legacy.register_id);
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn corrupt_storage_is_not_replaced_with_a_new_identity() {
        let dir = std::env::temp_dir().join(format!("axiz-o2-corrupt-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        let path = config_path(&dir);
        std::fs::write(&path, b"not-a-sealed-terminal").unwrap();
        assert!(load(&path).is_err());
        assert!(std::fs::read(&path).unwrap().starts_with(b"not-a-sealed"));
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn entitlement_restarts_offline_after_the_lease_window() {
        use crate::db::{Db, QueuedEvent};
        use crate::entitlement::{self, ExpectedBinding};
        use std::collections::BTreeMap;
        let dir = std::env::temp_dir().join(format!("axiz-o2-restart-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        let path = config_path(&dir);
        let (public_key, private_key) = entitlement::generate_device_key().unwrap();
        let binding = entitlement::device_binding(&public_key).unwrap();
        let mut document = BTreeMap::new();
        document.insert("schema_version", serde_json::Value::from(1));
        document.insert("entitlement_id", serde_json::Value::from("ent-restart"));
        document.insert("issuer", serde_json::Value::from("axizpos"));
        document.insert("audience", serde_json::Value::from("axizpos-register"));
        document.insert("tenant_id", serde_json::Value::from("tenant-a"));
        document.insert("branch_id", serde_json::Value::from("branch-a"));
        document.insert("terminal_id", serde_json::Value::from("till-a"));
        document.insert("device_binding", serde_json::Value::from(binding.clone()));
        document.insert("plan_id", serde_json::Value::from("local"));
        document.insert("issued_at", serde_json::Value::from("2020-01-01T00:00:00Z"));
        document.insert("permanent", serde_json::Value::Bool(true));
        document.insert("key_id", serde_json::Value::from("o2-test-1"));
        document.insert("capabilities", serde_json::json!([]));
        let (payload, signature, _) = entitlement::sign_for_test(&[7u8; 32], &document);
        let mut state = TerminalState::from_config(sample_config());
        state.device_public_key = public_key;
        state.device_private_key = private_key;
        state.entitlement_payload = payload;
        state.entitlement_signature = signature;
        state.entitlement_key_id = "o2-test-1".into();
        save(&path, &state).unwrap();
        drop(state);
        let opened = load(&path).unwrap().unwrap();
        let code = entitlement::code_for(
            &opened.entitlement_payload,
            &opened.entitlement_signature,
            &opened.entitlement_key_id,
            &ExpectedBinding {
                tenant_id: "tenant-a".into(),
                branch_id: "branch-a".into(),
                terminal_id: "till-a".into(),
                device_binding: binding,
            },
            1_700_000_000 + 60 * 60 * 24 * 30,
        );
        assert_eq!(code, entitlement::VALID);
        let database = dir.join("ai-pos.db");
        let db = Db::open(&database).unwrap();
        db.enqueue(
            "batch-1",
            &[QueuedEvent {
                id: "event-1".into(),
                idempotency_key: "sale-key-1".into(),
                entity_type: "sale".into(),
                operation: "create".into(),
                payload: serde_json::json!({"total_cents": 100}),
                occurred_at: "2020-01-01T00:00:00Z".into(),
            }],
        )
        .unwrap();
        assert_eq!(db.pending_count().unwrap(), 1);
        let again = db.enqueue(
            "batch-1",
            &[QueuedEvent {
                id: "event-1".into(),
                idempotency_key: "sale-key-1".into(),
                entity_type: "sale".into(),
                operation: "create".into(),
                payload: serde_json::json!({"total_cents": 100}),
                occurred_at: "2020-01-01T00:00:00Z".into(),
            }],
        );
        assert!(again.is_err());
        assert_eq!(db.pending_count().unwrap(), 1);
        let _ = std::fs::remove_dir_all(&dir);
    }
}
