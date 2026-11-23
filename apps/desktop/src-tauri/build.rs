use std::{env, fs, path::PathBuf};

const ENVIRONMENTS: [&str; 4] = ["development", "dev", "production", "acceptance"];

/// Bakes the activation endpoint from the repo-root env file into the binary, so an installer never
/// depends on files from the build machine. POS_ENV defaults to development for debug builds and
/// production for release builds. Development reads `.env`; dev and production read `.env.<name>`.
fn main() {
    println!("cargo:rerun-if-env-changed=POS_ENV");
    // Public keys only. Plural entries are key-id:base64,key-id:base64. The singular pair is one entry.
    println!("cargo:rerun-if-env-changed=POS_ENTITLEMENT_KEY_ID");
    println!("cargo:rerun-if-env-changed=POS_ENTITLEMENT_PUBLIC_KEY");
    println!("cargo:rerun-if-env-changed=POS_ENTITLEMENT_PUBLIC_KEYS");
    let mut key_id = env::var("POS_ENTITLEMENT_KEY_ID").unwrap_or_default();
    let mut public_key = env::var("POS_ENTITLEMENT_PUBLIC_KEY").unwrap_or_default();
    let public_keys = env::var("POS_ENTITLEMENT_PUBLIC_KEYS").unwrap_or_default();
    let pos_env_early = env::var("POS_ENV").unwrap_or_default().trim().to_lowercase();
    // A Tauri release spawn can drop the parent environment. An acceptance build may
    // read the disposable public key from the temp directory. Production never does.
    if pos_env_early == "acceptance" {
        if let Ok(temp) = env::var("TEMP").or_else(|_| env::var("TMP")) {
            let acceptance_profile = env::var("ACCEPTANCE_PROFILE").unwrap_or_default();
            let folder = if acceptance_profile == "restaurant" {
                "axiz-o810"
            } else if acceptance_profile.starts_with("zoom-") {
                "axiz-zoom"
            } else if acceptance_profile.starts_with("portion-") {
                "axiz-portion"
            } else if acceptance_profile == "ordertags" {
                "axiz-ordertags"
            } else {
                "axiz-o85"
            };
            let dir = PathBuf::from(temp).join(folder);
            if public_key.is_empty() {
                if let Ok(material) = fs::read_to_string(dir.join("public.b64")) {
                    public_key = material.trim().to_string();
                }
            }
            if key_id.is_empty() {
                if let Ok(id) = fs::read_to_string(dir.join("key-id.txt")) {
                    key_id = id.trim().to_string();
                }
            }
            if key_id.is_empty() && !public_key.is_empty() {
                key_id = if folder == "axiz-o810" {
                    "o810-accept-1".to_string()
                } else if folder == "axiz-zoom" {
                    "zoom-accept-1".to_string()
                } else if folder == "axiz-portion" {
                    "portion-accept-1".to_string()
                } else if folder == "axiz-ordertags" {
                    "ordertags-accept-1".to_string()
                } else {
                    "o85-accept-1".to_string()
                };
            }
            let _ = fs::write(
                dir.join("baked.txt"),
                format!("id={key_id}\npub_len={}\n", public_key.len()),
            );
        }
    }
    println!("cargo:rustc-env=POS_ENTITLEMENT_KEY_ID={key_id}");
    println!("cargo:rustc-env=POS_ENTITLEMENT_PUBLIC_KEY={public_key}");
    println!("cargo:rustc-env=POS_ENTITLEMENT_PUBLIC_KEYS={public_keys}");
    let release = env::var("PROFILE").is_ok_and(|profile| profile == "release");
    let pos_env = env::var("POS_ENV")
        .ok()
        .map(|value| value.trim().to_lowercase())
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| if release { "production" } else { "development" }.to_string());
    if !ENVIRONMENTS.contains(&pos_env.as_str()) {
        panic!("POS_ENV must be one of {ENVIRONMENTS:?}; got {pos_env:?}.");
    }
    if pos_env == "acceptance" {
        emit_acceptance();
        tauri_build::build();
        return;
    }
    println!("cargo:rustc-env=POS_ACCEPTANCE_BUILD=0");
    println!("cargo:rustc-env=POS_ACCEPTANCE_IDENTIFIER=");
    println!("cargo:rustc-env=POS_ACCEPTANCE_API_BASE=");

    let manifest_dir =
        PathBuf::from(env::var("CARGO_MANIFEST_DIR").expect("CARGO_MANIFEST_DIR is set by cargo"));
    let file_name = if pos_env == "development" {
        ".env".to_string()
    } else {
        format!(".env.{pos_env}")
    };
    let env_path = manifest_dir
        .join("..")
        .join("..")
        .join("..")
        .join(file_name);
    println!("cargo:rerun-if-changed={}", env_path.display());

    let (mut url_template, mut base_domain) = read_tenant_pair(&env_path);
    if url_template.is_empty() || base_domain.is_empty() {
        let production = env_path
            .parent()
            .unwrap_or(&env_path)
            .join(".env.production");
        println!("cargo:rerun-if-changed={}", production.display());
        let (prod_url, prod_domain) = read_tenant_pair(&production);
        if url_template.is_empty() {
            url_template = prod_url;
        }
        if base_domain.is_empty() {
            base_domain = prod_domain;
        }
    }
    if pos_env != "development" && (url_template.is_empty() || base_domain.is_empty()) {
        panic!(
            "{} must set TENANT_URL_TEMPLATE and TENANT_BASE_DOMAIN.",
            env_path.display()
        );
    }
    if release && pos_env == "production" && key_id.is_empty() && public_key.is_empty() && public_keys.is_empty() {
        println!(
            "cargo:warning=Production release has no POS_ENTITLEMENT public key. Entitlement grants fail closed until POS_ENTITLEMENT_KEY_ID and POS_ENTITLEMENT_PUBLIC_KEY, or POS_ENTITLEMENT_PUBLIC_KEYS, are set. No key was generated."
        );
    }

    println!("cargo:rustc-env=POS_TENANT_URL_TEMPLATE={url_template}");
    println!("cargo:rustc-env=POS_TENANT_BASE_DOMAIN={base_domain}");
    tauri_build::build()
}

