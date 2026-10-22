use std::{env, fs, path::PathBuf};

const ENVIRONMENTS: [&str; 3] = ["development", "dev", "production"];

/// Bakes the activation endpoint from the repo-root env file into the binary, so an installer never
/// depends on files from the build machine. POS_ENV defaults to development for debug builds and
/// production for release builds. Development reads `.env`; dev and production read `.env.<name>`.
fn main() {
    println!("cargo:rerun-if-env-changed=POS_ENV");
    let release = env::var("PROFILE").is_ok_and(|profile| profile == "release");
    let pos_env = env::var("POS_ENV")
        .ok()
        .map(|value| value.trim().to_lowercase())
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| if release { "production" } else { "development" }.to_string());
    if !ENVIRONMENTS.contains(&pos_env.as_str()) {
        panic!("POS_ENV must be one of {ENVIRONMENTS:?}; got {pos_env:?}.");
    }

    let manifest_dir = PathBuf::from(env::var("CARGO_MANIFEST_DIR").expect("CARGO_MANIFEST_DIR is set by cargo"));
    let file_name = if pos_env == "development" { ".env".to_string() } else { format!(".env.{pos_env}") };
    let env_path = manifest_dir.join("..").join("..").join("..").join(file_name);
    println!("cargo:rerun-if-changed={}", env_path.display());

    let mut url_template = String::new();
    let mut base_domain = String::new();
    if let Ok(text) = fs::read_to_string(&env_path) {
        for line in text.lines().map(str::trim).filter(|line| !line.starts_with('#')) {
            let Some((key, value)) = line.split_once('=') else { continue };
            let value = value.trim().trim_matches('"').to_string();
            match key.trim() {
                "TENANT_URL_TEMPLATE" => url_template = value,
                "TENANT_BASE_DOMAIN" => base_domain = value,
                _ => {}
            }
        }
    }
    if pos_env != "development" && (url_template.is_empty() || base_domain.is_empty()) {
        panic!("{} must set TENANT_URL_TEMPLATE and TENANT_BASE_DOMAIN.", env_path.display());
    }

    println!("cargo:rustc-env=POS_TENANT_URL_TEMPLATE={url_template}");
    println!("cargo:rustc-env=POS_TENANT_BASE_DOMAIN={base_domain}");
    tauri_build::build()
}
