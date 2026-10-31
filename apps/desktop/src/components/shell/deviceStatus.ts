import type { PrinterProbe } from "../../lib/tauri";
import type { KeyboardStatus } from "../../hooks/useVirtualKeyboard";

export type Light = "green" | "red" | "gray" | "amber";

export type IndicatorKind =
  | "api"
  | "receipt_printer"
  | "cash_drawer"
  | "scale"
  | "keyboard"
  | "customer_display"
  | "kds"
  | "table_apps"
  | "card_terminal";

export type IndicatorAction =
  | "test_printer"
  | "test_print"
  | "test_kick"
  | "read_scale"
  | "reconnect_display"
  | "toggle_keyboard"
  | "configure"
  | "check_terminal";

export interface Indicator {
  id: string;
  kind: IndicatorKind;
  label: string;
  name: string;
  light: Light;
  status: string;
  connection: string;
  lastSeenAt: string | null;
  lastOkAt: string | null;
  lastError: string | null;
  address: string | null;
  pending: number | null;
  failed: number | null;
  connected: number | null;
  configured: number | null;
  actions: IndicatorAction[];
}

export interface RemotePeripheral {
  id: string;
  kind: "kds" | "table_apps" | "customer_display" | "card_terminal";
  label: string;
  name: string;
  light: Light;
  status: string;
  connection: string;
  last_seen_at: string | null;
  last_ok_at: string | null;
  last_error: string | null;
  address: string | null;
  pending: number | null;
  connected: number | null;
  configured: number | null;
}

export type ScaleResult = { ok: true; stable: boolean; grams: number } | { ok: false; message: string } | null;

const RANK: Record<IndicatorKind, number> = {
  api: 0,
  receipt_printer: 1,
  customer_display: 2,
  kds: 3,
  table_apps: 4,
  cash_drawer: 5,
  scale: 6,
  card_terminal: 7,
  keyboard: 8,
};

function stamp(seconds: number | null): string | null {
  if (seconds == null || seconds <= 0) return null;
  return new Date(seconds * 1000).toISOString();
}

function row(
  partial: Pick<Indicator, "id" | "kind" | "label" | "name" | "light" | "status" | "connection" | "actions"> &
    Partial<Indicator>,
): Indicator {
  return {
    lastSeenAt: null,
    lastOkAt: null,
    lastError: null,
    address: null,
    pending: null,
    failed: null,
    connected: null,
    configured: null,
    ...partial,
  };
}

export function apiIndicator(reachable: boolean, detail: string): Indicator {
  return row({
    id: "api",
    kind: "api",
    label: "API",
    name: "Register API",
    light: reachable ? "green" : "red",
    status: reachable
      ? detail || "The register can reach the AxizPOS API. Local hardware is checked on this machine."
      : "The register cannot reach the AxizPOS API. Local printers, the scale, and the keyboard stay on their own status.",
    connection: "HTTPS",
    actions: [],
  });
}

/** A companion reading is dropped to unknown when the API itself cannot be asked. It is not marked failed. */
export function unverified(item: Indicator): Indicator {
  return {
    ...item,
    light: "gray",
    status: "Status is unavailable while the API is disconnected. This is not a confirmed failure.",
  };
}

export function printerIndicator(probe: PrinterProbe): Indicator | null {
  if (!probe.configured) return null;
  const failed = Boolean(probe.lastError) && (probe.lastOkAt == null || (probe.lastErrorAt ?? 0) >= probe.lastOkAt);
  let light: Light;
  let status: string;
  if (probe.printing) {
    light = "amber";
    status = "A receipt is being sent. This connection does not report paper level.";
  } else if (!probe.reachable) {
    light = "red";
    status = probe.reachError || "The printer is unreachable.";
  } else if (failed) {
    light = "amber";
    status = `The connection opened, and the last print failed. ${probe.lastError}`;
  } else if (probe.lastOkAt) {
    light = "green";
    status = "The printer is reachable and a receipt was printed. Opening the port alone does not count as ready.";
  } else {
    light = "amber";
    status = "The printer accepted a connection. It has not printed yet, so it is not marked ready.";
  }
  return row({
    id: "receipt-printer",
    kind: "receipt_printer",
    label: "Printer",
    name: "Receipt printer",
    light,
    status: `${status} Receipts are sent immediately. This register does not keep a print queue.`,
    connection: probe.transport === "tcp" ? "LAN" : probe.transport === "windows" ? "Windows spooler" : probe.transport,
    lastSeenAt: probe.reachable ? new Date().toISOString() : stamp(probe.lastOkAt),
    lastOkAt: stamp(probe.lastOkAt),
    lastError: probe.reachable ? probe.lastError : probe.reachError || probe.lastError,
    address: probe.address || null,
    pending: 0,
    failed: failed ? 1 : 0,
    connected: probe.reachable ? 1 : 0,
    configured: 1,
    actions: ["test_printer", "test_print", "configure"],
  });
}

