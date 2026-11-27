use std::time::{Duration, SystemTime, UNIX_EPOCH};

use argon2::password_hash::rand_core::OsRng;
use argon2::password_hash::{PasswordHash, PasswordHasher, PasswordVerifier, SaltString};
use argon2::Argon2;
use hmac::{Hmac, Mac};
use serde::{Deserialize, Serialize};
use sha2::Sha256;

use crate::db::{CachedUser, Db};
use crate::sync::DesktopConfig;

const LOCAL_MAX_ATTEMPTS: i64 = 5;
const LOCAL_LOCKOUT_SECS: i64 = 5 * 60;
const POS_ACCESS: &str = "pos:access";
/// The lock screen stays blank for this case. Staff sync while the register is online, so a missing cache is not an error to read aloud.
const OFFLINE_QUIET: &str = "offline-quiet";
const OFFLINE_ADDON_SECS: i64 = 24 * 60 * 60;
/// An unlocked register stays signed in across a restart for the same window as the offline add-on cache.
pub const REGISTER_SESSION_SECS: i64 = OFFLINE_ADDON_SECS;

/// Paid add-ons from the last online unlock. A corrupt list or a day-old cache grants none.
pub fn fresh_addons(encoded: &str, updated_at: i64, now: i64) -> Vec<String> {
    if now.saturating_sub(updated_at) > OFFLINE_ADDON_SECS {
        return Vec::new();
    }
    serde_json::from_str(encoded).unwrap_or_default()
}


#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CashierProfile {
    pub id: String,
    pub username: String,
    pub full_name: String,
    pub store_id: Option<String>,
    pub role_name: String,
    pub permissions: Vec<String>,
    /// Largest discount (basis points) the cashier gives without a manager; None uses the business default.
    #[serde(default)]
    pub max_discount_bps: Option<i64>,
    /// Paid add-ons this cashier may use. Empty when none were granted.
    #[serde(default)]
    pub addon_modules: Vec<String>,
    /// Unix seconds of the online unlock that refreshed add-on access.
    #[serde(default)]
    pub addon_synced_at: i64,
    /// Profile photo from the last online unlock. Missing on an offline unlock.
    #[serde(default)]
    pub avatar_url: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct Session {
    pub user: CashierProfile,
    pub mode: &'static str,
    pub unlocked_at: i64,
}

#[derive(Deserialize)]
struct RemoteRole {
    name: String,
    #[serde(default)]
    max_discount_bps: Option<i64>,
}

#[derive(Deserialize)]
struct RemoteUser {
    id: String,
    username: String,
    full_name: String,
    store_id: Option<String>,
    role: RemoteRole,
    permissions: Vec<String>,
    #[serde(default)]
    addon_modules: Vec<String>,
    #[serde(default)]
    avatar_url: Option<String>,
}

pub struct PinUnlock {
    pub session: Session,
    pub access_token: Option<String>,
}

#[derive(Deserialize)]
pub(crate) struct TokenResponse {
    #[serde(default)]
    access_token: String,
    #[serde(default)]
    scope: String,
    user: RemoteUser,
}

impl TokenResponse {
    pub(crate) fn is_pos_scope(&self) -> bool {
        self.scope == "pos"
    }
}

#[derive(Deserialize)]
struct ErrorBody {
    error: ErrorDetail,
}

#[derive(Deserialize)]
struct ErrorDetail {
    message: String,
}

enum Remote {
    Accepted(TokenResponse),
    /// The server answered and refused. Offline fallback must not override it.
    Refused {
        status: u16,
        message: String,
    },
    Unreachable,
}

pub fn now_secs() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|value| value.as_secs() as i64)
        .unwrap_or_default()
}

fn require_pin(pin: &str) -> Result<(), String> {
    if pin.len() != 4 || !pin.chars().all(|c| c.is_ascii_digit()) {
        return Err("PINs are 4 digits.".into());
    }
    Ok(())
}

