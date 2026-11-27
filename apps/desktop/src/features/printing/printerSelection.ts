import type { InstalledPrinter, PrinterProbe, PrinterSettings } from "../../lib/tauri";
import { drawerConnection, lacksKickCircuit, pulseProfileReady } from "./drawerProfiles";
import { BLE_UNSUPPORTED, TCP_OPEN_NOTICE } from "./printerConnections";

export const DISCOVERING = "Discovering Windows printers...";
export const NONE_FOUND = "No Windows printers were found. Connect or install a printer and refresh the list.";
export const MISSING = "The previously selected Windows printer is not installed. Refresh the printer list or select another device.";
export const OFFLINE = "The printer is installed but currently unavailable.";
export const REGISTER_VIEW_ONLY =
  "You can view printer status. Register management permission is required to change printer settings.";
export const PROFILE_UNVERIFIED =
  "Printer detected, but its receipt-printing profile has not been verified. Complete the printer test before using it for customer receipts.";
export const TEST_SUBMITTED = "Test receipt submitted. Please confirm that readable text printed correctly.";
export const PRINT_FAILURE = "Receipt content was generated, but the printer did not accept the print job.";
export const PHYSICAL_PENDING = "The printer job was submitted, but physical output has not yet been verified.";
export const CANDIDATE = PROFILE_UNVERIFIED;
export const UNSUPPORTED_METHOD = "This printer does not support the configured AxizPOS receipt-printing method.";
export const QUEUE_CLOSED = "Windows found the printer, but AxizPOS could not open its queue.";
export const RENDER_FAILED = "The invoice was generated, but its printable content could not be rendered.";
export const TRANSMIT_FAILED = PRINT_FAILURE;
export const SPOOLER_ACCEPTED = PHYSICAL_PENDING;
/** Kept so older status text can still be recognised. New warnings use the specific sentences above. */
export const UNVERIFIED = CANDIDATE;
export const CONNECTED = "Receipt printer connected successfully.";
export const SAVED = "Printer settings saved on this register.";
export const VIRTUAL_SAVED =
  "Register settings saved. The selected Windows queue is a virtual printer and cannot be used for receipt printing or drawer control.";
export const MISSING_SAVED =
  "Register settings saved. The selected Windows queue is not installed and cannot be used for receipt printing or drawer control.";

export function dedupePrinters(queues: readonly InstalledPrinter[]): InstalledPrinter[] {
  const seen = new Set<string>();
  const unique: InstalledPrinter[] = [];
  for (const queue of queues) {
    const name = queue.name.trim();
    if (name === "" || seen.has(queue.name)) continue;
    seen.add(queue.name);
    unique.push(queue);
  }
  return unique;
}

export function foundMessage(count: number): string {
  return count === 1 ? "Found 1 Windows printer" : `Found ${count} Windows printers`;
}

export function printerDetail(queue: InstalledPrinter): string {
  const maker = queue.manufacturer?.trim() ?? "";
  const driver = queue.driver.trim();
  const model =
    maker && driver && !driver.toLowerCase().includes(maker.toLowerCase())
      ? `${maker} · ${driver}`
      : driver || maker || "Driver not reported";
  const port = queue.port.trim() || "Port not reported";
  const connection = queue.connection.trim() || "Connection not reported";
  return `${model} · ${port} · ${connection}`;
}

/** Matches the searchable dropdown: queue name, driver, manufacturer, and port. */
export function filterPrinters(queues: readonly InstalledPrinter[], query: string): InstalledPrinter[] {
  const needle = query.trim().toLowerCase();
  if (needle === "") return [...queues];
  return queues.filter((queue) =>
    `${queue.name} ${printerDetail(queue)} ${queue.statusLabel}`.toLowerCase().includes(needle),
  );
}

/** Refresh never substitutes a different queue. A missing name stays selected. */
export function selectionAfterRefresh(previous: string, queues: readonly InstalledPrinter[]): { address: string; missing: boolean } {
  const address = previous.trim();
  if (address === "") return { address: "", missing: false };
  return { address, missing: !queues.some((queue) => queue.name === address) };
}

export function applySelection(queue: InstalledPrinter): Pick<
  PrinterSettings,
  "address" | "user_selected" | "saved_driver" | "saved_port" | "saved_model" | "saved_identity"