export function drawerIndicator(probe: PrinterProbe): Indicator | null {
  if (!probe.configured || !probe.drawerKick) return null;
  let light: Light = "gray";
  let status = "Configured to kick through the receipt printer. A kick has not been confirmed, and the drawer does not report open or closed.";
  if (!probe.reachable) {
    light = "red";
    status = "The receipt printer is unreachable, so the drawer cannot be kicked. Open or closed is not reported.";
  } else if (probe.lastKickError) {
    light = "amber";
    status = `The last drawer kick failed. Open or closed is not reported. ${probe.lastKickError}`;
  } else if (probe.lastKickOkAt) {
    light = "green";
    status = "The last drawer kick was accepted by the printer. The drawer does not report whether it is open or closed.";
  }
  return row({
    id: "cash-drawer",
    kind: "cash_drawer",
    label: "Drawer",
    name: "Cash drawer",
    light,
    status,
    connection: "Receipt printer",
    lastOkAt: stamp(probe.lastKickOkAt),
    lastError: probe.lastKickError,
    actions: ["test_kick", "configure"],
    configured: 1,
  });
}

function scaleBusy(message: string): boolean {
  return /busy|denied|access is denied|in use|permission/i.test(message);
}

export function scaleIndicator(port: string, result: ScaleResult): Indicator | null {
  if (!port.trim()) return null;
  if (result === null) {
    return row({
      id: "scale",
      kind: "scale",
      label: "Scale",
      name: "Weighing scale",
      light: "gray",
      status: "A scale port is configured. A reading has not been taken, so it is not marked connected.",
      connection: "Serial",
      address: port,
      configured: 1,
      actions: ["read_scale", "configure"],
    });
  }
  if (!result.ok) {
    const busy = scaleBusy(result.message);
    return row({
      id: "scale",
      kind: "scale",
      label: "Scale",
      name: "Weighing scale",
      light: busy ? "amber" : "red",
      status: busy ? `The scale port is busy. ${result.message}` : result.message,
      connection: "Serial",
      address: port,
      lastError: result.message,
      configured: 1,
      actions: ["read_scale", "configure"],
    });
  }
  return row({
    id: "scale",
    kind: "scale",
    label: "Scale",
    name: "Weighing scale",
    light: result.stable ? "green" : "amber",
    status: result.stable
      ? `The scale returned a stable reading of ${result.grams} g.`
      : "The scale answered, but the weight is still moving.",
    connection: "Serial",
    address: port,
    lastOkAt: result.stable ? new Date().toISOString() : null,
    connected: 1,
    configured: 1,
    actions: ["read_scale", "configure"],
  });
}

