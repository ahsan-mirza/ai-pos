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
    add_column(conn, "printer_status", "last_kick_attempt_at", "INTEGER")
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
        }
    }
}

pub fn load(db: &Db) -> Result<PrinterSettings, String> {
    db.read(|conn| {
        conn.query_row(
            "SELECT transport, address, paper_dots, drawer_kick, auto_print, copies, drawer_pin, drawer_on, drawer_off,
                    auto_discover, previous_address, saved_driver, saved_port, saved_model, user_selected, saved_identity
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
                })
            },
        )
        .optional()
        .map(Option::unwrap_or_default)
        .map_err(|err| err.to_string())
    })
}

pub fn hardware_change_allowed(permissions: &[String]) -> bool {
    permissions
        .iter()
        .any(|item| item == "devices:manage" || item == "settings:manage")
}

/// Checks a register configuration before it is written. A virtual Windows queue is allowed as a
/// diagnostic preference. It is not treated as a connected receipt printer by the probe.
pub fn prepare_settings(settings: &PrinterSettings) -> Result<PrinterSettings, String> {
    if !matches!(settings.transport.as_str(), "none" | "tcp" | "windows") {
        return Err("Choose Network (LAN), Windows printer, or None.".into());
    }
    if !matches!(settings.paper_dots, 384 | 576) {
        return Err("Paper width must be 58 mm (384 dots) or 80 mm (576 dots).".into());
    }
    if !(1..=3).contains(&settings.copies) {
        return Err("Copies per sale must be 1, 2, or 3.".into());
    }
    checked_pulse(settings.drawer_pin, settings.drawer_on, settings.drawer_off)?;
    let mut next = settings.clone();
    next.address = settings.address.trim().to_string();
    next.previous_address = settings.previous_address.trim().to_string();
    match next.transport.as_str() {
        "none" => {
            if !next.address.is_empty() {
                next.previous_address = next.address.clone();
                next.address.clear();
            }
            next.user_selected = false;
        }
        "tcp" => validate_tcp(&next.address)?,
        "windows" => {
            if next.address.is_empty() {
                return Err("Select a Windows printer.".into());
            }
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
                auto_discover, previous_address, saved_driver, saved_port, saved_model, user_selected, saved_identity
             ) VALUES (1, ?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16)
             ON CONFLICT(id) DO UPDATE SET transport = excluded.transport, address = excluded.address,
                paper_dots = excluded.paper_dots, drawer_kick = excluded.drawer_kick,
                auto_print = excluded.auto_print, copies = excluded.copies,
                drawer_pin = excluded.drawer_pin, drawer_on = excluded.drawer_on, drawer_off = excluded.drawer_off,
                auto_discover = excluded.auto_discover, previous_address = excluded.previous_address,
                saved_driver = excluded.saved_driver, saved_port = excluded.saved_port,
                saved_model = excluded.saved_model, user_selected = excluded.user_selected,
                saved_identity = excluded.saved_identity",
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
}

#[cfg(test)]
const DRAWER_KICK: [u8; 5] = [0x1b, b'p', 0, 25, 250];
const BAND_ROWS: u32 = 256;
const KICK_GAP_SECS: i64 = 3;
const SPOOLER_TIMEOUT: Duration = Duration::from_secs(8);
static PRINTING: AtomicBool = AtomicBool::new(false);
static LAST_KICK_AT: AtomicI64 = AtomicI64::new(0);

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
    Some(InstalledPrinter {
        name: name.to_string(),
        driver: raw.driver.clone(),
        port: raw.port.clone(),
        status: raw.status,
        status_label,
        unavailable,
        compatibility: classed.compatibility.as_str().to_string(),
        supports_drawer_kick: classed.supports_drawer_kick && availability != "virtual" && !unavailable,
        connection: classed.connection,
        profile_id: classed.profile_id,
        manufacturer: raw.manufacturer.trim().to_string(),
        identity: raw.identity.trim().to_string(),
        openable,
        availability,
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
        Err(format!("Windows printer \"{name}\" could not be opened."))
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
    if !kick_allowed(now, last_attempt, KICK_GAP_SECS) {
        return Err("Wait a moment before kicking the drawer again.".into());
    }
    let (pin, on_units, off_units) = checked_pulse(settings.drawer_pin, settings.drawer_on, settings.drawer_off)?;
    let mut bytes = vec![0x1b, b'@'];
    bytes.extend_from_slice(&drawer_pulse(pin, on_units, off_units));
    if settings.transport == "tcp" {
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
        return Err("This device is not verified as a supported receipt printer.".into());
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
    if !queue.supports_drawer_kick || queue.compatibility != "compatible" {
        return Err("This printer has no known drawer-kick profile. Test drawer kick stays off.".into());
    }
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
    let target = if address.contains(':') {
        address.to_string()
    } else {
        format!("{address}:9100")
    };
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
    }
}

pub fn refresh_discovery(db: &Db) -> Result<crate::printer_discovery::DiscoveryDecision, String> {
    use crate::printer_discovery::{decide, Discovered, SavedPrinter};
    let settings = load(db)?;
    if settings.transport == "tcp" {
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
            drawer_supported: settings.drawer_kick,
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
        return Ok(annotate(
            finish_probe(
                settings,
                history,
                ok,
                reach.err(),
                if ok { "ready" } else { "unavailable" },
                None,
                None,
            ),
            &decision,
            None,
        ));
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
                Some("This device is not verified as a supported receipt printer.".into()),
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
            "This printer is installed but currently offline.".to_string()
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
        ("unavailable", opened.err())
    } else if queue.compatibility == "compatible" {
        ("ready", None)
    } else {
        (
            "candidate",
            Some("This device is not verified as a supported receipt printer.".into()),
        )
    };
    Ok(annotate(
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
    ))
}

pub fn escpos_raster(job: &RasterJob, copies: u32, kick: &[u8]) -> Result<Vec<u8>, String> {
    let row_bytes = job.width.div_ceil(8);
    if job.width == 0 || job.height == 0 || job.data.len() != (row_bytes * job.height) as usize {
        return Err("The receipt image is malformed.".into());
    }
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
    match settings.transport.as_str() {
        "tcp" => send_tcp(&settings.address, bytes),
        "windows" => send_spooler(&settings.address, bytes),
        _ => Err("No receipt printer is configured. Open Register settings to add one.".into()),
    }
}

fn send_tcp(address: &str, bytes: &[u8]) -> Result<(), String> {
    let target = if address.contains(':') {
        address.to_string()
    } else {
        format!("{address}:9100")
    };
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

/// Opens one queue, reads the driver manufacturer and object GUID, then closes it. No bytes are written.
#[cfg(windows)]
fn inspect_queue(name: &str) -> (String, String, bool) {
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
            return (String::new(), String::new(), false);
        }
        let manufacturer = read_block(|buffer, size, needed| GetPrinterDriverW(handle, std::ptr::null(), 6, buffer, size, needed))
            .filter(|buffer| buffer.len() >= std::mem::size_of::<DRIVER_INFO_6W>())
            .map(|buffer| {
                let info = std::ptr::read_unaligned(buffer.as_ptr() as *const DRIVER_INFO_6W);
                wide_text(info.pszMfgName)
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
        (manufacturer, identity, true)
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
            });
        }
        raw_rows
    };
    if inspect {
        for row in &mut printers {
            let (manufacturer, identity, opened) = inspect_queue(&row.name);
            row.manufacturer = manufacturer;
            row.identity = identity;
            row.opened = Some(opened);
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

pub fn print_raster(db: &Db, job: &RasterJob) -> Result<(), String> {
    let settings = load(db)?;
    let mut kicking = job.kick_drawer && settings.drawer_kick && settings.transport != "none";
    let now = now_secs();
    if kicking && !kick_allowed(now, LAST_KICK_AT.load(Ordering::Relaxed), KICK_GAP_SECS) {
        kicking = false;
    }
    if kicking && settings.transport == "windows" {
        let allowed = match known_windows_printers() {
            Ok(queues) => find_queue(&settings.address, &queues)
                .map(|queue| {
                    queue.supports_drawer_kick
                        && queue.compatibility == "compatible"
                        && queue.availability == "ready"
                        && queue.openable
                })
                .unwrap_or(false),
            Err(_) => false,
        };
        if !allowed {
            kicking = false;
        }
    }
    let pulse = drawer_pulse(settings.drawer_pin, settings.drawer_on, settings.drawer_off);
    let kick: &[u8] = if kicking { &pulse } else { &[] };
    let printable = RasterJob {
        width: job.width,
        height: job.height,
        data: job.data.clone(),
        kick_drawer: kicking,
    };
    let bytes = escpos_raster(&printable, settings.copies, kick)?;
    PRINTING.store(true, Ordering::Relaxed);
    let result = send(&settings, &bytes);
    PRINTING.store(false, Ordering::Relaxed);
    if settings.transport != "none" {
        remember_print(db, result.as_ref().err().map(String::as_str));
        if result.is_ok() && kicking {
            LAST_KICK_AT.store(now, Ordering::Relaxed);
            remember_kick(db, None);
        }
    }
    result
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
        };
        let bytes = escpos_raster(&job, 2, &DRAWER_KICK).unwrap();
        let bands = bytes
            .windows(3)
            .filter(|w| w == &[0x1d, b'v', b'0'])
            .count();
        assert_eq!(bands, 4);
        assert_eq!(bytes.windows(5).filter(|w| w == &DRAWER_KICK).count(), 1);
    }

    #[test]
    fn malformed_raster_is_rejected() {
        let job = RasterJob {
            width: 16,
            height: 3,
            data: vec![0; 5],
            kick_drawer: false,
        };
        assert!(escpos_raster(&job, 1, &DRAWER_KICK).is_err());
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
        let plan = plan_drawer_kick(&windows_settings("Receipt"), &queues, 100, 0).unwrap();
        assert_eq!(plan.queue, "Receipt");
        assert_eq!(plan.bytes.windows(5).filter(|window| *window == DRAWER_KICK).count(), 1);
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
        assert!(queue_open_error(&closed.name, false).unwrap_err().contains("could not be opened"));
        assert!(queue_open_error(&closed.name, true).is_ok());

        let candidate = map_enumerated_queue(&enumerated("Label", "Generic Text Driver", "USB003", 0, Some(true))).unwrap();
        assert_eq!(candidate.compatibility, "candidate");
        assert_eq!(candidate.status_label, "Candidate");
        assert!(!candidate.supports_drawer_kick);

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
        assert!(refused.contains("not verified"));
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
        assert!(!hardware_change_allowed(&["pos:access".into(), "pos:orders".into()]));
        let _ = std::fs::remove_file(&path);
        let queues = vec![queue("Receipt", 0)];
        let probed = find_queue("Toshiba thermal", &queues);
        assert!(probed.is_none());
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