> {
  return {
    address: queue.name,
    user_selected: true,
    saved_driver: queue.driver,
    saved_port: queue.port,
    saved_model: queue.manufacturer?.trim() || queue.driver,
    saved_identity: queue.identity ?? "",
  };
}

/** Names the Toshiba Native driver. Other candidates get the generic unverified sentence. */
export function candidateMessage(queue: Pick<InstalledPrinter, "name" | "driver">): string {
  const driver = queue.driver.trim();
  const driverLower = driver.toLowerCase();
  if (driverLower.includes("toshiba") && driverLower.includes("native")) {
    return `${queue.name} was discovered using the ${driver}. Receipt printing has not yet been verified. Run the printer test to confirm the supported print method.`;
  }
  return CANDIDATE;
}

export function selectionWarning(address: string, queues: readonly InstalledPrinter[]): string | null {
  const trimmed = address.trim();
  if (trimmed === "") return null;
  const queue = queues.find((item) => item.name === trimmed);
  if (!queue) return MISSING;
  if (queue.availability === "offline") return OFFLINE;
  if (queue.availability === "virtual" || queue.compatibility === "unsupported") return UNSUPPORTED_METHOD;
  if (queue.compatibility === "candidate") return candidateMessage(queue);
  if (queue.availability === "unavailable" || queue.openable === false) return QUEUE_CLOSED;
  return null;
}

/** A name can be saved when it is an installed queue, or the name already stored for this register. */
export function acceptsSavedName(address: string, queues: readonly InstalledPrinter[], persisted: string): boolean {
  const trimmed = address.trim();
  if (trimmed === "") return false;
  if (queues.some((queue) => queue.name === trimmed)) return true;
  return persisted.trim() !== "" && trimmed === persisted.trim();
}

export function canTestPrint(draft: Pick<PrinterSettings, "transport" | "address">, queues: readonly InstalledPrinter[]): boolean {
  if (draft.transport === "ble") return false;
  if (draft.transport === "serial") return true;
  if (draft.transport === "none" || draft.transport === "tcp") return true;
  const queue = queues.find((item) => item.name === draft.address.trim());
  if (!queue || queue.openable === false || queue.availability !== "ready") return false;
  if (queue.compatibility === "unsupported") return false;
  return queue.compatibility === "compatible" || queue.compatibility === "candidate";
}

export function canTestDrawer(
  draft: Pick<PrinterSettings, "transport" | "address" | "drawer_kick" | "drawer_profile" | "host_voltage" | "drawer_connection"> & { protocol?: string },
  queues: readonly InstalledPrinter[],
): boolean {
  if (drawerConnection(draft.drawer_connection) !== "printer") return false;
  if (draft.transport === "none" || draft.transport === "serial" || draft.transport === "ble" || draft.drawer_kick === false) return false;
  if (!pulseProfileReady(draft)) return false;
  if (draft.transport === "tcp") return true;
  const queue = queues.find((item) => item.name === draft.address.trim());
  if (!queue || queue.openable === false || queue.availability !== "ready") return false;
  if (lacksKickCircuit(queue)) return false;
  if (windowsDriverDrawer(queue)) return true;
  return genericEscposDrawer(draft.protocol, queue);
}

/** Toshiba and other native Windows receipt drivers take the pulse inside the driver job, not as a raw spooler document. */
export function windowsDriverDrawer(queue: { compatibility?: string; driver?: string | null; port?: string | null }): boolean {
  if (queue.compatibility === "unsupported") return false;
  const driver = (queue.driver ?? "").toLowerCase();
  const port = (queue.port ?? "").trim().toLowerCase();
  if (driver.includes("text only") || driver.includes("generic text") || driver.includes("generic / text")) return false;
  return port.startsWith("toshiba:") || driver.includes("native windows driver");
}

/** A named receipt driver, or generic ESC/POS on a real candidate queue. Text-only drivers stay off. */
export function genericEscposDrawer(
  protocol: string | undefined,
  queue: { compatibility?: string; supportsDrawerKick?: boolean; driver?: string | null; port?: string | null; printTransport?: string },
): boolean {
  if (queue.compatibility === "unsupported") return false;
  const driver = (queue.driver ?? "").toLowerCase();
  const port = (queue.port ?? "").trim().toLowerCase();
  if (port.startsWith("toshiba:") || driver.includes("native windows driver")) return false;
  if (driver.includes("text only") || driver.includes("generic text") || driver.includes("generic / text")) return false;
  if (queue.compatibility === "compatible" && queue.supportsDrawerKick === true) return true;
  return protocol === "escpos" && queue.compatibility === "candidate";
}

