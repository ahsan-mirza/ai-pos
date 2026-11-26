//! Cash-drawer profiles. A pulse is returned only when the selected profile, the
//! confirmed drawer-port voltage, and the host interface all match.
//! Mechanical open or closed is not reported from a kick.

use crate::printer::{checked_pulse, drawer_pulse, PrinterSettings};

#[derive(Clone, Copy, PartialEq, Eq)]
enum Kind {
    /// RJ11/RJ12/RJ45 drawer kick supplied by the receipt printer, not by this PC.
    PrinterDk,
    /// No verified USB driver or SDK is installed.
    Usb,
    /// No verified serial open command is configured.
    Serial,
    /// No OPOS cash-drawer service is installed.
    Opos,
    /// A trigger adapter would be required, and none is verified.
    Adapter,
}

pub struct Profile {
    pub id: &'static str,
    pub name: &'static str,
    pub model: &'static str,
    pub voltage: &'static str,
    pub connector: &'static str,
    pub matrix: &'static str,
    kind: Kind,
    /// ESC/POS pin locked by the profile. None means the saved pin (0 or 1) is used.
    locked_pin: Option<u8>,
    on: u8,
    off: u8,
    pub physical_open_confirmed: bool,
}

const PROFILES: &[Profile] = &[
    Profile {
        id: "hp-vb400-bl1616",
        name: "HP Standard Duty Cash Drawer",
        model: "VB400-BL1616",
        voltage: "24",
        connector: "RJ45 on the drawer. An Epson printer needs an RJ12-to-RJ45 cable.",
        matrix: "supported",
        kind: Kind::PrinterDk,
        locked_pin: Some(0),
        on: 25,
        off: 250,
        physical_open_confirmed: false,
    },
    Profile {
        id: "escpos-dk-24v",
        name: "ESC/POS printer drawer port",
        model: "24V DK",
        voltage: "24",
        connector: "RJ11/RJ12 drawer kick on a 24V receipt printer",
        matrix: "supported",
        kind: Kind::PrinterDk,
        locked_pin: None,
        on: 25,
        off: 250,
        physical_open_confirmed: false,
    },
    Profile {
        id: "escpos-dk-12v",
        name: "ESC/POS printer drawer port",
        model: "12V DK",
        voltage: "12",
        connector: "RJ11/RJ12 drawer kick on a 12V receipt printer",
        matrix: "supported",
        kind: Kind::PrinterDk,
        locked_pin: None,
        on: 25,
        off: 250,
        physical_open_confirmed: false,
    },
    Profile {
        id: "usb-direct",
        name: "Direct USB cash drawer",
        model: "",
        voltage: "",
        connector: "USB",
        matrix: "not_supported",
        kind: Kind::Usb,
        locked_pin: None,
        on: 25,
        off: 250,
        physical_open_confirmed: false,
    },
    Profile {
        id: "serial-direct",
        name: "Serial cash drawer",
        model: "",
        voltage: "",
        connector: "COM",
        matrix: "not_supported",
        kind: Kind::Serial,
        locked_pin: None,
        on: 25,
        off: 250,
        physical_open_confirmed: false,
    },
    Profile {
        id: "opos",
        name: "OPOS cash drawer",
        model: "",
        voltage: "",
        connector: "OPOS",
        matrix: "not_supported",
        kind: Kind::Opos,
        locked_pin: None,
        on: 25,
        off: 250,
        physical_open_confirmed: false,
    },
    Profile {
        id: "trigger-adapter",
        name: "USB or serial trigger adapter",
        model: "",
        voltage: "",
        connector: "adapter",
        matrix: "requires_adapter",
        kind: Kind::Adapter,
        locked_pin: None,
        on: 25,
        off: 250,
        physical_open_confirmed: false,
    },
];

#[derive(Clone, Copy)]
pub struct KickHost<'a> {
    pub driver: &'a str,
    pub port: &'a str,
}

pub fn profiles() -> &'static [Profile] {
    PROFILES
}

pub fn find(id: &str) -> Option<&'static Profile> {
    PROFILES.iter().find(|profile| profile.id == id.trim())
}

pub fn validate(profile_id: &str, voltage: &str) -> Result<(), String> {
    let profile_id = profile_id.trim();
    if !profile_id.is_empty() && find(profile_id).is_none() {
        return Err("That cash drawer profile is not in the compatibility list.".into());
    }
    if !matches!(voltage.trim(), "" | "12" | "24") {
        return Err("Drawer-port voltage must be 12V, 24V, or left unconfirmed.".into());
    }
    Ok(())
}

/// A text-only driver or a raw COM port does not supply a printer drawer-kick solenoid.
pub fn lacks_kick_circuit(driver: &str, port: &str) -> bool {
    crate::printer_discovery::is_text_only_driver(driver) || port.trim().to_ascii_lowercase().starts_with("com")
}

