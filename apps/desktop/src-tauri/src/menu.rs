//! Cached copy of the business's menu modifiers so registers can sell modified items offline.

use std::time::Duration;

use rusqlite::{params, Connection, OptionalExtension};
use serde_json::Value;

use crate::db::Db;
use crate::sync::DesktopConfig;

pub fn migrate(conn: &Connection) -> Result<(), String> {
    conn.execute_batch(
        "CREATE TABLE IF NOT EXISTS menu_cache (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            body TEXT NOT NULL,
            fetched_at INTEGER NOT NULL
        );",
    )
    .map_err(|err| err.to_string())
}

fn fetch(config: &DesktopConfig) -> Result<Value, String> {
    let response = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(6))
        .build()
        .map_err(|err| err.to_string())?
        .get(format!("{}/api/v1/menu/register", config.api_base_url))
        .headers(config.auth_headers())
        .send()
        .map_err(|err| err.to_string())?;
    let status = response.status();
    if status.as_u16() == 403 {
        // Module switched off for this business: an empty menu, not an error.
        return Ok(serde_json::json!({ "groups": [], "products": {} }));
    }
    if !status.is_success() {
        return Err(format!("Menu request failed ({}).", status.as_u16()));
    }
    response.json().map_err(|err| err.to_string())
}

/// The live menu when the API answers, else the last cached one, else an empty menu.
pub fn refresh(db: &Db, config: &DesktopConfig) -> Result<Value, String> {
    match fetch(config) {
        Ok(menu) => {
            let body = menu.to_string();
            db.transaction(|tx| {
                tx.execute(
                    "INSERT INTO menu_cache (id, body, fetched_at) VALUES (1, ?1, strftime('%s','now'))
                     ON CONFLICT(id) DO UPDATE SET body = excluded.body, fetched_at = excluded.fetched_at",
                    params![body],
                )
                .map_err(|err| err.to_string())?;
                Ok(())
            })?;
            Ok(menu)
        }
        Err(_) => {
            let cached: Option<String> = db.read(|conn| {
                conn.query_row("SELECT body FROM menu_cache WHERE id = 1", [], |row| {
                    row.get(0)
                })
                .optional()
                .map_err(|err| err.to_string())
            })?;
            let cached = cached
                .and_then(|raw| serde_json::from_str::<Value>(&raw).ok())
                .unwrap_or_else(|| serde_json::json!({ "groups": [], "products": {} }));
            Ok(overlay_price_options(db, cached))
        }
    }
}

/// Older menu documents omit priced options. The signed register_menu rows fill that gap offline.
fn overlay_price_options(db: &Db, mut menu: Value) -> Value {
    if menu.get("price_options").is_some() {
        return menu;
    }
    let Ok(payloads) = db.config_payloads("menu") else {
        return menu;
    };
    let mut grouped = serde_json::Map::new();
    for text in payloads {
        let Ok(value) = serde_json::from_str::<Value>(&text) else {
            continue;
        };
        if value.get("kind").and_then(|item| item.as_str()) != Some("price_option") {
            continue;
        }
        if !value.get("is_active").and_then(|item| item.as_bool()).unwrap_or(true) {
            continue;
        }
        let Some(product_id) = value.get("product_id").and_then(|item| item.as_str()) else {
            continue;
        };
        let list = grouped
            .entry(product_id.to_string())
            .or_insert_with(|| Value::Array(Vec::new()));
        if let Some(rows) = list.as_array_mut() {
            rows.push(value);
        }
    }
    grouped.retain(|_, value| value.as_array().is_some_and(|rows| rows.len() >= 2));
    if grouped.is_empty() {
        return menu;
    }
    if let Some(object) = menu.as_object_mut() {
        object.insert("price_options".to_string(), Value::Object(grouped));
    }
    menu
}

#[tauri::command]
pub async fn refresh_menu(state: tauri::State<'_, crate::AppState>) -> Result<Value, String> {
    let db = state.db.clone();
    let config = state.config.clone();
    tauri::async_runtime::spawn_blocking(move || refresh(&db, &config))
        .await
        .map_err(|err| err.to_string())?
}
