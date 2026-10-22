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


///  Dummy 
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
}

#[derive(Deserialize)]
struct TokenResponse {
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
) -> Result<Session, String> {
    let username = username.trim().to_lowercase();
    if !(4..=6).contains(&pin.len()) || !pin.chars().all(|c| c.is_ascii_digit()) {
        return Err("PINs are 4 to 6 digits.".into());
    }
    match remote_login(config, &username, pin) {
        Remote::Accepted(response) => {
            let profile = CashierProfile {
                id: response.user.id,
                username: response.user.username,
                full_name: response.user.full_name,
                store_id: response.user.store_id,
                role_name: response.user.role.name,
                permissions: response.user.permissions,
                max_discount_bps: response.user.role.max_discount_bps,
            };
            db.upsert_cached_user(&profile, &hash_pin(pin)?, now_secs())?;
            Ok(Session {
                user: profile,
                mode: "online",
                unlocked_at: now_secs(),
            })
        }
        Remote::Refused { status, message } => {
            if status == 403 {
                db.remove_cached_user(&username)?;
            }
            Err(message)
        }
        Remote::Unreachable => offline_login(db, &username, pin),
    }
}

fn offline_login(db: &Db, username: &str, pin: &str) -> Result<Session, String> {
    let Some(cached) = db.cached_user(username)? else {
        return Err(
            "The server is unreachable and this cashier has not unlocked this register online yet."
                .into(),
        );
    };
    let now = now_secs();
    if cached.locked_until.is_some_and(|until| until > now) {
        return Err(
            "Too many failed attempts on this register. Try again in a few minutes.".into(),
        );
    }
    if !verify_pin(pin, &cached.pin_hash) {
        let attempts = cached.failed_attempts + 1;
        let locked_until = (attempts >= LOCAL_MAX_ATTEMPTS).then_some(now + LOCAL_LOCKOUT_SECS);
        db.record_cached_failure(
            username,
            if locked_until.is_some() { 0 } else { attempts },
            locked_until,
        )?;
        return Err("Invalid username or credentials.".into());
    }
    db.record_cached_failure(username, 0, None)?;
    let profile = cached_profile(cached)?;
    if !profile.permissions.iter().any(|item| item == POS_ACCESS) {
        return Err("This account cannot unlock a register.".into());
    }
    Ok(Session {
        user: profile,
        mode: "offline",
        unlocked_at: now,
    })
}

fn cached_profile(cached: CachedUser) -> Result<CashierProfile, String> {
    Ok(CashierProfile {
        id: cached.user_id,
        username: cached.username,
        full_name: cached.full_name,
        store_id: cached.store_id,
        role_name: cached.role_name,
        permissions: serde_json::from_str(&cached.permissions).map_err(|err| err.to_string())?,
        max_discount_bps: cached.max_discount_bps,
    })
}

fn remote_login(config: &DesktopConfig, username: &str, pin: &str) -> Remote {
    let Ok(client) = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(8))
        .build()
    else {
        return Remote::Unreachable;
    };
    let response = client
        .post(format!("{}/api/v1/auth/login-pin", config.api_base_url))
        .headers(config.auth_headers())
        .json(&serde_json::json!({ "username": username, "pin": pin }))
        .send();
    let Ok(response) = response else {
        return Remote::Unreachable;
    };
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

fn verify_pin(pin: &str, encoded: &str) -> bool {
    PasswordHash::new(encoded)
        .map(|parsed| {
            Argon2::default()
                .verify_password(pin.as_bytes(), &parsed)
                .is_ok()
        })
        .unwrap_or(false)
}
