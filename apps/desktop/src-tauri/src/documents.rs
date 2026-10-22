use std::time::Duration;

use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};

use crate::db::Db;
use crate::sync::DesktopConfig;

/// Offline document numbering. The API tells a registered register its series prefixes and the last
/// number it has seen; the register then numbers invoices, credit notes, and Z reports locally.
pub fn migrate(conn: &Connection) -> Result<(), String> {
    conn.execute_batch(
        "
        CREATE TABLE IF NOT EXISTS document_series (
            doc_type TEXT PRIMARY KEY,
            prefix TEXT NOT NULL,
            next_value INTEGER NOT NULL
        );
        ",
    )
    .map_err(|err| err.to_string())
}

#[derive(Deserialize)]
struct RemoteSeries {
    doc_type: String,
    prefix: String,
    last_value: i64,
}

#[derive(Deserialize)]
struct RemoteDevice {
    code: String,
    series: Vec<RemoteSeries>,
}

#[derive(Serialize)]
pub struct SeriesStatus {
    pub registered: bool,
    pub device_code: Option<String>,
    pub message: Option<String>,
}

pub fn refresh(db: &Db, config: &DesktopConfig) -> Result<SeriesStatus, String> {
    let response = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(6))
        .build()
        .map_err(|err| err.to_string())?
        .get(format!("{}/api/v1/devices/me", config.api_base_url))
        .headers(config.auth_headers())
        .send();
    let response = match response {
        Ok(response) => response,
        Err(err) => {
            return Ok(SeriesStatus {
                registered: has_series(db)?,
                device_code: None,
                message: Some(format!("Offline: {err}")),
            })
        }
    };
    if response.status().as_u16() == 404 {
        return Ok(SeriesStatus {
            registered: false,
            device_code: None,
            message: Some("Shared API key: the API numbers this register's invoices.".into()),
        });
    }
    if !response.status().is_success() {
        return Ok(SeriesStatus {
            registered: has_series(db)?,
            device_code: None,
            message: Some(format!(
                "Series refresh failed ({}).",
                response.status().as_u16()
            )),
        });
    }
    let device: RemoteDevice = response.json().map_err(|err| err.to_string())?;
    db.transaction(|tx| {
        for series in &device.series {
            tx.execute(
                "INSERT INTO document_series (doc_type, prefix, next_value) VALUES (?1, ?2, ?3)
                 ON CONFLICT(doc_type) DO UPDATE SET prefix = excluded.prefix,
                    next_value = MAX(document_series.next_value, excluded.next_value)",
                params![series.doc_type, series.prefix, series.last_value + 1],
            )
            .map_err(|err| err.to_string())?;
        }
        Ok(())
    })?;
    Ok(SeriesStatus {
        registered: true,
        device_code: Some(device.code),
        message: None,
    })
}

fn has_series(db: &Db) -> Result<bool, String> {
    db.read(|conn| {
        conn.query_row("SELECT COUNT(*) FROM document_series", [], |row| {
            row.get::<_, i64>(0)
        })
        .map(|count| count > 0)
        .map_err(|err| err.to_string())
    })
}

/// Takes the next number in a series, or None when this register has no series (shared key).
pub fn next_number(db: &Db, doc_type: &str) -> Result<Option<String>, String> {
    db.transaction(|tx| {
        let row: Option<(String, i64)> = tx
            .query_row(
                "SELECT prefix, next_value FROM document_series WHERE doc_type = ?1",
                params![doc_type],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .optional()
            .map_err(|err| err.to_string())?;
        let Some((prefix, value)) = row else {
            return Ok(None);
        };
        tx.execute(
            "UPDATE document_series SET next_value = next_value + 1 WHERE doc_type = ?1",
            params![doc_type],
        )
        .map_err(|err| err.to_string())?;
        Ok(Some(format!("{prefix}-{value:06}")))
    })
}
