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
struct TokenResponse {
    #[serde(default)]
    access_token: String,
    user: RemoteUser,
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

/// Online first: the API is the source of truth for credentials. When it cannot be reached, the PIN is
/// checked against the Argon2 verifier cached on this register after the cashier's last online unlock.
pub fn pin_login(
    db: &Db,
    config: &DesktopConfig,
    username: &str,
    pin: &str,
) -> Result<PinUnlock, String> {
    let username = username.trim().to_lowercase();
    if !(4..=6).contains(&pin.len()) || !pin.chars().all(|c| c.is_ascii_digit()) {
        return Err("PINs are 4 to 6 digits.".into());
    }
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
    if !(4..=6).contains(&pin.len()) || !pin.chars().all(|c| c.is_ascii_digit()) {
        return Err("PINs are 4 to 6 digits.".into());
    }
    match remote_unlock(config, user_id, pin) {
        Remote::Accepted(response) => accept_remote(db, response, pin),
        Remote::Refused { message, .. } => Err(message),
        Remote::Unreachable => offline_login_id(db, config, user_id, pin),
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

fn hash_pin(pin: &str) -> Result<String, String> {
    let salt = SaltString::generate(&mut OsRng);
    Argon2::default()
        .hash_password(pin.as_bytes(), &salt)
        .map(|hash| hash.to_string())
        .map_err(|err| err.to_string())
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
}

fn verify_pin(pin: &str, encoded: &str) -> bool {
    PasswordHash::new(encoded)
        .map(|parsed| {
            Argon2::default()
                .verify_password(pin.as_bytes(), &parsed)
                .is_ok()
        })
        .unwrap_or(false)
}
