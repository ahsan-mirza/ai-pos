import { describe, expect, it } from "vitest";
import { canTestDrawer, canTestPrint, saveFeedback } from "./printerSelection";
import {
  BLE_UNSUPPORTED,
  activeConnection,
  comPortError,
  isUsbQueue,
  labelProfile,
  scansNetwork,
  settingsForConnection,
} from "./printerConnections";
import type { InstalledPrinter, PrinterSettings } from "../../lib/tauri";

const queue = (patch: Partial<InstalledPrinter>): InstalledPrinter => ({
  name: "Front",
  driver: "Generic",
  port: "USB001",
  status: 0,
  statusLabel: "Ready",
  unavailable: false,
  compatibility: "candidate",
  supportsDrawerKick: false,
  connection: "USB",
  profileId: "",
  ...patch,
});

const draft = (patch: Partial<PrinterSettings>): PrinterSettings => ({
  transport: "windows",
  address: "Front",
  paper_dots: 576,
  drawer_kick: true,
  auto_print: false,
  copies: 1,
  ...patch,
});

describe("printer connections", () => {
  it("keeps USB on the Windows queue and does not scan the network", () => {
    expect(scansNetwork()).toBe(false);
    expect(isUsbQueue(queue({ connection: "USB", port: "USB001" }))).toBe(true);
    expect(isUsbQueue(queue({ connection: "USB", port: "Toshiba: 0_USB" }))).toBe(true);
    expect(isUsbQueue(queue({ connection: "Network", port: "192.168.1.20" }))).toBe(false);
    expect(settingsForConnection("usb", { windows: "Front", tcp: "", serial: "" }).transport).toBe("windows");
    expect(settingsForConnection("network", { windows: "", tcp: "192.168.1.20", serial: "" })).toMatchObject({
      transport: "tcp",
      connection_kind: "network",
    });
    expect(activeConnection(draft({ transport: "tcp", connection_kind: "wifi" }))).toBe("network");
  });

  it("treats MTP-3 as an unverified ESC/POS label and refuses an unknown BLE service", () => {
    expect(labelProfile("MTP-3")).toEqual({ paperDots: 576, protocol: "escpos", verified: false });
    expect(labelProfile("Epson TM-T88")).toBeNull();
    expect(labelProfile("Toshiba POS Printer (CR) Toshiba Native Windows Driver")).toBeNull();
    expect(labelProfile("Generic / Text Only COM4")).toBeNull();
    expect(comPortError("COM5")).toBeNull();
    expect(comPortError("COM0")).not.toBeNull();
    expect(comPortError("LPT1")).not.toBeNull();
    expect(BLE_UNSUPPORTED).toContain("not a working receipt printer");
    expect(canTestPrint(draft({ transport: "serial", address: "COM5" }), [])).toBe(true);
    expect(canTestPrint(draft({ transport: "ble", address: "radio" }), [])).toBe(false);
    expect(canTestDrawer(draft({ transport: "serial", address: "COM5" }), [])).toBe(false);
    expect(canTestDrawer(draft({ transport: "ble", address: "radio" }), [])).toBe(false);
    expect(saveFeedback(draft({ transport: "ble", address: "radio" }), [])).toContain("not a working receipt printer");
    expect(saveFeedback(draft({ transport: "tcp", address: "192.168.1.20" }), [])).toContain("does not prove");
  });
});