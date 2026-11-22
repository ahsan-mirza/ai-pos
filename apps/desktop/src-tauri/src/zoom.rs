//! Acceptance-only WebView zoom for the isolated catalogue windows.
//!
//! Production builds compile `acceptance::enabled()` to false, so these files are ignored and
//! `set_zoom` is never called. There is no zoom control in the POS UI.

use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use serde::Deserialize;
use serde_json::{json, Value};
use tauri::{AppHandle, Emitter, Manager};

use crate::acceptance;
use crate::auth;
use crate::db::Db;
use crate::entitlement;
use crate::shifts;
use crate::sync::DesktopConfig;
use crate::terminal::{self, TerminalState};

static DATA_DIR: OnceLock<PathBuf> = OnceLock::new();
static REQUESTED: AtomicU64 = AtomicU64::new(100);
static LAST_FACTOR: Mutex<Option<String>> = Mutex::new(None);

#[derive(Deserialize)]
struct ActivateFile {
    subdomain: String,
    activation_key: String,
}

#[derive(Deserialize)]
struct UnlockFile {
    username: String,
    pin: String,
}

#[derive(Deserialize)]
struct ActionFile {
    op: String,
    text: Option<String>,
}

pub fn parse_factor(raw: &str) -> Option<f64> {
    match raw.trim() {
        "1" | "1.0" | "1.00" | "100" => Some(1.0),
        "1.25" | "125" => Some(1.25),
        "1.5" | "1.50" | "150" => Some(1.5),
        "2" | "2.0" | "2.00" | "200" => Some(2.0),
        _ => None,
    }
}

fn dir() -> Option<PathBuf> {
    DATA_DIR.get().cloned()
}

fn write_status(message: &str) {
    let Some(directory) = dir() else {
        return;
    };
    let _ = fs::write(directory.join("zoom-status.txt"), message);
}

/// Activates from `zoom-activate.json` before the database is chosen. Production builds skip this.
pub fn prepare_activation(directory: &Path) -> Result<(), String> {
    if !acceptance::enabled() {
        return Ok(());
    }
    let _ = DATA_DIR.set(directory.to_path_buf());
    let request = directory.join("zoom-activate.json");
    if !request.exists() {
        return Ok(());
    }
    let terminal_path = terminal::config_path(directory);
    if matches!(terminal::load(&terminal_path), Ok(Some(_))) {
        let _ = fs::remove_file(&request);
        return Ok(());
    }
    let raw = fs::read_to_string(&request).map_err(|err| format!("Unable to read the zoom activation file: {err}"))?;
    let parsed: ActivateFile = serde_json::from_str(&raw).map_err(|err| format!("Zoom activation file is invalid: {err}"))?;
    let (public_key, private_key) = entitlement::generate_device_key()?;
    let outcome = terminal::activate(&parsed.subdomain, &parsed.activation_key, &public_key)?;
    let binding = entitlement::device_binding(&public_key).ok_or_else(|| "The device key could not be prepared.".to_string())?;
    let mut stored = TerminalState {
        storage_version: 2,
        config: outcome.config,
        device_public_key: public_key,
        device_private_key: private_key,
        entitlement_payload: String::new(),
        entitlement_signature: String::new(),
        entitlement_key_id: String::new(),
    };
    let Some(signed) = outcome.entitlement else {
        return Err("The server did not return a permanent entitlement. The register was not saved.".into());
    };
    let expected = entitlement::ExpectedBinding {
        tenant_id: if stored.config.tenant_id.is_empty() {
            stored.config.tenant_slug.clone()
        } else {
            stored.config.tenant_id.clone()
        },
        branch_id: stored.config.store_id.clone(),
        terminal_id: stored.config.register_id.clone(),
        device_binding: binding,
    };
    let code = entitlement::code_for(
        &signed.payload,
        &signed.signature,
        &signed.key_id,
        &expected,
        auth::now_secs(),
    );
    if code != entitlement::VALID {
        return Err(entitlement::verification_message(code).into());
    }
    stored.entitlement_payload = signed.payload;
    stored.entitlement_signature = signed.signature;
    stored.entitlement_key_id = signed.key_id;
    terminal::save(&terminal_path, &stored)?;
    let _ = fs::remove_file(&request);
    write_status("activated");
    Ok(())
}

pub fn sign_in(db: &Db, config: &DesktopConfig, directory: &Path) -> Result<Option<(crate::auth::Session, Option<String>)>, String> {
    if !acceptance::enabled() {
        return Ok(None);
    }
    let _ = DATA_DIR.set(directory.to_path_buf());
    let path = directory.join("zoom-unlock.json");
    if !path.exists() {
        return Ok(None);
    }
    let raw = fs::read_to_string(&path).map_err(|err| format!("Unable to read the zoom unlock file: {err}"))?;
    let parsed: UnlockFile = serde_json::from_str(&raw).map_err(|err| format!("Zoom unlock file is invalid: {err}"))?;
    let unlocked = auth::pin_login(db, config, &parsed.username, &parsed.pin)?;
    db.save_register_session(&unlocked.session.user, &unlocked.session.mode, unlocked.session.unlocked_at)?;
    write_status(&format!("signed-in {}", unlocked.session.mode));
    Ok(Some((unlocked.session, unlocked.access_token)))
}

