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

pub fn refresh(db: &Db, config: &DesktopConfig) -> Result<CurrencySnapshot, String> {
    match fetch(config) {
        Ok((currency, tax, profile)) => {
            // A failed receipt fetch keeps the last branding rather than printing unbranded slips.
            let fetched_receipt = fetch_receipt(config).ok();
            let tax_json = tax.to_string();
            let profile_json = profile.as_ref().map(Value::to_string);
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

fn fetch(config: &DesktopConfig) -> Result<(String, Value, Option<Value>), String> {
    let response = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(6))
        .build()
        .map_err(|err| err.to_string())?
        .get(format!("{}/api/v1/settings", config.api_base_url))
        .headers(config.auth_headers())
        .send()
        .map_err(|err| err.to_string())?;
    let status = response.status();
    if !status.is_success() {
        return Err(format!("Settings request failed ({}).", status.as_u16()));
    }
    let body: RemoteSettings = response.json().map_err(|err| err.to_string())?;
    let code = body.currency.trim().to_ascii_uppercase();
    if code.len() != 3 || !code.chars().all(|c| c.is_ascii_uppercase()) {
        return Err("The API returned an invalid currency code.".into());
    }
    let tax = serde_json::json!({
        "enforced": body.vat_registered,
        "prices_include_vat": body.prices_include_vat,
        "standard_rate_bps": body.standard_rate_bps,
        "trn": body.trn,
        "legal_name": body.legal_name,
        "legal_name_ar": body.legal_name_ar,
        "tax_authority": body.tax_authority.unwrap_or_else(|| "fta".into()),
    });
    let profile = body.capabilities.map(|capabilities| {
        serde_json::json!({
            "business_profile": body.business_profile,
            "capabilities": capabilities,
            "planned_capabilities": body.planned_capabilities.unwrap_or_default(),
            "module_settings": body.module_settings,
            "pos_policy": body.pos_policy,
            "practice_mode": body.practice_mode,
        })
    });
    Ok((code, tax, profile))
}