/// Five-byte ESC/POS pulse, or a refusal. Callers that send a standalone kick prepend ESC @.
pub fn require_pulse(settings: &PrinterSettings, host: Option<KickHost<'_>>) -> Result<Vec<u8>, String> {
    let id = settings.drawer_profile.trim();
    let Some(profile) = find(id) else {
        return Err(
            "Choose a cash drawer profile and confirm the printer drawer-port voltage before sending a pulse.".into(),
        );
    };
    match profile.kind {
        Kind::Usb => Err(
            "Direct USB opening is not available. No verified USB cash-drawer driver is installed. AxizPOS will not send a pulse."
                .into(),
        ),
        Kind::Serial => Err(
            "No verified serial open command is configured. AxizPOS will not send a pulse on a COM port.".into(),
        ),
        Kind::Opos => Err(
            "No OPOS cash-drawer service is installed. AxizPOS will not claim the drawer opened.".into(),
        ),
        Kind::Adapter => Err(
            "A compatible USB or serial trigger adapter is required, and no verified adapter command is configured. AxizPOS will not send a pulse."
                .into(),
        ),
        Kind::PrinterDk => {
            if let Some(host) = host {
                if lacks_kick_circuit(host.driver, host.port) {
                    return Err(format!(
                        "Generic / Text Only and COM ports do not supply the {}V drawer-kick circuit this drawer needs. Connect it to a {}V receipt printer DK port. {} AxizPOS will not send a pulse.",
                        profile.voltage, profile.voltage, profile.connector
                    ));
                }
            }
            voltage_ok(profile, &settings.host_voltage)?;
            let (pin, on_units, off_units) = pulse_timing(profile, settings)?;
            Ok(drawer_pulse(pin, on_units, off_units).to_vec())
        }
    }
}

fn voltage_ok(profile: &Profile, selected: &str) -> Result<(), String> {
    let selected = selected.trim();
    if selected.is_empty() {
        return Err(format!(
            "Confirm the receipt printer drawer-port voltage before opening this drawer. {} {} requires a {}V drawer kick port.",
            profile.name, profile.model, profile.voltage
        ));
    }
    if selected != profile.voltage {
        return Err(format!(
            "This drawer is {}V. The selected printer drawer port is {}V. AxizPOS will not send a pulse. 12V and 24V drawers are not interchangeable.",
            profile.voltage, selected
        ));
    }
    Ok(())
}

fn pulse_timing(profile: &Profile, settings: &PrinterSettings) -> Result<(u8, u8, u8), String> {
    if let Some(pin) = profile.locked_pin {
        if settings.drawer_pin != pin {
            return Err(
                "This drawer profile uses connector pin 2. Pin 5 is not part of the verified pulse.".into(),
            );
        }
        return Ok((pin, profile.on, profile.off));
    }
    checked_pulse(settings.drawer_pin, settings.drawer_on, settings.drawer_off)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn settings(profile: &str, voltage: &str) -> PrinterSettings {
        PrinterSettings {
            drawer_profile: profile.into(),
            host_voltage: voltage.into(),
            ..PrinterSettings::default()
        }
    }

    #[test]
    fn hp_drawer_pulses_only_on_a_confirmed_24v_printer_port() {
        let host = KickHost { driver: "EPSON TM-T20 Receipt", port: "USB001" };
        let pulse = require_pulse(&settings("hp-vb400-bl1616", "24"), Some(host)).unwrap();
        assert_eq!(pulse, vec![0x1b, b'p', 0, 25, 250]);
        let wrong = require_pulse(&settings("hp-vb400-bl1616", "12"), Some(host)).unwrap_err();
        assert!(wrong.contains("24V"));
        assert!(wrong.contains("12V"));
        assert!(wrong.contains("not interchangeable"));
        let blank = require_pulse(&settings("hp-vb400-bl1616", ""), Some(host)).unwrap_err();
        assert!(blank.contains("VB400-BL1616"));
        assert!(blank.contains("24V"));
        let com = require_pulse(
            &settings("hp-vb400-bl1616", "24"),
            Some(KickHost { driver: "Generic / Text Only", port: "COM4:" }),
        )
        .unwrap_err();
        assert!(com.contains("will not send a pulse"));
        assert!(com.contains("RJ45"));
    }

    #[test]
    fn twelve_and_twenty_four_volt_profiles_are_not_interchangeable() {
        let host = KickHost { driver: "EPSON TM-T88", port: "USB001" };
        assert!(require_pulse(&settings("escpos-dk-12v", "24"), Some(host)).is_err());
        assert!(require_pulse(&settings("escpos-dk-24v", "12"), Some(host)).is_err());
        let pulse = require_pulse(&settings("escpos-dk-12v", "12"), Some(host)).unwrap();
        assert_eq!(pulse[2], 0);
    }

    #[test]
    fn unverified_interfaces_return_no_bytes() {
        let host = KickHost { driver: "EPSON TM-T20 Receipt", port: "USB001" };
        for id in ["usb-direct", "serial-direct", "opos", "trigger-adapter", ""] {
            let error = require_pulse(&settings(id, "24"), Some(host)).unwrap_err();
            assert!(error.contains("not") || error.contains("No ") || error.contains("Choose"));
        }
        let hp = find("hp-vb400-bl1616").unwrap();
        assert_eq!(hp.matrix, "supported");
        assert!(!hp.physical_open_confirmed);
        assert_eq!(hp.model, "VB400-BL1616");
        assert_eq!(find("usb-direct").unwrap().matrix, "not_supported");
        assert_eq!(find("trigger-adapter").unwrap().matrix, "requires_adapter");
        assert!(profiles().iter().all(|profile| !profile.physical_open_confirmed));
    }
}
