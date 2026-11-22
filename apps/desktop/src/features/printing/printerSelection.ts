import type { InstalledPrinter, PrinterProbe, PrinterSettings } from "../../lib/tauri";

export const DISCOVERING = "Discovering Windows printers...";
export const NONE_FOUND = "No Windows printers were found. Connect or install a printer and refresh the list.";
export const MISSING = "The previously configured printer is not installed. Select an available printer to reconnect.";
export const OFFLINE = "This printer is installed but currently offline.";
export const UNVERIFIED = "This device is not verified as a supported receipt printer.";
export const CONNECTED = "Receipt printer connected successfully.";

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

export function connectionMessage(probe: Pick<PrinterProbe, "printerStatus" | "reachable" | "compatibility" | "reachError">): string {
  if (probe.printerStatus === "ready" && probe.reachable && probe.compatibility === "compatible") return CONNECTED;
  if (probe.printerStatus === "missing") return MISSING;
  if (probe.printerStatus === "offline") return OFFLINE;
  if (probe.printerStatus === "candidate" || probe.compatibility === "unsupported" || probe.compatibility === "candidate") return UNVERIFIED;
  return probe.reachError || `Windows printer could not be opened.`;
}