pub fn open_shift(db: &Db, session: &crate::auth::Session, store_id: &str, directory: &Path) -> Result<(), String> {
    if !acceptance::enabled() || !directory.join("zoom-shift.json").exists() {
        return Ok(());
    }
    if shifts::current(db)?.is_some() {
        return Ok(());
    }
    let input = shifts::OpenShift {
        id: random_uuid(),
        opened_at: unix_rfc3339(SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0)),
        opening_float_cents: 0,
        currency: "USD".into(),
    };
    shifts::open(db, session, store_id, &input)?;
    write_status("shift-open");
    Ok(())
}

pub fn start(app: AppHandle) {
    if !acceptance::enabled() {
        return;
    }
    std::thread::spawn(move || loop {
        let _ = tick(&app);
        std::thread::sleep(Duration::from_millis(400));
    });
}

fn tick(app: &AppHandle) -> Result<(), String> {
    let Some(directory) = dir() else {
        return Ok(());
    };
    let Some(window) = app.get_webview_window("main") else {
        return Ok(());
    };
    if !directory.join("zoom-identity.json").exists() {
        let hwnd = window.hwnd().map(|handle| handle.0 as usize).unwrap_or(0);
        let profile = fs::read_to_string(directory.join("zoom-profile.txt")).unwrap_or_default();
        let identity = json!({
            "pid": std::process::id(),
            "hwnd": hwnd,
            "identifier": app.config().identifier.clone(),
            "title": window.title().unwrap_or_default(),
            "data_dir": directory.display().to_string(),
            "profile": profile.trim(),
        });
        let _ = fs::write(directory.join("zoom-identity.json"), serde_json::to_vec_pretty(&identity).unwrap_or_default());
    }
    if let Ok(raw) = fs::read_to_string(directory.join("zoom-factor.txt")) {
        if let Some(factor) = parse_factor(&raw) {
            let label = raw.trim().to_string();
            let changed = LAST_FACTOR.lock().map(|guard| guard.as_deref() != Some(label.as_str())).unwrap_or(true);
            if changed {
                window.set_zoom(factor).map_err(|err| err.to_string())?;
                if let Ok(mut guard) = LAST_FACTOR.lock() {
                    *guard = Some(label);
                }
                REQUESTED.store((factor * 100.0).round() as u64, Ordering::Relaxed);
            }
        }
    }
    if let Ok(raw) = fs::read_to_string(directory.join("zoom-action.json")) {
        if let Ok(action) = serde_json::from_str::<ActionFile>(&raw) {
            let script = action_script(&action);
            let _ = window.eval(script);
        }
        let _ = fs::remove_file(directory.join("zoom-action.json"));
    }
    let _ = window.eval(PROBE);
    let _ = app.emit("zoom-probe", ());
    Ok(())
}

const PROBE: &str = r#"(function(){
  var root = getComputedStyle(document.documentElement);
  var tile = document.querySelector('li');
  var well = tile ? tile.querySelector('span.relative') : null;
  var photo = tile ? tile.querySelector('img') : null;
  var footer = null;
  if (tile) {
    var buttons = tile.querySelectorAll('button');
    for (var i = 0; i < buttons.length; i++) {
      if (String(buttons[i].className).indexOf('border-t') >= 0) footer = buttons[i];
    }
  }
  var dialog = document.querySelector('[role="dialog"]');
  var payload = {
    dpr: window.devicePixelRatio,
    scale: window.visualViewport ? window.visualViewport.scale : null,
    font: root.fontSize,
    innerWidth: window.innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
    objectFit: photo ? getComputedStyle(photo).objectFit : null,
    wellHeight: well ? Math.round(well.getBoundingClientRect().height) : null,
    footerHeight: footer ? Math.round(footer.getBoundingClientRect().height) : null,
    dialog: dialog ? (dialog.innerText || '').slice(0, 4000) : '',
    radios: [].slice.call(document.querySelectorAll('[role="radio"]')).slice(0, 8).map(function(el){
      var rect = el.getBoundingClientRect();
      var price = el.querySelectorAll('span')[1];
      var priceRect = price ? price.getBoundingClientRect() : null;
      var color = price ? getComputedStyle(price).color : '';
      return (el.innerText || '').replace(/\s+/g, ' ') + ' @' + Math.round(rect.x) + ',' + Math.round(rect.y) + ' ' + Math.round(rect.width) + 'x' + Math.round(rect.height) + (priceRect ? ' price@' + Math.round(priceRect.x) + ',' + Math.round(priceRect.y) + ' ' + Math.round(priceRect.width) + 'x' + Math.round(priceRect.height) + ' ' + color : '');
    }).join(' | '),
    priceHit: (function(){
      var spans = [].slice.call(document.querySelectorAll('[role="radio"] span'));
      var priced = spans.find(function(el){ return (el.textContent || '').indexOf('$') >= 0; });
      if (!priced) return '';
      var rect = priced.getBoundingClientRect();
      var hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
      var clips = [];
      var node = priced;
      while (node) {
        var style = getComputedStyle(node);
        var box = node.getBoundingClientRect();
        if (style.overflowX !== 'visible' || style.overflowY !== 'visible' || style.opacity !== '1') {
          clips.push(node.tagName + ' ' + style.overflowX + '/' + style.overflowY + ' op' + style.opacity + ' @' + Math.round(box.x) + ',' + Math.round(box.y) + ' ' + Math.round(box.width) + 'x' + Math.round(box.height));
        }
        node = node.parentElement;
      }
      var hitText = hit ? ((hit.innerText || hit.className || hit.tagName || '') + '').replace(/\s+/g, ' ').slice(0, 80) : 'none';
      return hitText + ' || ' + clips.join(' > ');
    })(),
    text: (document.body && document.body.innerText || '').slice(0, 6000)
  };
  var internals = window.__TAURI_INTERNALS__;
  if (internals && internals.invoke) void internals.invoke('acceptance_zoom_report', { measurement: payload });
})()"#;

