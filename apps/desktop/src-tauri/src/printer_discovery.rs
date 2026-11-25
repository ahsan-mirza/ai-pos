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

/// How a Windows queue can receive a receipt. Raw ESC/POS is only for a known receipt profile.
/// A native Windows driver, including Toshiba's, gets a rendered page instead.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PrintTransport {
    EscPos,
    WindowsGdi,
    None,
}

impl PrintTransport {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::EscPos => "escpos",
            Self::WindowsGdi => "windows-gdi",
            Self::None => "none",
        }
    }
}

pub const CANDIDATE_NOTICE: &str =
    "Printer detected, but its receipt-printing profile has not been verified. Complete the printer test before using it for customer receipts.";
pub const UNSUPPORTED_METHOD: &str = "This printer does not support the configured AxizPOS receipt-printing method.";
pub const OFFLINE_NOTICE: &str = "The printer is installed but currently unavailable.";
pub const QUEUE_CLOSED: &str = "Windows found the printer, but AxizPOS could not open its queue.";
pub const RENDER_FAILED: &str = "The invoice was generated, but its printable content could not be rendered.";
pub const TRANSMIT_FAILED: &str = "Receipt content was generated, but the printer did not accept the print job.";
pub const SPOOLER_ACCEPTED: &str = "The printer job was submitted, but physical output has not yet been verified.";
pub const MISSING_QUEUE: &str =
    "The previously selected Windows printer is not installed. Refresh the printer list or select another device.";

/// Candidate copy. A Toshiba Native driver names the queue and the driver instead of a generic warning.
pub fn candidate_notice(name: &str, driver: &str) -> String {
    let driver_l = driver.trim().to_ascii_lowercase();
    if driver_l.contains("toshiba") && driver_l.contains("native") {
        return format!(
            "{name} was discovered using the {driver}. Receipt printing has not yet been verified. Run the printer test to confirm the supported print method."
        );
    }
    CANDIDATE_NOTICE.to_string()
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
    if port.starts_with("toshiba:") || port.starts_with("usb") || port.starts_with("dot4") {
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

/// Generic / Text Only prints characters and discards a picture, while still accepting the job.
pub fn is_text_only_driver(driver: &str) -> bool {
    let folded = driver.trim().to_ascii_lowercase();
    folded.contains("text only") || folded.contains("generic text") || folded.contains("generic / text")
}

/// Vendor port monitors and "Native Windows Driver" expect a GDI page, not ESC/POS bytes.
pub fn expects_rendered_job(driver: &str, port: &str) -> bool {
    let driver_l = driver.trim().to_ascii_lowercase();
    let port_l = port.trim().to_ascii_lowercase();
    port_l.starts_with("toshiba:") || driver_l.contains("native windows driver")
}

/// Known receipt profiles use raw ESC/POS. Everything else that is still a real printer uses GDI.
/// An unverified queue is not given raw commands.
pub fn select_transport(driver: &str, port: &str) -> PrintTransport {
    let classed = classify(driver, port);
    if classed.compatibility == Compatibility::Unsupported {
        return PrintTransport::None;
    }
    if expects_rendered_job(driver, port) {
        return PrintTransport::WindowsGdi;
    }
    if classed.compatibility == Compatibility::Compatible {
        return PrintTransport::EscPos;
    }
    PrintTransport::WindowsGdi
}

/// A driver that reports EMF or XPS confirms the rendered path. RAW does not override a native Windows driver.
pub fn transport_for(driver: &str, port: &str, default_datatype: &str) -> PrintTransport {
    let selected = select_transport(driver, port);
    if selected == PrintTransport::None {
        return selected;
    }
    let kind = default_datatype.trim().to_ascii_lowercase();
    if kind.contains("emf") || kind.contains("xps") {
        return PrintTransport::WindowsGdi;
    }
    selected
}

pub fn capability_summary(transport: PrintTransport, drawer: bool) -> String {
    match transport {
        PrintTransport::EscPos if drawer => "ESC/POS receipt graphics. Drawer kick is a separate verified profile.".into(),
        PrintTransport::EscPos => "ESC/POS receipt graphics. Drawer kick is not verified.".into(),
        PrintTransport::WindowsGdi => "Windows driver graphics. Raw ESC/POS is not sent. Drawer kick is not verified.".into(),
        PrintTransport::None => "No supported receipt transport.".into(),
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
    fn toshiba_native_driver_stays_a_candidate_and_uses_gdi() {
        let classed = classify("Toshiba Native Windows Driver", "Toshiba: 0_USB");
        assert_eq!(classed.compatibility, Compatibility::Candidate);
        assert!(!classed.supports_drawer_kick);
        assert_eq!(classed.connection, "USB");
        assert_eq!(classed.profile_id, "");
        assert!(expects_rendered_job("Toshiba Native Windows Driver", "Toshiba: 0_USB"));
        assert_eq!(
            select_transport("Toshiba Native Windows Driver", "Toshiba: 0_USB"),
            PrintTransport::WindowsGdi
        );
        assert_eq!(
            transport_for("Toshiba Native Windows Driver", "Toshiba: 0_USB", "RAW"),
            PrintTransport::WindowsGdi
        );
        assert_eq!(
            transport_for("EPSON TM-T88V Receipt", "USB001", "NT EMF 1.008"),
            PrintTransport::WindowsGdi
        );
        let notice = candidate_notice("Toshiba POS Printer (CR)", "Toshiba Native Windows Driver");
        assert_eq!(
            notice,
            "Toshiba POS Printer (CR) was discovered using the Toshiba Native Windows Driver. Receipt printing has not yet been verified. Run the printer test to confirm the supported print method."
        );
        assert!(!notice.to_ascii_lowercase().contains("unsupported"));
        assert_eq!(select_transport("EPSON TM-T88V Receipt", "USB001"), PrintTransport::EscPos);
        assert_eq!(select_transport("Unknown Thermal", "USB002"), PrintTransport::WindowsGdi);
        assert_eq!(select_transport("Microsoft Print To PDF", "PORTPROMPT:"), PrintTransport::None);
        assert_eq!(select_transport("Canon Generic PCL6 Driver", "10.10.101.250"), PrintTransport::None);
        assert!(capability_summary(PrintTransport::WindowsGdi, false).contains("Drawer kick is not verified"));
        assert!(SPOOLER_ACCEPTED.contains("physical output has not yet been verified"));
        assert!(RENDER_FAILED.contains("could not be rendered"));
        assert!(TRANSMIT_FAILED.contains("did not accept"));
        assert!(QUEUE_CLOSED.contains("could not open"));
        assert!(OFFLINE_NOTICE.contains("unavailable"));
        assert!(MISSING_QUEUE.contains("not installed"));
        assert!(UNSUPPORTED_METHOD.contains("does not support"));
    }

    #[test]
    fn the_queue_name_alone_does_not_make_a_printer_compatible() {
        let named = classify("Generic Text Driver", "USB001");
        assert_ne!(named.compatibility, Compatibility::Compatible);
        assert!(is_text_only_driver("Generic / Text Only"));
        assert!(is_text_only_driver("Generic Text Driver"));
        assert!(!is_text_only_driver("EPSON TM-T20 Receipt"));
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
