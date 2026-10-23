//! Asks the store's API whether a newer Windows installer is published.
//! A failed or timed-out request means the till is offline, so the installed version keeps running.

use std::io::Write;
use std::time::Duration;

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use tauri::{AppHandle, Emitter};

use crate::sync::DesktopConfig;

const CHECK_TIMEOUT: Duration = Duration::from_secs(3);
const DOWNLOAD_TIMEOUT: Duration = Duration::from_secs(600);

#[derive(Debug, Serialize, Clone)]
pub struct AppUpdate {
    pub version: String,
    pub notes: Option<String>,
    pub sha256: String,
    pub url: String,
}

#[derive(Deserialize)]
struct Feed {
    version: String,
    notes: Option<String>,
    sha256: String,
    path: String,
}

#[derive(Serialize, Clone)]
struct Progress {
    percent: u8,
}

fn parts(version: &str) -> [u64; 3] {
    let mut numbers = [0u64; 3];
    for (index, piece) in version.split('.').take(3).enumerate() {
        numbers[index] = piece.parse().unwrap_or(0);
    }
    numbers
}

fn is_newer(current: &str, offered: &str) -> bool {
    parts(offered) > parts(current)
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

async fn feed(config: &DesktopConfig) -> Result<Option<AppUpdate>, String> {
    if config.api_base_url.contains("not-activated") {
        return Ok(None);
    }
    let client = reqwest::Client::builder()
        .timeout(CHECK_TIMEOUT)
        .build()
        .map_err(|err| err.to_string())?;
    let response = client
        .get(format!("{}/api/v1/downloads/latest.json", config.api_base_url))
        .send()
        .await
        .map_err(|err| err.to_string())?;
    if response.status().as_u16() == 404 {
        return Ok(None);
    }
    if !response.status().is_success() {
        return Err(format!("Update check failed ({})", response.status()));
    }
    let body: Feed = response.json().await.map_err(|err| err.to_string())?;
    let path = body.path.trim();
    if path.is_empty() || !path.starts_with('/') {
        return Err("The update feed did not include a download path.".into());
    }
    Ok(Some(AppUpdate {
        version: body.version,
        notes: body.notes.filter(|notes| !notes.trim().is_empty()),
        sha256: body.sha256.to_ascii_lowercase(),
        url: format!("{}{path}", config.api_base_url),
    }))
}

pub async fn check(config: &DesktopConfig, current: &str) -> Option<AppUpdate> {
    match feed(config).await {
        Ok(Some(update)) if is_newer(current, &update.version) => Some(update),
        Ok(_) => None,
        Err(message) => {
            eprintln!("ai-pos: update check skipped: {message}");
            None
        }
    }
}

pub async fn install(app: &AppHandle, config: &DesktopConfig, current: &str) -> Result<(), String> {
    let Some(update) = check(config, current).await else {
        return Err("No update is available.".into());
    };
    let client = reqwest::Client::builder()
        .timeout(DOWNLOAD_TIMEOUT)
        .build()
        .map_err(|err| err.to_string())?;
    let mut response = client.get(&update.url).send().await.map_err(|err| err.to_string())?;
    if !response.status().is_success() {
        return Err(format!("Download failed ({})", response.status()));
    }
    let total = response.content_length().unwrap_or(0);
    let mut received: u64 = 0;
    let mut bytes = Vec::new();
    while let Some(chunk) = response.chunk().await.map_err(|err| err.to_string())? {
        received += chunk.len() as u64;
        bytes.extend_from_slice(&chunk);
        let percent = if total == 0 { 0 } else { ((received * 100) / total).min(100) as u8 };
        let _ = app.emit("update-progress", Progress { percent });
    }
    let digest = hex(&Sha256::digest(&bytes));
    if digest != update.sha256 {
        return Err("The downloaded installer did not match the published checksum.".into());
    }
    let path = std::env::temp_dir().join("AI-POS-Setup-latest.exe");
    let mut file = std::fs::File::create(&path).map_err(|err| err.to_string())?;
    file.write_all(&bytes).map_err(|err| err.to_string())?;
    file.sync_all().map_err(|err| err.to_string())?;
    launch_installer(&path)?;
    app.exit(0);
    Ok(())
}

fn launch_installer(path: &std::path::Path) -> Result<(), String> {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        // Detach so the silent installer keeps running after this process exits.
        const DETACHED_PROCESS: u32 = 0x0000_0008;
        std::process::Command::new(path)
            .arg("/S")
            .creation_flags(DETACHED_PROCESS)
            .spawn()
            .map_err(|err| format!("Could not start the installer: {err}"))?;
        return Ok(());
    }
    #[cfg(not(windows))]
    {
        let _ = path;
        Err("POS updates install on Windows.".into())
    }
}
