import { describe, expect, it } from "vitest";
import type { PrinterProbe } from "../../lib/tauri";
import {
  customerDisplayIndicator,
  drawerCanTest,
  drawerIndicator,
  footerIndicators,
  fromRemote,
  keyboardIndicator,
  printerIndicator,
  scaleIndicator,
  unverified,
  type RemotePeripheral,
} from "./deviceStatus";

const printer = (patch: Partial<PrinterProbe> = {}): PrinterProbe => ({
  configured: true,
  transport: "tcp",
  address: "192.168.1.40",
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
  driver: null,
  port: null,
  discoveredAt: null,
  drawerOpenState: "not_reported",
  compatibility: "compatible",
  supportsDrawerKick: true,
  connection: "Network",
  discoveryOutcome: "kept",
  previousAddress: "",
  autoDiscover: true,
  model: "",
  driverVersion: null,
  ...patch,
});

const remote = (patch: Partial<RemotePeripheral> = {}): RemotePeripheral => ({
  id: "kds:1",
  kind: "kds",
  label: "KDS",
  name: "Kitchen display",
  light: "green",
  status: "2 of 2 kitchen screens are connected.",
  connection: "WebSocket",
  last_seen_at: "2026-10-31T12:00:00Z",
  last_ok_at: "2026-10-31T12:00:00Z",
  last_error: null,
  address: null,
  pending: 1,
  connected: 2,
  configured: 2,
  ...patch,
});

const keyboard = { hasPhysicalKeyboard: true, connectionType: "wired" as const, isTouchDevice: false };

describe("footer device lights", () => {
  it("marks a ready printer connected and keeps a failed print amber", () => {
    expect(printerIndicator(printer({ configured: false }))?.light).toBe("red");
    expect(printerIndicator(printer({ configured: false }))?.status).toContain("not configured");
    expect(printerIndicator(printer())?.light).toBe("green");
    expect(printerIndicator(printer())?.status).toContain("Receipt printer connected");
    expect(printerIndicator(printer({ lastOkAt: 1_700_000_000 }))?.light).toBe("green");
    expect(printerIndicator(printer({ reachable: false, reachError: "unreachable" }))?.light).toBe("red");
    expect(printerIndicator(printer({ printing: true, lastOkAt: 1 }))?.light).toBe("amber");
    const virtual = printerIndicator(printer({ compatibility: "unsupported", printerStatus: "unavailable", reachable: false, reachError: "This device is not verified as a supported receipt printer." }));
    expect(virtual?.light).not.toBe("green");
    expect(virtual?.status).toContain("not verified");
    expect(drawerCanTest(printer({ compatibility: "unsupported", supportsDrawerKick: true }))).toBe(false);
    expect(drawerCanTest(printer({ compatibility: "candidate", printerStatus: "candidate", supportsDrawerKick: false }))).toBe(false);
    const fault = printerIndicator(printer({ lastOkAt: 10, lastError: "paper", lastErrorAt: 11 }));
    expect(fault?.light).toBe("amber");
    expect(fault?.failed).toBe(1);
    expect(fault?.pending).toBe(0);
  });

  it("does not claim the drawer is open or closed", () => {
    expect(drawerIndicator(printer({ configured: false }))?.light).toBe("red");
    expect(drawerIndicator(printer({ configured: false }))?.status).toContain("not configured");
    expect(drawerIndicator(printer({ drawerKick: false }))?.light).toBe("gray");
    expect(drawerIndicator(printer())?.light).toBe("green");
    expect(drawerIndicator(printer())?.status).toContain("Not reported");
    expect(drawerIndicator(printer({ supportsDrawerKick: false }))?.light).toBe("red");
    expect(drawerIndicator(printer({ supportsDrawerKick: false }))?.actions).not.toContain("test_kick");
    expect(drawerIndicator(printer({ reachable: false }))?.light).toBe("red");
    const submitted = drawerIndicator(printer({ lastKickOkAt: 20 }));
    expect(submitted?.status).toMatch(/Not reported/);
    expect(submitted?.status).toMatch(/submitted/i);
    expect(submitted?.light).toBe("amber");
    expect(drawerIndicator(printer({ lastKickError: "refused" }))?.light).toBe("amber");
    const missing = drawerIndicator(printer({ reachable: false, printerStatus: "missing", address: "Toshiba thermal" }));
    expect(missing?.light).toBe("red");
    expect(missing?.status).toContain("Selected receipt printer not found");
    expect(missing?.actions).not.toContain("test_kick");
    expect(missing?.status).toContain("Not reported");
  });

  it("keeps local hardware when the API is down and does not duplicate the keyboard as USB", () => {
    const items = footerIndicators({
      apiUp: false,
      apiDetail: "",
      printer: printer({ lastOkAt: 50 }),
      scalePort: "COM3",
      scale: null,
      keyboard,
      keyboardReliable: true,
      displayLocal: "open",
      remotes: [remote(), remote({ id: "tables:1", kind: "table_apps", label: "Tables", light: "red" })],
    });
    expect(items.find((item) => item.kind === "api")?.light).toBe("red");
    expect(items.find((item) => item.kind === "receipt_printer")?.light).toBe("green");
    expect(items.find((item) => item.kind === "customer_display")?.light).toBe("green");
    expect(items.find((item) => item.kind === "kds")?.light).toBe("gray");
    expect(items.find((item) => item.kind === "table_apps")?.light).toBe("gray");
    expect(items.find((item) => item.kind === "scale")?.light).toBe("gray");
    expect(items.find((item) => item.kind === "keyboard")?.light).toBe("green");
    expect(items.filter((item) => item.label === "USB")).toHaveLength(0);
    expect(items.filter((item) => item.connection === "USB")).toHaveLength(1);
    expect(items.map((item) => item.kind)).toEqual([
      "api",
      "receipt_printer",
      "customer_display",
      "kds",
      "table_apps",
      "cash_drawer",
      "scale",
      "keyboard",
    ]);
  });

  it("hides a display that was never opened and marks a closed window red", () => {
    expect(customerDisplayIndicator("absent", null, true)).toBeNull();
    expect(customerDisplayIndicator("closed", null, false)?.light).toBe("red");
    expect(customerDisplayIndicator("absent", fromRemote(remote({ kind: "customer_display", light: "red" })), false)?.light).toBe("gray");
    expect(scaleIndicator("", null)).toBeNull();
    expect(scaleIndicator("COM3", { ok: false, message: "Access is denied" })?.light).toBe("amber");
    expect(scaleIndicator("COM3", { ok: false, message: "Could not open the scale on COM3" })?.light).toBe("red");
    expect(scaleIndicator("COM3", { ok: true, stable: true, grams: 450 })?.light).toBe("green");
    expect(keyboardIndicator(keyboard, false).light).toBe("gray");
    expect(unverified(fromRemote(remote())).light).toBe("gray");
  });
});
