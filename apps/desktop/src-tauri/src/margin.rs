use std::time::Duration;

use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};

use crate::db::Db;
use crate::sync::DesktopConfig;

/// Margin floors cached per branch so the register can stop a below-floor price while offline.
pub fn migrate(conn: &Connection) -> Result<(), String> {
    conn.execute_batch(
        "
        CREATE TABLE IF NOT EXISTS margin_floors (
            product_id TEXT PRIMARY KEY,
            floor_cents INTEGER NOT NULL,
            min_margin_bps INTEGER NOT NULL
        );
        ",
    )
    .map_err(|err| err.to_string())
}

#[derive(Clone, Serialize, Deserialize)]
pub struct FloorRow {
    pub product_id: String,
    pub floor_cents: i64,
    pub min_margin_bps: i64,
}

#[derive(Serialize)]
pub struct FloorSnapshot {
    pub floors: Vec<FloorRow>,
    pub source: &'static str,
}

fn cached(db: &Db) -> Result<Vec<FloorRow>, String> {
    db.read(|conn| {
        let mut statement = conn
            .prepare("SELECT product_id, floor_cents, min_margin_bps FROM margin_floors")
            .map_err(|err| err.to_string())?;
        let rows = statement
            .query_map([], |row| {
                Ok(FloorRow { product_id: row.get(0)?, floor_cents: row.get(1)?, min_margin_bps: row.get(2)? })
            })
            .map_err(|err| err.to_string())?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|err| err.to_string());
        rows
    })
}

pub fn refresh(db: &Db, config: &DesktopConfig) -> Result<FloorSnapshot, String> {
    let response = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(8))
        .build()
        .map_err(|err| err.to_string())?
        .get(format!("{}/api/v1/margin/floors", config.api_base_url))
        .query(&[("store_id", config.store_id.as_str())])
        .headers(config.auth_headers())
        .send();
    let rows: Vec<FloorRow> = match response {
        Ok(response) if response.status().is_success() => response.json().map_err(|err| err.to_string())?,
        _ => return Ok(FloorSnapshot { floors: cached(db)?, source: "cache" }),
    };
    db.transaction(|tx| {
        tx.execute("DELETE FROM margin_floors", []).map_err(|err| err.to_string())?;
        for row in &rows {
            tx.execute(
                "INSERT INTO margin_floors (product_id, floor_cents, min_margin_bps) VALUES (?1, ?2, ?3)",
                params![row.product_id, row.floor_cents, row.min_margin_bps],
            )
            .map_err(|err| err.to_string())?;
        }
        Ok(())
    })?;
    Ok(FloorSnapshot { floors: rows, source: "api" })
}
