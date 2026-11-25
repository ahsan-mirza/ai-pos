use std::time::Duration;

use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::db::Db;
use crate::sync::DesktopConfig;

pub fn migrate(conn: &Connection) -> Result<(), String> {
    conn.execute_batch(
        "
        CREATE TABLE IF NOT EXISTS business_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            currency TEXT NOT NULL,
            fetched_at INTEGER NOT NULL
        );
        ",
    )
    .map_err(|err| err.to_string())?;
    for column in ["tax_json", "profile_json", "receipt_json"] {
        let exists: bool = conn
            .prepare("SELECT 1 FROM pragma_table_info('business_settings') WHERE name = ?1")
            .and_then(|mut statement| statement.exists([column]))
            .map_err(|err| err.to_string())?;
        if !exists {
            conn.execute_batch(&format!(
                "ALTER TABLE business_settings ADD COLUMN {column} TEXT;"
            ))
            .map_err(|err| err.to_string())?;
        }
    }
    conn.execute_batch(
        "
        CREATE TABLE IF NOT EXISTS foreign_currencies (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            rate_micros INTEGER NOT NULL
        );
        ",
    )
    .map_err(|err| err.to_string())?;
    Ok(())
}

/// Accepted foreign currencies and their rate into the business currency, cached for offline cash tenders.
#[derive(Clone, Serialize, Deserialize)]
pub struct ForeignCurrency {
    pub code: String,
    pub name: String,
    pub rate_micros: i64,
}

#[derive(Deserialize)]
struct RemoteCurrency {
    code: String,
    name: String,
    is_active: bool,
    rate_micros: Option<i64>,
}

pub fn refresh_currencies(db: &Db, config: &DesktopConfig) -> Result<Vec<ForeignCurrency>, String> {
    let fetched = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(6))
        .build()
        .map_err(|err| err.to_string())?
        .get(format!("{}/api/v1/currencies", config.api_base_url))
        .headers(config.auth_headers())
        .send()
        .ok()
        .filter(|response| response.status().is_success())
        .and_then(|response| response.json::<Vec<RemoteCurrency>>().ok());
    if let Some(rows) = fetched {
        let usable: Vec<ForeignCurrency> = rows
            .into_iter()
            .filter_map(|row| {
                row.rate_micros
                    .filter(|_| row.is_active)
                    .map(|rate| ForeignCurrency {
                        code: row.code,
                        name: row.name,
                        rate_micros: rate,
                    })
            })
            .collect();
        db.transaction(|tx| {
            tx.execute("DELETE FROM foreign_currencies", [])
                .map_err(|err| err.to_string())?;
            for row in &usable {
                tx.execute(
                    "INSERT INTO foreign_currencies (code, name, rate_micros) VALUES (?1, ?2, ?3)",
                    params![row.code, row.name, row.rate_micros],
                )
                .map_err(|err| err.to_string())?;
            }
            Ok(())
        })?;
        return Ok(usable);
    }
    db.read(|conn| {
        let mut statement = conn
            .prepare("SELECT code, name, rate_micros FROM foreign_currencies ORDER BY code")
            .map_err(|err| err.to_string())?;
        let rows = statement
            .query_map([], |row| {
                Ok(ForeignCurrency {
                    code: row.get(0)?,
                    name: row.get(1)?,
                    rate_micros: row.get(2)?,
                })
            })
            .map_err(|err| err.to_string())?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|err| err.to_string());
        rows
    })
}

