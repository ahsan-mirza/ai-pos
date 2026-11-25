//! Printer profiles and transport selection. This module does not open a device or write bytes.
//!
//! USB printers stay on the Windows spooler. A direct USB claim would take the device away from Windows.
//! Network and Wi-Fi share one TCP adapter. An open port is not a verified receipt printer.
//! Bluetooth Classic is a Windows RFCOMM serial port created after the user pairs in Windows.
//! Bluetooth Low Energy is refused until a documented GATT printing service is registered here.

use serde::Serialize;

pub const BLE_UNSUPPORTED: &str =
    "This Bluetooth Low Energy device does not expose a documented receipt-printing service. It is not a working receipt printer.";
pub const TCP_OPEN_NOTICE: &str =
    "The address accepted a connection. That does not prove it is a receipt printer.";
pub const USB_VIA_WINDOWS: &str =
    "USB printers are used through their Windows queue. AxizPOS does not take the USB device away from Windows.";
pub const NO_VENDOR_ADAPTER: &str = "No documented vendor printing adapter is configured for this printer.";
pub const DRAWER_UNVERIFIED: &str = "Drawer kick is not verified for this connection.";

/// No vendor protocol is registered. Adding one requires a documented command set, not a model-name guess.
pub fn documented_vendor_protocols() -> &'static [&'static str] {
    &[]
}

pub fn automatic_network_scan() -> bool {
    false
}

pub fn default_raw_port() -> u16 {
    9100
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Adapter {
    WindowsSpooler,
    UsbViaSpooler,
    NetworkTcp,
    BluetoothClassic,
    BluetoothBle,
    Vendor,
    None,
}

impl Adapter {
    pub fn name(self) -> &'static str {
        match self {
            Self::WindowsSpooler => "WindowsSpoolerTransport",
            Self::UsbViaSpooler => "UsbRawTransport",
            Self::NetworkTcp => "NetworkTcpTransport",
            Self::BluetoothClassic => "BluetoothClassicTransport",
            Self::BluetoothBle => "BluetoothBleTransport",
            Self::Vendor => "VendorPrinterTransport",
            Self::None => "None",
        }
    }
}

pub fn adapter_name(adapter: Adapter) -> &'static str {
    adapter.name()
}