/// Online first: the API is the source of truth for credentials. When it cannot be reached, the PIN is
/// checked against the Argon2 verifier cached on this register after the cashier's last online unlock.
pub fn pin_login(
    db: &Db,
    config: &DesktopConfig,
    username: &str,
    pin: &str,
) -> Result<PinUnlock, String> {
    let username = username.trim().to_lowercase();
    require_pin(pin)?;
    match remote_login(config, &username, pin) {
        Remote::Accepted(response) => accept_remote(db, response, pin),
        Remote::Refused { status, message } => {
            if status == 403 {
                db.remove_cached_user(&username)?;
            }
            Err(message)
        }
        Remote::Unreachable => offline_login(db, &username, pin),
    }
}

/// A selected profile. The PIN still goes through the same online check, then the local Argon2 cache.
pub fn unlock_by_id(db: &Db, config: &DesktopConfig, user_id: &str, pin: &str) -> Result<PinUnlock, String> {
    require_pin(pin)?;
    match remote_unlock(config, user_id, pin) {
        Remote::Accepted(response) => accept_remote(db, response, pin),
        Remote::Refused { status, message } => {
            if status == 401 {
                if let Ok(Some(cached)) = db.cached_user_by_id(user_id) {
                    if cached.provisioning_status == "pending" {
                        return offline_login_id(db, config, user_id, pin);
                    }
                }
            }
            Err(message)
        }
        Remote::Unreachable => offline_login_id(db, config, user_id, pin),
    }
}

/// A server-issued demo POS session. No PIN is hashed or stored, so this cannot unlock a production cashier.
pub fn accept_demo_session(response: TokenResponse) -> Result<PinUnlock, String> {
    if !response.user.permissions.iter().any(|item| item == POS_ACCESS) {
        return Err("This account cannot unlock a register.".into());
    }
    if response.access_token.is_empty() {
        return Err("The demo session was empty.".into());
    }
    let now = now_secs();
    Ok(PinUnlock {
        session: Session {
            user: profile_from(&response, now),
            mode: "online",
            unlocked_at: now,
        },
        access_token: Some(response.access_token),
    })
}

fn profile_from(response: &TokenResponse, now: i64) -> CashierProfile {
    CashierProfile {
        id: response.user.id.clone(),
        username: response.user.username.clone(),
        full_name: response.user.full_name.clone(),
        store_id: response.user.store_id.clone(),
        role_name: response.user.role.name.clone(),
        permissions: response.user.permissions.clone(),
        max_discount_bps: response.user.role.max_discount_bps,
        addon_modules: response.user.addon_modules.clone(),
        addon_synced_at: now,
        avatar_url: response.user.avatar_url.clone(),
    }
}

fn accept_remote(db: &Db, response: TokenResponse, pin: &str) -> Result<PinUnlock, String> {
    let now = now_secs();
    let profile = CashierProfile {
        id: response.user.id,
        username: response.user.username,
        full_name: response.user.full_name,
        store_id: response.user.store_id,
        role_name: response.user.role.name,
        permissions: response.user.permissions,
        max_discount_bps: response.user.role.max_discount_bps,
        addon_modules: response.user.addon_modules,
        addon_synced_at: now,
        avatar_url: response.user.avatar_url,
    };
    db.upsert_cached_user(&profile, &hash_pin(pin)?, now)?;
    Ok(PinUnlock {
        session: Session {
            user: profile,
            mode: "online",
            unlocked_at: now,
        },
        access_token: if response.access_token.is_empty() {
            None
        } else {
            Some(response.access_token)
        },
    })
}

fn offline_login(db: &Db, username: &str, pin: &str) -> Result<PinUnlock, String> {
    let Some(cached) = db.cached_user(username)? else {
        return Err(OFFLINE_QUIET.into());
    };
    finish_offline(db, cached, pin)
}

