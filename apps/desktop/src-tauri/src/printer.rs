use std::io::Write;
use std::net::{TcpStream, ToSocketAddrs};
use std::path::Path;
use std::sync::atomic::{AtomicBool, AtomicI64, Ordering};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};

use tauri::Emitter;

use crate::db::Db;
use crate::sync::DesktopConfig;

/// Receipts are rendered to a 1-bit raster in the webview (so Arabic shaping and the brand fonts come from
/// the browser engine) and sent here as packed rows; this module frames them as ESC/POS and ships the bytes.
pub fn migrate(conn: &Connection) -> Result<(), String> {
    conn.execute_batch(
        "
        CREATE TABLE IF NOT EXISTS printer_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            transport TEXT NOT NULL DEFAULT 'none',
            address TEXT NOT NULL DEFAULT '',
            paper_dots INTEGER NOT NULL DEFAULT 576,
            drawer_kick INTEGER NOT NULL DEFAULT 1,
            auto_print INTEGER NOT NULL DEFAULT 1,
            copies INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS printer_status (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            last_ok_at INTEGER,
            last_error TEXT,
            last_error_at INTEGER,
            last_kick_ok_at INTEGER,
            last_kick_error TEXT
        );
        ",
    )
    .map_err(|err| err.to_string())?;
    add_column(conn, "printer_settings", "drawer_pin", "INTEGER NOT NULL DEFAULT 0")?;
    add_column(conn, "printer_settings", "drawer_on", "INTEGER NOT NULL DEFAULT 25")?;
    add_column(conn, "printer_settings", "drawer_off", "INTEGER NOT NULL DEFAULT 250")?;
    add_column(conn, "printer_settings", "auto_discover", "INTEGER NOT NULL DEFAULT 1")?;
    add_column(conn, "printer_settings", "previous_address", "TEXT NOT NULL DEFAULT ''")?;
    add_column(conn, "printer_settings", "saved_driver", "TEXT NOT NULL DEFAULT ''")?;
    add_column(conn, "printer_settings", "saved_port", "TEXT NOT NULL DEFAULT ''")?;
    add_column(conn, "printer_settings", "saved_model", "TEXT NOT NULL DEFAULT ''")?;
    add_column(conn, "printer_settings", "user_selected", "INTEGER NOT NULL DEFAULT 0")?;
    add_column(conn, "printer_settings", "saved_identity", "TEXT NOT NULL DEFAULT ''")?;
    add_column(conn, "printer_settings", "connection_kind", "TEXT NOT NULL DEFAULT ''")?;
    add_column(conn, "printer_settings", "protocol", "TEXT NOT NULL DEFAULT ''")?;
    add_column(conn, "printer_settings", "bluetooth_identity", "TEXT NOT NULL DEFAULT ''")?;
    add_column(conn, "printer_settings", "verification", "TEXT NOT NULL DEFAULT 'candidate'")?;
    add_column(conn, "printer_settings", "drawer_profile", "TEXT NOT NULL DEFAULT ''")?;
    add_column(conn, "printer_settings", "host_voltage", "TEXT NOT NULL DEFAULT ''")?;
    add_column(conn, "printer_settings", "open_on_non_cash", "INTEGER NOT NULL DEFAULT 0")?;
    add_column(conn, "printer_status", "last_kick_attempt_at", "INTEGER")?;
    conn.execute_batch(
        "
        CREATE TABLE IF NOT EXISTS printer_jobs (
            id TEXT PRIMARY KEY,
            invoice_id TEXT NOT NULL DEFAULT '',
            printer_id TEXT NOT NULL DEFAULT '',
            transport TEXT NOT NULL DEFAULT '',
            payload_type TEXT NOT NULL DEFAULT '',
            created_at INTEGER NOT NULL,
            status TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 1,
            error TEXT NOT NULL DEFAULT '',
            verification TEXT NOT NULL DEFAULT 'physical-not-verified'
        );
        ",
    )
    .map_err(|err| err.to_string())?;
    add_column(conn, "printer_jobs", "connection", "TEXT NOT NULL DEFAULT ''")?;
    add_column(conn, "printer_jobs", "protocol", "TEXT NOT NULL DEFAULT ''")?;
    add_column(conn, "printer_jobs", "payload_bytes", "INTEGER NOT NULL DEFAULT 0")?;
    Ok(())
}

fn add_column(conn: &Connection, table: &str, column: &str, definition: &str) -> Result<(), String> {
    let mut info = conn
        .prepare(&format!("PRAGMA table_info({table})"))
        .map_err(|err| err.to_string())?;
    let present = info
        .query_map([], |row| row.get::<_, String>(1))
        .map_err(|err| err.to_string())?
        .filter_map(Result::ok)
        .any(|name| name == column);
    if present {
        return Ok(());
    }
    conn.execute(&format!("ALTER TABLE {table} ADD COLUMN {column} {definition}"), [])
        .map_err(|err| err.to_string())?;
    Ok(())
}

#[derive(Clone, Serialize, Deserialize)]
pub struct PrinterSettings {
    /// "none", "tcp" (host[:port], default 9100) or "windows" (spooler printer name).
    pub transport: String,
    pub address: String,
    /// 576 dots for 80 mm paper, 384 for 58 mm.
    pub paper_dots: u32,
    pub drawer_kick: bool,
    pub auto_print: bool,
    pub copies: u32,
    /// ESC/POS drawer connector: 0 is pin 2, 1 is pin 5.
    #[serde(default)]
    pub drawer_pin: u8,
    /// Pulse on-time in units of 2 ms. 25 is 50 ms.
    #[serde(default = "default_drawer_on")]
    pub drawer_on: u8,
    /// Pulse off-time in units of 2 ms. 250 is 500 ms.
    #[serde(default = "default_drawer_off")]
    pub drawer_off: u8,
    #[serde(default = "default_auto")]
    pub auto_discover: bool,
    #[serde(default)]
    pub previous_address: String,
    #[serde(default)]
    pub saved_driver: String,
    #[serde(default)]
    pub saved_port: String,
    #[serde(default)]
    pub saved_model: String,
    #[serde(default)]
    pub user_selected: bool,
    /// Windows object GUID when the spooler provides one. Empty when it does not.
    #[serde(default)]
    pub saved_identity: String,
    /// windows, usb, network, wifi, serial, bluetooth-classic, bluetooth-ble, or none.
    #[serde(default)]
    pub connection_kind: String,
    /// escpos, windows-gdi, or unknown. Empty until the print path selects one.
    #[serde(default)]
    pub protocol: String,
    /// Bluetooth device identity. Empty for Windows and network printers.
    #[serde(default)]
    pub bluetooth_identity: String,
    /// candidate, offline, unsupported, missing, or connection-error. Never stored as verified from the client.
    #[serde(default)]
    pub verification: String,
    /// Compatibility-list id. Empty until a cashier chooses a drawer profile.
    #[serde(default)]
    pub drawer_profile: String,
    /// Confirmed printer drawer-port voltage: "12", "24", or empty when unconfirmed.
    #[serde(default)]
    pub host_voltage: String,
    /// Card and other non-cash tenders stay closed unless this is explicitly on.
    #[serde(default)]
    pub open_on_non_cash: bool,
}

fn default_auto() -> bool {
    true
}

fn default_drawer_on() -> u8 {
    25
}

fn default_drawer_off() -> u8 {
    250
}

impl Default for PrinterSettings {
    fn default() -> Self {
        Self {
            transport: "none".into(),
            address: String::new(),
            paper_dots: 576,
            drawer_kick: true,
            auto_print: true,
            copies: 1,
            drawer_pin: 0,
            drawer_on: default_drawer_on(),
            drawer_off: default_drawer_off(),
            auto_discover: true,
            previous_address: String::new(),
            saved_driver: String::new(),
            saved_port: String::new(),
            saved_model: String::new(),
            user_selected: false,
            saved_identity: String::new(),
            connection_kind: String::new(),
            protocol: String::new(),
            bluetooth_identity: String::new(),
            verification: "candidate".into(),
            drawer_profile: String::new(),
            host_voltage: String::new(),
            open_on_non_cash: false,
        }
    }
}

pub fn load(db: &Db) -> Result<PrinterSettings, String> {
    db.read(|conn| {
        conn.query_row(
            "SELECT transport, address, paper_dots, drawer_kick, auto_print, copies, drawer_pin, drawer_on, drawer_off,
                    auto_discover, previous_address, saved_driver, saved_port, saved_model, user_selected, saved_identity,
                    connection_kind, protocol, bluetooth_identity, verification, drawer_profile, host_voltage, open_on_non_cash
             FROM printer_settings WHERE id = 1",
            [],
            |row| {
                Ok(PrinterSettings {
                    transport: row.get(0)?,
                    address: row.get(1)?,
                    paper_dots: row.get(2)?,
                    drawer_kick: row.get::<_, i64>(3)? != 0,
                    auto_print: row.get::<_, i64>(4)? != 0,
                    copies: row.get(5)?,
                    drawer_pin: row.get::<_, i64>(6)?.clamp(0, 255) as u8,
                    drawer_on: row.get::<_, i64>(7)?.clamp(1, 255) as u8,
                    drawer_off: row.get::<_, i64>(8)?.clamp(1, 255) as u8,
                    auto_discover: row.get::<_, i64>(9)? != 0,
                    previous_address: row.get(10)?,
                    saved_driver: row.get(11)?,
                    saved_port: row.get(12)?,
                    saved_model: row.get(13)?,
                    user_selected: row.get::<_, i64>(14)? != 0,
                    saved_identity: row.get(15)?,
                    connection_kind: row.get(16)?,
                    protocol: row.get(17)?,
                    bluetooth_identity: row.get(18)?,
                    verification: row.get(19)?,
                    drawer_profile: row.get(20)?,
                    host_voltage: row.get(21)?,
                    open_on_non_cash: row.get::<_, i64>(22)? != 0,
                })
            },
        )
        .optional()
        .map(Option::unwrap_or_default)
        .map_err(|err| err.to_string())
    })
}

pub const REGISTER_MANAGE_REQUIRED: &str =
    "You can view printer status. Register management permission is required to change printer settings.";

pub fn hardware_change_allowed(permissions: &[String]) -> bool {
    permissions.iter().any(|item| {
        item == "pos:access" || item == "devices:manage" || item == "settings:manage"
    })
}

/// Rejects a settings write. The stored row is left as it was, and the denial is appended to the audit ledger.
pub fn refuse_hardware_change(db: &Db, session: &crate::auth::Session, store_id: &str) -> String {
    let previous = load(db).ok();
    let _ = crate::audit::record(
        db,
        session,
        store_id,
        crate::audit::AuditInput {
            action_type: "REGISTER_SETTINGS".into(),
            action: "register.printer_settings".into(),
            target_entity: "RegisterSettings".into(),
            target_entity_id: None,
            reason_notes: None,
            approver_id: None,
            old_values: previous.map(|row| {
                serde_json::json!({
                    "transport": row.transport,
                    "address": row.address,
                    "paper_dots": row.paper_dots,
                })
            }),
            new_values: Some(serde_json::json!({ "outcome": "denied" })),
            details: Some(serde_json::json!({ "source": "desktop" })),
        },
    );
    REGISTER_MANAGE_REQUIRED.to_string()
}

/// Checks a register configuration before it is written. A virtual Windows queue is allowed as a
/// diagnostic preference. It is not treated as a connected receipt printer by the probe.
pub fn prepare_settings(settings: &PrinterSettings) -> Result<PrinterSettings, String> {
    if !matches!(settings.transport.as_str(), "none" | "tcp" | "windows" | "serial" | "ble") {
        return Err("Choose Windows, USB, Network / Wi-Fi, Bluetooth, Serial / COM, or None.".into());
    }
    if !matches!(settings.paper_dots, 384 | 576) {
        return Err("Paper width must be 58 mm (384 dots) or 80 mm (576 dots).".into());
    }
    if !(1..=3).contains(&settings.copies) {
        return Err("Copies per sale must be 1, 2, or 3.".into());
    }
    checked_pulse(settings.drawer_pin, settings.drawer_on, settings.drawer_off)?;
    crate::cash_drawer::validate(&settings.drawer_profile, &settings.host_voltage)?;
    let mut next = settings.clone();
    next.address = settings.address.trim().to_string();
    next.previous_address = settings.previous_address.trim().to_string();
    next.bluetooth_identity = settings.bluetooth_identity.trim().to_string();
    if next.transport == "none" || next.connection_kind.trim().is_empty() {
        next.connection_kind = crate::printer_profile::default_connection(&next.transport).to_string();
    }
    next.connection_kind = next.connection_kind.trim().to_string();
    if !crate::printer_profile::connection_pair_ok(&next.transport, &next.connection_kind) {
        return Err("That connection does not match the selected printer type.".into());
    }
    next.verification = crate::printer_profile::stored_verification(&next.verification).to_string();
    next.drawer_profile = next.drawer_profile.trim().to_string();
    next.host_voltage = next.host_voltage.trim().to_string();
    match next.transport.as_str() {
        "none" => {
            if !next.address.is_empty() {
                next.previous_address = next.address.clone();
                next.address.clear();
            }
            next.user_selected = false;
            next.protocol.clear();
        }
        "tcp" => {
            validate_tcp(&next.address)?;
            if next.protocol.is_empty() {
                next.protocol = "escpos".into();
            }
        }
        "windows" => {
            if next.address.is_empty() {
                return Err("Select a Windows printer.".into());
            }
            if next.connection_kind == "usb" && !next.saved_port.trim().is_empty() && !crate::printer_profile::port_is_usb(&next.saved_port) {
                return Err("This queue is not a USB printer. Choose Windows printer for a driver queue, or Network / Wi-Fi for an address.".into());
            }
            if next.protocol == "escpos"
                && (crate::printer_discovery::expects_rendered_job(&next.saved_driver, &next.saved_port)
                    || crate::printer_discovery::is_text_only_driver(&next.saved_driver))
            {
                return Err("This Windows driver does not accept raw ESC/POS. The receipt is rendered by Windows.".into());
            }
            if !next.protocol.is_empty() && !matches!(next.protocol.as_str(), "escpos" | "windows-gdi") {
                return Err("That printing language is not supported for this printer.".into());
            }
        }
        "serial" => {
            next.address = crate::printer_profile::normalize_com(&next.address)?;
            next.protocol = "escpos".into();
        }
        "ble" => {
            if next.address.is_empty() {
                return Err("Select a Bluetooth Low Energy device.".into());
            }
            next.protocol = "unknown".into();
        }
        _ => {}
    }
    Ok(next)
}

