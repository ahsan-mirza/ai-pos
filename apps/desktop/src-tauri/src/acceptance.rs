//! Fail-closed checks for the pharmacy acceptance register.
//!
//! The ordinary developer and production builds compile this out of the startup path.
//! An acceptance build refuses to open a database unless its identifier, data directory,
//! and API address are the dedicated acceptance values.

use std::path::{Path, PathBuf};

use crate::terminal;

pub const IDENTIFIER: &str = env!("POS_ACCEPTANCE_IDENTIFIER");
const API_BASE: &str = env!("POS_ACCEPTANCE_API_BASE");
const DEVELOPER_IDENTIFIERS: [&str; 2] = ["com.aipos.desktop", "com.aipos.desktop.dev"];

pub fn enabled() -> bool {
    env!("POS_ACCEPTANCE_BUILD") == "1"
}

pub fn assert_isolated(identifier: &str, directory: &Path) -> Result<(), String> {
    if !enabled() {
        return Ok(());
    }
    if identifier != IDENTIFIER {
        return Err("Acceptance build is not using the acceptance application identifier.".into());
    }
    let Some(appdata) = std::env::var_os("APPDATA") else {
        return Err("Acceptance build cannot see APPDATA, so it cannot prove data-directory isolation.".into());
    };
    let resolved = normalize(directory);
    for name in DEVELOPER_IDENTIFIERS {
        let forbidden = normalize(&PathBuf::from(&appdata).join(name));
        if same_or_inside(&resolved, &forbidden) {
            return Err(
                "Acceptance data directory is the developer application data directory. Startup stopped."
                    .into(),
            );
        }
    }
    terminal::acceptance_api_base()?;
    Ok(())
}

pub fn assert_database(identifier: &str, directory: &Path, database: &Path, api_base_url: &str) -> Result<(), String> {
    if !enabled() {
        return Ok(());
    }
    assert_isolated(identifier, directory)?;
    assert_isolated(identifier, database)?;
    if !same_or_inside(&normalize(database), &normalize(directory)) {
        return Err("SQLite path is outside the acceptance data directory.".into());
    }
    if api_base_url != "http://not-activated.invalid" && api_base_url != API_BASE {
        return Err("Acceptance register refused an API address other than the dedicated loopback endpoint.".into());
    }
    Ok(())
}

pub fn write_diagnostics(
    directory: &Path,
    database: &Path,
    identifier: &str,
    api_base_url: &str,
    source: &str,
) -> Result<(), String> {
    if !enabled() {
        return Ok(());
    }
    let executable = std::env::current_exe()
        .map(|path| path.display().to_string())
        .unwrap_or_else(|_| "unknown".into());
    let report = serde_json::json!({
        "profile": "acceptance",
        "identifier": identifier,
        "executable": executable,
        "app_data_dir": directory.display().to_string(),
        "sqlite_path": database.display().to_string(),
        "activation_path": terminal::config_path(directory).display().to_string(),
        "api_base_url": api_base_url,
        "activation_source": source,
        "developer_env_loaded": false,
        "dev_env_config_ignored": std::env::var("POS_DEV_ENV_CONFIG").is_ok(),
        "guard": "passed",
    });
    let path = directory.join("acceptance-diagnostics.json");
    std::fs::write(&path, serde_json::to_vec_pretty(&report).map_err(|err| err.to_string())?)
        .map_err(|err| format!("Unable to write acceptance diagnostics: {err}"))
}

fn normalize(path: &Path) -> String {
    let text = path.to_string_lossy().replace('/', "\\");
    if cfg!(windows) {
        text.to_lowercase()
    } else {
        text
    }
}

fn same_or_inside(candidate: &str, forbidden: &str) -> bool {
    candidate == forbidden || candidate.starts_with(&format!("{forbidden}\\"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn developer_directory_is_forbidden_and_acceptance_directory_is_not() {
        let developer = r"c:\users\cashier\appdata\roaming\com.aipos.desktop";
        let nested = r"c:\users\cashier\appdata\roaming\com.aipos.desktop\tenants\pharmacy-accept\ai-pos.db";
        let acceptance = r"c:\users\cashier\appdata\roaming\com.axizpos.pharmacy.acceptance";
        let acceptance_db =
            r"c:\users\cashier\appdata\roaming\com.axizpos.pharmacy.acceptance\tenants\pharmacy-accept\ai-pos.db";
        assert!(same_or_inside(developer, developer));
        assert!(same_or_inside(nested, developer));
        assert!(!same_or_inside(acceptance, developer));
        assert!(!same_or_inside(acceptance_db, developer));
        assert!(same_or_inside(acceptance_db, acceptance));
    }
}
