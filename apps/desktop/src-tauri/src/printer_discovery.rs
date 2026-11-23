//! Receipt-printer classification and the automatic selection policy.
//!
//! Compatibility comes from driver and port metadata. The Windows queue name is only the handle
//! used to print. A PDF, OneNote, office, or remote-support queue is never chosen because of its name.

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Compatibility {
    Compatible,
    Candidate,
    Unsupported,
}

impl Compatibility {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Compatible => "compatible",
            Self::Candidate => "candidate",
            Self::Unsupported => "unsupported",
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Classified {
    pub compatibility: Compatibility,
    pub supports_drawer_kick: bool,
    pub profile_id: String,
    pub connection: String,
}

struct Profile {
    id: &'static str,
    /// Matched against the driver name, never against the queue name alone.
    driver: &'static str,
}

const PROFILES: &[Profile] = &[
    Profile { id: "epson-tm", driver: "epson tm" },
    Profile { id: "epson-receipt", driver: "epson receipt" },
    Profile { id: "epson-apd", driver: "epson advanced printer" },
    Profile { id: "star-tsp", driver: "star tsp" },
    Profile { id: "star", driver: "star micronics" },
    Profile { id: "bixolon", driver: "bixolon" },
    Profile { id: "citizen-ct", driver: "citizen ct-" },
    Profile { id: "xprinter", driver: "xprinter" },
    Profile { id: "snbc", driver: "snbc" },
    Profile { id: "posiflex", driver: "posiflex" },
    Profile { id: "sewoo", driver: "sewoo" },
    Profile { id: "hprt", driver: "hprt" },
    Profile { id: "gprinter", driver: "gprinter" },
    Profile { id: "rongta", driver: "rongta" },
    Profile { id: "toshiba-tec", driver: "toshiba tec" },
    Profile { id: "thermal-receipt", driver: "thermal receipt" },
];

pub fn connection_kind(port: &str) -> &'static str {
    let port = port.trim().to_ascii_lowercase();
    if port.starts_with("usb") || port.starts_with("dot4") {
        "USB"
    } else if port.starts_with("com") {
        "Serial"
    } else if port == "nul:"
        || port.starts_with("portprompt")
        || port.starts_with("file:")
        || port.starts_with("ad_")
        || port.contains("onenote")
        || port.contains("virtual")
    {
        "Virtual"
    } else if port.starts_with("wsd") || port.starts_with("ip_") || port.starts_with("tcp") || port.contains('.') {
        "Network"
    } else {
        "Other"
    }
}

fn unsupported(driver: &str, port: &str) -> bool {
    const DRIVER_MARKS: &[&str] = &[
        "pdf",
        "onenote",
        "anydesk",
        "xps document",
        "office xps",
        "microsoft xps",
        "microsoft print",
        "fax",
        "virtual print",
        "pcl",
        "postscript",
        "laserjet",
        "hp universal",
        "send to microsoft onenote",
    ];
    if DRIVER_MARKS.iter().any(|mark| driver.contains(mark)) {
        return true;
    }
    let port = port.trim().to_ascii_lowercase();
    port == "nul:" || port.starts_with("portprompt") || port.starts_with("file:") || port.starts_with("ad_")
}

/// Driver and port only. The queue name is intentionally not an argument.
pub fn classify(driver: &str, port: &str) -> Classified {
    let driver_l = driver.trim().to_ascii_lowercase();
    let connection = connection_kind(port).to_string();
    if unsupported(&driver_l, port) {
        return Classified {
            compatibility: Compatibility::Unsupported,
            supports_drawer_kick: false,
            profile_id: String::new(),
            connection,
        };
    }
    if let Some(profile) = PROFILES.iter().find(|profile| driver_l.contains(profile.driver)) {
        return Classified {
            compatibility: Compatibility::Compatible,
            supports_drawer_kick: true,
            profile_id: profile.id.to_string(),
            connection,
        };
    }
    Classified {
        compatibility: Compatibility::Candidate,
        supports_drawer_kick: false,
        profile_id: String::new(),
        connection,
    }
}