/// USB is the spooler adapter. The name UsbRawTransport is the extension point, and it does not bypass Windows.
pub fn adapter_for(transport: &str, connection_kind: &str) -> Adapter {
    match (transport, connection_kind) {
        ("windows", "usb") => Adapter::UsbViaSpooler,
        ("windows", _) => Adapter::WindowsSpooler,
        ("tcp", _) => Adapter::NetworkTcp,
        ("serial", _) => Adapter::BluetoothClassic,
        ("ble", _) => Adapter::BluetoothBle,
        ("vendor", _) => Adapter::Vendor,
        _ => Adapter::None,
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum JobPhase {
    Rendering,
    Ready,
    Submitted,
    AcceptedUnverified,
    Failed,
    RetryAvailable,
}

pub fn advance_job(submitted: bool) -> JobPhase {
    if submitted {
        JobPhase::AcceptedUnverified
    } else {
        JobPhase::Failed
    }
}

pub fn retry_creates_sale() -> bool {
    false
}

pub fn retry_kicks_drawer() -> bool {
    false
}

pub fn accept_job(current: Option<&str>, incoming: &str) -> Result<(), &'static str> {
    if incoming.trim().is_empty() {
        return Err("A print job needs an id.");
    }
    if current.is_some() {
        return Err("A print job is already being sent. Wait for it to finish.");
    }
    Ok(())
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct LabelProfile {
    pub model: &'static str,
    pub paper_dots: u32,
    pub protocol: &'static str,
    pub speed_mm_s: u32,
    pub drawer_electrical: &'static str,
    pub connection_known: bool,
    pub drawer_verified: bool,
    pub verified: bool,
}

/// The MTP-3 label is an initial test profile. It does not imply Wi-Fi, Bluetooth, or a verified drawer.
pub fn label_profile(model: &str) -> Option<LabelProfile> {
    let folded = model.trim().to_ascii_lowercase();
    if !folded.contains("mtp-3") && !folded.contains("mtp3") {
        return None;
    }
    Some(LabelProfile {
        model: "MTP-3",
        paper_dots: 576,
        protocol: "escpos",
        speed_mm_s: 90,
        drawer_electrical: "DC 12V / 1A cashbox output",
        connection_known: false,
        drawer_verified: false,
        verified: false,
    })
}

pub fn port_is_usb(port: &str) -> bool {
    let folded = port.trim().to_ascii_lowercase();
    folded.starts_with("usb") || folded.starts_with("toshiba:") || folded.contains("usb")
}

pub fn normalize_com(value: &str) -> Result<String, String> {
    let trimmed = value.trim();
    let folded = trimmed.to_ascii_uppercase();
    let number = folded.strip_prefix("COM").ok_or_else(|| "Select a Bluetooth serial port such as COM5.".to_string())?;
    if number.is_empty() || !number.chars().all(|c| c.is_ascii_digit()) || number.len() > 3 {
        return Err("Select a Bluetooth serial port such as COM5.".into());
    }
    let parsed: u16 = number.parse().map_err(|_| "Select a Bluetooth serial port such as COM5.".to_string())?;
    if parsed == 0 || parsed > 256 {
        return Err("Select a Bluetooth serial port such as COM5.".into());
    }
    Ok(format!("COM{parsed}"))
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct BluetoothSerial {
    pub device: String,
    pub port: String,
    pub pairing: &'static str,
    pub connection: &'static str,
    pub protocol: &'static str,
}

/// A COM port is a Classic printing candidate only when Windows created it for Bluetooth.
/// Detection is not verification.
pub fn bluetooth_serial_port(device_name: &str, com: &str) -> Option<BluetoothSerial> {
    let folded = device_name.to_ascii_lowercase();
    if !(folded.contains("bthmodem") || folded.contains("bthenum") || folded.contains("bluetooth")) {
        return None;
    }
    let port = normalize_com(com).ok()?;
    Some(BluetoothSerial {
        device: device_name.trim().to_string(),
        port,
        pairing: "paired",
        connection: "not_connected",
        protocol: "unverified",
    })
}

/// The documented GATT registry is empty. An unknown service is not a receipt printer.
pub fn ble_service_supported(service_uuid: &str) -> bool {
    let wanted = service_uuid.trim().to_ascii_lowercase();
    if wanted.is_empty() {
        return false;
    }
    documented_ble_services().iter().any(|service| service.eq_ignore_ascii_case(&wanted))
}

fn documented_ble_services() -> &'static [&'static str] {
    &[]
}

pub fn segment_ble<'a>(payload: &'a [u8], max_chunk: usize) -> Result<Vec<&'a [u8]>, String> {
    if max_chunk == 0 {
        return Err("The Bluetooth Low Energy payload size is not known.".into());
    }
    if payload.is_empty() {
        return Err("The printable payload is empty.".into());
    }
    let mut parts = Vec::new();
    let mut start = 0;
    while start < payload.len() {
        let end = (start + max_chunk).min(payload.len());
        parts.push(&payload[start..end]);
        start = end;
    }
    Ok(parts)
}

pub fn tcp_endpoint(address: &str) -> Result<String, String> {
    let trimmed = address.trim();
    if trimmed.is_empty() {
        return Err("Enter the printer IP address or hostname.".into());
    }
    if trimmed.contains(':') {
        return Ok(trimmed.to_string());
    }
    Ok(format!("{trimmed}:{}", default_raw_port()))
}

/// Client-supplied "verified" is ignored. Paper output is the only verification this build accepts, and it is recorded by hand.
pub fn stored_verification(requested: &str) -> &'static str {
    match requested.trim() {
        "offline" => "offline",
        "unsupported" => "unsupported",
        "missing" => "missing",
        "connection-error" => "connection-error",
        _ => "candidate",
    }
}

pub fn connection_pair_ok(transport: &str, connection_kind: &str) -> bool {
    matches!(
        (transport, connection_kind),
        ("none", "none")
            | ("windows", "windows")
            | ("windows", "usb")
            | ("tcp", "network")
            | ("tcp", "wifi")
            | ("serial", "bluetooth-classic")
            | ("ble", "bluetooth-ble")
    )
}

