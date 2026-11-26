//! Cash drawer routing. The receipt printer is one adapter, not a requirement.
//!
//! A separate USB, serial, network, or vendor controller is kicked only when a
//! verified protocol is registered. This build registers none, so those paths
//! return an error and send no bytes. Discovery and Save do not pulse.

use crate::cash_drawer;
use crate::printer::{kick_allowed, PrinterSettings};

pub const CONNECTION_PRINTER: &str = "printer";
pub const CONNECTION_SEPARATE: &str = "separate";
pub const CONNECTION_NONE: &str = "none";

pub const KICK_GAP_SECS: i64 = 3;

/// Empty stays on the printer path so registers saved before this field keep their kick.
pub fn normalize_connection(value: &str) -> &'static str {
    match value.trim() {
        CONNECTION_SEPARATE => CONNECTION_SEPARATE,
        CONNECTION_NONE => CONNECTION_NONE,
        _ => CONNECTION_PRINTER,
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum KickRoute {
    Printer,
    Separate,
    Off,
}

pub fn route(connection: &str) -> KickRoute {
    match normalize_connection(connection) {
        CONNECTION_SEPARATE => KickRoute::Separate,
        CONNECTION_NONE => KickRoute::Off,
        _ => KickRoute::Printer,
    }
}

/// A controller whose command bytes are documented and cleared for this build.
/// The list is empty on purpose: no USB, serial, network, or vendor SDK is installed.
struct VerifiedController {
    #[cfg_attr(not(test), allow(dead_code))]
    kind: &'static str,
    #[cfg_attr(not(test), allow(dead_code))]
    protocol: &'static str,
}

const VERIFIED_CONTROLLERS: &[VerifiedController] = &[];

pub fn verified_controller(kind: &str, protocol: &str) -> bool {
    VERIFIED_CONTROLLERS
        .iter()
        .any(|item| item.kind == kind && item.protocol == protocol && !protocol.is_empty())
}

pub fn validate_connection(settings: &PrinterSettings) -> Result<(), String> {
    let connection = settings.drawer_connection.trim();
    if !connection.is_empty() && !matches!(connection, CONNECTION_PRINTER | CONNECTION_SEPARATE | CONNECTION_NONE) {
        return Err("Drawer connection must be the receipt printer, a separate device, or none.".into());
    }
    if normalize_connection(connection) != CONNECTION_SEPARATE {
        return Ok(());
    }
    let kind = settings.drawer_controller_kind.trim();
    if !kind.is_empty() && !matches!(kind, "usb" | "serial" | "network" | "vendor") {
        return Err("Choose a USB, serial, network, or vendor drawer controller.".into());
    }
    let address = settings.drawer_controller_address.trim();
    if address.is_empty() {
        return Ok(());
    }
    match kind {
        "serial" => validate_com(address),
        "network" => validate_host(address),
        "usb" | "vendor" | "" => Ok(()),
        _ => Ok(()),
    }
}

pub fn plan_separate(settings: &PrinterSettings, now: i64, last_attempt: i64) -> Result<(), String> {
    if !kick_allowed(now, last_attempt, KICK_GAP_SECS) {
        return Err("Wait a moment before kicking the drawer again.".into());
    }
    let profile_id = settings.drawer_profile.trim();
    if let Some("printer") = cash_drawer::interface(profile_id) {
        return Err(
            "This drawer profile opens through a receipt printer drawer port. Switch the connection to Through receipt printer, or choose a controller that matches the cable. AxizPOS will not send a pulse."
                .into(),
        );
    }
    let kind = settings.drawer_controller_kind.trim();
    if kind.is_empty() {
        return Err("Choose the separate drawer controller before sending a pulse.".into());
    }
    let address = settings.drawer_controller_address.trim();
    let protocol = settings.drawer_controller_protocol.trim();
    match kind {
        "usb" => {
            if verified_controller("usb", protocol) {
                return Ok(());
            }
            Err(
                "No verified USB cash-drawer controller is installed. An RJ11/RJ12 drawer cannot be opened from a PC USB port without a compatible controller. AxizPOS will not send a pulse."
                    .into(),
            )
        }
        "serial" => {
            if address.is_empty() {
                return Err("Choose the COM port for this drawer controller. AxizPOS will not open a port.".into());
            }
            validate_com(address)?;
            if verified_controller("serial", protocol) {
                return Ok(());
            }
            Err(
                "No verified serial open command is configured for this COM port. AxizPOS will not send a pulse."
                    .into(),
            )
        }
        "network" => {
            if address.is_empty() {
                return Err("Enter the drawer controller address. AxizPOS will not search the network.".into());
            }
            validate_host(address)?;
            if verified_controller("network", protocol) {
                return Ok(());
            }
            Err(
                "No verified network drawer protocol is configured. AxizPOS will not send a command to this address."
                    .into(),
            )
        }
        "vendor" => {
            if verified_controller("vendor", protocol) {
                return Ok(());
            }
            Err(
                "No verified vendor cash-drawer SDK is installed for this controller. AxizPOS will not send a pulse."
                    .into(),
            )
        }
        _ => Err("Choose a USB, serial, network, or vendor drawer controller.".into()),
    }
}

/// Status shown beside the printer. The printer's own status is not reused.
pub fn status_label(settings: &PrinterSettings) -> &'static str {
    match route(&settings.drawer_connection) {
        KickRoute::Off => "off",
        KickRoute::Printer => "printer",
        KickRoute::Separate => "blocked",
    }
}