fn validate_tcp(address: &str) -> Result<(), String> {
    if address.is_empty() || address.chars().any(|c| c.is_whitespace()) {
        return Err("Enter the printer IP address or hostname.".into());
    }
    let (host, port_text) = match address.rsplit_once(':') {
        Some((host, port)) if !host.is_empty() && !host.contains(':') && port.chars().all(|c| c.is_ascii_digit()) => {
            (host, Some(port))
        }
        Some(_) => return Err("Enter an IPv4 address or hostname, with an optional port.".into()),
        None => (address, None),
    };
    if let Some(port) = port_text {
        let parsed: u32 = port.parse().unwrap_or(0);
        if parsed == 0 || parsed > 65535 {
            return Err("The printer port must be a number from 1 to 65535.".into());
        }
    }
    let labels: Vec<&str> = host.split('.').collect();
    let ipv4 = labels.len() == 4
        && labels.iter().all(|part| !part.is_empty() && part.parse::<u8>().is_ok() && part.len() <= 3);
    let all_numeric = labels.iter().all(|part| !part.is_empty() && part.chars().all(|c| c.is_ascii_digit()));
    if all_numeric {
        if ipv4 {
            return Ok(());
        }
        return Err("Enter a valid printer IP address or hostname.".into());
    }
    let hostname = !labels.is_empty()
        && labels.iter().all(|label| {
            !label.is_empty()
                && label.len() <= 63
                && label.chars().all(|c| c.is_ascii_alphanumeric() || c == '-')
                && !label.starts_with('-')
                && !label.ends_with('-')
        });
    if !hostname {
        return Err("Enter a valid printer IP address or hostname.".into());
    }
    Ok(())
}

pub fn save(db: &Db, settings: &PrinterSettings) -> Result<PrinterSettings, String> {
    let settings = prepare_settings(settings)?;
    let copies = settings.copies;
    let (drawer_pin, drawer_on, drawer_off) = checked_pulse(settings.drawer_pin, settings.drawer_on, settings.drawer_off)?;
    db.transaction(|tx| {
        tx.execute(
            "INSERT INTO printer_settings (
                id, transport, address, paper_dots, drawer_kick, auto_print, copies, drawer_pin, drawer_on, drawer_off,
                auto_discover, previous_address, saved_driver, saved_port, saved_model, user_selected, saved_identity,
                connection_kind, protocol, bluetooth_identity, verification, drawer_profile, host_voltage, open_on_non_cash
             ) VALUES (1, ?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16, ?17, ?18, ?19, ?20, ?21, ?22, ?23)
             ON CONFLICT(id) DO UPDATE SET transport = excluded.transport, address = excluded.address,
                paper_dots = excluded.paper_dots, drawer_kick = excluded.drawer_kick,
                auto_print = excluded.auto_print, copies = excluded.copies,
                drawer_pin = excluded.drawer_pin, drawer_on = excluded.drawer_on, drawer_off = excluded.drawer_off,
                auto_discover = excluded.auto_discover, previous_address = excluded.previous_address,
                saved_driver = excluded.saved_driver, saved_port = excluded.saved_port,
                saved_model = excluded.saved_model, user_selected = excluded.user_selected,
                saved_identity = excluded.saved_identity, connection_kind = excluded.connection_kind,
                protocol = excluded.protocol, bluetooth_identity = excluded.bluetooth_identity,
                verification = excluded.verification, drawer_profile = excluded.drawer_profile,
                host_voltage = excluded.host_voltage, open_on_non_cash = excluded.open_on_non_cash",
            params![
                settings.transport,
                settings.address.trim(),
                settings.paper_dots,
                settings.drawer_kick as i64,
                settings.auto_print as i64,
                copies,
                drawer_pin as i64,
                drawer_on as i64,
                drawer_off as i64,
                settings.auto_discover as i64,
                settings.previous_address.trim(),
                settings.saved_driver.trim(),
                settings.saved_port.trim(),
                settings.saved_model.trim(),
                settings.user_selected as i64,
                settings.saved_identity.trim(),
                settings.connection_kind.trim(),
                settings.protocol.trim(),
                settings.bluetooth_identity.trim(),
                settings.verification.trim(),
                settings.drawer_profile.trim(),
                settings.host_voltage.trim(),
                settings.open_on_non_cash as i64,
            ],
        )
        .map_err(|err| err.to_string())?;
        Ok(())
    })?;
    load(db)
}

#[derive(Deserialize)]
pub struct RasterJob {
    pub width: u32,
    pub height: u32,
    /// Packed 1-bit rows, most significant bit first, 1 = black. Each row is ceil(width / 8) bytes.
    pub data: Vec<u8>,
    pub kick_drawer: bool,
    /// Safe invoice facts for the print diagnostic. Zero when the caller does not have them.
    #[serde(default)]
    pub line_count: u32,
    #[serde(default)]
    pub document_number: String,
    #[serde(default)]
    pub subtotal_cents: i64,
    #[serde(default)]
    pub tax_cents: i64,
    #[serde(default)]
    pub discount_cents: i64,
    #[serde(default)]
    pub total_cents: i64,
    /// Plain receipt text. Text-only Windows drivers print this instead of the picture.
    #[serde(default)]
    pub plain_text: String,
}

#[cfg(test)]
const DRAWER_KICK: [u8; 5] = [0x1b, b'p', 0, 25, 250];
/// One ESC/POS graphic band. 256 encodes as a zero low byte, and some printers then print only the leftover rows.
const BAND_ROWS: u32 = 128;
const KICK_GAP_SECS: i64 = 3;
const SPOOLER_TIMEOUT: Duration = Duration::from_secs(30);
static PRINTING: AtomicBool = AtomicBool::new(false);
static LAST_KICK_AT: AtomicI64 = AtomicI64::new(0);
static LAST_DIAGNOSTIC: std::sync::Mutex<Option<PrintDiagnostic>> = std::sync::Mutex::new(None);

/// ESC/POS drawer pulse. `pin` 0 is connector pin 2 and 1 is pin 5. Times are units of 2 ms.
pub fn drawer_pulse(pin: u8, on_units: u8, off_units: u8) -> [u8; 5] {
    [0x1b, b'p', pin, on_units, off_units]
}

pub fn checked_pulse(pin: u8, on_units: u8, off_units: u8) -> Result<(u8, u8, u8), String> {
    if pin > 1 {
        return Err("The drawer connector must be pin 2 or pin 5.".into());
    }
    if on_units == 0 || off_units == 0 {
        return Err("The drawer pulse must be at least 2 ms.".into());
    }
    Ok((pin, on_units, off_units))
}

pub fn kick_allowed(now: i64, last_attempt: i64, gap_secs: i64) -> bool {
    last_attempt <= 0 || now.saturating_sub(last_attempt) >= gap_secs
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct InstalledPrinter {
    pub name: String,
    pub driver: String,
    pub port: String,
    pub status: u32,
    pub status_label: String,
    pub unavailable: bool,
    pub compatibility: String,
    pub supports_drawer_kick: bool,
    pub connection: String,
    pub profile_id: String,
    pub manufacturer: String,
    /// Spooler object GUID when Windows returns one.
    pub identity: String,
    /// False when OpenPrinterW was tried and failed. True when the queue opened, or when this pass did not open it.
    pub openable: bool,
    /// ready, offline, unavailable, or virtual.
    pub availability: String,
    /// escpos, windows-gdi, or none.
    pub print_transport: String,
    /// Spooler default datatype when GetPrinterDriverW returned one. Empty when this pass did not read it.
    pub default_datatype: String,
    pub driver_version: String,
    pub capabilities: String,
}

/// One row from EnumPrinters, plus optional OpenPrinter / GetPrinter / GetPrinterDriver facts.
#[derive(Clone, Debug)]
pub struct EnumeratedQueue {
    pub name: String,
    pub driver: String,
    pub port: String,
    pub status: u32,
    pub attributes: u32,
    pub manufacturer: String,
    pub identity: String,
    /// None when this pass did not call OpenPrinterW.
    pub opened: Option<bool>,
    pub default_datatype: String,
    pub driver_version: String,
}

const PRINTER_ATTRIBUTE_WORK_OFFLINE: u32 = 0x400;

/// Maps spooler flags and the existing compatibility classifier onto the labels the register shows.
pub fn describe_queue(status: u32, attributes: u32, connection: &str, compatibility: &str, opened: Option<bool>) -> (String, String, bool) {
    if connection == "Virtual" {
        return ("Virtual printer".into(), "virtual".into(), false);
    }
    let offline = status & 0x80 != 0 || attributes & PRINTER_ATTRIBUTE_WORK_OFFLINE != 0;
    if offline {
        return ("Offline".into(), "offline".into(), true);
    }
    let fault = status & 0x1000 != 0 || status & 0x4 != 0 || status & 0x2 != 0 || status & 0x10 != 0;
    if fault || opened == Some(false) {
        return ("Unavailable".into(), "unavailable".into(), true);
    }
    let label = if compatibility == "unsupported" {
        "Unsupported"
    } else if compatibility == "candidate" {
        "Candidate"
    } else {
        "Ready"
    };
    (label.into(), "ready".into(), false)
}

/// Builds one installed-printer record from a spooler row. An empty name is dropped.
pub fn map_enumerated_queue(raw: &EnumeratedQueue) -> Option<InstalledPrinter> {
    let name = raw.name.trim();
    if name.is_empty() {
        return None;
    }
    let classed = crate::printer_discovery::classify(&raw.driver, &raw.port);
    let (status_label, availability, unavailable) = describe_queue(
        raw.status,
        raw.attributes,
        &classed.connection,
        classed.compatibility.as_str(),
        raw.opened,
    );
    let openable = raw.opened.unwrap_or(true);
    let transport = crate::printer_discovery::transport_for(&raw.driver, &raw.port, &raw.default_datatype);
    let drawer = classed.supports_drawer_kick && availability != "virtual" && !unavailable;
    Some(InstalledPrinter {
        name: name.to_string(),
        driver: raw.driver.clone(),
        port: raw.port.clone(),
        status: raw.status,
        status_label,
        unavailable,
        compatibility: classed.compatibility.as_str().to_string(),
        supports_drawer_kick: drawer,
        connection: classed.connection,
        profile_id: classed.profile_id,
        manufacturer: raw.manufacturer.trim().to_string(),
        identity: raw.identity.trim().to_string(),
        openable,
        availability,
        print_transport: transport.as_str().to_string(),
        default_datatype: raw.default_datatype.trim().to_string(),
        driver_version: raw.driver_version.trim().to_string(),
        capabilities: if crate::printer_discovery::is_text_only_driver(&raw.driver) {
            "Text only. The receipt is sent as text, not as a picture. Drawer kick is not verified.".into()
        } else {
            crate::printer_discovery::capability_summary(transport, drawer)
        },
    })
}

/// Keeps the first row for each exact queue name.
pub fn dedupe_printers(printers: Vec<InstalledPrinter>) -> Vec<InstalledPrinter> {
    let mut seen = std::collections::HashSet::new();
    printers
        .into_iter()
        .filter(|printer| seen.insert(printer.name.clone()))
        .collect()
}

/// A queue the spooler could not open is not a connected receipt printer.
pub fn queue_open_error(name: &str, opened: bool) -> Result<(), String> {
    if opened {
        Ok(())
    } else {
        let _ = name;
        Err(crate::printer_discovery::QUEUE_CLOSED.into())
    }
}

/// Exact queue name only. A different installed printer is not a match.
pub fn find_queue<'a>(configured: &str, queues: &'a [InstalledPrinter]) -> Option<&'a InstalledPrinter> {
    let wanted = configured.trim();
    if wanted.is_empty() {
        return None;
    }
    queues.iter().find(|queue| queue.name == wanted)
}

#[derive(Debug)]
pub struct KickPlan {
    pub queue: String,
    pub bytes: Vec<u8>,
}

