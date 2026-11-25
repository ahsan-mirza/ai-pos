import type { InstalledPrinter, PrinterSettings } from "../../lib/tauri";

export const USB_VIA_WINDOWS =
  "USB printers are used through their Windows queue. AxizPOS does not take the USB device away from Windows.";
export const TCP_OPEN_NOTICE = "The address accepted a connection. That does not prove it is a receipt printer.";
export const BLE_UNSUPPORTED =
  "This Bluetooth Low Energy device does not expose a documented receipt-printing service. It is not a working receipt printer.";
export const BLUETOOTH_EMPTY =
  "No paired Bluetooth serial printer was found. Pair it in Windows Bluetooth settings, then refresh. A detected Bluetooth device is not a receipt printer until it exposes a serial printing port.";
export const MTP3_LABEL =
  "MTP-3 label profile: 80 mm, ESC/POS, 90 mm/s, cashbox output DC 12V/1A. The label does not identify USB, Wi-Fi, or Bluetooth, and the drawer kick is not verified.";

export type ConnectionChoice = "windows" | "usb" | "network" | "bluetooth" | "none";

export const connectionChoices: { id: ConnectionChoice; label: string }[] = [
  { id: "windows", label: "Windows printer" },
  { id: "usb", label: "USB" },
  { id: "network", label: "Network / Wi-Fi" },
  { id: "bluetooth", label: "Bluetooth" },
  { id: "none", label: "None" },
];

export function activeConnection(draft: Pick<PrinterSettings, "transport" | "connection_kind">): ConnectionChoice {
  if (draft.transport === "none") return "none";
  if (draft.transport === "tcp") return "network";
  if (draft.transport === "serial" || draft.transport === "ble") return "bluetooth";
  if (draft.connection_kind === "usb") return "usb";
  return "windows";
}

export function settingsForConnection(
  choice: ConnectionChoice,
  remembered: { windows: string; tcp: string; serial: string },
): Pick<PrinterSettings, "transport" | "connection_kind" | "address"> {
  if (choice === "none") return { transport: "none", connection_kind: "none", address: "" };
  if (choice === "network") return { transport: "tcp", connection_kind: "network", address: remembered.tcp };
  if (choice === "bluetooth") return { transport: "serial", connection_kind: "bluetooth-classic", address: remembered.serial };
  if (choice === "usb") return { transport: "windows", connection_kind: "usb", address: remembered.windows };
  return { transport: "windows", connection_kind: "windows", address: remembered.windows };
}

export function isUsbQueue(queue: Pick<InstalledPrinter, "connection" | "port">): boolean {
  const connection = queue.connection.trim().toLowerCase();
  const port = queue.port.trim().toLowerCase();
  return connection === "usb" || port.startsWith("usb") || port.startsWith("toshiba:") || port.includes("usb");
}

export function comPortError(address: string): string | null {
  const folded = address.trim().toUpperCase();
  const number = folded.startsWith("COM") ? folded.slice(3) : "";
  if (!/^\d{1,3}$/.test(number)) return "Select a Bluetooth serial port such as COM5.";
  const parsed = Number(number);
  if (parsed < 1 || parsed > 256) return "Select a Bluetooth serial port such as COM5.";
  return null;
}

export function labelProfile(model: string): { paperDots: 576; protocol: "escpos"; verified: false } | null {
  const folded = model.trim().toLowerCase();
  if (!folded.includes("mtp-3") && !folded.includes("mtp3")) return null;
  return { paperDots: 576, protocol: "escpos", verified: false };
}

/** Wi-Fi and LAN use the same TCP adapter. Nothing here scans the network. */
export function scansNetwork(): boolean {
  return false;
}