fn validate_com(address: &str) -> Result<(), String> {
    let text = address.trim().trim_end_matches(':');
    let number = text
        .get(3..)
        .filter(|_| text.len() > 3 && text[..3].eq_ignore_ascii_case("com"))
        .and_then(|rest| rest.parse::<u16>().ok());
    match number {
        Some(port) if (1..=256).contains(&port) => Ok(()),
        _ => Err("Enter a COM port from COM1 to COM256. AxizPOS will not open it until a verified command exists.".into()),
    }
}

fn validate_host(address: &str) -> Result<(), String> {
    let value = address.trim();
    if value.is_empty() || value.contains(' ') || value.contains('/') {
        return Err("Enter a drawer controller IP address or hostname. AxizPOS will not send a command.".into());
    }
    let (host, port) = match value.rsplit_once(':') {
        Some((host, port)) if !host.is_empty() && port.chars().all(|c| c.is_ascii_digit()) => (host, Some(port)),
        _ => (value, None),
    };
    if let Some(port) = port {
        let parsed: u32 = port.parse().unwrap_or(0);
        if parsed == 0 || parsed > 65535 {
            return Err("The drawer controller port must be a number from 1 to 65535.".into());
        }
    }
    let labels: Vec<&str> = host.split('.').collect();
    let ok = !labels.is_empty()
        && labels.iter().all(|label| {
            !label.is_empty()
                && label.len() <= 63
                && label.chars().all(|c| c.is_ascii_alphanumeric() || c == '-')
                && !label.starts_with('-')
                && !label.ends_with('-')
        });
    if ok {
        Ok(())
    } else {
        Err("Enter a drawer controller IP address or hostname. AxizPOS will not send a command.".into())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn settings(connection: &str, profile: &str, kind: &str, address: &str) -> PrinterSettings {
        PrinterSettings {
            drawer_connection: connection.into(),
            drawer_profile: profile.into(),
            drawer_controller_kind: kind.into(),
            drawer_controller_address: address.into(),
            ..PrinterSettings::default()
        }
    }

    #[test]
    fn an_empty_connection_stays_on_the_printer_and_none_sends_nothing() {
        assert_eq!(route(""), KickRoute::Printer);
        assert_eq!(route("printer"), KickRoute::Printer);
        assert_eq!(route("separate"), KickRoute::Separate);
        assert_eq!(route("none"), KickRoute::Off);
        assert!(verified_controller("usb", "anything") == false);
    }

    #[test]
    fn a_separate_drawer_does_not_use_the_printer_and_sends_no_bytes() {
        let printer_off = settings("separate", "", "usb", "");
        assert_eq!(printer_off.transport, "none");
        let usb = plan_separate(&printer_off, 100, 0).unwrap_err();
        assert!(usb.contains("USB"));
        assert!(usb.contains("will not send a pulse"));
        let serial = plan_separate(&settings("separate", "", "serial", "COM4"), 100, 0).unwrap_err();
        assert!(serial.contains("serial"));
        assert!(serial.contains("will not send a pulse"));
        let network = plan_separate(&settings("separate", "", "network", "192.168.1.40"), 100, 0).unwrap_err();
        assert!(network.contains("will not send a command"));
        let vendor = plan_separate(&settings("separate", "", "vendor", "controller-1"), 100, 0).unwrap_err();
        assert!(vendor.contains("vendor"));
        assert!(plan_separate(&settings("separate", "", "", ""), 100, 0).unwrap_err().contains("Choose"));
    }

    #[test]
    fn a_printer_profile_cannot_be_kicked_as_a_separate_device() {
        let error = plan_separate(&settings("separate", "hp-vb400-bl1616", "usb", ""), 100, 0).unwrap_err();
        assert!(error.contains("receipt printer"));
        assert!(error.contains("will not send a pulse"));
        let rj = plan_separate(&settings("separate", "escpos-dk-12v", "usb", ""), 100, 0).unwrap_err();
        assert!(rj.contains("receipt printer"));
    }

    #[test]
    fn bad_addresses_and_a_second_kick_are_refused() {
        assert!(plan_separate(&settings("separate", "", "serial", "USB001"), 100, 0).is_err());
        assert!(plan_separate(&settings("separate", "", "network", "not a host"), 100, 0).is_err());
        assert!(plan_separate(&settings("separate", "", "network", ""), 100, 0)
            .unwrap_err()
            .contains("will not search"));
        let again = plan_separate(&settings("separate", "", "usb", ""), 102, 100).unwrap_err();
        assert!(again.contains("Wait a moment"));
        assert!(validate_connection(&settings("separate", "", "serial", "COM1")).is_ok());
        assert!(validate_connection(&settings("sideways", "", "", "")).is_err());
    }

    #[test]
    fn separate_status_stays_blocked_until_a_controller_is_verified() {
        assert_eq!(status_label(&settings("none", "", "", "")), "off");
        assert_eq!(status_label(&settings("", "hp-vb400-bl1616", "", "")), "printer");
        assert_eq!(status_label(&settings("separate", "", "usb", "")), "blocked");
    }
}