#[derive(Deserialize)]
struct RemoteSettings {
    currency: String,
    #[serde(default)]
    vat_registered: bool,
    #[serde(default)]
    prices_include_vat: bool,
    #[serde(default = "standard_rate")]
    standard_rate_bps: i64,
    #[serde(default)]
    trn: Option<String>,
    #[serde(default)]
    legal_name: Option<String>,
    #[serde(default)]
    legal_name_ar: Option<String>,
    #[serde(default)]
    tax_authority: Option<String>,
    #[serde(default)]
    tax_configuration_required: bool,
    #[serde(default)]
    business_profile: Option<String>,
    #[serde(default)]
    capabilities: Option<Vec<String>>,
    #[serde(default)]
    planned_capabilities: Option<Vec<String>>,
    /// Per-module configuration (scale labels, service charge, kitchen timers), cached with the profile.
    #[serde(default)]
    module_settings: Option<Value>,
    /// Till rules (discount reasons and limits, gift cards, returns policy), cached so they hold offline.
    #[serde(default)]
    pos_policy: Option<Value>,
    /// A self-service store before Go live; the register shows a "Practice mode" pill.
    #[serde(default)]
    practice_mode: bool,
    #[serde(default)]
    entitlement_revision: i64,
    #[serde(default)]
    purchased_capabilities: Option<Vec<String>>,
    #[serde(default)]
    entitlement_until: Option<String>,
    /// Canonical tenant store code. Empty on a server that does not name the tenant.
    #[serde(default)]
    store_code: String,
    /// Last change on the business-settings row. Absent means the page must not invent a time.
    #[serde(default)]
    updated_at: Option<String>,
    #[serde(default)]
    updated_by_name: Option<String>,
    #[serde(default)]
    country: Option<String>,
    #[serde(default)]
    location: Option<String>,
    /// IANA zone used to display the saved instant. The stored instant stays UTC.
    #[serde(default = "default_timezone")]
    timezone: String,
}

fn default_timezone() -> String {
    "Asia/Dubai".into()
}

fn revision_of(value: &Value) -> i64 {
    value
        .get("entitlement_revision")
        .and_then(Value::as_i64)
        .unwrap_or(0)
}

/// True when the copy already on this register is newer than the response just fetched.
fn keep_stored_revision(stored_revision: i64, incoming_revision: i64) -> bool {
    stored_revision > incoming_revision && stored_revision > 0
}

fn tax_document(body: &RemoteSettings) -> Value {
    serde_json::json!({
        "enforced": body.vat_registered,
        "prices_include_vat": body.prices_include_vat,
        "standard_rate_bps": body.standard_rate_bps,
        "trn": body.trn,
        "legal_name": body.legal_name,
        "legal_name_ar": body.legal_name_ar,
        "tax_authority": body.tax_authority.clone().unwrap_or_else(|| "fta".into()),
        "tax_configuration_required": body.tax_configuration_required,
        "updated_at": body.updated_at,
        "updated_by_name": body.updated_by_name,
        "country": body.country,
        "location": body.location,
        "timezone": body.timezone,
        "entitlement_revision": body.entitlement_revision,
    })
}

fn standard_rate() -> i64 {
    500
}

/// `currency` is `None` only when the register has never reached the API; callers fall back to the seed catalog.
/// `tax` is the business VAT policy plus the TRN and legal names printed on tax invoices.
/// `profile` is the business type and its enabled modules, cached so module gating holds offline. `None` means the
/// API never sent one, and the register keeps every module on.
/// `receipt` is the receipt branding plus this branch's address and phone (GET /settings/receipt), cached so
/// slips printed offline still carry the logo and footer.
#[derive(Serialize)]
pub struct CurrencySnapshot {
    currency: Option<String>,
    tax: Option<Value>,
    profile: Option<Value>,
    receipt: Option<Value>,
    source: &'static str,
    message: Option<String>,
}

type CachedRow = (String, Option<String>, Option<String>, Option<String>);

/// The currency last fetched from head office. `None` until this register has reached the API once.
pub fn cached_currency(db: &Db) -> Result<Option<String>, String> {
    Ok(cached(db)?.map(|(currency, _, _, _)| currency))
}

fn cached(db: &Db) -> Result<Option<CachedRow>, String> {
    db.read(|conn| {
        conn.query_row(
            "SELECT currency, tax_json, profile_json, receipt_json FROM business_settings WHERE id = 1",
            [],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
        )
        .optional()
        .map_err(|err| err.to_string())
    })
}

fn parse(raw: Option<&str>) -> Option<Value> {
    raw.and_then(|raw| serde_json::from_str(raw).ok())
}

fn profile_tenant(value: &Value) -> String {
    value
        .get("tenant_id")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim()
        .to_string()
}