fn cached_profile(cached: CachedUser) -> Result<CashierProfile, String> {
    let synced_at = cached.updated_at;
    Ok(CashierProfile {
        id: cached.user_id,
        username: cached.username,
        full_name: cached.full_name,
        store_id: cached.store_id,
        role_name: cached.role_name,
        permissions: serde_json::from_str(&cached.permissions).map_err(|err| err.to_string())?,
        max_discount_bps: cached.max_discount_bps,
        addon_modules: fresh_addons(&cached.addon_modules, synced_at, now_secs()),
        addon_synced_at: synced_at,
        avatar_url: None,
    })
}

fn offline_login_id(db: &Db, config: &DesktopConfig, user_id: &str, pin: &str) -> Result<PinUnlock, String> {
    let Some(cached) = db.cached_user_by_id(user_id)? else {
        return Err(OFFLINE_QUIET.into());
    };
    if let Some(store) = &cached.store_id {
        if !config.store_id.is_empty() && store != &config.store_id {
            return Err("Invalid username or credentials.".into());
        }
    }
    finish_offline(db, cached, pin)
}

fn finish_offline(db: &Db, cached: CachedUser, pin: &str) -> Result<PinUnlock, String> {
    let username = cached.username.clone();
    let now = now_secs();
    if cached.is_active == 0 {
        return Err("This account is disabled on this register.".into());
    }
    if cached.provisioning_status == "rejected" {
        return Err("This account was not accepted by the server.".into());
    }
    if cached.locked_until.is_some_and(|until| until > now) {
        return Err("Too many failed attempts on this register. Try again in a few minutes.".into());
    }
    let pepper = db.local_meta("pin_salt").ok().flatten();
    if !verify_cached_pin(pin, &cached.pin_hash, pepper.as_deref()) {
        let attempts = cached.failed_attempts + 1;
        let locked_until = (attempts >= LOCAL_MAX_ATTEMPTS).then_some(now + LOCAL_LOCKOUT_SECS);
        db.record_cached_failure(
            &username,
            if locked_until.is_some() { 0 } else { attempts },
            locked_until,
        )?;
        return Err("Invalid username or credentials.".into());
    }
    db.record_cached_failure(&username, 0, None)?;
    let profile = cached_profile(cached)?;
    if !profile.permissions.iter().any(|item| item == POS_ACCESS) {
        return Err("This account cannot unlock a register.".into());
    }
    Ok(PinUnlock {
        session: Session {
            user: profile,
            mode: "offline",
            unlocked_at: now,
        },
        access_token: None,
    })
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CashierCard {
    pub id: String,
    pub display_name: String,
    pub initials: String,
    pub role_label: String,
    #[serde(default)]
    pub avatar_url: Option<String>,
}

impl From<crate::db::CashierDirectoryRow> for CashierCard {
    fn from(row: crate::db::CashierDirectoryRow) -> Self {
        Self {
            id: row.user_id,
            display_name: row.display_name,
            initials: row.initials,
            role_label: row.role_label,
            avatar_url: row.avatar_url,
        }
    }
}

/// The latest directory from the server, or the last directory saved for this branch when the server is down.
pub fn cashier_directory(db: &Db, config: &DesktopConfig) -> Result<Vec<CashierCard>, String> {
    let scope = directory_scope(config);
    match remote_cashiers(config) {
        Ok(cards) => {
            let rows = cards
                .iter()
                .map(|card| crate::db::CashierDirectoryRow {
                    user_id: card.id.clone(),
                    display_name: card.display_name.clone(),
                    initials: card.initials.clone(),
                    role_label: card.role_label.clone(),
                    avatar_url: card.avatar_url.clone(),
                })
                .collect::<Vec<_>>();
            db.replace_cashier_directory(&scope, &rows)?;
            let _ = sync_cashier_verifiers(db, config);
            Ok(cards)
        }
        Err(true) => Ok(db.list_cashier_directory(&scope)?.into_iter().map(CashierCard::from).collect()),
        Err(false) => Err("The register could not load cashiers.".into()),
    }
}

fn directory_scope(config: &DesktopConfig) -> String {
    if config.store_id.is_empty() {
        "unscoped".into()
    } else {
        config.store_id.clone()
    }
}

fn remote_cashiers(config: &DesktopConfig) -> Result<Vec<CashierCard>, bool> {
    let Ok(client) = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(8))
        .build()
    else {
        return Err(true);
    };
    let Ok(response) = client
        .get(format!("{}/api/v1/auth/cashiers", config.api_base_url))
        .headers(config.auth_headers())
        .send()
    else {
        return Err(true);
    };
    let status = response.status();
    if status.as_u16() == 200 {
        return response.json::<Vec<CashierCard>>().map_err(|_| true);
    }
    Err(status.is_server_error())
}

