use std::io::Write;
use std::net::{TcpStream, ToSocketAddrs};
use std::path::Path;
use std::time::Duration;

use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};

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
        ",
    )
    .map_err(|err| err.to_string())
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
        }
    }
}

pub fn load(db: &Db) -> Result<PrinterSettings, String> {
    db.read(|conn| {
        conn.query_row(
            "SELECT transport, address, paper_dots, drawer_kick, auto_print, copies FROM printer_settings WHERE id = 1",
            [],
            |row| {
                Ok(PrinterSettings {
                    transport: row.get(0)?,
                    address: row.get(1)?,
                    paper_dots: row.get(2)?,
                    drawer_kick: row.get::<_, i64>(3)? != 0,
                    auto_print: row.get::<_, i64>(4)? != 0,
                    copies: row.get(5)?,
                })
            },
        )
        .optional()
        .map(Option::unwrap_or_default)
        .map_err(|err| err.to_string())
    })
}

pub fn save(db: &Db, settings: &PrinterSettings) -> Result<PrinterSettings, String> {
    if !matches!(settings.transport.as_str(), "none" | "tcp" | "windows") {
        return Err("Choose Network (TCP), Windows printer, or None.".into());
    }
    if settings.transport != "none" && settings.address.trim().is_empty() {
        return Err("Enter the printer address or Windows printer name.".into());
    }
    if !matches!(settings.paper_dots, 384 | 576) {
        return Err("Paper width must be 58 mm (384 dots) or 80 mm (576 dots).".into());
    }
    let copies = settings.copies.clamp(1, 3);
    db.transaction(|tx| {
        tx.execute(
            "INSERT INTO printer_settings (id, transport, address, paper_dots, drawer_kick, auto_print, copies)
             VALUES (1, ?1, ?2, ?3, ?4, ?5, ?6)
             ON CONFLICT(id) DO UPDATE SET transport = excluded.transport, address = excluded.address,
                paper_dots = excluded.paper_dots, drawer_kick = excluded.drawer_kick,
                auto_print = excluded.auto_print, copies = excluded.copies",
            params![
                settings.transport,
                settings.address.trim(),
                settings.paper_dots,
                settings.drawer_kick as i64,
                settings.auto_print as i64,
                copies
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

const DRAWER_KICK: [u8; 5] = [0x1b, b'p', 0, 25, 250];
const BAND_ROWS: u32 = 256;

pub fn escpos_raster(job: &RasterJob, copies: u32) -> Result<Vec<u8>, String> {
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
        if copy == 0 && job.kick_drawer {
            out.extend_from_slice(&DRAWER_KICK);
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
fn send_spooler(name: &str, bytes: &[u8]) -> Result<(), String> {
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
            return Err(format!("Windows printer \"{name}\" was not found."));
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

pub fn print_raster(db: &Db, job: &RasterJob) -> Result<(), String> {
    let settings = load(db)?;
    let bytes = escpos_raster(job, settings.copies)?;
    send(&settings, &bytes)
}

pub fn kick_drawer(db: &Db) -> Result<(), String> {
    let settings = load(db)?;
    let mut bytes = vec![0x1b, b'@'];
    bytes.extend_from_slice(&DRAWER_KICK);
    send(&settings, &bytes)
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
        let bytes = escpos_raster(&job, 2).unwrap();
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
        assert!(escpos_raster(&job, 1).is_err());
    }
}
