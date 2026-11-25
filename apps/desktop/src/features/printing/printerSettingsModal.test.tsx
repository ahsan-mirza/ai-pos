import { PAPER_DOTS, type ReceiptDoc } from "@ai-pos/receipt";
import { diagnosticReceipt } from "./saleReceipt";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { InstalledPrinter, PrinterProbe, PrinterSettings } from "../../lib/tauri";
import { PrinterSettingsModal } from "./PrinterSettingsModal";
import { ReceiptHardwareCard } from "./ReceiptHardwareCard";
import {
  CONNECTED,
  DISCOVERING,
  MISSING,
  CANDIDATE,
  NONE_FOUND,
  OFFLINE,
  SPOOLER_ACCEPTED,
  UNSUPPORTED_METHOD,
  acceptsSavedName,
  applySelection,
  canTestDrawer,
  canTestDrawerFromProbe,
  canTestPrint,
  canTestPrintFromProbe,
  candidateMessage,
  connectionMessage,
  dedupePrinters,
  diagnosticStages,
  printableDots,
  REGISTER_VIEW_ONLY,
  testReceiptPrompt,
  filterPrinters,
  foundMessage,
  inkBytes,
  rejectEmptyRaster,
  selectionAfterRefresh,
  networkAddressError,
  saveFeedback,
  selectionWarning,
  VIRTUAL_SAVED,
  MISSING_SAVED,
} from "./printerSelection";

const sample = {} as ReceiptDoc;

function queue(patch: Partial<InstalledPrinter> & Pick<InstalledPrinter, "name">): InstalledPrinter {
  return {
    driver: "EPSON TM-T20 Receipt",
    port: "USB001",
    status: 0,
    statusLabel: "Ready",
    unavailable: false,
    compatibility: "compatible",
    supportsDrawerKick: true,
    connection: "USB",
    profileId: "epson-tm",
    manufacturer: "Epson",
    identity: "{epson}",
    openable: true,
    availability: "ready",
    ...patch,
  };
}

function settings(patch: Partial<PrinterSettings> = {}): PrinterSettings {
  return {
    transport: "windows",
    address: "Epson TM-T20",
    paper_dots: 576,
    drawer_kick: true,
    auto_print: true,
    copies: 1,
    drawer_pin: 0,
    saved_driver: "EPSON TM-T20 Receipt",
    saved_port: "USB001",
    saved_identity: "{epson}",
    user_selected: true,
    ...patch,
  };
}

function probe(patch: Partial<PrinterProbe> = {}): PrinterProbe {
  return {
    configured: true,
    transport: "windows",
    address: "Epson TM-T20",
    reachable: true,
    reachError: null,
    lastOkAt: null,
    lastError: null,
    lastErrorAt: null,
    lastKickOkAt: null,
    lastKickError: null,
    lastKickAttemptAt: null,
    drawerKick: true,
    printing: false,
    printerStatus: "ready",
    driver: "EPSON TM-T20 Receipt",
    port: "USB001",
    discoveredAt: null,
    drawerOpenState: "not_reported",
    compatibility: "compatible",
    supportsDrawerKick: true,
    connection: "USB",
    discoveryOutcome: "kept",
    previousAddress: "",
    autoDiscover: true,
    model: "Epson",
    driverVersion: null,
    ...patch,
  };
}

const epson = queue({ name: "Epson TM-T20" });
const pdf = queue({
  name: "Microsoft Print to PDF",
  driver: "Microsoft Print To PDF",
  port: "PORTPROMPT:",
  statusLabel: "Virtual printer",
  compatibility: "unsupported",
  supportsDrawerKick: false,
  connection: "Virtual",
  profileId: "",
  manufacturer: "Microsoft",
  identity: "{pdf}",
  availability: "virtual",
});
const offline = queue({
  name: "Canon iR-ADV C3525",
  driver: "Canon Office XPS Class Driver",
  port: "WSD",
  status: 0x80,
  statusLabel: "Offline",
  unavailable: true,
  compatibility: "unsupported",
  supportsDrawerKick: false,
  connection: "Network",
  profileId: "",
  manufacturer: "Canon",
  identity: "",
  availability: "offline",
});