fn action_script(action: &ActionFile) -> String {
    if action.op == "reload" {
        return "location.reload()".into();
    }
    if action.op == "scroll" {
        return r#"(function(){var nodes=[].slice.call(document.querySelectorAll('main,div,section'));var scroller=nodes.find(function(el){var style=getComputedStyle(el);return el.scrollHeight>el.clientHeight+80 && (style.overflowY==='auto'||style.overflowY==='scroll');});if(scroller)scroller.scrollTop=scroller.scrollHeight;})()"#
            .into();
    }
    if action.op == "escape" {
        return "document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))".into();
    }
    let text = serde_json::to_string(action.text.as_deref().unwrap_or("")).unwrap_or_else(|_| "\"\"".into());
    format!(
        "(function(){{var wanted={text};var nodes=[].slice.call(document.querySelectorAll('button,[role=radio],a'));\
var node=nodes.find(function(el){{return (el.innerText||'').indexOf(wanted)>=0;}});if(node)node.click();}})()"
    )
}

#[tauri::command]
pub fn acceptance_zoom_report(measurement: Value) -> Result<(), String> {
    if !acceptance::enabled() {
        return Err("Zoom reporting is only available on an acceptance build.".into());
    }
    let Some(directory) = dir() else {
        return Err("Zoom data directory is not ready.".into());
    };
    let mut body = measurement;
    if let Some(map) = body.as_object_mut() {
        map.insert("requested_percent".into(), json!(REQUESTED.load(Ordering::Relaxed)));
        map.insert("pid".into(), json!(std::process::id()));
    }
    fs::write(directory.join("zoom-measured.json"), serde_json::to_vec_pretty(&body).unwrap_or_default())
        .map_err(|err| err.to_string())
}

fn random_uuid() -> String {
    let mut bytes = [0u8; 16];
    for (index, byte) in bytes.iter_mut().enumerate() {
        *byte = (auth::now_secs() as u8).wrapping_add(index as u8).wrapping_mul(17);
    }
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    format!(
        "{:02x}{:02x}{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}{:02x}{:02x}{:02x}{:02x}",
        bytes[0], bytes[1], bytes[2], bytes[3], bytes[4], bytes[5], bytes[6], bytes[7], bytes[8], bytes[9], bytes[10],
        bytes[11], bytes[12], bytes[13], bytes[14], bytes[15]
    )
}

fn unix_rfc3339(secs: u64) -> String {
    let days = (secs / 86_400) as i64;
    let tod = secs % 86_400;
    let z = days + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = (z - era * 146_097) as u64;
    let yoe = (doe - doe / 1_460 + doe / 36_524 - doe / 146_096) / 365;
    let y = yoe as i64 + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let month = if mp < 10 { mp + 3 } else { mp - 9 };
    let year = if month <= 2 { y + 1 } else { y };
    format!(
        "{year:04}-{month:02}-{day:02}T{:02}:{:02}:{:02}Z",
        tod / 3600,
        (tod % 3600) / 60,
        tod % 60
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_the_four_zoom_levels_are_accepted() {
        assert_eq!(parse_factor("100"), Some(1.0));
        assert_eq!(parse_factor("1.25"), Some(1.25));
        assert_eq!(parse_factor("150"), Some(1.5));
        assert_eq!(parse_factor("200"), Some(2.0));
        assert_eq!(parse_factor("175"), None);
        assert_eq!(parse_factor("2.5"), None);
    }

    #[test]
    fn production_builds_ignore_zoom_files() {
        assert!(!acceptance::enabled());
        let directory = std::env::temp_dir().join("axiz-zoom-production-guard");
        let _ = fs::create_dir_all(&directory);
        fs::write(directory.join("zoom-activate.json"), b"{\"subdomain\":\"nope\",\"activation_key\":\"nope\"}").unwrap();
        assert!(prepare_activation(&directory).is_ok());
        assert!(!directory.join("zoom-status.txt").exists() || fs::read_to_string(directory.join("zoom-status.txt")).unwrap_or_default().is_empty());
        let _ = fs::remove_dir_all(&directory);
    }
}
