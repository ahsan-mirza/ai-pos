use std::time::{Duration, SystemTime, UNIX_EPOCH};

use argon2::password_hash::rand_core::OsRng;
use argon2::password_hash::{PasswordHash, PasswordHasher, PasswordVerifier, SaltString};
use argon2::Argon2;
use serde::{Deserialize, Serialize};

use crate::db::{CachedUser, Db};
use crate::sync::DesktopConfig;

const LOCAL_MAX_ATTEMPTS: i64 = 5;
const LOCAL_LOCKOUT_SECS: i64 = 5 * 60;
const POS_ACCESS: &str = "pos:access";
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
        return Err(
            "The server is unreachable and this cashier has not unlocked this register online yet."
                .into(),
        );
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
        return Err(
            "The server is unreachable and this cashier has not unlocked this register online yet."
                .into(),
        );
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
    if !verify_pin(pin, &cached.pin_hash) {
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
}

pub(crate) fn verify_pin(pin: &str, encoded: &str) -> bool {
    PasswordHash::new(encoded)
        .map(|parsed| {
            Argon2::default()
                .verify_password(pin.as_bytes(), &parsed)
                .is_ok()
        })
        .unwrap_or(false)
}