pub fn refresh(db: &Db, config: &DesktopConfig) -> Result<CurrencySnapshot, String> {
    let pending = db.pending_count().ok();
    match fetch(config, pending) {
        Ok((currency, tax, mut profile)) => {
            // A failed receipt fetch keeps the last branding rather than printing unbranded slips.
            let fetched_receipt = fetch_receipt(config).ok();
            let mut accept_profile = true;
            if let Some(incoming) = profile.as_ref() {
                let incoming_tenant = incoming
                    .get("tenant_id")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .trim();
                let same_tenant = !config.tenant_slug.is_empty() && incoming_tenant == config.tenant_slug;
                if !same_tenant {
                    accept_profile = false;
                    profile = cached(db)?.and_then(|(_, _, raw, _)| parse(raw.as_deref())).filter(|stored| {
                        profile_tenant(stored) == config.tenant_slug || profile_tenant(stored).is_empty()
                    });
                } else {
                    let incoming_revision = incoming
                        .get("entitlement_revision")
                        .and_then(Value::as_i64)
                        .unwrap_or(0);
                    if let Some((_, _, cached_profile, _)) = cached(db)? {
                        let stored = parse(cached_profile.as_deref());
                        let stored_tenant = stored.as_ref().map(profile_tenant).unwrap_or_default();
                        let stored_revision = stored
                            .as_ref()
                            .and_then(|value| value.get("entitlement_revision"))
                            .and_then(Value::as_i64)
                            .unwrap_or(0);
                        if stored_tenant == config.tenant_slug
                            && keep_stored_revision(stored_revision, incoming_revision)
                        {
                            profile = stored;
                        }
                    }
                }
            }
            let tax = {
                let stored = cached(db)?.and_then(|(_, raw, _, _)| parse(raw.as_deref()));
                let stored_profile = cached(db)?.and_then(|(_, _, raw, _)| parse(raw.as_deref()));
                let stored_tenant = stored_profile.as_ref().map(profile_tenant).unwrap_or_default();
                if let Some(stored) = stored {
                    if !config.tenant_slug.is_empty()
                        && stored_tenant == config.tenant_slug
                        && keep_stored_revision(revision_of(&stored), revision_of(&tax))
                    {
                        stored
                    } else {
                        tax
                    }
                } else {
                    tax
                }
            };
            let tax_json = tax.to_string();
            let profile_json = if accept_profile {
                profile.as_ref().map(Value::to_string)
            } else {
                cached(db)?.and_then(|(_, _, raw, _)| raw)
            };
            let receipt_json = fetched_receipt.as_ref().map(Value::to_string);
            db.transaction(|tx| {
                tx.execute(
                    "INSERT INTO business_settings (id, currency, fetched_at, tax_json, profile_json, receipt_json)
                     VALUES (1, ?1, strftime('%s','now'), ?2, ?3, ?4)
                     ON CONFLICT(id) DO UPDATE SET currency = excluded.currency, fetched_at = excluded.fetched_at,
                        tax_json = excluded.tax_json, profile_json = excluded.profile_json,
                        receipt_json = COALESCE(excluded.receipt_json, business_settings.receipt_json)",
                    params![currency, tax_json, profile_json, receipt_json],
                )
                .map_err(|err| err.to_string())?;
                Ok(())
            })?;
            let receipt = match fetched_receipt {
                Some(receipt) => Some(receipt),
                None => cached(db)?.and_then(|(_, _, _, raw)| parse(raw.as_deref())),
            };
            Ok(CurrencySnapshot {
                currency: Some(currency),
                tax: Some(tax),
                profile,
                receipt,
                source: "api",
                message: None,
            })
        }
        Err(reason) => {
            let cached = cached(db)?;
            let tax = parse(cached.as_ref().and_then(|(_, raw, _, _)| raw.as_deref()));
            let profile = parse(cached.as_ref().and_then(|(_, _, raw, _)| raw.as_deref()));
            let receipt = parse(cached.as_ref().and_then(|(_, _, _, raw)| raw.as_deref()));
            Ok(CurrencySnapshot {
                source: if cached.is_some() { "cache" } else { "seed" },
                currency: cached.map(|(currency, _, _, _)| currency),
                tax,
                profile,
                receipt,
                message: Some(reason),
            })
        }
    }
}