#[derive(Clone, Debug)]
pub struct Discovered {
    pub name: String,
    pub driver: String,
    pub port: String,
    pub unavailable: bool,
    pub classed: Classified,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SavedPrinter {
    pub address: String,
    pub previous_address: String,
    pub driver: String,
    pub port: String,
    pub auto_discover: bool,
    pub user_selected: bool,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DiscoveryDecision {
    pub address: String,
    pub previous_address: String,
    pub driver: String,
    pub port: String,
    pub model: String,
    pub user_selected: bool,
    pub outcome: String,
    pub drawer_supported: bool,
    pub changed: bool,
}

impl DiscoveryDecision {
    fn keep(saved: &SavedPrinter, device: Option<&Discovered>, outcome: &str) -> Self {
        let device = device.filter(|item| item.name == saved.address);
        Self {
            address: saved.address.clone(),
            previous_address: saved.previous_address.clone(),
            driver: device.map(|item| item.driver.clone()).unwrap_or_else(|| saved.driver.clone()),
            port: device.map(|item| item.port.clone()).unwrap_or_else(|| saved.port.clone()),
            model: device.map(|item| item.driver.clone()).unwrap_or_else(|| saved.driver.clone()),
            user_selected: saved.user_selected,
            outcome: outcome.to_string(),
            drawer_supported: device.map(|item| item.classed.supports_drawer_kick).unwrap_or(false),
            changed: false,
        }
    }
}

/// Chooses at most one compatible receipt printer. Never substitutes an unsupported queue.
pub fn decide(saved: &SavedPrinter, devices: &[Discovered]) -> DiscoveryDecision {
    if let Some(found) = devices.iter().find(|device| device.name == saved.address) {
        let mut decision = DiscoveryDecision::keep(
            saved,
            Some(found),
            if found.unavailable { "unavailable" } else { "kept" },
        );
        decision.changed = decision.driver != saved.driver || decision.port != saved.port;
        return decision;
    }

    let mut previous = saved.previous_address.clone();
    if previous.trim().is_empty() && !saved.address.trim().is_empty() {
        previous = saved.address.clone();
    }

    if !saved.driver.trim().is_empty() && !saved.port.trim().is_empty() {
        let same: Vec<&Discovered> = devices
            .iter()
            .filter(|device| device.driver == saved.driver && device.port == saved.port && !device.unavailable)
            .collect();
        if same.len() == 1 {
            return adopt(saved, same[0], &previous, "restored", saved.user_selected);
        }
    }

    // An explicit choice stays put when that queue disappears. Automatic selection is only for a name the cashier did not choose.
    if saved.auto_discover && !saved.user_selected {
        let compatible: Vec<&Discovered> = devices
            .iter()
            .filter(|device| device.classed.compatibility == Compatibility::Compatible && !device.unavailable)
            .collect();
        if compatible.len() == 1 {
            return adopt(saved, compatible[0], &previous, "auto", false);
        }
        if compatible.len() > 1 {
            return DiscoveryDecision {
                address: saved.address.clone(),
                previous_address: previous.clone(),
                driver: saved.driver.clone(),
                port: saved.port.clone(),
                model: saved.driver.clone(),
                user_selected: saved.user_selected,
                outcome: "choose".into(),
                drawer_supported: false,
                changed: previous != saved.previous_address,
            };
        }
    }

    DiscoveryDecision {
        address: saved.address.clone(),
        previous_address: previous.clone(),
        driver: saved.driver.clone(),
        port: saved.port.clone(),
        model: saved.driver.clone(),
        user_selected: saved.user_selected,
        outcome: "missing".into(),
        drawer_supported: false,
        changed: previous != saved.previous_address,
    }
}

fn adopt(saved: &SavedPrinter, device: &Discovered, previous: &str, outcome: &str, user_selected: bool) -> DiscoveryDecision {
    let previous = if previous.trim().is_empty() && saved.address != device.name {
        saved.address.clone()
    } else {
        previous.to_string()
    };
    DiscoveryDecision {
        changed: saved.address != device.name
            || saved.driver != device.driver
            || saved.port != device.port
            || saved.previous_address != previous
            || saved.user_selected != user_selected,
        address: device.name.clone(),
        previous_address: previous,
        driver: device.driver.clone(),
        port: device.port.clone(),
        model: device.driver.clone(),
        user_selected,
        outcome: outcome.into(),
        drawer_supported: device.classed.supports_drawer_kick,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn device(name: &str, driver: &str, port: &str, unavailable: bool) -> Discovered {
        Discovered {
            name: name.into(),
            driver: driver.into(),
            port: port.into(),
            unavailable,
            classed: classify(driver, port),
        }
    }

    fn saved(address: &str) -> SavedPrinter {
        SavedPrinter {
            address: address.into(),
            previous_address: String::new(),
            driver: String::new(),
            port: String::new(),
            auto_discover: true,
            user_selected: false,
        }
    }

    #[test]
    fn virtual_and_office_queues_are_not_receipt_printers() {
        assert_eq!(classify("Microsoft Print To PDF", "PORTPROMPT:").compatibility, Compatibility::Unsupported);
        assert_eq!(classify("Send to Microsoft OneNote 16 Driver", "nul:").compatibility, Compatibility::Unsupported);
        assert_eq!(
            classify("Microsoft Virtual Print Class Driver", "Microsoft.Office.OneNoteVirtualPrinter_8wekyb3d8bbwe").connection,
            "Virtual"
        );
        assert_eq!(classify("Canon Office XPS Class Driver", "WSD-1").compatibility, Compatibility::Unsupported);
        assert_eq!(classify("Canon Generic PCL6 Driver", "10.10.101.250").compatibility, Compatibility::Unsupported);
        assert_eq!(classify("AnyDesk v4 Printer Driver", "AD_Port").compatibility, Compatibility::Unsupported);
        let epson = classify("EPSON TM-T88V Receipt", "USB001");
        assert_eq!(epson.compatibility, Compatibility::Compatible);
        assert!(epson.supports_drawer_kick);
        assert_eq!(epson.connection, "USB");
        assert_eq!(classify("Unknown Thermal", "USB002").compatibility, Compatibility::Candidate);
        assert!(!classify("Unknown Thermal", "USB002").supports_drawer_kick);
    }

    #[test]
    fn the_queue_name_alone_does_not_make_a_printer_compatible() {
        let named = classify("Generic Text Driver", "USB001");
        assert_ne!(named.compatibility, Compatibility::Compatible);
    }

    #[test]
    fn an_explicit_missing_printer_is_not_replaced() {
        let devices = vec![device("TM-T20", "EPSON TM-T20 Receipt", "USB001", false)];
        let mut chosen = saved("OneNote (Desktop) - Protected");
        chosen.user_selected = true;
        let decision = decide(&chosen, &devices);
        assert_eq!(decision.address, "OneNote (Desktop) - Protected");
        assert_ne!(decision.outcome, "auto");
    }

    #[test]
    fn one_compatible_printer_replaces_a_missing_saved_name() {
        let devices = vec![
            device("Microsoft Print to PDF", "Microsoft Print To PDF", "PORTPROMPT:", false),
            device("AnyDesk Printer", "AnyDesk v4 Printer Driver", "AD_Port", false),
            device("TM-T20", "EPSON TM-T20 Receipt", "USB001", false),
        ];
        let decision = decide(&saved("Toshiba thermal"), &devices);
        assert_eq!(decision.outcome, "auto");
        assert_eq!(decision.address, "TM-T20");
        assert_eq!(decision.previous_address, "Toshiba thermal");
        assert!(decision.drawer_supported);
        assert!(devices.iter().any(|item| item.name == "Microsoft Print to PDF"));
        assert_ne!(decision.address, "Microsoft Print to PDF");
    }

    #[test]
    fn several_compatible_printers_wait_for_a_choice() {
        let devices = vec![
            device("Front", "EPSON TM-T20 Receipt", "USB001", false),
            device("Bar", "Star TSP100 Cutter", "USB002", false),
        ];
        let decision = decide(&saved("Toshiba thermal"), &devices);
        assert_eq!(decision.outcome, "choose");
        assert_eq!(decision.address, "Toshiba thermal");
        assert!(!decision.drawer_supported);
    }

    #[test]
    fn no_compatible_printer_keeps_the_missing_name() {
        let devices = vec![
            device("Microsoft Print to PDF", "Microsoft Print To PDF", "PORTPROMPT:", false),
            device("iR-ADV C3525", "Canon Office XPS Class Driver", "WSD-1", true),
            device("Canon Generic PCL6 Driver", "Canon Generic PCL6 Driver", "10.10.101.250", false),
        ];
        let decision = decide(&saved("Toshiba thermal"), &devices);
        assert_eq!(decision.outcome, "missing");
        assert_eq!(decision.address, "Toshiba thermal");
        assert_eq!(decision.previous_address, "Toshiba thermal");
        assert!(!decision.drawer_supported);
    }

    #[test]
    fn an_offline_compatible_printer_is_not_auto_selected() {
        let devices = vec![device("TM-T20", "EPSON TM-T20 Receipt", "USB001", true)];
        let decision = decide(&saved("Toshiba thermal"), &devices);
        assert_eq!(decision.outcome, "missing");
        assert_eq!(decision.address, "Toshiba thermal");
    }

    #[test]
    fn a_saved_printer_is_kept_when_it_returns() {
        let devices = vec![device("TM-T20", "EPSON TM-T20 Receipt", "USB001", false)];
        let mut stored = saved("TM-T20");
        stored.driver = "EPSON TM-T20 Receipt".into();
        stored.port = "USB001".into();
        stored.user_selected = true;
        let decision = decide(&stored, &devices);
        assert_eq!(decision.outcome, "kept");
        assert_eq!(decision.address, "TM-T20");
        assert!(decision.drawer_supported);
    }

    #[test]
    fn the_same_driver_and_port_restore_a_renamed_queue() {
        let devices = vec![
            device("TM-T20 Copy", "EPSON TM-T20 Receipt", "USB001", false),
            device("Microsoft Print to PDF", "Microsoft Print To PDF", "PORTPROMPT:", false),
        ];
        let mut stored = saved("TM-T20");
        stored.driver = "EPSON TM-T20 Receipt".into();
        stored.port = "USB001".into();
        let decision = decide(&stored, &devices);
        assert_eq!(decision.outcome, "restored");
        assert_eq!(decision.address, "TM-T20 Copy");
        assert_eq!(decision.previous_address, "TM-T20");
    }

    #[test]
    fn an_ambiguous_replacement_is_not_chosen() {
        let devices = vec![
            device("Copy A", "EPSON TM-T20 Receipt", "USB001", false),
            device("Copy B", "EPSON TM-T20 Receipt", "USB001", false),
        ];
        let mut stored = saved("TM-T20");
        stored.driver = "EPSON TM-T20 Receipt".into();
        stored.port = "USB001".into();
        let decision = decide(&stored, &devices);
        assert_ne!(decision.outcome, "restored");
        assert_eq!(decision.address, "TM-T20");
    }

    #[test]
    fn two_register_databases_do_not_share_a_choice() {
        let one = decide(&saved("Toshiba thermal"), &[device("Front", "EPSON TM-T20 Receipt", "USB001", false)]);
        let two = decide(&saved("Toshiba thermal"), &[]);
        assert_eq!(one.address, "Front");
        assert_eq!(two.address, "Toshiba thermal");
    }
}
