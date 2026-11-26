import { describe, expect, it } from "vitest";
import { canTestDrawer, canTestPrint, saveFeedback } from "./printerSelection";
import {
  BLE_UNSUPPORTED,
  activeConnection,
  allowsRawEscpos,
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
    expect(settingsForConnection("serial", { windows: "", tcp: "", serial: "COM4", bluetooth: "COM5" })).toMatchObject({
      transport: "serial",
      connection_kind: "serial",
      address: "COM4",
    });
    expect(settingsForConnection("bluetooth", { windows: "", tcp: "", serial: "COM4", bluetooth: "COM5" })).toMatchObject({
      transport: "serial",
      connection_kind: "bluetooth-classic",
      address: "COM5",
    });
    expect(activeConnection(draft({ transport: "serial", connection_kind: "serial", address: "COM4" }))).toBe("serial");
    expect(activeConnection(draft({ transport: "serial", connection_kind: "bluetooth-classic", address: "COM5" }))).toBe(
      "bluetooth",
    );
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
    expect(saveFeedback(draft({ transport: "serial", connection_kind: "serial", address: "COM4" }), [])).toContain("COM port");
    expect(allowsRawEscpos(queue({ driver: "Unknown Thermal", port: "USB009", compatibility: "candidate" }))).toBe(true);
    expect(allowsRawEscpos(queue({ driver: "Toshiba Native Windows Driver", port: "Toshiba: 0_USB", compatibility: "candidate" }))).toBe(
      false,
    );
    expect(allowsRawEscpos(queue({ driver: "Generic / Text Only", port: "COM4", compatibility: "candidate" }))).toBe(false);
    expect(allowsRawEscpos(queue({ driver: "EPSON TM-T88V Receipt", port: "USB001", compatibility: "compatible" }))).toBe(false);
  });
});