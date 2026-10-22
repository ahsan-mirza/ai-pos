//! Retail scales on a serial (or USB-serial) port. Two common dialects:
//! - "continuous": the scale streams frames such as `ST,GS,+  1.234kg` (ST = stable, US = unstable);
//! - "request": the register sends `W\r` (Toledo / CAS) and the scale answers with one reading.
//! Readings are returned in whole grams; the register subtracts the product's tare itself.

use std::io::{Read, Write};
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize)]
pub struct ScaleReading {
    pub grams: i64,
    pub stable: bool,
    pub raw: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ScaleConfig {
    pub port: String,
    #[serde(default = "default_baud")]
    pub baud: u32,
    /// "continuous" or "request".
    #[serde(default = "default_protocol")]
    pub protocol: String,
}

fn default_baud() -> u32 {
    9600
}

fn default_protocol() -> String {
    "continuous".into()
}

/// The last weight in `text`, in grams. Units: kg (default when a decimal point is present), g, lb, oz.
pub fn parse_frame(text: &str) -> Option<ScaleReading> {
    let frame = text.trim_matches(|c: char| c.is_control() || c.is_whitespace());
    if frame.is_empty() {
        return None;
    }
    let upper = frame.to_ascii_uppercase();
    let stable = !(upper.contains("US") || upper.contains("MOTION") || upper.contains('?'));
    let bytes: Vec<char> = frame.chars().collect();
    let mut found: Option<(f64, String)> = None;
    let mut index = 0;
    while index < bytes.len() {
        let c = bytes[index];
        if c.is_ascii_digit()
            || ((c == '-' || c == '+')
                && index + 1 < bytes.len()
                && bytes[index + 1].is_ascii_digit())
        {
            let start = index;
            index += 1;
            while index < bytes.len() && (bytes[index].is_ascii_digit() || bytes[index] == '.') {
                index += 1;
            }
            let number: String = bytes[start..index].iter().collect();
            let mut unit = String::new();
            let mut cursor = index;
            while cursor < bytes.len() && bytes[cursor] == ' ' {
                cursor += 1;
            }
            while cursor < bytes.len() && bytes[cursor].is_ascii_alphabetic() && unit.len() < 3 {
                unit.push(bytes[cursor].to_ascii_lowercase());
                cursor += 1;
            }
            if let Ok(value) = number.replace('+', "").parse::<f64>() {
                let unit = if unit.is_empty() && number.contains('.') {
                    "kg".to_string()
                } else {
                    unit
                };
                found = Some((value, unit));
            }
            continue;
        }
        index += 1;
    }
    let (value, unit) = found?;
    let grams = match unit.as_str() {
        "g" => value,
        "lb" => value * 453.592_37,
        "oz" => value * 28.349_523,
        _ => value * 1000.0,
    };
    Some(ScaleReading {
        grams: grams.round() as i64,
        stable,
        raw: frame.to_string(),
    })
}

fn read_from(config: &ScaleConfig) -> Result<ScaleReading, String> {
    let mut port = serialport::new(&config.port, config.baud)
        .timeout(Duration::from_millis(300))
        .open()
        .map_err(|err| format!("Could not open the scale on {}: {err}", config.port))?;
    if config.protocol == "request" {
        port.write_all(b"W\r")
            .map_err(|err| format!("Could not ask the scale for a weight: {err}"))?;
    }
    let deadline = Instant::now() + Duration::from_millis(1500);
    let mut buffer = String::new();
    let mut last: Option<ScaleReading> = None;
    let mut chunk = [0u8; 256];
    while Instant::now() < deadline {
        match port.read(&mut chunk) {
            Ok(0) => {}
            Ok(read) => {
                buffer.push_str(&String::from_utf8_lossy(&chunk[..read]));
                while let Some(end) = buffer.find(['\r', '\n']) {
                    let line: String = buffer.drain(..=end).collect();
                    if let Some(reading) = parse_frame(&line) {
                        if reading.stable {
                            return Ok(reading);
                        }
                        last = Some(reading);
                    }
                }
            }
            Err(err) if err.kind() == std::io::ErrorKind::TimedOut => {}
            Err(err) => return Err(format!("The scale stopped responding: {err}")),
        }
    }
    if let Some(reading) = parse_frame(&buffer).or(last) {
        return Ok(reading);
    }
    Err("No reading from the scale. Check the cable, port and protocol.".into())
}

#[tauri::command]
pub fn scale_ports() -> Result<Vec<String>, String> {
    serialport::available_ports()
        .map(|ports| ports.into_iter().map(|port| port.port_name).collect())
        .map_err(|err| err.to_string())
}

#[tauri::command]
pub async fn read_scale(config: ScaleConfig) -> Result<ScaleReading, String> {
    tauri::async_runtime::spawn_blocking(move || read_from(&config))
        .await
        .map_err(|err| err.to_string())?
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_common_frames() {
        let stable = parse_frame("ST,GS,+  1.234kg\r\n").unwrap();
        assert_eq!((stable.grams, stable.stable), (1234, true));
        let moving = parse_frame("US,GS,+  0.998kg").unwrap();
        assert_eq!((moving.grams, moving.stable), (998, false));
        assert_eq!(parse_frame("\u{2}  0.450\r").unwrap().grams, 450);
        assert_eq!(parse_frame("   875 g").unwrap().grams, 875);
        assert_eq!(parse_frame("1.000 lb").unwrap().grams, 454);
        assert!(parse_frame("\r\n").is_none());
    }
}