fn remote_unlock(config: &DesktopConfig, user_id: &str, pin: &str) -> Remote {
    let Ok(client) = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(8))
        .build()
    else {
        return Remote::Unreachable;
    };
    let Ok(response) = client
        .post(format!("{}/api/v1/auth/unlock", config.api_base_url))
        .headers(config.auth_headers())
        .json(&serde_json::json!({ "user_id": user_id, "pin": pin }))
        .send()
    else {
        return Remote::Unreachable;
    };
    interpret(response)
}

fn remote_login(config: &DesktopConfig, username: &str, pin: &str) -> Remote {
    let Ok(client) = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(8))
        .build()
    else {
        return Remote::Unreachable;
    };
    let Ok(response) = client
        .post(format!("{}/api/v1/auth/login-pin", config.api_base_url))
        .headers(config.auth_headers())
        .json(&serde_json::json!({ "username": username, "pin": pin }))
        .send()
    else {
        return Remote::Unreachable;
    };
    interpret(response)
}

fn interpret(response: reqwest::blocking::Response) -> Remote {
    let status = response.status().as_u16();
    let Ok(body) = response.text() else {
        return Remote::Unreachable;
    };
    if status == 200 {
        return match serde_json::from_str::<TokenResponse>(&body) {
            Ok(parsed) => Remote::Accepted(parsed),
            Err(_) => Remote::Unreachable,
        };
    }
    if matches!(status, 401 | 403 | 422 | 423) {
        let message = serde_json::from_str::<ErrorBody>(&body)
            .map(|parsed| parsed.error.message)
            .unwrap_or_else(|_| "Unlock was refused.".into());
        return Remote::Refused { status, message };
    }
    Remote::Unreachable
}

/// Reads this cashier's permissions from the server. A missed call leaves the cached list unchanged.
pub fn account_permissions(config: &DesktopConfig, token: &str, user_id: &str) -> Result<Option<Vec<String>>, String> {
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(5))
        .build()
        .map_err(|err| err.to_string())?;
    let response = match client
        .get(format!("{}/api/v1/auth/me", config.api_base_url.trim_end_matches('/')))
        .headers(config.auth_headers())
        .header("Authorization", format!("Bearer {token}"))
        .send()
    {
        Ok(response) => response,
        Err(_) => return Ok(None),
    };
    if !response.status().is_success() {
        return Ok(None);
    }
    let body: serde_json::Value = match response.json() {
        Ok(body) => body,
        Err(_) => return Ok(None),
    };
    if body.get("id").and_then(|item| item.as_str()) != Some(user_id) {
        return Ok(None);
    }
    let Some(items) = body.get("permissions").and_then(|item| item.as_array()) else {
        return Ok(None);
    };
    Ok(Some(
        items
            .iter()
            .filter_map(|item| item.as_str().map(ToOwned::to_owned))
            .collect(),
    ))
}

pub(crate) fn hash_pin(pin: &str) -> Result<String, String> {
    let salt = SaltString::generate(&mut OsRng);
    Argon2::default()
        .hash_password(pin.as_bytes(), &salt)
        .map(|hash| hash.to_string())
        .map_err(|err| err.to_string())
}

#[cfg(test)]
pub(crate) fn tests_verify_pin(pin: &str, encoded: &str) -> bool {
    verify_pin(pin, encoded)
}

#[cfg(test)]
mod tests {
    use super::fresh_addons;