export function canTestPrintFromProbe(probe: PrinterProbe | null): boolean {
  if (!probe || !probe.configured || probe.transport === "none") return true;
  if (probe.transport === "tcp" || probe.transport === "serial") {
    return probe.reachable && (probe.printerStatus === "ready" || probe.printerStatus === "candidate");
  }
  if (probe.transport === "ble") return false;
  if (probe.printerStatus === "candidate" && probe.reachable && probe.compatibility !== "unsupported") return true;
  return probe.reachable && probe.printerStatus === "ready" && probe.compatibility === "compatible";
}

export function canTestDrawerFromProbe(probe: PrinterProbe | null): boolean {
  if (!probe || drawerConnection(probe.drawerConnection) !== "printer") return false;
  const windowsDrawer = windowsDriverDrawer(probe);
  const statusOk =
    probe.printerStatus === "ready" ||
    (probe.printerStatus === "candidate" && (probe.printTransport === "escpos" || windowsDrawer));
  const reachable =
    probe.configured &&
    probe.transport !== "none" &&
    probe.drawerKick &&
    probe.reachable &&
    statusOk &&
    probe.compatibility !== "unsupported";
  if (!reachable) return false;
  if (!pulseProfileReady({ drawer_profile: probe.drawerProfile, host_voltage: probe.hostVoltage })) return false;
  if (lacksKickCircuit(probe)) return false;
  const escpos = windowsDrawer || genericEscposDrawer(probe.printTransport === "escpos" ? "escpos" : "", probe);
  if (!escpos) return false;
  return probe.printerStatus === "ready" || probe.printerStatus === "candidate";
}

/** A saved Windows queue is operational only when discovery classifies it as a ready compatible receipt printer. */
export function queueOperational(queue: InstalledPrinter | undefined): boolean {
  if (!queue) return false;
  return queue.availability === "ready" && queue.compatibility === "compatible" && queue.openable !== false;
}

export function networkAddressError(address: string): string | null {
  const value = address.trim();
  if (value === "" || /\s/.test(value)) return "Enter the printer IP address or hostname.";
  let host = value;
  const split = value.lastIndexOf(":");
  if (split >= 0) {
    const portText = value.slice(split + 1);
    if (!/^\d+$/.test(portText)) return "Enter an IPv4 address or hostname, with an optional port.";
    const port = Number(portText);
    if (!Number.isInteger(port) || port < 1 || port > 65535) return "The printer port must be a number from 1 to 65535.";
    host = value.slice(0, split);
  }
  if (host === "" || host.includes(":")) return "Enter an IPv4 address or hostname, with an optional port.";
  const labels = host.split(".");
  if (labels.some((part) => part === "")) return "Enter a valid printer IP address or hostname.";
  const numeric = labels.every((part) => /^\d{1,3}$/.test(part));
  if (numeric) {
    const ipv4 = labels.length === 4 && labels.every((part) => Number(part) <= 255);
    return ipv4 ? null : "Enter a valid printer IP address or hostname.";
  }
  const hostname = labels.every((label) => label.length <= 63 && /^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?$/.test(label));
  return hostname ? null : "Enter a valid printer IP address or hostname.";
}