pub fn plan_drawer_kick(
    settings: &PrinterSettings,
    queues: &[InstalledPrinter],
    now: i64,
    last_attempt: i64,
) -> Result<KickPlan, String> {
    if settings.transport == "none" {
        return Err("No receipt printer is configured. Open Register settings to add one.".into());
    }
    if settings.transport == "serial" || settings.transport == "ble" {
        return Err(crate::printer_profile::DRAWER_UNVERIFIED.into());
    }
    if !kick_allowed(now, last_attempt, KICK_GAP_SECS) {
        return Err("Wait a moment before kicking the drawer again.".into());
    }
    if settings.transport == "tcp" {
        let pulse = crate::cash_drawer::require_pulse(settings, None)?;
        let mut bytes = vec![0x1b, b'@'];
        bytes.extend(pulse);
        return Ok(KickPlan {
            queue: settings.address.trim().to_string(),
            bytes,
        });
    }
    if settings.transport != "windows" {
        return Err("Unknown printer connection.".into());
    }
    let Some(queue) = find_queue(&settings.address, queues) else {
        return Err(missing_printer_message(settings.address.trim()));
    };
    if queue.availability == "virtual" || queue.compatibility == "unsupported" {
        return Err(crate::printer_discovery::UNSUPPORTED_METHOD.into());
    }
    if queue.unavailable || queue.availability == "offline" || queue.availability == "unavailable" {
        return Err(format!(
            "Windows printer \"{}\" is unavailable ({}).",
            queue.name, queue.status_label
        ));
    }
    if !queue.openable {
        return Err(queue_open_error(&queue.name, false).unwrap_err());
    }
    let known = queue.supports_drawer_kick && queue.compatibility == "compatible";
    if !known {
        if crate::cash_drawer::lacks_kick_circuit(&queue.driver, &queue.port) && !settings.drawer_profile.trim().is_empty() {
            let message = match crate::cash_drawer::require_pulse(
                settings,
                Some(crate::cash_drawer::KickHost {
                    driver: &queue.driver,
                    port: &queue.port,
                }),
            ) {
                Ok(_) => "This printer has no known drawer-kick profile. Test drawer kick stays off.".into(),
                Err(message) => message,
            };
            return Err(message);
        }
        return Err("This printer has no known drawer-kick profile. Test drawer kick stays off.".into());
    }
    let pulse = crate::cash_drawer::require_pulse(
        settings,
        Some(crate::cash_drawer::KickHost {
            driver: &queue.driver,
            port: &queue.port,
        }),
    )?;
    let mut bytes = vec![0x1b, b'@'];
    bytes.extend(pulse);
    Ok(KickPlan {
        queue: queue.name.clone(),
        bytes,
    })
}

pub fn missing_printer_message(name: &str) -> String {
    format!(
        "Configured receipt printer \"{name}\" was not found. Select an installed receipt printer to enable cash drawer control."
    )
}

fn now_secs() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|elapsed| elapsed.as_secs() as i64)
        .unwrap_or(0)
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PrinterProbe {
    pub configured: bool,
    pub transport: String,
    pub address: String,
    pub reachable: bool,
    pub reach_error: Option<String>,
    pub last_ok_at: Option<i64>,
    pub last_error: Option<String>,
    pub last_error_at: Option<i64>,
    pub last_kick_ok_at: Option<i64>,
    pub last_kick_error: Option<String>,
    pub last_kick_attempt_at: Option<i64>,
    pub drawer_kick: bool,
    pub printing: bool,
    /// not_configured, missing, offline, unavailable, ready.
    pub printer_status: String,
    pub driver: Option<String>,
    pub port: Option<String>,
    pub discovered_at: Option<i64>,
    /// Mechanical open/closed is never inferred from a kick. This stays "not_reported".
    pub drawer_open_state: String,
    pub compatibility: String,
    pub supports_drawer_kick: bool,
    pub connection: String,
    pub discovery_outcome: String,
    pub previous_address: String,
    pub auto_discover: bool,
    pub model: String,
    pub driver_version: Option<String>,
    /// escpos, windows-gdi, or none. Empty when no queue metadata is available.
    pub print_transport: String,
    pub capabilities: String,
    pub diagnostic: Option<PrintDiagnostic>,
    /// Saved drawer profile id. Empty until a cashier chooses one.
    #[serde(default)]
    pub drawer_profile: String,
    /// Confirmed drawer-port voltage, or empty when unconfirmed.
    #[serde(default)]
    pub host_voltage: String,
    #[serde(default)]
    pub open_on_non_cash: bool,
}

static JOB_SEQ: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(1);

/// One user-requested print. A later retry is a new row. An accepted row is not sent again, because the paper may already be out.
pub fn record_print_job(
    db: &Db,
    invoice: &str,
    printer_id: &str,
    connection: &str,
    protocol: &str,
    transport: &str,
    payload_type: &str,
    payload_bytes: usize,
    phase: &crate::printer_profile::JobPhase,
    error: Option<&str>,
) -> Result<(), String> {
    if crate::printer_profile::retry_when_output_unknown() {
        return Err("An unverified print is not sent again.".into());
    }
    let now = now_secs();
    let seq = JOB_SEQ.fetch_add(1, Ordering::Relaxed);
    let id = format!("{now}-{seq}-{invoice}");
    let status = match phase {
        crate::printer_profile::JobPhase::AcceptedUnverified => "accepted-unverified",
        crate::printer_profile::JobPhase::Failed => "failed",
        _ => "submitted",
    };
    db.transaction(|tx| {
        tx.execute(
            "INSERT INTO printer_jobs (
                id, invoice_id, printer_id, transport, payload_type, created_at, status, attempts, error, verification,
                connection, protocol, payload_bytes
             ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, 1, ?8, 'physical-not-verified', ?9, ?10, ?11)",
            params![
                id,
                invoice,
                printer_id,
                transport,
                payload_type,
                now,
                status,
                error.unwrap_or(""),
                connection,
                protocol,
                payload_bytes as i64
            ],
        )
        .map_err(|err| err.to_string())?;
        Ok(())
    })
}

fn remember_print(db: &Db, error: Option<&str>) {
    let now = now_secs();
    let _ = db.transaction(|tx| {
        let saved = if let Some(message) = error {
            tx.execute(
                "INSERT INTO printer_status (id, last_error, last_error_at) VALUES (1, ?1, ?2)
                 ON CONFLICT(id) DO UPDATE SET last_error = excluded.last_error, last_error_at = excluded.last_error_at",
                params![message, now],
            )
        } else {
            tx.execute(
                "INSERT INTO printer_status (id, last_ok_at, last_error, last_error_at) VALUES (1, ?1, NULL, NULL)
                 ON CONFLICT(id) DO UPDATE SET last_ok_at = excluded.last_ok_at, last_error = NULL, last_error_at = NULL",
                params![now],
            )
        };
        saved.map_err(|err| err.to_string())?;
        Ok(())
    });
}

fn remember_kick(db: &Db, error: Option<&str>) {
    let now = now_secs();
    let _ = db.transaction(|tx| {
        let saved = if let Some(message) = error {
            tx.execute(
                "INSERT INTO printer_status (id, last_kick_error, last_kick_attempt_at) VALUES (1, ?1, ?2)
                 ON CONFLICT(id) DO UPDATE SET last_kick_error = excluded.last_kick_error,
                    last_kick_ok_at = NULL, last_kick_attempt_at = excluded.last_kick_attempt_at",
                params![message, now],
            )
        } else {
            tx.execute(
                "INSERT INTO printer_status (id, last_kick_ok_at, last_kick_error, last_kick_attempt_at) VALUES (1, ?1, NULL, ?1)
                 ON CONFLICT(id) DO UPDATE SET last_kick_ok_at = excluded.last_kick_ok_at, last_kick_error = NULL,
                    last_kick_attempt_at = excluded.last_kick_attempt_at",
                params![now],
            )
        };
        saved.map_err(|err| err.to_string())?;
        Ok(())
    });
}

fn status_row(db: &Db) -> (Option<i64>, Option<String>, Option<i64>, Option<i64>, Option<String>, Option<i64>) {
    db.read(|conn| {
        conn.query_row(
            "SELECT last_ok_at, last_error, last_error_at, last_kick_ok_at, last_kick_error, last_kick_attempt_at
             FROM printer_status WHERE id = 1",
            [],
            |row| {
                Ok((
                    row.get(0)?,
                    row.get(1)?,
                    row.get(2)?,
                    row.get(3)?,
                    row.get(4)?,
                    row.get(5)?,
                ))
            },
        )
        .optional()
        .map(|row| row.unwrap_or((None, None, None, None, None, None)))
        .map_err(|err| err.to_string())
    })
    .unwrap_or((None, None, None, None, None, None))
}

fn probe_tcp(address: &str) -> Result<(), String> {
    let target = crate::printer_profile::tcp_endpoint(address)?;
    let socket = target
        .to_socket_addrs()
        .map_err(|err| format!("Printer address {target} is invalid: {err}"))?
        .next()
        .ok_or_else(|| format!("Printer address {target} did not resolve."))?;
    TcpStream::connect_timeout(&socket, Duration::from_secs(2))
        .map(|_| ())
        .map_err(|err| format!("Printer at {target} is unreachable: {err}"))
}