    #[test]
    fn a_stale_or_broken_cache_does_not_keep_add_on_access() {
        assert_eq!(fresh_addons("[\"gift_cards\"]", 1_000, 1_000 + 24 * 60 * 60 + 1), Vec::<String>::new());
        assert_eq!(fresh_addons("[\"gift_cards\"]", 1_000, 1_000 + 60), vec!["gift_cards".to_string()]);
        assert!(fresh_addons("not-json", 1_000, 1_000).is_empty());
    }

    #[test]
    fn five_wrong_pins_lock_the_local_cashier() {
        let path = std::env::temp_dir().join(format!("axiz-o7-lock-{}.db", std::process::id()));
        let _ = std::fs::remove_file(&path);
        let db = crate::db::Db::open(&path).unwrap();
        crate::staff::create_local(
            &db,
            crate::staff::NewStaff {
                actor_id: "manager".into(),
                actor_role: "Store Manager".into(),
                actor_store_id: "branch-a".into(),
                seat_limit: Some(5),
                seat_trusted: true,
                tenant_id: "tenant-a".into(),
                terminal_id: "till-a".into(),
                user_id: "cashier-local".into(),
                username: "new.cashier".into(),
                full_name: "New Cashier".into(),
                store_id: "branch-a".into(),
                role_name: "Cashier".into(),
                pin: "1357".into(),
                event_id: "event-lock".into(),
            },
        )
        .unwrap();
        assert!(super::finish_offline(&db, db.cached_user("new.cashier").unwrap().unwrap(), "1357").is_ok());
        for _ in 0..5 {
            let cached = db.cached_user("new.cashier").unwrap().unwrap();
            assert!(super::finish_offline(&db, cached, "0000").is_err());
        }
        let locked = super::finish_offline(&db, db.cached_user("new.cashier").unwrap().unwrap(), "1357");
        let Err(message) = locked else {
            panic!("a locked cashier was allowed in");
        };
        assert!(message.contains("Too many failed attempts"));
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn a_synced_scrypt_pin_unlocks_offline_without_a_prior_online_sign_in() {
        let path = std::env::temp_dir().join(format!("axiz-o7-sync-{}.db", std::process::id()));
        let _ = std::fs::remove_file(&path);
        let db = crate::db::Db::open(&path).unwrap();
        let encoded = "scrypt$00112233445566778899aabbccddeeff$9de2f8791a80046bf8fb9d6d1280be7829d2d602181373450149888af19475d6";
        db.set_local_meta("pin_salt", "test-pin-pepper-16chars").unwrap();
        db.replace_synced_staff(
            "branch-a",
            &[crate::db::SyncedStaff {
                user_id: "bilal".into(),
                username: "bilal".into(),
                full_name: "Bilal".into(),
                store_id: Some("branch-a".into()),
                role_name: "Cashier".into(),
                permissions: "[\"pos:access\"]".into(),
                pin_hash: encoded.into(),
                is_active: true,
                max_discount_bps: None,
            }],
            1,
        )
        .unwrap();
        let config = crate::sync::DesktopConfig {
            api_base_url: "https://example.invalid".into(),
            api_key: String::new(),
            device_id: "till-a".into(),
            store_id: "branch-a".into(),
            tenant_domain: String::new(),
            tenant_slug: String::new(),
        };
        assert!(super::offline_login_id(&db, &config, "bilal", "1357").is_ok());
        assert!(super::offline_login_id(&db, &config, "bilal", "0000").is_err());
        let Err(missing) = super::offline_login_id(&db, &config, "nobody", "1357") else {
            panic!("a cashier who was never synced was allowed in");
        };
        assert_eq!(missing, super::OFFLINE_QUIET);
        let _ = std::fs::remove_file(&path);
    }
}

#[cfg_attr(not(test), allow(dead_code))]
pub(crate) fn verify_pin(pin: &str, encoded: &str) -> bool {
    verify_cached_pin(pin, encoded, None)
}

fn verify_cached_pin(pin: &str, encoded: &str, pepper: Option<&str>) -> bool {
    if encoded.starts_with("$argon2") {
        return PasswordHash::new(encoded)
            .map(|parsed| Argon2::default().verify_password(pin.as_bytes(), &parsed).is_ok())
            .unwrap_or(false);
    }
    let Some(pepper) = pepper else {
        return false;
    };
    verify_scrypt_pin(pin, encoded, pepper)
}

/// Server PINs are `scrypt$salt$digest` of HMAC-SHA256(pepper, pin), matching the API.
fn verify_scrypt_pin(pin: &str, encoded: &str, pepper: &str) -> bool {
    let mut parts = encoded.split('$');
    if parts.next() != Some("scrypt") {
        return false;
    }
    let Some(salt_hex) = parts.next() else {
        return false;
    };
    let Some(digest_hex) = parts.next() else {
        return false;
    };
    if parts.next().is_some() {
        return false;
    }
    let Some(salt) = decode_hex(salt_hex) else {
        return false;
    };
    let Some(expected) = decode_hex(digest_hex) else {
        return false;
    };
    if expected.len() != 32 {
        return false;
    }
    let Ok(mut mac) = Hmac::<Sha256>::new_from_slice(pepper.as_bytes()) else {
        return false;
    };
    mac.update(pin.as_bytes());
    let peppered = encode_hex(&mac.finalize().into_bytes());
    let Ok(params) = scrypt::Params::new(14, 8, 1, 32) else {
        return false;
    };
    let mut out = [0u8; 32];
    if scrypt::scrypt(peppered.as_bytes(), &salt, &params, &mut out).is_err() {
        return false;
    }
    out.as_slice() == expected.as_slice()
}

fn decode_hex(value: &str) -> Option<Vec<u8>> {
    if value.len() % 2 != 0 {
        return None;
    }
    (0..value.len())
        .step_by(2)
        .map(|index| u8::from_str_radix(&value[index..index + 2], 16).ok())
        .collect()
}

fn encode_hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

#[derive(Deserialize)]
struct VerifierFeed {
    pin_salt: String,
    staff: Vec<VerifierRow>,
}

#[derive(Deserialize)]
struct VerifierRow {
    user_id: String,
    username: String,
    full_name: String,
    store_id: Option<String>,
    role_name: String,
    permissions: Vec<String>,
    pin_verifier: String,
    is_active: bool,
    max_discount_bps: Option<i64>,
}

/// Pulls every cashier for this branch, including the PIN verifier, so offline unlock does not wait for a first online sign-in.
pub fn sync_cashier_verifiers(db: &Db, config: &DesktopConfig) -> Result<(), String> {
    if config.api_base_url.is_empty() || config.api_base_url.contains("not-activated") {
        return Ok(());
    }
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(8))
        .build()
        .map_err(|err| err.to_string())?;
    let response = client
        .get(format!("{}/api/v1/auth/cashier-verifiers", config.api_base_url))
        .headers(config.auth_headers())
        .send()
        .map_err(|err| err.to_string())?;
    if !response.status().is_success() {
        return Err("The register could not refresh cashiers.".into());
    }
    let feed: VerifierFeed = response.json().map_err(|err| err.to_string())?;
    if !feed.pin_salt.is_empty() {
        db.set_local_meta("pin_salt", &feed.pin_salt)?;
    }
    let rows = feed
        .staff
        .into_iter()
        .filter(|row| row.pin_verifier.starts_with("scrypt$") || row.pin_verifier.starts_with("$argon2"))
        .map(|row| crate::db::SyncedStaff {
            user_id: row.user_id,
            username: row.username,
            full_name: row.full_name,
            store_id: row.store_id,
            role_name: row.role_name,
            permissions: serde_json::to_string(&row.permissions).unwrap_or_else(|_| "[]".into()),
            pin_hash: row.pin_verifier,
            is_active: row.is_active,
            max_discount_bps: row.max_discount_bps,
        })
        .collect::<Vec<_>>();
    db.replace_synced_staff(&config.store_id, &rows, now_secs())
}
