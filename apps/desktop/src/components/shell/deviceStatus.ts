import type { PrinterProbe } from "../../lib/tauri";
import { drawerConnection, pulseProfileReady } from "../../features/printing/drawerProfiles";
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
      ? detail || "The register can reach the AxizPOS API. This light does not mean the cashier is signed in or that laundry sync succeeded."
      : "You're working offline. Local POS operations remain available. Pending changes will synchronize when a connection is restored. Local printers, the scale, and the keyboard stay on their own status.",
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
  if (!probe.configured) {
    return row({
      id: "receipt-printer",
      kind: "receipt_printer",
      label: "Printer",
      name: "Receipt printer",
      light: "red",
      status: "Receipt printer not configured.",
      connection: "None",
      configured: 0,
      actions: ["configure"],
    });
  }
  const failed = Boolean(probe.lastError) && (probe.lastOkAt == null || (probe.lastErrorAt ?? 0) >= probe.lastOkAt);
  let light: Light;
  let status: string;
  if (probe.printing) {
    light = "amber";
    status = "A receipt is being sent. This connection does not report paper level.";
  } else if (probe.printerStatus === "missing") {
    light = "red";
    status = "Selected receipt printer not found. Select an installed receipt printer to enable cash drawer control.";
  } else if (probe.compatibility === "unsupported") {
    light = "amber";
    status = "This printer does not support the configured AxizPOS receipt-printing method.";
  } else if (probe.compatibility === "candidate" || probe.printerStatus === "candidate") {
    light = "amber";
    status =
      probe.reachError ||
      "Printer detected, but its receipt-printing profile has not been verified. Complete the printer test before using it for customer receipts.";
  } else if (!probe.reachable || probe.printerStatus === "offline" || probe.printerStatus === "unavailable") {
    light = "red";
    status = probe.reachError || "Receipt printer unavailable.";
  } else if (failed) {
    light = "amber";
    status = `The connection opened, and the last print failed. ${probe.lastError}`;
  } else if (probe.printerStatus === "ready") {
    light = "green";
    status = "Receipt printer connected.";
  } else {
    light = "amber";
    status = probe.reachError || "Receipt printer status is still being checked.";
  }
  return row({
    id: "receipt-printer",
    kind: "receipt_printer",
    label: "Printer",
    name: "Receipt printer",
    light,
    status: `${status} Receipts are sent one at a time. A submitted job is not proof the paper printed.`,
    connection:
      probe.transport === "tcp"
        ? "Network"
        : probe.transport === "windows"
          ? "Windows spooler"
          : probe.transport === "serial"
            ? probe.connection === "Serial"
              ? "Serial / COM"
              : "Bluetooth Classic"
            : probe.transport === "ble"
              ? "Bluetooth Low Energy"
              : probe.transport,
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

const DRAWER_UNKNOWN = "Open/closed state: Not reported.";

export function drawerCanTest(probe: PrinterProbe): boolean {
  if (drawerConnection(probe.drawerConnection) !== "printer") return false;
  const known = probe.supportsDrawerKick === true && probe.compatibility === "compatible";
  return (
    probe.configured &&
    probe.drawerKick &&
    probe.reachable &&
    probe.printerStatus === "ready" &&
    known &&
    pulseProfileReady({ drawer_profile: probe.drawerProfile, host_voltage: probe.hostVoltage })
  );
}

export function drawerIndicator(probe: PrinterProbe): Indicator | null {
  const connection = drawerConnection(probe.drawerConnection);
  if (connection === "none") {
    return row({
      id: "cash-drawer",
      kind: "cash_drawer",
      label: "Drawer",
      name: "Cash drawer",
      light: "gray",
      status: `Cash drawer is off for this register. ${DRAWER_UNKNOWN}`,
      connection: "None",
      configured: 1,
      actions: ["configure"],
    });
  }
  if (connection === "separate") {
    return row({
      id: "cash-drawer",
      kind: "cash_drawer",
      label: "Drawer",
      name: "Cash drawer",
      light: probe.drawerKick ? "amber" : "gray",
      status: probe.drawerKick
        ? `Separate drawer controller is not verified. No pulse will be sent. ${DRAWER_UNKNOWN}`
        : `Cash payments do not kick the drawer on this register. ${DRAWER_UNKNOWN}`,
      connection: "Separate device",
      lastError: probe.lastKickError,
      configured: 1,
      actions: ["configure"],
    });
  }
  if (!probe.configured) {
    return row({
      id: "cash-drawer",
      kind: "cash_drawer",
      label: "Drawer",
      name: "Cash drawer",
      light: "red",
      status: `Receipt printer not configured. ${DRAWER_UNKNOWN}`,
      connection: "Receipt printer",
      configured: 0,
      actions: ["configure"],
    });
  }
  let light: Light = "red";
  let status = `Drawer control is unavailable. ${DRAWER_UNKNOWN}`;
  const actions: IndicatorAction[] = ["configure"];
  if (!probe.drawerKick) {
    light = "gray";
    status = `Cash payments do not kick the drawer on this register. ${DRAWER_UNKNOWN}`;
  } else if (probe.printerStatus === "missing") {
    status = `Selected receipt printer not found. Select an installed receipt printer to enable cash drawer control. ${DRAWER_UNKNOWN}`;
  } else if (!probe.reachable || probe.printerStatus === "offline" || probe.printerStatus === "unavailable") {
    status = `Receipt printer unavailable, so the drawer cannot be kicked. ${DRAWER_UNKNOWN}`;
  } else if (!pulseProfileReady({ drawer_profile: probe.drawerProfile, host_voltage: probe.hostVoltage })) {
    status = `Choose a cash drawer profile and confirm the drawer-port voltage before sending a pulse. ${DRAWER_UNKNOWN}`;
  } else if (!probe.supportsDrawerKick) {
    status = `This printer has no known drawer-kick profile. ${DRAWER_UNKNOWN}`;
  } else if (probe.lastKickError) {
    light = "amber";
    status = `Drawer command failed. ${DRAWER_UNKNOWN} ${probe.lastKickError}`;
    actions.unshift("test_kick");
  } else if (probe.lastKickOkAt) {
    light = "amber";
    status = `Drawer command submitted. ${DRAWER_UNKNOWN}`;
    actions.unshift("test_kick");
  } else if (drawerCanTest(probe)) {
    light = "green";
    status = `Drawer control available through the selected printer. ${DRAWER_UNKNOWN}`;
    actions.unshift("test_kick");
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
    lastError: probe.lastKickError || probe.reachError,
    address: probe.address || null,
    actions,
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