fn emit_acceptance() {
    println!("cargo:rerun-if-env-changed=ACCEPTANCE_PROFILE");
    println!("cargo:rerun-if-env-changed=ACCEPTANCE_TENANT_URL_TEMPLATE");
    println!("cargo:rerun-if-env-changed=ACCEPTANCE_TENANT_BASE_DOMAIN");
    let profile = env::var("ACCEPTANCE_PROFILE").unwrap_or_else(|_| "pharmacy".to_string());
    let (identifier, expected_url) = match profile.as_str() {
        "pharmacy" => (
            "com.axizpos.pharmacy.acceptance",
            "http://127.0.0.1:18080",
        ),
        "inventory" => (
            "com.axizpos.inventory.acceptance",
            "http://127.0.0.1:18081",
        ),
        "laundry" => (
            "com.axizpos.laundry.acceptance",
            "http://127.0.0.1:18082",
        ),
        "offline" => (
            "com.axizpos.offline.acceptance",
            "http://127.0.0.1:18084",
        ),
        "restaurant" => (
            "com.axizpos.restaurant.acceptance",
            "http://127.0.0.1:18089",
        ),
        "zoom-grocery" => ("com.axizpos.grocery.zoom", "http://127.0.0.1:18090"),
        "zoom-electronics" => ("com.axizpos.electronics.zoom", "http://127.0.0.1:18091"),
        "zoom-fashion" => ("com.axizpos.fashion.zoom", "http://127.0.0.1:18092"),
        "zoom-restaurant" => ("com.axizpos.restaurant.zoom", "http://127.0.0.1:18093"),
        "portion-restaurant" => ("com.axizpos.restaurant.portion", "http://127.0.0.1:18094"),
        "portion-cafe" => ("com.axizpos.cafe.portion", "http://127.0.0.1:18095"),
        "ordertags" => ("com.axizpos.ordertags.acceptance", "http://127.0.0.1:18096"),
        other => panic!(
            "ACCEPTANCE_PROFILE must be pharmacy, inventory, laundry, offline, restaurant, a zoom profile, a portion profile, or ordertags; got {other:?}."
        ),
    };
    let url = env::var("ACCEPTANCE_TENANT_URL_TEMPLATE").unwrap_or_default();
    let domain = env::var("ACCEPTANCE_TENANT_BASE_DOMAIN").unwrap_or_default();
    if url != expected_url {
        panic!("Acceptance profile {profile} requires ACCEPTANCE_TENANT_URL_TEMPLATE={expected_url}.");
    }
    if domain != "acceptance.invalid" {
        panic!("Acceptance builds require ACCEPTANCE_TENANT_BASE_DOMAIN=acceptance.invalid.");
    }
    println!("cargo:rustc-env=POS_TENANT_URL_TEMPLATE={url}");
    println!("cargo:rustc-env=POS_TENANT_BASE_DOMAIN={domain}");
    println!("cargo:rustc-env=POS_ACCEPTANCE_BUILD=1");
    println!("cargo:rustc-env=POS_ACCEPTANCE_IDENTIFIER={identifier}");
    println!("cargo:rustc-env=POS_ACCEPTANCE_API_BASE={url}");
}

fn read_tenant_pair(path: &std::path::Path) -> (String, String) {
    let mut url_template = String::new();
    let mut base_domain = String::new();
    let Ok(text) = fs::read_to_string(path) else {
        return (url_template, base_domain);
    };
    for line in text
        .lines()
        .map(str::trim)
        .filter(|line| !line.starts_with('#'))
    {
        let Some((key, value)) = line.split_once('=') else {
            continue;
        };
        let value = value.trim().trim_matches('"').to_string();
        match key.trim() {
            "TENANT_URL_TEMPLATE" => url_template = value,
            "TENANT_BASE_DOMAIN" => base_domain = value,
            _ => {}
        }
    }
    (url_template, base_domain)
}