fn fetch_receipt(config: &DesktopConfig) -> Result<Value, String> {
    let mut url = format!("{}/api/v1/settings/receipt", config.api_base_url);
    if !config.store_id.is_empty() {
        url.push_str(&format!("?store_id={}", config.store_id));
    }
    let response = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(6))
        .build()
        .map_err(|err| err.to_string())?
        .get(url)
        .headers(config.auth_headers())
        .send()
        .map_err(|err| err.to_string())?;
    if !response.status().is_success() {
        return Err(format!(
            "Receipt settings request failed ({}).",
            response.status().as_u16()
        ));
    }
    response.json::<Value>().map_err(|err| err.to_string())
}

fn fetch(config: &DesktopConfig, pending: Option<i64>) -> Result<(String, Value, Option<Value>), String> {
    let mut request = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(6))
        .build()
        .map_err(|err| err.to_string())?
        .get(format!("{}/api/v1/settings", config.api_base_url))
        .headers(config.auth_headers());
    if let Some(count) = pending.filter(|count| *count >= 0) {
        request = request.header("X-Pending-Sales", count.to_string());
    }
    let response = request.send().map_err(|err| err.to_string())?;
    let status = response.status();
    if !status.is_success() {
        return Err(format!("Settings request failed ({}).", status.as_u16()));
    }
    let body: RemoteSettings = response.json().map_err(|err| err.to_string())?;
    let code = body.currency.trim().to_ascii_uppercase();
    if code.len() != 3 || !code.chars().all(|c| c.is_ascii_uppercase()) {
        return Err("The API returned an invalid currency code.".into());
    }
    let tax = tax_document(&body);
    let profile = body.capabilities.as_ref().map(|capabilities| {
        serde_json::json!({
            "tenant_id": body.store_code,
            "business_profile": body.business_profile,
            "capabilities": capabilities,
            "planned_capabilities": body.planned_capabilities.clone().unwrap_or_default(),
            "module_settings": body.module_settings,
            "pos_policy": body.pos_policy,
            "practice_mode": body.practice_mode,
            "entitlement_revision": body.entitlement_revision,
            "purchased_capabilities": body.purchased_capabilities.clone().unwrap_or_default(),
            "entitlement_until": body.entitlement_until,
        })
    });
    Ok((code, tax, profile))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn decoded(body: serde_json::Value) -> RemoteSettings {
        serde_json::from_value(body).unwrap()
    }

    #[test]
    fn tax_document_keeps_the_saved_timestamp_actor_country_and_location() {
        let tax = tax_document(&decoded(serde_json::json!({
            "currency": "AED",
            "updated_at": "2026-11-22T20:15:00Z",
            "updated_by_name": "Portion Owner",
            "country": "AE",
            "location": "Deira",
            "timezone": "Asia/Dubai",
            "entitlement_revision": 11,
            "legal_name": "Portion Trading",
        })));
        assert_eq!(tax["updated_at"], "2026-11-22T20:15:00Z");
        assert_eq!(tax["updated_by_name"], "Portion Owner");
        assert_eq!(tax["country"], "AE");
        assert_eq!(tax["location"], "Deira");
        assert_eq!(tax["timezone"], "Asia/Dubai");
        assert_eq!(tax["entitlement_revision"], 11);
        assert_eq!(tax["legal_name"], "Portion Trading");
    }

    #[test]
    fn a_missing_timestamp_stays_null_and_an_invalid_one_is_not_replaced() {
        let missing = tax_document(&decoded(serde_json::json!({ "currency": "USD" })));
        assert!(missing["updated_at"].is_null());
        assert!(missing["updated_by_name"].is_null());
        assert!(missing["country"].is_null());
        assert!(missing["location"].is_null());
        assert_eq!(missing["timezone"], "Asia/Dubai");
        let invalid = tax_document(&decoded(serde_json::json!({
            "currency": "USD",
            "updated_at": "not-a-time",
        })));
        assert_eq!(invalid["updated_at"], "not-a-time");
    }

    #[test]
    fn an_older_snapshot_does_not_replace_a_newer_revision() {
        assert!(keep_stored_revision(11, 10));
        assert!(!keep_stored_revision(10, 11));
        assert!(!keep_stored_revision(10, 10));
        assert!(!keep_stored_revision(0, 0));
    }
}