function controlDisabled(html: string, label: string): boolean {
  const tag = html.match(new RegExp(`<button[^>]*>${label}</button>`))?.[0] ?? "";
  return tag.replace(/class="[^"]*"/g, "").includes("disabled");
}

function modal(draft: PrinterSettings, queues: InstalledPrinter[], loading = false): string {
  return renderToStaticMarkup(
    <PrinterSettingsModal
      sample={sample}
      onClose={() => undefined}
      onSaved={() => undefined}
      initialDraft={draft}
      initialQueues={queues}
      initialLoading={loading}
    />,
  );
}

describe("Windows printer dropdown", () => {
  const listed = [epson, pdf, offline];

  it("populates the list from discovery and keeps the selected queue", () => {
    const html = modal(settings(), listed);
    expect(html).toContain("Select Windows printer");
    expect(html).toContain("Epson TM-T20");
    expect(html).toContain("Microsoft Print to PDF");
    expect(html).toContain("Canon iR-ADV C3525");
    expect(html).toContain("Ready");
    expect(html).toContain("Virtual printer");
    expect(html).toContain("Offline");
    expect(html).toContain(foundMessage(3));
    expect(html).toContain("Refresh printers");
    expect(html).toContain("USB001");
    expect(html).not.toContain("Windows printer name");
  });

  it("searches by queue name and selects that exact name", () => {
    expect(filterPrinters(listed, "pdf").map((item) => item.name)).toEqual(["Microsoft Print to PDF"]);
    expect(filterPrinters(listed, "epson").map((item) => item.name)).toEqual(["Epson TM-T20"]);
    expect(filterPrinters(listed, "not-a-printer")).toEqual([]);
    const chosen = applySelection(epson);
    expect(chosen.address).toBe("Epson TM-T20");
    expect(chosen.saved_driver).toBe("EPSON TM-T20 Receipt");
    expect(chosen.saved_port).toBe("USB001");
    expect(chosen.saved_identity).toBe("{epson}");
    expect(chosen.user_selected).toBe(true);
  });

  it("refreshes without duplicating rows or replacing the selection", () => {
    const refreshed = dedupePrinters([epson, epson, pdf]);
    expect(refreshed.map((item) => item.name)).toEqual(["Epson TM-T20", "Microsoft Print to PDF"]);
    expect(selectionAfterRefresh("Epson TM-T20", refreshed)).toEqual({ address: "Epson TM-T20", missing: false });
    expect(selectionAfterRefresh("Toshiba thermal", refreshed)).toEqual({ address: "Toshiba thermal", missing: true });
    expect(selectionAfterRefresh("Toshiba thermal", refreshed).address).not.toBe("Epson TM-T20");
  });

  it("warns when the saved printer is no longer installed", () => {
    const html = modal(settings({ address: "Toshiba thermal", saved_identity: "" }), listed);
    expect(html).toContain("Toshiba thermal");
    expect(html).toContain("Not installed");
    expect(html).toContain(MISSING);
    expect(controlDisabled(html, "Print test receipt")).toBe(true);
    expect(canTestPrint(settings({ address: "Toshiba thermal" }), listed)).toBe(false);
    expect(canTestDrawer(settings({ address: "Toshiba thermal" }), listed)).toBe(false);
  });

  it("shows an empty discovery result", () => {
    const html = modal(settings({ address: "" }), [], false);
    expect(html).toContain(NONE_FOUND);
    expect(html).toContain("Select a printer");
    expect(canTestPrint(settings({ address: "" }), [])).toBe(false);
  });

  it("shows a loading discovery result", () => {
    const html = modal(settings(), [], true);
    expect(html).toContain(DISCOVERING);
    expect(html).not.toContain(NONE_FOUND);
  });

  it("marks an offline printer and blocks test print and drawer kick", () => {
    const html = modal(settings({ address: offline.name }), listed);
    expect(html).toContain(OFFLINE);
    expect(selectionWarning(offline.name, listed)).toBe(OFFLINE);
    expect(canTestPrint(settings({ address: offline.name }), listed)).toBe(false);
    expect(canTestDrawer(settings({ address: offline.name }), listed)).toBe(false);
    expect(controlDisabled(html, "Print test receipt")).toBe(true);
  });

  it("saves an unsupported queue without calling it a connected receipt printer", () => {
    expect(saveFeedback(settings({ address: pdf.name }), listed)).toBe(VIRTUAL_SAVED);
    expect(saveFeedback(settings({ address: "Missing queue" }), listed)).toBe(MISSING_SAVED);
    expect(saveFeedback(settings({ transport: "none", address: "" }), listed)).toContain("No receipt printer");
    expect(saveFeedback(settings({ transport: "tcp", address: "192.168.1.50" }), listed)).toContain("Printer settings saved");
    expect(networkAddressError("192.168.1.50")).toBeNull();
    expect(networkAddressError("192.168.1.50:9100")).toBeNull();
    expect(networkAddressError("999.1.1.1")).not.toBeNull();
    expect(networkAddressError("10.0.0.5:0")).not.toBeNull();
    expect(networkAddressError("")).not.toBeNull();
    const blocked = modal(settings({ address: pdf.name }), listed);
    expect(blocked).toContain("Save");
    const saving = renderToStaticMarkup(
      <PrinterSettingsModal sample={sample} onClose={() => undefined} onSaved={() => undefined} initialDraft={settings()} initialQueues={listed} initialBusy />,
    );
    expect(controlDisabled(saving, "Saving…")).toBe(true);
    const denied = renderToStaticMarkup(
      <PrinterSettingsModal sample={sample} onClose={() => undefined} onSaved={() => undefined} initialDraft={settings()} initialQueues={listed} canSave={false} />,
    );
    expect(denied.match(/You can view printer status/g)).toHaveLength(1);
    expect(denied).toContain(REGISTER_VIEW_ONLY);
    expect(denied).not.toContain("needs permission to manage this register");
    expect(controlDisabled(denied, "Windows printer")).toBe(false);
    expect(controlDisabled(denied, "USB")).toBe(false);
    expect(controlDisabled(denied, "Network / Wi-Fi")).toBe(false);
    expect(controlDisabled(denied, "Bluetooth")).toBe(false);
    expect(controlDisabled(denied, "None")).toBe(false);
    expect(denied.match(/<button[^>]*data-connection="windows"[^>]*>/)?.[0]).toContain('tabindex="0"');
    expect(denied.match(/<button[^>]*data-connection="none"[^>]*>/)?.[0]).toContain('tabindex="-1"');
    const listboxes = [...denied.matchAll(/<button[^>]*aria-haspopup="listbox"[^>]*>/g)].map((match) => match[0].replace(/class="[^"]*"/g, ""));
    expect(listboxes[0]?.includes("disabled")).toBe(false);
    expect(listboxes[1]?.includes("disabled")).toBe(true);
    expect(controlDisabled(denied, "Print test receipt")).toBe(true);
    expect(printableDots("80 mm")).toBe(PAPER_DOTS["80mm"]);
    expect(printableDots("58 mm")).toBe(384);
    expect(testReceiptPrompt("Front")).toContain("does not create a sale");
    expect(testReceiptPrompt("Front")).toContain("cash drawer");
    expect(controlDisabled(denied, "Save")).toBe(true);
  });

  it("identifies a virtual printer and does not treat it as a receipt printer", () => {
    const html = modal(settings({ address: pdf.name, saved_identity: "{pdf}" }), listed);
    expect(html).toContain("Virtual printer");
    expect(html).toContain(UNSUPPORTED_METHOD);
    expect(controlDisabled(html, "Print test receipt")).toBe(true);
    expect(canTestPrint(settings({ address: pdf.name }), listed)).toBe(false);
    expect(canTestDrawer(settings({ address: pdf.name }), listed)).toBe(false);
    expect(connectionMessage(probe({ printerStatus: "unavailable", reachable: false, compatibility: "unsupported", reachError: UNSUPPORTED_METHOD }))).toBe(UNSUPPORTED_METHOD);
    expect(connectionMessage(probe())).toBe(CONNECTED);
  });

  it("saves only an installed queue or the previously stored name", () => {
    expect(acceptsSavedName("Epson TM-T20", listed, "")).toBe(true);
    expect(acceptsSavedName("Typed printer", listed, "")).toBe(false);
    expect(acceptsSavedName("Toshiba thermal", listed, "Toshiba thermal")).toBe(true);
    expect(acceptsSavedName("", listed, "Epson TM-T20")).toBe(false);
  });

  it("reopens with the persisted queue still selected", () => {
    const html = modal(settings(), [epson]);
    expect(html).toContain("Epson TM-T20");
    expect(html).toContain(foundMessage(1));
    expect(html).not.toContain(MISSING);
    expect(controlDisabled(html, "Print test receipt")).toBe(false);
    expect(canTestPrint(settings(), [epson])).toBe(true);
    expect(canTestDrawer(settings(), [epson])).toBe(true);
  });

  it("leaves network and none modes on their existing controls", () => {
    const lan = modal(settings({ transport: "tcp", address: "192.168.1.50" }), listed);
    expect(lan).toContain("Printer IP address");
    expect(lan).toContain("192.168.1.50");
    expect(lan).not.toContain("Select Windows printer");
    expect(lan).toContain("80 mm");
    expect(lan).toContain("Ask before printing a sale receipt");
    expect(lan).toContain("Pay always asks after the payment is saved");
    expect(lan).not.toContain("Print a receipt after every sale");
    expect(lan).toMatch(/Ask before printing a sale receipt[\s\S]*<input[^>]*disabled/);
    expect(lan).toContain("Print test receipt");
    expect(lan).toContain("Cancel");
    expect(lan).toContain("Save");
    expect(canTestPrint(settings({ transport: "tcp", address: "192.168.1.50" }), [])).toBe(true);

    const none = modal(settings({ transport: "none", address: "" }), listed);
    expect(none).toContain("Without a receipt printer");
    expect(none).not.toContain("Select Windows printer");
    expect(none).toMatch(/Open the cash drawer for cash payments<input[^>]*disabled/);
    expect(canTestDrawer(settings({ transport: "none" }), listed)).toBe(false);
    expect(canTestPrint(settings({ transport: "none", address: "" }), [])).toBe(true);
  });

  it("disables drawer kick on the hardware card when the printer cannot kick", () => {
    const blocked = renderToStaticMarkup(
      <ReceiptHardwareCard
        sample={sample}
        onChangePrinter={() => undefined}
        initialProbe={probe({ printerStatus: "offline", reachable: false, compatibility: "compatible", reachError: OFFLINE })}
        initialQueues={[offline]}
      />,
    );
    expect(blocked).toContain(OFFLINE);
    expect(blocked).toMatch(/Test drawer kick/);
    expect(controlDisabled(blocked, "Test drawer kick")).toBe(true);
    expect(controlDisabled(blocked, "Print test receipt")).toBe(true);
    expect(canTestDrawerFromProbe(probe({ printerStatus: "offline", reachable: false }))).toBe(false);
    expect(canTestPrintFromProbe(probe({ printerStatus: "offline", reachable: false }))).toBe(false);

    const virtual = renderToStaticMarkup(
      <ReceiptHardwareCard
        sample={sample}
        onChangePrinter={() => undefined}
        initialProbe={probe({
          address: pdf.name,
          printerStatus: "unavailable",
          reachable: false,
          compatibility: "unsupported",
          supportsDrawerKick: false,
          reachError: UNSUPPORTED_METHOD,
        })}
        initialQueues={[pdf]}
      />,
    );
    expect(virtual).toContain(UNSUPPORTED_METHOD);
    expect(virtual).toContain("Microsoft Print to PDF");
    expect(canTestDrawerFromProbe(probe({ compatibility: "unsupported", supportsDrawerKick: true, printerStatus: "ready" }))).toBe(false);

    const ready = renderToStaticMarkup(
      <ReceiptHardwareCard sample={sample} onChangePrinter={() => undefined} initialProbe={probe()} initialQueues={[epson]} />,
    );
    expect(ready).toContain("Epson TM-T20");
    expect(ready).toContain("Not reported");
    expect(canTestDrawerFromProbe(probe())).toBe(true);
    expect(canTestPrintFromProbe(probe())).toBe(true);
    expect(controlDisabled(ready, "Test drawer kick")).toBe(false);
  });

  it("keeps the Toshiba queue as a candidate and does not call it unsupported", () => {
    const toshiba = queue({
      name: "Toshiba POS Printer (CR)",
      driver: "Toshiba Native Windows Driver",
      port: "Toshiba: 0_USB",
      statusLabel: "Candidate",
      compatibility: "candidate",
      supportsDrawerKick: false,
      connection: "USB",
      profileId: "",
      manufacturer: "Toshiba",
      availability: "ready",
      printTransport: "windows-gdi",
      capabilities: "Windows driver graphics. Raw ESC/POS is not sent. Drawer kick is not verified.",
    });
    const draft = settings({
      address: toshiba.name,
      saved_driver: toshiba.driver,
      saved_port: toshiba.port,
      drawer_pin: 1,
      paper_dots: 576,
    });
    const html = modal(draft, [toshiba, pdf]);
    const notice = candidateMessage(toshiba);
    expect(notice).toBe(
      "Toshiba POS Printer (CR) was discovered using the Toshiba Native Windows Driver. Receipt printing has not yet been verified. Run the printer test to confirm the supported print method.",
    );
    expect(html).toContain(notice);
    expect(html).toContain("windows-gdi");
    expect(html).toContain("Toshiba: 0_USB");
    expect(html).not.toContain("does not support the configured");
    expect(selectionWarning(toshiba.name, [toshiba])).toBe(notice);
    expect(canTestPrint(draft, [toshiba])).toBe(true);
    expect(canTestDrawer(draft, [toshiba])).toBe(false);
    expect(controlDisabled(html, "Print test receipt")).toBe(false);
    expect(controlDisabled(html, "Test drawer kick")).toBe(true);
    expect(saveFeedback(draft, [toshiba])).toContain("Register settings saved");
    expect(saveFeedback(draft, [toshiba])).toContain("not yet been verified");
    expect(saveFeedback(draft, [toshiba])).not.toContain(CANDIDATE);
    const slip = diagnosticReceipt({ queue: toshiba.name, driver: toshiba.driver, port: toshiba.port, paper: "80 mm" });
    expect(slip.storeName).toBe("AXIZPOS PRINTER TEST");
    expect(slip.storeAddress).toContain("Printer: Toshiba POS Printer (CR)");
    expect(slip.storeAddress).toContain("Driver: Toshiba Native Windows Driver");
    expect(slip.storeAddress).toContain("Port: Toshiba: 0_USB");
    expect(slip.storeAddress).toContain("Paper: 80 mm");
    expect(slip.storeAddress).toContain("Text rendering: TEST");
    expect(slip.storeAddress).not.toContain("Protocol: ESC/POS");
    const verified = diagnosticReceipt({ queue: "MTP-3", driver: "ESC/POS", port: "USB001", paper: "80 mm", model: "MTP-3", protocol: "escpos" });
    expect(verified.storeAddress).toContain("Printer: MTP-3");
    expect(verified.storeAddress).toContain("Protocol: ESC/POS");
    expect(slip.lines[0]?.name).toBe("Sample item");
    expect(slip.lines[0]?.detail).toBe("Regular portion");
    expect(slip.totalCents).toBe(1_050);
    expect(slip.footer).toContain("Not a sale");
    expect(rejectEmptyRaster([])).toBeTruthy();
    expect(rejectEmptyRaster([0, 0])).toBeTruthy();
    expect(inkBytes([0, 0xff])).toBe(1);
    expect(rejectEmptyRaster([0xff])).toBeNull();
    const stages = diagnosticStages({ queue: toshiba, missing: false, rendered: true, ink: 12, submitted: true, lineCount: 1 });
    expect(stages.find((item) => item.stage === "Printer profile identified")?.result).toBe("unverified");
    expect(stages.find((item) => item.stage === "Print job submitted")?.result).toBe("passed");
    expect(stages.find((item) => item.stage === "Physical text verified")?.result).toBe("not_run");
    expect(SPOOLER_ACCEPTED).toContain("physical output has not yet been verified");
    const preview = diagnosticStages({ queue: toshiba, missing: false, rendered: true, ink: 9472, submitted: false, lineCount: 1 });
    expect(preview.find((item) => item.stage === "Print job submitted")?.result).toBe("not_run");
    expect(preview.find((item) => item.stage === "Physical text verified")?.result).toBe("not_run");
  });
});
