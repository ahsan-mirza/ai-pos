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
/// Quiet period after launch so the register can open before the first lookup.
const FIRST_CHECK: Duration = Duration::from_secs(20);
/// How often an open register looks again. The request itself is not shown.
const CHECK_EVERY: Duration = Duration::from_secs(15 * 60);

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

/// Looks up the published installer for as long as this window stays open.
/// A newer version is announced once; the lookup itself never surfaces in the register.
pub fn watch(app: AppHandle, config: DesktopConfig) {
    std::thread::Builder::new()
        .name("update-check".into())
        .spawn(move || {
            let mut announced = String::new();
            std::thread::sleep(FIRST_CHECK);
            loop {
                let current = app.package_info().version.to_string();
                if let Some(update) = tauri::async_runtime::block_on(check(&config, &current)) {
                    if announced != update.version {
                        announced = update.version.clone();
                        let _ = app.emit("app-update-available", update);
                    }
                }
                std::thread::sleep(CHECK_EVERY);
            }
        })
        .ok();
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
    let path = std::env::temp_dir().join(format!("AI-POS-Setup-{}.exe", update.version));
    // Close the file before starting it. Windows will not run an exe that this process still has open.
    {
        let mut file = std::fs::File::create(&path).map_err(|err| format!("Could not save the installer: {err}"))?;
        file.write_all(&bytes).map_err(|err| format!("Could not save the installer: {err}"))?;
        file.sync_all().map_err(|err| format!("Could not save the installer: {err}"))?;
    }
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
        // A scanner can briefly lock a newly written exe. Sharing error 32 clears once it lets go.
        let mut locked = String::new();
        for attempt in 0..8 {
            match std::process::Command::new(path)
                .arg("/S")
                .creation_flags(DETACHED_PROCESS)
                .spawn()
            {
                Ok(_) => return Ok(()),
                Err(err) if err.raw_os_error() == Some(32) && attempt + 1 < 8 => {
                    locked = err.to_string();
                    std::thread::sleep(Duration::from_millis(250));
                }
                Err(err) => return Err(format!("Could not start the installer: {err}")),
            }
        }
        return Err(format!("Could not start the installer: {locked}"));
    }
    #[cfg(not(windows))]
    {
        let _ = path;
        Err("POS updates install on Windows.".into())
    }
}