fn finish_probe(
    settings: PrinterSettings,
    history: (Option<i64>, Option<String>, Option<i64>, Option<i64>, Option<String>, Option<i64>),
    reachable: bool,
    reach_error: Option<String>,
    printer_status: &str,
    driver: Option<String>,
    port: Option<String>,
) -> PrinterProbe {
    PrinterProbe {
        configured: settings.transport != "none",
        transport: settings.transport,
        address: settings.address,
        reachable,
        reach_error,
        last_ok_at: history.0,
        last_error: history.1,
        last_error_at: history.2,
        last_kick_ok_at: history.3,
        last_kick_error: history.4,
        last_kick_attempt_at: history.5,
        drawer_kick: settings.drawer_kick,
        printing: PRINTING.load(Ordering::Relaxed),
        printer_status: printer_status.to_string(),
        driver,
        port,
        discovered_at: Some(now_secs()),
        drawer_open_state: "not_reported".to_string(),
        compatibility: settings.saved_model.clone(),
        supports_drawer_kick: false,
        connection: crate::printer_discovery::connection_kind(&settings.saved_port).to_string(),
        discovery_outcome: String::new(),
        previous_address: settings.previous_address.clone(),
        auto_discover: settings.auto_discover,
        model: settings.saved_model.clone(),
        driver_version: None,
        print_transport: crate::printer_discovery::select_transport(&settings.saved_driver, &settings.saved_port)
            .as_str()
            .to_string(),
        capabilities: String::new(),
        diagnostic: last_diagnostic(),
        drawer_profile: settings.drawer_profile.clone(),
        host_voltage: settings.host_voltage.clone(),
        open_on_non_cash: settings.open_on_non_cash,
    }
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PrintStage {
    pub stage: String,
    pub result: String,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PrintDiagnostic {
    pub recorded_at: i64,
    pub document_number: String,
    pub line_count: u32,
    pub subtotal_cents: i64,
    pub tax_cents: i64,
    pub discount_cents: i64,
    pub total_cents: i64,
    pub width: u32,
    pub height: u32,
    pub ink_bytes: usize,
    pub payload_bytes: usize,
    pub payload_type: String,
    pub encoding: String,
    pub queue: String,
    pub driver: String,
    pub port: String,
    pub transport: String,
    pub submitted: bool,
    pub native_error: Option<String>,
    pub stages: Vec<PrintStage>,
}

fn last_diagnostic() -> Option<PrintDiagnostic> {
    LAST_DIAGNOSTIC.lock().ok().and_then(|slot| slot.clone())
}

fn store_diagnostic(diagnostic: PrintDiagnostic) {
    if let Ok(mut slot) = LAST_DIAGNOSTIC.lock() {
        *slot = Some(diagnostic);
    }
}

pub fn refresh_discovery(db: &Db) -> Result<crate::printer_discovery::DiscoveryDecision, String> {
    use crate::printer_discovery::{decide, Discovered, SavedPrinter};
    let settings = load(db)?;
    if settings.transport == "tcp" || settings.transport == "serial" || settings.transport == "ble" {
        return Ok(DiscoveryKept::tcp(&settings));
    }
    let queues = known_windows_printers().unwrap_or_default();
    let devices: Vec<Discovered> = queues
        .iter()
        .map(|queue| Discovered {
            name: queue.name.clone(),
            driver: queue.driver.clone(),
            port: queue.port.clone(),
            unavailable: queue.unavailable,
            classed: crate::printer_discovery::classify(&queue.driver, &queue.port),
        })
        .collect();
    let saved = SavedPrinter {
        address: settings.address.clone(),
        previous_address: settings.previous_address.clone(),
        driver: settings.saved_driver.clone(),
        port: settings.saved_port.clone(),
        auto_discover: settings.auto_discover,
        user_selected: settings.user_selected,
    };
    let decision = decide(&saved, &devices);
    if decision.changed {
        let previous_address = settings.address.clone();
        let mut next = settings;
        if decision.address != previous_address {
            next.saved_identity.clear();
        }
        if decision.outcome == "auto" || decision.outcome == "restored" {
            next.transport = "windows".into();
        }
        next.address = decision.address.clone();
        next.previous_address = decision.previous_address.clone();
        next.saved_driver = decision.driver.clone();
        next.saved_port = decision.port.clone();
        next.saved_model = decision.model.clone();
        next.user_selected = decision.user_selected;
        if next.transport == "none" && next.address.trim().is_empty() {
            return Ok(decision);
        }
        if next.transport != "none" && next.address.trim().is_empty() {
            next.transport = "none".into();
        }
        save(db, &next)?;
    }
    Ok(decision)
}

struct DiscoveryKept;

impl DiscoveryKept {
    fn tcp(settings: &PrinterSettings) -> crate::printer_discovery::DiscoveryDecision {
        crate::printer_discovery::DiscoveryDecision {
            address: settings.address.clone(),
            previous_address: settings.previous_address.clone(),
            driver: settings.saved_driver.clone(),
            port: settings.saved_port.clone(),
            model: settings.saved_model.clone(),
            user_selected: settings.user_selected,
            outcome: "manual".into(),
            drawer_supported: false,
            changed: false,
        }
    }
}

fn annotate(mut probe: PrinterProbe, decision: &crate::printer_discovery::DiscoveryDecision, queue: Option<&InstalledPrinter>) -> PrinterProbe {
    probe.discovery_outcome = decision.outcome.clone();
    probe.previous_address = decision.previous_address.clone();
    probe.model = decision.model.clone();
    probe.supports_drawer_kick = decision.drawer_supported;
    if let Some(queue) = queue {
        probe.compatibility = queue.compatibility.clone();
        probe.supports_drawer_kick = queue.supports_drawer_kick && !queue.unavailable;
        probe.connection = queue.connection.clone();
        probe.driver = Some(queue.driver.clone());
        probe.port = Some(queue.port.clone());
        probe.model = if queue.driver.is_empty() { decision.model.clone() } else { queue.driver.clone() };
        probe.print_transport = queue.print_transport.clone();
        probe.capabilities = queue.capabilities.clone();
        if !queue.driver_version.is_empty() {
            probe.driver_version = Some(queue.driver_version.clone());
        }
    } else if probe.printer_status == "missing" || probe.printer_status == "not_configured" {
        probe.compatibility = if probe.configured { "not_found".into() } else { "unsupported".into() };
        probe.supports_drawer_kick = false;
    }
    probe
}

/// Opens the configured printer and closes it again. A successful open is reachability, not proof it can print.
/// Discovery may persist a single compatible printer. It never sends a drawer pulse.
pub fn probe(db: &Db) -> Result<PrinterProbe, String> {
    let decision = refresh_discovery(db)?;
    let settings = load(db)?;
    let history = status_row(db);
    if settings.transport == "none" {
        return Ok(annotate(finish_probe(settings, history, false, None, "not_configured", None, None), &decision, None));
    }
    if settings.transport == "tcp" {
        let reach = probe_tcp(&settings.address);
        let ok = reach.is_ok();
        let mut probe = finish_probe(
            settings,
            history,
            ok,
            if ok { Some(crate::printer_profile::TCP_OPEN_NOTICE.into()) } else { reach.err() },
            if ok { "candidate" } else { "unavailable" },
            None,
            None,
        );
        probe.compatibility = "candidate".into();
        probe.supports_drawer_kick = false;
        probe.print_transport = "escpos".into();
        probe.connection = "Network".into();
        probe.capabilities = crate::printer_profile::TCP_OPEN_NOTICE.into();
        return Ok(annotate(probe, &decision, None));
    }
    if settings.transport == "serial" {
        let kind = settings.connection_kind.clone();
        let opened = probe_serial(&settings.address, &kind);
        let ok = opened.is_ok();
        let mut probe = finish_probe(
            settings,
            history,
            ok,
            opened.err(),
            if ok { "candidate" } else { "unavailable" },
            None,
            None,
        );
        probe.compatibility = "candidate".into();
        probe.supports_drawer_kick = false;
        probe.print_transport = "escpos".into();
        probe.connection = if kind == "serial" { "Serial".into() } else { "Bluetooth Classic".into() };
        probe.capabilities = crate::printer_profile::serial_capability(&kind).into();
        return Ok(annotate(probe, &decision, None));
    }
    if settings.transport == "ble" {
        let mut probe = finish_probe(
            settings,
            history,
            false,
            Some(crate::printer_profile::BLE_UNSUPPORTED.into()),
            "unavailable",
            None,
            None,
        );
        probe.compatibility = "unsupported".into();
        probe.supports_drawer_kick = false;
        probe.print_transport = "none".into();
        probe.connection = "Bluetooth Low Energy".into();
        probe.capabilities = crate::printer_profile::BLE_UNSUPPORTED.into();
        return Ok(annotate(probe, &decision, None));
    }
    if settings.transport != "windows" {
        return Ok(annotate(
            finish_probe(
                settings,
                history,
                false,
                Some("Unknown printer connection.".into()),
                "unavailable",
                None,
                None,
            ),
            &decision,
            None,
        ));
    }
    let queues = known_windows_printers().unwrap_or_default();
    let Some(queue) = find_queue(&settings.address, &queues).cloned() else {
        return Ok(annotate(
            finish_probe(
                settings.clone(),
                history,
                false,
                Some(missing_printer_message(settings.address.trim())),
                "missing",
                None,
                None,
            ),
            &decision,
            None,
        ));
    };
    if queue.availability == "virtual" || queue.compatibility == "unsupported" {
        return Ok(annotate(
            finish_probe(
                settings,
                history,
                false,
                Some(crate::printer_discovery::UNSUPPORTED_METHOD.into()),
                "unavailable",
                Some(queue.driver.clone()),
                Some(queue.port.clone()),
            ),
            &decision,
            Some(&queue),
        ));
    }
    if queue.unavailable {
        let offline = queue.availability == "offline" || queue.status & 0x80 != 0;
        let status = if offline { "offline" } else { "unavailable" };
        let message = if offline {
            crate::printer_discovery::OFFLINE_NOTICE.to_string()
        } else if !queue.openable {
            crate::printer_discovery::QUEUE_CLOSED.to_string()
        } else {
            format!("Windows printer \"{}\" is unavailable ({}).", queue.name, queue.status_label)
        };
        return Ok(annotate(
            finish_probe(
                settings,
                history,
                false,
                Some(message),
                status,
                Some(queue.driver.clone()),
                Some(queue.port.clone()),
            ),
            &decision,
            Some(&queue),
        ));
    }
    let opened = probe_spooler(&queue.name);
    let ok = opened.is_ok();
    let (status, reach_error) = if !ok {
        let detail = opened.err().unwrap_or_default();
        let message = if detail.is_empty() {
            crate::printer_discovery::QUEUE_CLOSED.to_string()
        } else {
            format!("{} {detail}", crate::printer_discovery::QUEUE_CLOSED)
        };
        ("unavailable", Some(message))
    } else if queue.compatibility == "compatible" {
        ("ready", None)
    } else {
        (
            "candidate",
            Some(crate::printer_discovery::candidate_notice(&queue.name, &queue.driver)),
        )
    };
    let explicit = settings.protocol.clone();
    let mut probe = annotate(
        finish_probe(
            settings,
            history,
            ok,
            reach_error,
            status,
            Some(queue.driver.clone()),
            Some(queue.port.clone()),
        ),
        &decision,
        Some(&queue),
    );
    let selected = crate::printer_discovery::select_output(&queue.driver, &queue.port, &queue.default_datatype, &explicit);
    if selected != crate::printer_discovery::PrintTransport::None {
        probe.print_transport = selected.as_str().into();
    }
    if explicit == "escpos" && selected == crate::printer_discovery::PrintTransport::EscPos && queue.compatibility != "compatible" {
        probe.capabilities = "Generic ESC/POS was selected for this model. It is not verified, and the drawer is not kicked.".into();
        probe.supports_drawer_kick = false;
    }
    Ok(probe)
}

/// A settings sample is not a sale. It must not open the drawer even if the caller asks.
pub fn sample_document(number: &str) -> bool {
    let folded = number.trim().to_ascii_uppercase();
    folded.starts_with("SAMPLE") || folded == "TEST" || folded.starts_with("TEST-")
}

pub fn ink_bytes(data: &[u8]) -> usize {
    data.iter().filter(|byte| **byte != 0).count()
}

/// Rejects a raster that cannot be printed. An all-white image used to become a feed-and-cut with no text.
pub fn validate_raster(job: &RasterJob) -> Result<(), String> {
    let row_bytes = job.width.div_ceil(8);
    if job.width == 0 || job.height == 0 || job.data.len() != (row_bytes * job.height) as usize {
        return Err("The receipt image is malformed.".into());
    }
    if ink_bytes(&job.data) == 0 {
        return Err(crate::printer_discovery::RENDER_FAILED.into());
    }
    Ok(())
}

pub fn escpos_raster(job: &RasterJob, copies: u32, kick: &[u8]) -> Result<Vec<u8>, String> {
    validate_raster(job)?;
    let row_bytes = job.width.div_ceil(8);
    let mut out = Vec::with_capacity(job.data.len() * copies as usize + 64);
    for copy in 0..copies.max(1) {
        out.extend_from_slice(&[0x1b, b'@']);
        let mut start = 0;
        while start < job.height {
            let rows = (job.height - start).min(BAND_ROWS);
            out.extend_from_slice(&[0x1d, b'v', b'0', 0]);
            out.extend_from_slice(&[(row_bytes & 0xff) as u8, (row_bytes >> 8) as u8]);
            out.extend_from_slice(&[(rows & 0xff) as u8, (rows >> 8) as u8]);
            let offset = (start * row_bytes) as usize;
            out.extend_from_slice(&job.data[offset..offset + (rows * row_bytes) as usize]);
            start += rows;
        }
        out.extend_from_slice(&[0x1b, b'd', 4, 0x1d, b'V', 66, 0]);
        if copy == 0 && job.kick_drawer && !kick.is_empty() {
            out.extend_from_slice(kick);
        }
    }
    Ok(out)
}

pub fn send(settings: &PrinterSettings, bytes: &[u8]) -> Result<(), String> {
    let adapter = crate::printer_profile::adapter_for(&settings.transport, &settings.connection_kind);
    match adapter {
        crate::printer_profile::Adapter::NetworkTcp => send_tcp(&settings.address, bytes),
        crate::printer_profile::Adapter::WindowsSpooler | crate::printer_profile::Adapter::UsbViaSpooler => {
            send_spooler(&settings.address, bytes)
        }
        crate::printer_profile::Adapter::BluetoothClassic | crate::printer_profile::Adapter::SerialCom => {
            send_serial(&settings.address, &settings.connection_kind, bytes)
        }
        crate::printer_profile::Adapter::BluetoothBle => Err(crate::printer_profile::BLE_UNSUPPORTED.into()),
        crate::printer_profile::Adapter::Vendor => Err(crate::printer_profile::NO_VENDOR_ADAPTER.into()),
        crate::printer_profile::Adapter::None => Err("No receipt printer is configured. Open Register settings to add one.".into()),
    }
}

fn send_tcp(address: &str, bytes: &[u8]) -> Result<(), String> {
    let target = crate::printer_profile::tcp_endpoint(address)?;
    let socket = target
        .to_socket_addrs()
        .map_err(|err| format!("Printer address {target} is invalid: {err}"))?
        .next()
        .ok_or_else(|| format!("Printer address {target} did not resolve."))?;
    let mut stream = TcpStream::connect_timeout(&socket, Duration::from_secs(4))
        .map_err(|err| format!("Printer at {target} is unreachable: {err}"))?;
    stream
        .set_write_timeout(Some(Duration::from_secs(8)))
        .map_err(|err| err.to_string())?;
    stream
        .write_all(bytes)
        .map_err(|err| format!("Printing failed: {err}"))?;
    stream.flush().map_err(|err| err.to_string())
}

fn probe_serial(port: &str, connection_kind: &str) -> Result<(), String> {
    let normalized = crate::printer_profile::normalize_com(port)?;
    close_serial(open_serial(&normalized, connection_kind)?)
}

#[cfg(windows)]
fn close_serial(handle: windows_sys::Win32::Foundation::HANDLE) -> Result<(), String> {
    use windows_sys::Win32::Foundation::CloseHandle;
    unsafe { CloseHandle(handle) };
    Ok(())
}

#[cfg(not(windows))]
fn close_serial(_handle: ()) -> Result<(), String> {
    Ok(())
}

fn send_serial(port: &str, connection_kind: &str, bytes: &[u8]) -> Result<(), String> {
    let normalized = crate::printer_profile::normalize_com(port)?;
    let handle = open_serial(&normalized, connection_kind)?;
    write_serial(handle, connection_kind, bytes)
}

#[cfg(windows)]
fn open_serial(port: &str, connection_kind: &str) -> Result<windows_sys::Win32::Foundation::HANDLE, String> {
    use windows_sys::Win32::Devices::Communication::{SetCommTimeouts, COMMTIMEOUTS};
    use windows_sys::Win32::Foundation::{CloseHandle, GENERIC_READ, GENERIC_WRITE, INVALID_HANDLE_VALUE};
    use windows_sys::Win32::Storage::FileSystem::{CreateFileW, FILE_ATTRIBUTE_NORMAL, OPEN_EXISTING};

    let path = format!(r"\\.\{port}");
    let wide: Vec<u16> = path.encode_utf16().chain(std::iter::once(0)).collect();
    let handle = unsafe {
        CreateFileW(
            wide.as_ptr(),
            GENERIC_READ | GENERIC_WRITE,
            0,
            std::ptr::null(),
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL,
            std::ptr::null_mut(),
        )
    };
    if handle == INVALID_HANDLE_VALUE || handle.is_null() {
        return Err(crate::printer_profile::serial_open_error(connection_kind, port));
    }
    let timeouts = COMMTIMEOUTS {
        ReadIntervalTimeout: 50,
        ReadTotalTimeoutMultiplier: 0,
        ReadTotalTimeoutConstant: 1000,
        WriteTotalTimeoutMultiplier: 0,
        WriteTotalTimeoutConstant: 8000,
    };
    let armed = unsafe { SetCommTimeouts(handle, &timeouts) };
    if armed == 0 {
        unsafe { CloseHandle(handle) };
        return Err(crate::printer_profile::serial_timeout_error(connection_kind, port));
    }
    Ok(handle)
}

#[cfg(windows)]
fn write_serial(handle: windows_sys::Win32::Foundation::HANDLE, connection_kind: &str, bytes: &[u8]) -> Result<(), String> {
    use windows_sys::Win32::Foundation::CloseHandle;
    use windows_sys::Win32::Storage::FileSystem::WriteFile;

    let result = unsafe {
        let mut written = 0u32;
        let ok = WriteFile(handle, bytes.as_ptr(), bytes.len() as u32, &mut written, std::ptr::null_mut());
        CloseHandle(handle);
        if ok == 0 || written as usize != bytes.len() {
            Err(crate::printer_profile::serial_write_error(connection_kind))
        } else {
            Ok(())
        }
    };
    result
}

#[cfg(not(windows))]
fn open_serial(port: &str, connection_kind: &str) -> Result<(), String> {
    Err(crate::printer_profile::serial_platform_error(connection_kind, port))
}

#[cfg(not(windows))]
fn write_serial(_handle: (), connection_kind: &str, _bytes: &[u8]) -> Result<(), String> {
    Err(crate::printer_profile::serial_write_error(connection_kind))
}

/// COM ports that are not Windows Bluetooth modems. Listing does not open the port or send bytes.
pub fn list_serial_ports() -> Vec<crate::printer_profile::ComPort> {
    bluetooth_com_names()
        .into_iter()
        .filter_map(|(device, com)| {
            if crate::printer_profile::com_connection_kind(&device) != "serial" {
                return None;
            }
            let port = crate::printer_profile::normalize_com(&com).ok()?;
            Some(crate::printer_profile::ComPort {
                device,
                port,
                connection: "serial".into(),
            })
        })
        .collect()
}

/// Paired Bluetooth Classic ports that Windows exposed as serial devices. No pairing and no bytes are sent.
pub fn list_bluetooth_serial() -> Vec<crate::printer_profile::BluetoothSerial> {
    bluetooth_com_names()
        .into_iter()
        .filter_map(|(device, com)| crate::printer_profile::bluetooth_serial_port(&device, &com))
        .collect()
}

#[cfg(windows)]
fn bluetooth_com_names() -> Vec<(String, String)> {
    use windows_sys::Win32::Foundation::ERROR_NO_MORE_ITEMS;
    use windows_sys::Win32::System::Registry::{
        RegCloseKey, RegEnumValueW, RegOpenKeyExW, HKEY, HKEY_LOCAL_MACHINE, KEY_READ, REG_SZ,
    };

    let path: Vec<u16> = "HARDWARE\\DEVICEMAP\\SERIALCOMM".encode_utf16().chain(std::iter::once(0)).collect();
    let mut key: HKEY = std::ptr::null_mut();
    let opened = unsafe { RegOpenKeyExW(HKEY_LOCAL_MACHINE, path.as_ptr(), 0, KEY_READ, &mut key) };
    if opened != 0 || key.is_null() {
        return Vec::new();
    }
    let mut rows = Vec::new();
    let mut index = 0u32;
    loop {
        let mut name = [0u16; 256];
        let mut name_len = name.len() as u32;
        let mut kind = 0u32;
        let mut data = [0u16; 64];
        let mut data_len = (data.len() * 2) as u32;
        let status = unsafe {
            RegEnumValueW(
                key,
                index,
                name.as_mut_ptr(),
                &mut name_len,
                std::ptr::null_mut(),
                &mut kind,
                data.as_mut_ptr() as *mut u8,
                &mut data_len,
            )
        };
        if status == ERROR_NO_MORE_ITEMS {
            break;
        }
        if status != 0 {
            break;
        }
        index += 1;
        if kind != REG_SZ || name_len == 0 {
            continue;
        }
        let device = String::from_utf16_lossy(&name[..name_len as usize]);
        let value_chars = (data_len as usize / 2).saturating_sub(1);
        let com = String::from_utf16_lossy(&data[..value_chars.min(data.len())]);
        rows.push((device, com.trim_end_matches('\0').to_string()));
    }
    unsafe { RegCloseKey(key) };
    rows
}

#[cfg(not(windows))]
fn bluetooth_com_names() -> Vec<(String, String)> {
    Vec::new()
}

#[cfg(windows)]
fn windows_open_error(name: &str) -> String {
    use windows_sys::Win32::Foundation::GetLastError;
    let code = unsafe { GetLastError() };
    if code == 1801 {
        return missing_printer_message(name);
    }
    if code == 5 {
        return format!("Windows printer \"{name}\" is unavailable (access denied, {code}).");
    }
    format!("Windows printer \"{name}\" could not be opened (Windows error {code}).")
}

pub fn spooler_timeout_message() -> &'static str {
    "The printer did not accept the job before the timeout. The drawer was not confirmed."
}

#[cfg(windows)]
fn send_spooler(name: &str, bytes: &[u8]) -> Result<(), String> {
    let owned_name = name.to_string();
    let owned_bytes = bytes.to_vec();
    let (sender, receiver) = std::sync::mpsc::channel();
    std::thread::Builder::new()
        .name("receipt-spooler".into())
        .spawn(move || {
            let _ = sender.send(write_spooler(&owned_name, &owned_bytes));
        })
        .map_err(|err| err.to_string())?;
    match receiver.recv_timeout(SPOOLER_TIMEOUT) {
        Ok(result) => result,
        Err(std::sync::mpsc::RecvTimeoutError::Timeout) => Err(spooler_timeout_message().into()),
        Err(std::sync::mpsc::RecvTimeoutError::Disconnected) => {
            Err("The printer connection ended before a result.".into())
        }
    }
}

#[cfg(windows)]
fn write_spooler(name: &str, bytes: &[u8]) -> Result<(), String> {
    use windows_sys::Win32::Graphics::Printing::{
        ClosePrinter, EndDocPrinter, EndPagePrinter, OpenPrinterW, StartDocPrinterW,
        StartPagePrinter, WritePrinter, DOC_INFO_1W, PRINTER_HANDLE,
    };

    fn wide(value: &str) -> Vec<u16> {
        value.encode_utf16().chain(std::iter::once(0)).collect()
    }
    let printer = wide(name);
    let document = wide("ai-pos receipt");
    let datatype = wide("RAW");
    let mut handle = PRINTER_HANDLE::default();
    // SAFETY: every pointer passed below references a live, NUL-terminated buffer owned by this frame, and the
    // handle is closed on every exit path once OpenPrinterW succeeds.
    unsafe {
        if OpenPrinterW(printer.as_ptr(), &mut handle, std::ptr::null()) == 0 {
            return Err(windows_open_error(name));
        }
        let info = DOC_INFO_1W {
            pDocName: document.as_ptr() as *mut u16,
            pOutputFile: std::ptr::null_mut(),
            pDatatype: datatype.as_ptr() as *mut u16,
        };
        let result = (|| {
            if StartDocPrinterW(handle, 1, &info as *const DOC_INFO_1W) == 0 {
                return Err("The spooler refused the print job.".to_string());
            }
            StartPagePrinter(handle);
            let mut written = 0u32;
            let ok = WritePrinter(
                handle,
                bytes.as_ptr().cast(),
                bytes.len() as u32,
                &mut written,
            );
            EndPagePrinter(handle);
            EndDocPrinter(handle);
            if ok == 0 || written as usize != bytes.len() {
                return Err("The spooler did not accept the whole receipt.".to_string());
            }
            Ok(())
        })();
        ClosePrinter(handle);
        result
    }
}

#[cfg(not(windows))]
fn send_spooler(_name: &str, _bytes: &[u8]) -> Result<(), String> {
    Err("Windows printers are only available on Windows; use a network printer.".into())
}

#[cfg(windows)]
fn probe_spooler(name: &str) -> Result<(), String> {
    use windows_sys::Win32::Graphics::Printing::{ClosePrinter, OpenPrinterW, PRINTER_HANDLE};

    let printer: Vec<u16> = name.encode_utf16().chain(std::iter::once(0)).collect();
    let mut handle = PRINTER_HANDLE::default();
    unsafe {
        if OpenPrinterW(printer.as_ptr(), &mut handle, std::ptr::null()) == 0 {
            return Err(windows_open_error(name));
        }
        ClosePrinter(handle);
    }
    Ok(())
}

#[cfg(not(windows))]
fn probe_spooler(name: &str) -> Result<(), String> {
    Err(format!(
        "Windows printer \"{name}\" cannot be checked on this system."
    ))
}

#[cfg(windows)]
fn wide_text(ptr: *const u16) -> String {
    if ptr.is_null() {
        return String::new();
    }
    let mut len = 0usize;
    unsafe {
        while *ptr.add(len) != 0 {
            len += 1;
            if len > 512 {
                break;
            }
        }
        String::from_utf16_lossy(std::slice::from_raw_parts(ptr, len))
    }
}

struct QueueInspection {
    manufacturer: String,
    identity: String,
    opened: bool,
    datatype: String,
    driver_version: String,
}

pub fn format_driver_version(value: u64) -> String {
    if value == 0 {
        return String::new();
    }
    let major = (value >> 48) & 0xffff;
    let minor = (value >> 32) & 0xffff;
    let build = value & 0xffff_ffff;
    format!("{major}.{minor}.{build}")
}

/// Opens one queue, reads the driver manufacturer, datatype, version, and object GUID, then closes it. No bytes are written.
#[cfg(windows)]
fn inspect_queue(name: &str) -> QueueInspection {
    use windows_sys::Win32::Graphics::Printing::{
        ClosePrinter, GetPrinterDriverW, GetPrinterW, OpenPrinterW, DRIVER_INFO_6W, PRINTER_HANDLE, PRINTER_INFO_7W,
    };

    fn read_block(fill: impl Fn(*mut u8, u32, *mut u32) -> i32) -> Option<Vec<u8>> {
        let mut needed = 0u32;
        let _ = fill(std::ptr::null_mut(), 0, &mut needed);
        if needed == 0 {
            return None;
        }
        let mut buffer = vec![0u8; needed as usize];
        if fill(buffer.as_mut_ptr(), needed, &mut needed) == 0 {
            return None;
        }
        Some(buffer)
    }

    let printer: Vec<u16> = name.encode_utf16().chain(std::iter::once(0)).collect();
    let mut handle = PRINTER_HANDLE::default();
    unsafe {
        if OpenPrinterW(printer.as_ptr(), &mut handle, std::ptr::null()) == 0 {
            return QueueInspection {
                manufacturer: String::new(),
                identity: String::new(),
                opened: false,
                datatype: String::new(),
                driver_version: String::new(),
            };
        }
        let driver = read_block(|buffer, size, needed| GetPrinterDriverW(handle, std::ptr::null(), 6, buffer, size, needed))
            .filter(|buffer| buffer.len() >= std::mem::size_of::<DRIVER_INFO_6W>())
            .map(|buffer| std::ptr::read_unaligned(buffer.as_ptr() as *const DRIVER_INFO_6W));
        let (manufacturer, datatype, driver_version) = driver
            .map(|info| {
                (
                    wide_text(info.pszMfgName),
                    wide_text(info.pDefaultDataType),
                    format_driver_version(info.dwlDriverVersion),
                )
            })
            .unwrap_or_default();
        let identity = read_block(|buffer, size, needed| GetPrinterW(handle, 7, buffer, size, needed))
            .filter(|buffer| buffer.len() >= std::mem::size_of::<PRINTER_INFO_7W>())
            .map(|buffer| {
                let info = std::ptr::read_unaligned(buffer.as_ptr() as *const PRINTER_INFO_7W);
                wide_text(info.pszObjectGUID)
            })
            .unwrap_or_default();
        ClosePrinter(handle);
        QueueInspection {
            manufacturer,
            identity,
            opened: true,
            datatype,
            driver_version,
        }
    }
}

#[cfg(windows)]
fn enumerate_windows_printers(inspect: bool) -> Result<Vec<InstalledPrinter>, String> {
    use windows_sys::Win32::Foundation::GetLastError;
    use windows_sys::Win32::Graphics::Printing::{EnumPrintersW, PRINTER_INFO_2W};

    const FLAGS: u32 = 2 | 4;
    let mut printers = unsafe {
        let mut needed = 0u32;
        let mut returned = 0u32;
        EnumPrintersW(FLAGS, std::ptr::null(), 2, std::ptr::null_mut(), 0, &mut needed, &mut returned);
        if needed == 0 {
            return Ok(Vec::new());
        }
        let mut buffer = vec![0u8; needed as usize];
        if EnumPrintersW(FLAGS, std::ptr::null(), 2, buffer.as_mut_ptr(), needed, &mut needed, &mut returned) == 0 {
            return Err(format!("Windows could not list printers ({}).", GetLastError()));
        }
        let rows = std::slice::from_raw_parts(buffer.as_ptr() as *const PRINTER_INFO_2W, returned as usize);
        let mut seen = std::collections::HashSet::new();
        let mut raw_rows = Vec::with_capacity(rows.len());
        for row in rows {
            let name = wide_text(row.pPrinterName);
            if name.is_empty() || !seen.insert(name.clone()) {
                continue;
            }
            raw_rows.push(EnumeratedQueue {
                name,
                driver: wide_text(row.pDriverName),
                port: wide_text(row.pPortName),
                status: row.Status,
                attributes: row.Attributes,
                manufacturer: String::new(),
                identity: String::new(),
                opened: None,
                default_datatype: String::new(),
                driver_version: String::new(),
            });
        }
        raw_rows
    };
    if inspect {
        for row in &mut printers {
            let inspected = inspect_queue(&row.name);
            row.manufacturer = inspected.manufacturer;
            row.identity = inspected.identity;
            row.opened = Some(inspected.opened);
            row.default_datatype = inspected.datatype;
            row.driver_version = inspected.driver_version;
        }
    }
    Ok(dedupe_printers(printers.iter().filter_map(map_enumerated_queue).collect()))
}

#[cfg(not(windows))]
fn enumerate_windows_printers(_inspect: bool) -> Result<Vec<InstalledPrinter>, String> {
    Err("Windows printers are only available on Windows.".into())
}

/// Names, drivers, ports, and status. Does not open a queue.
fn known_windows_printers() -> Result<Vec<InstalledPrinter>, String> {
    enumerate_windows_printers(false)
}

struct ResolvedPrint {
    transport: crate::printer_discovery::PrintTransport,
    queue: String,
    driver: String,
    port: String,
}

fn resolve_print(settings: &PrinterSettings) -> Result<ResolvedPrint, String> {
    match settings.transport.as_str() {
        "tcp" => Ok(ResolvedPrint {
            transport: crate::printer_discovery::PrintTransport::EscPos,
            queue: settings.address.trim().to_string(),
            driver: "Network".into(),
            port: crate::printer_profile::tcp_endpoint(&settings.address).unwrap_or_else(|_| "9100".into()),
        }),
        "serial" => Ok(ResolvedPrint {
            transport: crate::printer_discovery::PrintTransport::EscPos,
            queue: settings.address.trim().to_string(),
            driver: if settings.connection_kind == "serial" {
                "Serial COM".into()
            } else {
                "Bluetooth Classic".into()
            },
            port: settings.address.trim().to_string(),
        }),
        "ble" => Err(crate::printer_profile::BLE_UNSUPPORTED.into()),
        "windows" => {
            let queues = known_windows_printers()?;
            let queue = find_queue(&settings.address, &queues)
                .cloned()
                .ok_or_else(|| crate::printer_discovery::MISSING_QUEUE.to_string())?;
            if queue.availability == "virtual" || queue.compatibility == "unsupported" || queue.print_transport == "none" {
                return Err(crate::printer_discovery::UNSUPPORTED_METHOD.into());
            }
            if queue.availability == "offline" {
                return Err(crate::printer_discovery::OFFLINE_NOTICE.into());
            }
            if !queue.openable {
                return Err(crate::printer_discovery::QUEUE_CLOSED.into());
            }
            let transport = crate::printer_discovery::select_output(
                &queue.driver,
                &queue.port,
                &queue.default_datatype,
                &settings.protocol,
            );
            if transport == crate::printer_discovery::PrintTransport::None {
                return Err(crate::printer_discovery::UNSUPPORTED_METHOD.into());
            }
            Ok(ResolvedPrint {
                transport,
                queue: queue.name,
                driver: queue.driver,
                port: queue.port,
            })
        }
        "none" => Err("No receipt printer is configured. Open Register settings to add one.".into()),
        _ => Err("Unknown printer connection.".into()),
    }
}

fn stage(name: &str, result: &str) -> PrintStage {
    PrintStage {
        stage: name.into(),
        result: result.into(),
    }
}

fn record_print(job: &RasterJob, resolved: &ResolvedPrint, payload_bytes: usize, payload_type: &str, submitted: bool, error: Option<&str>) {
    let profile = match resolved.transport {
        crate::printer_discovery::PrintTransport::EscPos => "passed",
        crate::printer_discovery::PrintTransport::WindowsGdi => "unverified",
        crate::printer_discovery::PrintTransport::None => "failed",
    };
    store_diagnostic(PrintDiagnostic {
        recorded_at: now_secs(),
        document_number: job.document_number.clone(),
        line_count: job.line_count,
        subtotal_cents: job.subtotal_cents,
        tax_cents: job.tax_cents,
        discount_cents: job.discount_cents,
        total_cents: job.total_cents,
        width: job.width,
        height: job.height,
        ink_bytes: ink_bytes(&job.data),
        payload_bytes,
        payload_type: payload_type.into(),
        encoding: if payload_type == "escpos" { "ESC/POS" } else { "BGR24" }.into(),
        queue: resolved.queue.clone(),
        driver: resolved.driver.clone(),
        port: resolved.port.clone(),
        transport: resolved.transport.as_str().into(),
        submitted,
        native_error: error.map(str::to_string),
        stages: vec![
            stage("Printer discovered", "passed"),
            stage("Queue opened", if submitted { "passed" } else { "unverified" }),
            stage("Printer profile identified", profile),
            stage("Invoice data loaded", if job.line_count > 0 || !job.document_number.is_empty() { "passed" } else { "not_run" }),
            stage("Printable content generated", "passed"),
            stage("Payload validated", "passed"),
            stage("Print transport selected", "passed"),
            stage("Print job submitted", if submitted { "passed" } else { "failed" }),
            stage("Physical text verified", "not_run"),
        ],
    });
}

pub fn print_raster(db: &Db, job: &RasterJob) -> Result<(), String> {
    if PRINTING.load(Ordering::Relaxed) {
        return Err("A print job is already being sent. Wait for it to finish.".into());
    }
    validate_raster(job)?;
    let settings = load(db)?;
    let resolved = match resolve_print(&settings) {
        Ok(resolved) => resolved,
        Err(message) => {
            store_diagnostic(PrintDiagnostic {
                recorded_at: now_secs(),
                document_number: job.document_number.clone(),
                line_count: job.line_count,
                subtotal_cents: job.subtotal_cents,
                tax_cents: job.tax_cents,
                discount_cents: job.discount_cents,
                total_cents: job.total_cents,
                width: job.width,
                height: job.height,
                ink_bytes: ink_bytes(&job.data),
                payload_bytes: 0,
                payload_type: "rejected".into(),
                encoding: String::new(),
                queue: settings.address.clone(),
                driver: settings.saved_driver.clone(),
                port: settings.saved_port.clone(),
                transport: "none".into(),
                submitted: false,
                native_error: Some(message.clone()),
                stages: vec![
                    stage("Printer discovered", "failed"),
                    stage("Queue opened", "not_run"),
                    stage("Printer profile identified", "not_run"),
                    stage("Invoice data loaded", "passed"),
                    stage("Printable content generated", "passed"),
                    stage("Payload validated", "passed"),
                    stage("Print transport selected", "failed"),
                    stage("Print job submitted", "not_run"),
                    stage("Physical text verified", "not_run"),
                ],
            });
            return Err(message);
        }
    };
    let now = now_secs();
    let queues = if job.kick_drawer && settings.transport == "windows" {
        known_windows_printers().unwrap_or_default()
    } else {
        Vec::new()
    };
    let planned = if job.kick_drawer && !sample_document(&job.document_number) {
        plan_drawer_kick(&settings, &queues, now, LAST_KICK_AT.load(Ordering::Relaxed)).ok()
    } else {
        None
    };
    let mut kicking = planned.is_some();
    let kick_owned = planned
        .map(|plan| {
            if plan.bytes.starts_with(&[0x1b, b'@']) {
                plan.bytes[2..].to_vec()
            } else {
                plan.bytes
            }
        })
        .unwrap_or_default();
    let kick: &[u8] = if kicking { &kick_owned } else { &[] };
    let printable = RasterJob {
        width: job.width,
        height: job.height,
        data: job.data.clone(),
        kick_drawer: kicking,
        line_count: job.line_count,
        document_number: job.document_number.clone(),
        subtotal_cents: job.subtotal_cents,
        tax_cents: job.tax_cents,
        discount_cents: job.discount_cents,
        total_cents: job.total_cents,
        plain_text: job.plain_text.clone(),
    };
    PRINTING.store(true, Ordering::Relaxed);
    let result = match resolved.transport {
        crate::printer_discovery::PrintTransport::EscPos => match escpos_raster(&printable, settings.copies, kick) {
            Ok(bytes) => {
                if !crate::printer_gdi::graphics_precede_cut(&bytes) {
                    let message = crate::printer_discovery::RENDER_FAILED.to_string();
                    record_print(&printable, &resolved, bytes.len(), "escpos", false, Some(&message));
                    Err(message)
                } else {
                    let sent = send(&settings, &bytes);
                    record_print(
                        &printable,
                        &resolved,
                        bytes.len(),
                        "escpos",
                        sent.is_ok(),
                        sent.as_ref().err().map(String::as_str),
                    );
                    sent
                }
            }
            Err(message) => {
                record_print(&printable, &resolved, 0, "escpos", false, Some(&message));
                Err(message)
            }
        },
        crate::printer_discovery::PrintTransport::WindowsGdi => {
            let text_only = crate::printer_discovery::is_text_only_driver(&resolved.driver);
            let payload_bytes = if text_only { printable.plain_text.len() } else { printable.data.len() };
            let sent = if text_only {
                let text = printable.plain_text.trim();
                if text.is_empty() {
                    Err("This printer only prints text, and this receipt had no text to send.".into())
                } else {
                    send_gdi_text(&resolved.queue, text, settings.copies)
                }
            } else {
                send_gdi(&resolved.queue, &printable, settings.copies)
            };
            record_print(
                &printable,
                &resolved,
                payload_bytes,
                if text_only { "text" } else { "raster-image" },
                sent.is_ok(),
                sent.as_ref().err().map(String::as_str),
            );
            if sent.is_ok() && kicking {
                let mut pulse_bytes = vec![0x1b, b'@'];
                pulse_bytes.extend_from_slice(kick);
                if let Err(message) = send_spooler(&resolved.queue, &pulse_bytes) {
                    remember_kick(db, Some(&message));
                    kicking = false;
                }
            }
            sent
        }
        crate::printer_discovery::PrintTransport::None => {
            let message = crate::printer_discovery::UNSUPPORTED_METHOD.to_string();
            record_print(&printable, &resolved, 0, "rejected", false, Some(&message));
            Err(message)
        }
    };
    PRINTING.store(false, Ordering::Relaxed);
    let phase = crate::printer_profile::advance_job(result.is_ok());
    let payload_type = match resolved.transport {
        crate::printer_discovery::PrintTransport::EscPos => "escpos",
        crate::printer_discovery::PrintTransport::WindowsGdi => "raster-image",
        crate::printer_discovery::PrintTransport::None => "rejected",
    };
    let _ = record_print_job(
        db,
        &job.document_number,
        &resolved.queue,
        &settings.connection_kind,
        resolved.transport.as_str(),
        resolved.transport.as_str(),
        payload_type,
        job.data.len(),
        &phase,
        result.as_ref().err().map(String::as_str),
    );
    if settings.transport != "none" {
        remember_print(db, result.as_ref().err().map(String::as_str));
        if result.is_ok() && kicking {
            LAST_KICK_AT.store(now_secs(), Ordering::Relaxed);
            remember_kick(db, None);
        }
    }
    result
}

fn send_gdi_text(name: &str, text: &str, copies: u32) -> Result<(), String> {
    let owned_name = name.to_string();
    let owned_text = text.to_string();
    let (sender, receiver) = std::sync::mpsc::channel();
    std::thread::Builder::new()
        .name("receipt-gdi-text".into())
        .spawn(move || {
            let _ = sender.send(crate::printer_gdi::print_gdi_text(&owned_name, &owned_text, copies));
        })
        .map_err(|err| err.to_string())?;
    match receiver.recv_timeout(SPOOLER_TIMEOUT) {
        Ok(result) => result,
        Err(std::sync::mpsc::RecvTimeoutError::Timeout) => Err(spooler_timeout_message().into()),
        Err(std::sync::mpsc::RecvTimeoutError::Disconnected) => Err("The printer connection ended before a result.".into()),
    }
}

fn send_gdi(name: &str, job: &RasterJob, copies: u32) -> Result<(), String> {
    let owned_name = name.to_string();
    let width = job.width;
    let height = job.height;
    let data = job.data.clone();
    let (sender, receiver) = std::sync::mpsc::channel();
    std::thread::Builder::new()
        .name("receipt-gdi".into())
        .spawn(move || {
            let _ = sender.send(crate::printer_gdi::print_gdi(&owned_name, width, height, &data, copies));
        })
        .map_err(|err| err.to_string())?;
    match receiver.recv_timeout(SPOOLER_TIMEOUT) {
        Ok(result) => result,
        Err(std::sync::mpsc::RecvTimeoutError::Timeout) => Err(spooler_timeout_message().into()),
        Err(std::sync::mpsc::RecvTimeoutError::Disconnected) => Err("The printer connection ended before a result.".into()),
    }
}

pub fn kick_drawer(db: &Db) -> Result<(), String> {
    let _ = refresh_discovery(db);
    let settings = load(db)?;
    let now = now_secs();
    let queues = if settings.transport == "windows" {
        known_windows_printers()?
    } else {
        Vec::new()
    };
    let plan = match plan_drawer_kick(&settings, &queues, now, LAST_KICK_AT.load(Ordering::Relaxed)) {
        Ok(plan) => plan,
        Err(message) => {
            if settings.transport != "none" {
                remember_kick(db, Some(&message));
            }
            return Err(message);
        }
    };
    LAST_KICK_AT.store(now, Ordering::Relaxed);
    PRINTING.store(true, Ordering::Relaxed);
    let result = match settings.transport.as_str() {
        "tcp" => send_tcp(&settings.address, &plan.bytes),
        "windows" => send_spooler(&plan.queue, &plan.bytes),
        _ => Err("No receipt printer is configured. Open Register settings to add one.".into()),
    };
    PRINTING.store(false, Ordering::Relaxed);
    remember_kick(db, result.as_ref().err().map(String::as_str));
    result
}

pub fn list_windows_printers() -> Result<Vec<InstalledPrinter>, String> {
    enumerate_windows_printers(true)
}

/// Listens for Windows printer changes and asks the register to refresh. The listener holds one
/// server handle, not a handle per queue, and it never sends a drawer pulse.
pub fn watch(app: tauri::AppHandle, db: std::sync::Arc<Db>) {
    std::thread::Builder::new()
        .name("printer-watch".into())
        .spawn(move || {
            if let Err(message) = watch_printers(&app, &db) {
                eprintln!("ai-pos: printer change notifications are unavailable: {message}");
            }
        })
        .ok();
}

#[cfg(windows)]
fn watch_printers(app: &tauri::AppHandle, db: &Db) -> Result<(), String> {
    use windows_sys::Win32::Foundation::{GetLastError, WAIT_OBJECT_0, WAIT_TIMEOUT};
    use windows_sys::Win32::Graphics::Printing::{
        ClosePrinter, FindClosePrinterChangeNotification, FindFirstPrinterChangeNotification,
        FindNextPrinterChangeNotification, OpenPrinterW, PRINTER_HANDLE,
    };
    use windows_sys::Win32::System::Threading::WaitForSingleObject;

    let mut printer = PRINTER_HANDLE::default();
    unsafe {
        if OpenPrinterW(std::ptr::null(), &mut printer, std::ptr::null()) == 0 {
            return Err(format!("The local print server could not be opened ({}).", GetLastError()));
        }
        let notify = FindFirstPrinterChangeNotification(printer, 0x0000_00FF, 0, std::ptr::null());
        if notify.is_null() || notify == windows_sys::Win32::Foundation::INVALID_HANDLE_VALUE {
            ClosePrinter(printer);
            return Err(format!("Printer change notifications could not start ({}).", GetLastError()));
        }
        loop {
            let waited = WaitForSingleObject(notify, 30_000);
            if waited == WAIT_OBJECT_0 {
                let mut change = 0u32;
                FindNextPrinterChangeNotification(notify, &mut change, std::ptr::null_mut(), std::ptr::null_mut());
                let _ = refresh_discovery(db);
                let _ = app.emit("printer-hardware-change", ());
            } else if waited != WAIT_TIMEOUT {
                break;
            }
        }
        FindClosePrinterChangeNotification(notify);
        ClosePrinter(printer);
    }
    Ok(())
}

#[cfg(not(windows))]
fn watch_printers(_app: &tauri::AppHandle, _db: &Db) -> Result<(), String> {
    Ok(())
}

/// Downloads the API's A4 tax invoice or credit note PDF for the cashier to print or hand over.
pub fn download_document(
    config: &DesktopConfig,
    kind: &str,
    id: &str,
    number: &str,
    directory: &Path,
) -> Result<String, String> {
    let safe_id: String = id
        .chars()
        .filter(|c| c.is_ascii_hexdigit() || *c == '-')
        .collect();
    let safe_number: String = number
        .chars()
        .filter(|c| c.is_ascii_alphanumeric() || *c == '-')
        .collect();
    let path = match kind {
        "invoice" => format!("sales/{safe_id}/invoice.pdf"),
        "credit_note" => format!("returns/{safe_id}/credit-note.pdf"),
        "gift_receipt" => format!("sales/{safe_id}/gift-receipt.pdf"),
        _ => return Err("Unknown document.".into()),
    };
    let safe_number = if kind == "gift_receipt" && !safe_number.is_empty() {
        format!("gift-{safe_number}")
    } else {
        safe_number
    };
    if safe_id.is_empty() {
        return Err("Unknown document.".into());
    }
    let response = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(20))
        .build()
        .map_err(|err| err.to_string())?
        .get(format!("{}/api/v1/{path}", config.api_base_url))
        .headers(config.auth_headers())
        .send()
        .map_err(|err| format!("The server is unreachable: {err}"))?;
    let status = response.status();
    let bytes = response.bytes().map_err(|err| err.to_string())?;
    if status.as_u16() == 404 {
        return Err("The server has not received this document yet. Sync, then try again.".into());
    }
    if !status.is_success() {
        return Err(format!(
            "The server rejected the request ({}).",
            status.as_u16()
        ));
    }
    std::fs::create_dir_all(directory).map_err(|err| err.to_string())?;
    let name = if safe_number.is_empty() {
        safe_id
    } else {
        safe_number
    };
    let file = directory.join(format!("{name}.pdf"));
    std::fs::write(&file, &bytes).map_err(|err| err.to_string())?;
    Ok(file.to_string_lossy().into_owned())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn raster_is_banded_and_kicks_once() {
        let job = RasterJob {
            width: 16,
            height: 300,
            data: vec![0xff; 2 * 300],
            kick_drawer: true,
            line_count: 1,
            document_number: "TEST".into(),
            subtotal_cents: 1000,
            tax_cents: 50,
            discount_cents: 0,
            total_cents: 1050,
            plain_text: String::new(),
        };
        let bytes = escpos_raster(&job, 2, &DRAWER_KICK).unwrap();
        let bands = bytes
            .windows(3)
            .filter(|w| w == &[0x1d, b'v', b'0'])
            .count();
        assert_eq!(bands, 6);
        assert_eq!(bytes.windows(5).filter(|w| w == &DRAWER_KICK).count(), 1);
        let heights = graphic_band_heights(&bytes);
        assert!(heights.iter().all(|height| (1..=128).contains(height)), "{heights:?}");
        assert_eq!(heights.iter().sum::<u32>(), 600);
        assert!(sample_document("SAMPLE-1001"));
        assert!(sample_document("TEST-000000"));
        assert!(!sample_document("INV-1001"));
    }

    fn graphic_band_heights(bytes: &[u8]) -> Vec<u32> {
        let mut heights = Vec::new();
        let mut index = 0;
        while index + 8 <= bytes.len() {
            if bytes[index] == 0x1d && bytes[index + 1] == b'v' && bytes[index + 2] == b'0' {
                let rows = u32::from(bytes[index + 6]) | (u32::from(bytes[index + 7]) << 8);
                heights.push(rows);
            }
            index += 1;
        }
        heights
    }

    #[test]
    fn malformed_raster_is_rejected() {
        let job = RasterJob {
            width: 16,
            height: 3,
            data: vec![0; 5],
            kick_drawer: false,
            line_count: 0,
            document_number: String::new(),
            subtotal_cents: 0,
            tax_cents: 0,
            discount_cents: 0,
            total_cents: 0,
            plain_text: String::new(),
        };
        assert!(escpos_raster(&job, 1, &DRAWER_KICK).is_err());
    }

    #[test]
    fn a_blank_raster_is_rejected_before_feed_and_cut() {
        let job = RasterJob {
            width: 8,
            height: 8,
            data: vec![0; 8],
            kick_drawer: false,
            line_count: 1,
            document_number: "INV-1".into(),
            subtotal_cents: 100,
            tax_cents: 5,
            discount_cents: 0,
            total_cents: 105,
            plain_text: String::new(),
        };
        let error = validate_raster(&job).unwrap_err();
        assert!(error.contains("could not be rendered"));
        assert!(escpos_raster(&job, 1, &[]).is_err());
    }

    #[test]
    fn escpos_image_bytes_precede_the_cut() {
        let job = RasterJob {
            width: 8,
            height: 8,
            data: vec![0xff; 8],
            kick_drawer: false,
            line_count: 1,
            document_number: "INV-1".into(),
            subtotal_cents: 100,
            tax_cents: 5,
            discount_cents: 0,
            total_cents: 105,
            plain_text: String::new(),
        };
        let bytes = escpos_raster(&job, 1, &[]).unwrap();
        assert!(crate::printer_gdi::graphics_precede_cut(&bytes));
        assert!(bytes.len() > 16);
    }

    #[test]
    fn toshiba_native_queue_is_a_candidate_on_the_gdi_transport() {
        let mapped = map_enumerated_queue(&enumerated(
            "Toshiba POS Printer (CR)",
            "Toshiba Native Windows Driver",
            "Toshiba: 0_USB",
            0,
            Some(true),
        ))
        .unwrap();
        assert_eq!(mapped.compatibility, "candidate");
        assert_eq!(mapped.status_label, "Candidate");
        assert_eq!(mapped.connection, "USB");
        assert_eq!(mapped.print_transport, "windows-gdi");
        assert!(!mapped.supports_drawer_kick);
        assert!(mapped.capabilities.contains("Raw ESC/POS is not sent"));
        let refused = plan_drawer_kick(&windows_settings(&mapped.name), &[mapped], 100, 0).unwrap_err();
        assert!(refused.contains("drawer-kick"));
        let text_only = map_enumerated_queue(&enumerated("Generic / Text Only", "Generic / Text Only", "COM4:", 0, Some(true))).unwrap();
        assert!(!text_only.supports_drawer_kick);
        let refused_com = plan_drawer_kick(&windows_settings(&text_only.name), &[text_only.clone()], 100, 0).unwrap_err();
        assert!(refused_com.contains("drawer-kick"));
        let mut hp_on_com = windows_settings(&text_only.name);
        hp_on_com.drawer_profile = "hp-vb400-bl1616".into();
        hp_on_com.host_voltage = "24".into();
        let circuit = plan_drawer_kick(&hp_on_com, &[text_only], 100, 0).unwrap_err();
        assert!(circuit.contains("will not send a pulse"));
        assert!(circuit.contains("24V"));
        assert_eq!(format_driver_version(0), "");
        assert_eq!(format_driver_version(0x000a_0001_0000_0020), "10.1.32");
    }

    fn enumerated(name: &str, driver: &str, port: &str, status: u32, opened: Option<bool>) -> EnumeratedQueue {
        EnumeratedQueue {
            name: name.into(),
            driver: driver.into(),
            port: port.into(),
            status,
            attributes: 0,
            manufacturer: String::new(),
            identity: String::new(),
            opened,
            default_datatype: String::new(),
            driver_version: String::new(),
        }
    }

    fn queue(name: &str, status: u32) -> InstalledPrinter {
        map_enumerated_queue(&EnumeratedQueue {
            name: name.into(),
            driver: "EPSON TM-T20 Receipt".into(),
            port: "USB001".into(),
            status,
            attributes: 0,
            manufacturer: String::new(),
            identity: String::new(),
            opened: Some(true),
            default_datatype: String::new(),
            driver_version: String::new(),
        })
        .expect("queue")
    }

    fn windows_settings(address: &str) -> PrinterSettings {
        PrinterSettings {
            transport: "windows".into(),
            address: address.into(),
            ..PrinterSettings::default()
        }
    }

    fn hp_settings(address: &str) -> PrinterSettings {
        PrinterSettings {
            drawer_profile: "hp-vb400-bl1616".into(),
            host_voltage: "24".into(),
            ..windows_settings(address)
        }
    }

    #[test]
    fn drawer_pulse_uses_the_configured_pin_and_timing() {
        assert_eq!(drawer_pulse(0, 25, 250), DRAWER_KICK);
        assert_eq!(drawer_pulse(1, 50, 250)[2], 1);
        assert!(checked_pulse(2, 25, 250).is_err());
        assert!(checked_pulse(0, 0, 250).is_err());
    }

    #[test]
    fn a_missing_queue_is_not_replaced() {
        let queues = vec![queue("Microsoft Print to PDF", 0), queue("Toshiba thermal extra", 0)];
        assert!(find_queue("Toshiba thermal", &queues).is_none());
        assert_eq!(find_queue("Microsoft Print to PDF", &queues).unwrap().name, "Microsoft Print to PDF");
        let missing = plan_drawer_kick(&windows_settings("Toshiba thermal"), &queues, 100, 0).unwrap_err();
        assert!(missing.contains("was not found"));
        assert!(!missing.contains("Microsoft Print to PDF"));
    }

    #[test]
    fn an_offline_queue_blocks_the_kick() {
        let queues = vec![queue("Receipt", 0x80)];
        let error = plan_drawer_kick(&windows_settings("Receipt"), &queues, 100, 0).unwrap_err();
        assert!(error.contains("unavailable"));
    }

    #[test]
    fn a_ready_queue_plans_one_pulse() {
        let queues = vec![queue("Receipt", 0)];
        let unconfigured = plan_drawer_kick(&windows_settings("Receipt"), &queues, 100, 0).unwrap_err();
        assert!(unconfigured.contains("drawer profile"));
        let plan = plan_drawer_kick(&hp_settings("Receipt"), &queues, 100, 0).unwrap();
        assert_eq!(plan.queue, "Receipt");
        assert_eq!(plan.bytes.windows(5).filter(|window| *window == DRAWER_KICK).count(), 1);
        let mut twelve = hp_settings("Receipt");
        twelve.host_voltage = "12".into();
        let mismatch = plan_drawer_kick(&twelve, &queues, 100, 0).unwrap_err();
        assert!(mismatch.contains("not interchangeable"));
    }

    #[test]
    fn repeated_kicks_are_refused_and_open_state_is_unknown() {
        assert!(!kick_allowed(10, 8, 3));
        assert!(kick_allowed(12, 8, 3));
        let queues = vec![queue("Receipt", 0)];
        let error = plan_drawer_kick(&windows_settings("Receipt"), &queues, 10, 8).unwrap_err();
        assert!(error.contains("Wait a moment"));
        assert_eq!(spooler_timeout_message().contains("timeout"), true);
    }

    #[test]
    fn a_printer_without_a_drawer_profile_cannot_be_kicked() {
        let mut item = queue("Label", 0);
        item.supports_drawer_kick = false;
        item.compatibility = "candidate".into();
        let error = plan_drawer_kick(&windows_settings("Label"), &[item], 100, 0).unwrap_err();
        assert!(error.contains("drawer-kick"));
    }

    #[test]
    fn no_installed_printer_cannot_be_kicked() {
        let error = plan_drawer_kick(&windows_settings("Receipt"), &[], 100, 0).unwrap_err();
        assert!(error.contains("was not found"));
    }

    #[test]
    fn enumerated_rows_map_status_without_calling_windows() {
        let ready = queue("Epson TM-T20", 0);
        assert_eq!(ready.status_label, "Ready");
        assert_eq!(ready.availability, "ready");
        assert!(ready.openable);
        assert!(ready.supports_drawer_kick);
        assert_eq!(ready.compatibility, "compatible");

        let offline = queue("Epson TM-T20", 0x80);
        assert_eq!(offline.status_label, "Offline");
        assert_eq!(offline.availability, "offline");
        assert!(offline.unavailable);
        assert!(!offline.supports_drawer_kick);

        let mut work_offline = enumerated("Front", "EPSON TM-T20 Receipt", "USB001", 0, Some(true));
        work_offline.attributes = 0x400;
        let flagged = map_enumerated_queue(&work_offline).unwrap();
        assert_eq!(flagged.availability, "offline");

        let closed = map_enumerated_queue(&enumerated("Front", "EPSON TM-T20 Receipt", "USB001", 0, Some(false))).unwrap();
        assert!(!closed.openable);
        assert_eq!(closed.status_label, "Unavailable");
        assert!(queue_open_error(&closed.name, false).unwrap_err().contains("could not open"));
        assert!(queue_open_error(&closed.name, true).is_ok());

        let candidate = map_enumerated_queue(&enumerated("Label", "Generic Text Driver", "USB003", 0, Some(true))).unwrap();
        assert_eq!(candidate.compatibility, "candidate");
        assert_eq!(candidate.status_label, "Candidate");
        assert!(!candidate.supports_drawer_kick);
        assert!(candidate.capabilities.contains("Text only"));

        let mut pdf = enumerated("Microsoft Print to PDF", "Microsoft Print To PDF", "PORTPROMPT:", 0, Some(true));
        pdf.manufacturer = "Microsoft".into();
        pdf.identity = "{pdf}".into();
        let virtual_printer = map_enumerated_queue(&pdf).unwrap();
        assert_eq!(virtual_printer.status_label, "Virtual printer");
        assert_eq!(virtual_printer.availability, "virtual");
        assert_eq!(virtual_printer.compatibility, "unsupported");
        assert_eq!(virtual_printer.manufacturer, "Microsoft");
        assert_eq!(virtual_printer.identity, "{pdf}");
        assert!(!virtual_printer.supports_drawer_kick);
        let mut forced = virtual_printer.clone();
        forced.supports_drawer_kick = true;
        let refused = plan_drawer_kick(&windows_settings(&forced.name), &[forced], 100, 0).unwrap_err();
        assert!(refused.contains("does not support"));
        assert!(!refused.contains("Epson"));

        let blank = map_enumerated_queue(&enumerated("  ", "EPSON TM-T20 Receipt", "USB001", 0, Some(true)));
        assert!(blank.is_none());
        let duplicated = dedupe_printers(vec![queue("Front", 0), queue("Front", 0), queue("Bar", 0)]);
        assert_eq!(duplicated.len(), 2);
        assert_eq!(duplicated[0].name, "Front");
        assert_eq!(duplicated[1].name, "Bar");
    }

    #[test]
    fn printer_selection_is_saved_and_can_be_changed() {
        let path = std::env::temp_dir().join(format!(
            "aipos-printer-{}.sqlite",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let db = crate::db::Db::open(&path).unwrap();
        let mut draft = windows_settings("Toshiba thermal");
        draft.saved_identity = "{toshiba}".into();
        draft.saved_driver = "TOSHIBA TEC".into();
        draft.saved_port = "USB001".into();
        let saved = save(&db, &draft).unwrap();
        assert_eq!(saved.address, "Toshiba thermal");
        assert_eq!(saved.saved_identity, "{toshiba}");
        assert_eq!(saved.saved_driver, "TOSHIBA TEC");
        assert_eq!(saved.saved_port, "USB001");
        let changed = save(
            &db,
            &PrinterSettings {
                address: "Receipt".into(),
                ..saved
            },
        )
        .unwrap();
        assert_eq!(load(&db).unwrap().address, "Receipt");
        assert_eq!(changed.drawer_pin, 0);
        let mut invalid = changed.clone();
        invalid.copies = 0;
        match save(&db, &invalid) {
            Err(err) => assert!(err.contains("Copies"), "{err}"),
            Ok(_) => panic!("invalid copies were saved"),
        }
        assert_eq!(load(&db).unwrap().address, "Receipt");
        assert_eq!(load(&db).unwrap().copies, 1);
        let mut network = PrinterSettings {
            transport: "tcp".into(),
            address: "192.168.1.50".into(),
            paper_dots: 384,
            copies: 2,
            ..PrinterSettings::default()
        };
        let lan = save(&db, &network).unwrap();
        assert_eq!(lan.transport, "tcp");
        assert_eq!(lan.address, "192.168.1.50");
        assert_eq!(lan.paper_dots, 384);
        assert_eq!(lan.connection_kind, "network");
        assert_eq!(lan.protocol, "escpos");
        assert_eq!(lan.verification, "candidate");
        network.address = "999.1.1.1".into();
        assert!(save(&db, &network).is_err());
        assert_eq!(load(&db).unwrap().address, "192.168.1.50");
        let mut none = lan.clone();
        none.transport = "none".into();
        let cleared = save(&db, &none).unwrap();
        assert_eq!(cleared.transport, "none");
        assert_eq!(cleared.address, "");
        assert_eq!(cleared.previous_address, "192.168.1.50");
        let mut virtual_queue = PrinterSettings {
            transport: "windows".into(),
            address: "OneNote (Desktop) - Protected".into(),
            paper_dots: 384,
            copies: 2,
            drawer_kick: false,
            user_selected: true,
            auto_discover: true,
            ..PrinterSettings::default()
        };
        let kept = save(&db, &virtual_queue).unwrap();
        assert_eq!(kept.address, "OneNote (Desktop) - Protected");
        assert_eq!(kept.paper_dots, 384);
        assert!(!kept.drawer_kick);
        virtual_queue.address.clear();
        assert!(save(&db, &virtual_queue).is_err());
        assert_eq!(load(&db).unwrap().address, "OneNote (Desktop) - Protected");
        assert!(hardware_change_allowed(&["devices:manage".into()]));
        assert!(hardware_change_allowed(&["settings:manage".into()]));
        assert!(hardware_change_allowed(&["pos:access".into(), "pos:orders".into()]));
        assert!(!hardware_change_allowed(&["portal:reports_read".into()]));
        let _ = std::fs::remove_file(&path);
        let queues = vec![queue("Receipt", 0)];
        let probed = find_queue("Toshiba thermal", &queues);
        assert!(probed.is_none());
    }

    #[test]
    fn a_session_without_register_access_cannot_replace_the_saved_printer() {
        let path = std::env::temp_dir().join(format!(
            "aipos-printer-deny-{}.sqlite",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let db = crate::db::Db::open(&path).unwrap();
        let saved = save(&db, &windows_settings("Front counter")).unwrap();
        let session = crate::auth::Session {
            user: crate::auth::CashierProfile {
                id: "cashier-1".into(),
                username: "ahsan".into(),
                full_name: "Ahsan".into(),
                store_id: Some("store-a".into()),
                role_name: "Reports Viewer".into(),
                permissions: vec!["portal:reports_read".into()],
                max_discount_bps: None,
                addon_modules: Vec::new(),
                addon_synced_at: 0,
                avatar_url: None,
            },
            mode: "online",
            unlocked_at: 10,
        };
        let message = refuse_hardware_change(&db, &session, "store-a");
        assert_eq!(message, REGISTER_MANAGE_REQUIRED);
        assert_eq!(load(&db).unwrap().address, saved.address);
        let events = crate::audit::recent(&db, 5).unwrap();
        assert!(events.iter().any(|event| event.action == "register.printer_settings"));
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn network_bluetooth_and_usb_profiles_stay_on_this_register() {
        let path = std::env::temp_dir().join(format!(
            "aipos-profiles-{}.sqlite",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let db = crate::db::Db::open(&path).unwrap();
        let mut network = PrinterSettings {
            transport: "tcp".into(),
            address: "192.168.1.50".into(),
            connection_kind: "wifi".into(),
            verification: "verified".into(),
            ..PrinterSettings::default()
        };
        let wifi = save(&db, &network).unwrap();
        assert_eq!(wifi.connection_kind, "wifi");
        assert_eq!(wifi.verification, "candidate");
        assert_eq!(load(&db).unwrap().protocol, "escpos");
        network.address = "10.0.0.8:9101".into();
        assert!(save(&db, &network).is_ok());
        let mut serial = PrinterSettings {
            transport: "serial".into(),
            address: "com5".into(),
            connection_kind: "bluetooth-classic".into(),
            ..PrinterSettings::default()
        };
        let paired = save(&db, &serial).unwrap();
        assert_eq!(paired.address, "COM5");
        assert_eq!(load(&db).unwrap().address, "COM5");
        serial.address = "COM0".into();
        assert!(save(&db, &serial).is_err());
        assert_eq!(load(&db).unwrap().address, "COM5");
        let kicked = plan_drawer_kick(&paired, &[], 100, 0).unwrap_err();
        assert!(kicked.contains("not verified"));
        let ble = PrinterSettings {
            transport: "ble".into(),
            address: "ble-device".into(),
            connection_kind: "bluetooth-ble".into(),
            verification: "verified".into(),
            ..PrinterSettings::default()
        };
        let low_energy = save(&db, &ble).unwrap();
        assert_eq!(low_energy.verification, "candidate");
        assert_eq!(low_energy.protocol, "unknown");
        assert!(plan_drawer_kick(&low_energy, &[], 100, 0).unwrap_err().contains("not verified"));
        let mut usb = windows_settings("Front");
        usb.connection_kind = "usb".into();
        usb.saved_port = "192.168.1.9".into();
        match save(&db, &usb) {
            Err(message) => assert!(message.contains("not a USB"), "{message}"),
            Ok(_) => panic!("a network port was saved as USB"),
        }
        usb.saved_port = "Toshiba: 0_USB".into();
        let kept = save(&db, &usb).unwrap();
        assert_eq!(kept.connection_kind, "usb");
        assert_eq!(kept.address, "Front");
        let com = PrinterSettings {
            transport: "serial".into(),
            address: "COM4".into(),
            connection_kind: "serial".into(),
            ..PrinterSettings::default()
        };
        let stored = save(&db, &com).unwrap();
        assert_eq!(stored.connection_kind, "serial");
        assert_eq!(stored.protocol, "escpos");
        assert_eq!(stored.address, "COM4");
        let mut rendered = windows_settings("Toshiba");
        rendered.saved_driver = "Toshiba Native Windows Driver".into();
        rendered.saved_port = "Toshiba: 0_USB".into();
        rendered.protocol = "escpos".into();
        match save(&db, &rendered) {
            Err(refused) => assert!(refused.contains("does not accept raw ESC/POS"), "{refused}"),
            Ok(_) => panic!("raw ESC/POS was saved for a Windows-rendered driver"),
        }
        let mut unknown = windows_settings("Counter");
        unknown.saved_driver = "Unknown Thermal".into();
        unknown.saved_port = "USB009".into();
        unknown.protocol = "escpos".into();
        let generic = save(&db, &unknown).unwrap();
        assert_eq!(generic.protocol, "escpos");
        unknown.protocol = "zpl".into();
        assert!(save(&db, &unknown).is_err());
        assert_eq!(load(&db).unwrap().protocol, "escpos");
        record_print_job(
            &db,
            "INV-1",
            "Counter",
            "usb",
            "escpos",
            "escpos",
            "escpos",
            120,
            &crate::printer_profile::JobPhase::AcceptedUnverified,
            None,
        )
        .unwrap();
        let status: String = db
            .read(|conn| {
                conn.query_row(
                    "SELECT status || ' ' || verification || ' ' || connection || ' ' || CAST(payload_bytes AS TEXT) FROM printer_jobs",
                    [],
                    |row| row.get(0),
                )
                .map_err(|err| err.to_string())
            })
            .unwrap();
        assert!(status.contains("accepted-unverified"), "{status}");
        assert!(status.contains("physical-not-verified"), "{status}");
        assert!(status.contains("usb"), "{status}");
        assert!(status.contains("120"), "{status}");
        assert!(!crate::printer_profile::retry_when_output_unknown());
        let _ = std::fs::remove_file(&path);
    }

    #[cfg(windows)]
    #[test]
    fn a_missing_saved_printer_is_not_replaced_by_an_office_queue() {
        let path = std::env::temp_dir().join(format!(
            "aipos-discover-{}.sqlite",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let db = crate::db::Db::open(&path).unwrap();
        save(&db, &windows_settings("Toshiba thermal")).unwrap();
        let decision = refresh_discovery(&db).unwrap();
        let loaded = load(&db).unwrap();
        let queues = known_windows_printers().unwrap_or_default();
        let available = queues
            .iter()
            .filter(|queue| queue.compatibility == "compatible" && !queue.unavailable)
            .count();
        if available == 0 {
            assert_eq!(decision.outcome, "missing");
            assert_eq!(loaded.address, "Toshiba thermal");
            assert_eq!(loaded.previous_address, "Toshiba thermal");
        } else if available == 1 {
            assert_eq!(decision.outcome, "auto");
            assert_eq!(loaded.previous_address, "Toshiba thermal");
        } else {
            assert_eq!(decision.outcome, "choose");
            assert_eq!(loaded.address, "Toshiba thermal");
        }
        assert!(queues.iter().all(|queue| loaded.address == "Toshiba thermal" || queue.name == loaded.address));
        assert!(queues.iter().filter(|queue| queue.compatibility == "unsupported").all(|queue| queue.name != loaded.address || available == 0 && loaded.address == "Toshiba thermal"));
        let _ = std::fs::remove_file(&path);
    }

    #[cfg(windows)]
    #[test]
    fn installed_queues_use_exact_names() {
        let queues = known_windows_printers().expect("list");
        for queue in &queues {
            assert!(!queue.name.trim().is_empty());
            assert_eq!(find_queue(&queue.name, &queues).unwrap().name, queue.name);
            assert!(find_queue(&format!("{} extra", queue.name), &queues).is_none());
        }
    }
}