export function keyboardIndicator(status: KeyboardStatus, reliable: boolean): Indicator {
  if (!reliable) {
    return row({
      id: "keyboard",
      kind: "keyboard",
      label: "Keyboard",
      name: "Physical keyboard",
      light: "gray",
      status: "This session cannot see USB or Bluetooth keyboards, so none is marked connected.",
      connection: "Unknown",
      actions: ["toggle_keyboard"],
    });
  }
  if (!status.hasPhysicalKeyboard) {
    return row({
      id: "keyboard",
      kind: "keyboard",
      label: "Keyboard",
      name: "Physical keyboard",
      light: "gray",
      status: "No physical keyboard is connected. The on-screen keyboard can still be used.",
      connection: "None",
      actions: ["toggle_keyboard"],
    });
  }
  const connection =
    status.connectionType === "wired"
      ? "USB"
      : status.connectionType === "bluetooth"
        ? "Bluetooth"
        : status.connectionType === "surface_cover"
          ? "Surface cover"
          : "Detected";
  return row({
    id: "keyboard",
    kind: "keyboard",
    label: "Keyboard",
    name: "Physical keyboard",
    light: "green",
    status: `A physical keyboard is connected over ${connection}. A separate USB light is not shown for the same device.`,
    connection,
    lastSeenAt: new Date().toISOString(),
    connected: 1,
    configured: 1,
    actions: ["toggle_keyboard"],
  });
}

export function fromRemote(remote: RemotePeripheral): Indicator {
  const actions: IndicatorAction[] =
    remote.kind === "card_terminal" ? ["check_terminal"] : remote.kind === "customer_display" ? ["reconnect_display"] : [];
  return row({
    id: remote.id,
    kind: remote.kind,
    label: remote.label,
    name: remote.name,
    light: remote.light,
    status: remote.status,
    connection: remote.connection,
    lastSeenAt: remote.last_seen_at,
    lastOkAt: remote.last_ok_at,
    lastError: remote.last_error,
    address: remote.address,
    pending: remote.pending,
    connected: remote.connected,
    configured: remote.configured,
    actions,
  });
}

export function customerDisplayIndicator(
  local: "open" | "closed" | "absent",
  remote: Indicator | null,
  apiUp: boolean,
): Indicator | null {
  if (local === "open") {
    return row({
      id: "customer-display",
      kind: "customer_display",
      label: "Display",
      name: "Customer display",
      light: "green",
      status: "The customer display window is open on this register.",
      connection: "Local window",
      lastSeenAt: new Date().toISOString(),
      connected: 1,
      configured: 1,
      actions: ["reconnect_display"],
    });
  }
  if (local === "closed") {
    return row({
      id: "customer-display",
      kind: "customer_display",
      label: "Display",
      name: "Customer display",
      light: "red",
      status: "The customer display window was open and has closed.",
      connection: "Local window",
      lastError: "The display window closed.",
      configured: 1,
      connected: 0,
      actions: ["reconnect_display"],
    });
  }
  if (!remote) return null;
  return apiUp ? remote : unverified(remote);
}

export interface FooterInput {
  apiUp: boolean;
  apiDetail: string;
  printer: PrinterProbe | null;
  scalePort: string;
  scale: ScaleResult;
  keyboard: KeyboardStatus;
  keyboardReliable: boolean;
  displayLocal: "open" | "closed" | "absent";
  remotes: RemotePeripheral[];
}

export function footerIndicators(input: FooterInput): Indicator[] {
  const apiUp = input.apiUp;
  const printer = input.printer ? printerIndicator(input.printer) : null;
  const drawer = input.printer ? drawerIndicator(input.printer) : null;
  const scale = scaleIndicator(input.scalePort, input.scale);
  const remoteDisplay = input.remotes.find((item) => item.kind === "customer_display");
  const display = customerDisplayIndicator(
    input.displayLocal,
    remoteDisplay ? fromRemote(remoteDisplay) : null,
    apiUp,
  );
  const companions = input.remotes
    .filter((item) => item.kind !== "customer_display")
    .map((item) => (apiUp ? fromRemote(item) : unverified(fromRemote(item))));
  return [
    apiIndicator(apiUp, input.apiDetail),
    printer,
    display,
    ...companions,
    drawer,
    scale,
    keyboardIndicator(input.keyboard, input.keyboardReliable),
  ]
    .filter((item): item is Indicator => item !== null)
    .sort((left, right) => RANK[left.kind] - RANK[right.kind]);
}

export const LIGHT_CLASS: Record<Light, string> = {
  green: "bg-emerald-400",
  red: "bg-red-500",
  gray: "bg-slate-500",
  amber: "bg-amber-400",
};