pub fn default_connection(transport: &str) -> &'static str {
    match transport {
        "tcp" => "network",
        "windows" => "windows",
        "serial" => "bluetooth-classic",
        "ble" => "bluetooth-ble",
        _ => "none",
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn adapters_follow_the_connection_not_a_brand_name() {
        assert_eq!(adapter_for("windows", "windows"), Adapter::WindowsSpooler);
        assert_eq!(adapter_for("windows", "usb"), Adapter::UsbViaSpooler);
        assert_eq!(adapter_for("tcp", "wifi"), Adapter::NetworkTcp);
        assert_eq!(adapter_for("tcp", "network"), Adapter::NetworkTcp);
        assert_eq!(adapter_for("serial", "bluetooth-classic"), Adapter::BluetoothClassic);
        assert_eq!(adapter_for("ble", "bluetooth-ble"), Adapter::BluetoothBle);
        assert_eq!(adapter_for("none", "none"), Adapter::None);
        assert_eq!(adapter_name(Adapter::NetworkTcp), "NetworkTcpTransport");
        assert_eq!(adapter_name(Adapter::BluetoothBle), "BluetoothBleTransport");
        assert_eq!(adapter_name(Adapter::Vendor), "VendorPrinterTransport");
        assert!(documented_vendor_protocols().is_empty());
        assert!(!automatic_network_scan());
        assert_eq!(default_raw_port(), 9100);
    }

    #[test]
    fn an_open_port_and_the_mtp3_label_stay_unverified() {
        assert_eq!(stored_verification("verified"), "candidate");
        assert_eq!(stored_verification("connection-error"), "connection-error");
        let label = label_profile("MTP-3").unwrap();
        assert_eq!(label.paper_dots, 576);
        assert_eq!(label.protocol, "escpos");
        assert_eq!(label.speed_mm_s, 90);
        assert!(!label.connection_known);
        assert!(!label.drawer_verified);
        assert!(!label.verified);
        assert!(label_profile("Epson TM-T88").is_none());
        assert_eq!(tcp_endpoint("192.168.1.20").unwrap(), "192.168.1.20:9100");
        assert_eq!(tcp_endpoint("printer.local:9101").unwrap(), "printer.local:9101");
        assert!(TCP_OPEN_NOTICE.contains("does not prove"));
        assert!(USB_VIA_WINDOWS.contains("Windows queue"));
    }

    #[test]
    fn bluetooth_classic_requires_a_windows_bluetooth_port() {
        let found = bluetooth_serial_port(r"\Device\BthModem0", "com5").unwrap();
        assert_eq!(found.port, "COM5");
        assert_eq!(found.pairing, "paired");
        assert_eq!(found.protocol, "unverified");
        assert!(bluetooth_serial_port(r"\Device\Serial0", "COM3").is_none());
        assert!(normalize_com("COM0").is_err());
        assert!(normalize_com(r"\\.\COM5").is_err());
        assert!(normalize_com("COM5 extra").is_err());
    }

    #[test]
    fn ble_without_a_documented_service_is_refused_and_payloads_are_segmented() {
        assert!(!ble_service_supported(""));
        assert!(!ble_service_supported("0000ff00-0000-1000-8000-00805f9b34fb"));
        assert_eq!(segment_ble(&[1, 2, 3, 4, 5], 2).unwrap(), vec![&[1, 2][..], &[3, 4][..], &[5][..]]);
        assert!(segment_ble(&[], 20).is_err());
        assert!(segment_ble(&[1], 0).is_err());
        assert!(BLE_UNSUPPORTED.contains("not a working receipt printer"));
        assert!(!connection_pair_ok("ble", "bluetooth-classic"));
        assert!(connection_pair_ok("tcp", "wifi"));
        assert!(connection_pair_ok("windows", "usb"));
    }

    #[test]
    fn jobs_do_not_overlap_and_a_retry_does_not_create_a_sale_or_kick() {
        assert!(accept_job(None, "job-1").is_ok());
        assert!(accept_job(Some("job-1"), "job-2").is_err());
        assert_eq!(advance_job(true), JobPhase::AcceptedUnverified);
        assert_eq!(advance_job(false), JobPhase::Failed);
        let _ = (JobPhase::Rendering, JobPhase::Ready, JobPhase::Submitted, JobPhase::RetryAvailable);
        assert!(!retry_creates_sale());
        assert!(!retry_kicks_drawer());
        assert!(port_is_usb("USB001"));
        assert!(port_is_usb("Toshiba: 0_USB"));
        assert!(!port_is_usb("192.168.1.20"));
        assert_eq!(NO_VENDOR_ADAPTER.contains("vendor"), true);
        assert_eq!(DRAWER_UNVERIFIED.contains("not verified"), true);
    }
}
