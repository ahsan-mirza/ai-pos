import type { InstalledPrinter, PrinterProbe, PrinterSettings } from "../../lib/tauri";

export const DISCOVERING = "Discovering Windows printers...";
export const NONE_FOUND = "No Windows printers were found. Connect or install a printer and refresh the list.";
export const MISSING = "The previously configured printer is not installed. Select an available printer to reconnect.";
export const OFFLINE = "This printer is installed but currently offline.";
export const UNVERIFIED = "This device is not verified as a supported receipt printer.";
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

export function selectionWarning(address: string, queues: readonly InstalledPrinter[]): string | null {
  const trimmed = address.trim();
  if (trimmed === "") return null;
  const queue = queues.find((item) => item.name === trimmed);
  if (!queue) return MISSING;
  if (queue.availability === "offline") return OFFLINE;
  if (queue.availability === "virtual" || queue.compatibility === "unsupported" || queue.compatibility === "candidate") return UNVERIFIED;
  if (queue.availability === "unavailable" || queue.openable === false) {
    return `Windows printer "${queue.name}" could not be opened.`;
  }
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
  if (draft.transport === "none" || draft.transport === "tcp") return true;
  const queue = queues.find((item) => item.name === draft.address.trim());
  if (!queue || queue.openable === false || queue.availability !== "ready") return false;
  if (queue.compatibility === "unsupported") return false;
  return queue.compatibility === "compatible" || queue.compatibility === "candidate";
}

export function canTestDrawer(
  draft: Pick<PrinterSettings, "transport" | "address" | "drawer_kick">,
  queues: readonly InstalledPrinter[],
): boolean {
  if (draft.transport === "none" || draft.drawer_kick === false) return false;
  if (draft.transport === "tcp") return true;
  const queue = queues.find((item) => item.name === draft.address.trim());
  if (!queue || queue.openable === false) return false;
  return queue.availability === "ready" && queue.compatibility === "compatible" && queue.supportsDrawerKick;
}

export function canTestPrintFromProbe(probe: PrinterProbe | null): boolean {
  if (!probe || !probe.configured || probe.transport === "none") return true;
  if (probe.transport === "tcp") return probe.reachable && probe.printerStatus === "ready";
  if (probe.printerStatus === "candidate" && probe.reachable && probe.compatibility !== "unsupported") return true;
  return probe.reachable && probe.printerStatus === "ready" && probe.compatibility === "compatible";
}

export function canTestDrawerFromProbe(probe: PrinterProbe | null): boolean {
  if (!probe) return false;
  return (
    probe.configured &&
    probe.transport !== "none" &&
    probe.drawerKick &&
    probe.reachable &&
    probe.printerStatus === "ready" &&
    probe.supportsDrawerKick &&
    probe.compatibility !== "unsupported" &&
    probe.compatibility !== "candidate"
  );
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
export function saveFeedback(settings: Pick<PrinterSettings, "transport" | "address">, queues: readonly InstalledPrinter[]): string {
  if (settings.transport === "none") return "Printer settings saved on this register. No receipt printer is connected.";
  if (settings.transport === "tcp") return SAVED;
  const queue = queues.find((item) => item.name === settings.address.trim());
  if (!queue) return MISSING_SAVED;
  if (queue.availability === "virtual" || queue.connection === "Virtual" || queue.compatibility === "unsupported") return VIRTUAL_SAVED;
  if (queue.availability === "offline") {
    return "Register settings saved. The selected Windows queue is offline and is not a connected receipt printer.";
  }
  if (!queueOperational(queue)) {
    return "Register settings saved. The selected Windows queue is not verified as a receipt printer.";
  }
  return SAVED;
}

export function connectionMessage(probe: Pick<PrinterProbe, "printerStatus" | "reachable" | "compatibility" | "reachError">): string {
  if (probe.printerStatus === "ready" && probe.reachable && probe.compatibility === "compatible") return CONNECTED;
  if (probe.printerStatus === "missing") return MISSING;
  if (probe.printerStatus === "offline") return OFFLINE;
  if (probe.printerStatus === "candidate" || probe.compatibility === "unsupported" || probe.compatibility === "candidate") return UNVERIFIED;
  return probe.reachError || `Windows printer could not be opened.`;
}