/** Persistence succeeded. The message says when the queue still cannot print or open the drawer. */
export function saveFeedback(
  settings: Pick<PrinterSettings, "transport" | "address"> & { connection_kind?: string },
  queues: readonly InstalledPrinter[],
): string {
  if (settings.transport === "none") return "Printer settings saved on this register. No receipt printer is connected.";
  if (settings.transport === "tcp") return `${SAVED} ${TCP_OPEN_NOTICE}`;
  if (settings.transport === "serial" && settings.connection_kind === "serial") {
    return `Register settings saved. ${CANDIDATE} The COM port is not opened during save. Drawer kick is not verified.`;
  }
  if (settings.transport === "serial") return `Register settings saved. ${CANDIDATE} Drawer kick is not verified.`;
  if (settings.transport === "ble") return `Register settings saved. ${BLE_UNSUPPORTED}`;
  const queue = queues.find((item) => item.name === settings.address.trim());
  if (!queue) return MISSING_SAVED;
  if (queue.availability === "virtual" || queue.connection === "Virtual" || queue.compatibility === "unsupported") return VIRTUAL_SAVED;
  if (queue.availability === "offline") {
    return `Register settings saved. ${OFFLINE}`;
  }
  if (queue.compatibility === "candidate") {
    return `Register settings saved. ${candidateMessage(queue)} The queue is kept for diagnostics and is not marked operational.`;
  }
  if (queue.openable === false || queue.availability === "unavailable") {
    return `Register settings saved. ${QUEUE_CLOSED}`;
  }
  if (!queueOperational(queue)) {
    return `Register settings saved. ${CANDIDATE}`;
  }
  return SAVED;
}

export function connectionMessage(
  probe: Pick<PrinterProbe, "printerStatus" | "reachable" | "compatibility" | "reachError" | "address" | "driver">,
): string {
  if (probe.printerStatus === "ready" && probe.reachable && probe.compatibility === "compatible") return CONNECTED;
  if (probe.printerStatus === "missing") return MISSING;
  if (probe.printerStatus === "offline") return OFFLINE;
  if (probe.compatibility === "candidate" || probe.printerStatus === "candidate") {
    return candidateMessage({ name: probe.address, driver: probe.driver ?? "" });
  }
  if (probe.compatibility === "unsupported") return UNSUPPORTED_METHOD;
  if (!probe.reachable) return probe.reachError || QUEUE_CLOSED;
  return probe.reachError || QUEUE_CLOSED;
}

/** ESC/POS 80 mm rolls use 576 printable dots at 203 dpi. 58 mm rolls use 384. A Windows driver DPI is not this width. */
export function printableDots(paper: "58 mm" | "80 mm"): 384 | 576 {
  return paper === "58 mm" ? 384 : 576;
}

export function testReceiptPrompt(printer: string): string {
  const name = printer.trim() || "the selected printer";
  return `Send one test receipt to ${name}? This does not create a sale or open the cash drawer.`;
}

export function inkBytes(data: readonly number[]): number {
  return data.reduce((count, byte) => count + (byte === 0 ? 0 : 1), 0);
}

export function rejectEmptyRaster(data: readonly number[]): string | null {
  if (data.length === 0 || inkBytes(data) === 0) return RENDER_FAILED;
  return null;
}

export interface DiagnosticStage {
  stage: string;
  result: "passed" | "failed" | "unverified" | "not_run";
}

/** Software stages only. Physical text stays not_run until someone reads the paper. */
export function diagnosticStages(input: {
  queue: InstalledPrinter | undefined;
  missing: boolean;
  rendered: boolean;
  ink: number;
  submitted: boolean;
  lineCount: number;
}): DiagnosticStage[] {
  const queue = input.queue;
  const opened = Boolean(queue && queue.openable !== false && queue.availability !== "offline" && queue.availability !== "unavailable");
  const profile = !queue ? "not_run" : queue.compatibility === "compatible" ? "passed" : queue.compatibility === "candidate" ? "unverified" : "failed";
  const transport = !queue || queue.printTransport === "none" || queue.compatibility === "unsupported" ? "failed" : queue.printTransport ? "passed" : "unverified";
  return [
    { stage: "Printer discovered", result: queue ? "passed" : input.missing ? "failed" : "not_run" },
    { stage: "Queue opened", result: !queue ? "not_run" : opened ? "passed" : "failed" },
    { stage: "Printer profile identified", result: profile },
    { stage: "Invoice data loaded", result: input.lineCount > 0 ? "passed" : input.rendered ? "failed" : "not_run" },
    { stage: "Printable content generated", result: !input.rendered ? "not_run" : input.ink > 0 ? "passed" : "failed" },
    { stage: "Payload validated", result: !input.rendered ? "not_run" : input.ink > 0 ? "passed" : "failed" },
    { stage: "Print transport selected", result: !queue ? "not_run" : transport },
    { stage: "Print job submitted", result: input.submitted ? "passed" : "not_run" },
    { stage: "Physical text verified", result: "not_run" },
  ];
}
