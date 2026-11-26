import { describe, expect, it } from "vitest";
import { canTestDrawer } from "./printerSelection";
import { DRAWER_PROFILES, lacksKickCircuit, pulseProfileReady } from "./drawerProfiles";
import type { InstalledPrinter, PrinterSettings } from "../../lib/tauri";

const settings = (patch: Partial<PrinterSettings> = {}): PrinterSettings => ({
  transport: "windows",
  address: "Epson TM-T20",
  paper_dots: 576,
  drawer_kick: true,
  auto_print: true,
  copies: 1,
  drawer_profile: "hp-vb400-bl1616",
  host_voltage: "24",
  ...patch,
});

const epson: InstalledPrinter = {
  name: "Epson TM-T20",
  driver: "EPSON TM-T20 Receipt",
  port: "USB001",
  status: 0,
  statusLabel: "Ready",
  availability: "ready",
  unavailable: false,
  compatibility: "compatible",
  supportsDrawerKick: true,
  connection: "USB",
  profileId: "epson-tm",
  manufacturer: "Epson",
  identity: "{epson}",
  openable: true,
};

describe("cash drawer profiles", () => {
  it("keeps the HP drawer on a 24V printer port and refuses the other voltages", () => {
    const hp = DRAWER_PROFILES.find((item) => item.id === "hp-vb400-bl1616");
    expect(hp?.voltage).toBe("24");
    expect(hp?.matrix).toBe("supported");
    expect(hp?.lockedPin).toBe(0);
    expect(pulseProfileReady(settings())).toBe(true);
    expect(pulseProfileReady(settings({ host_voltage: "12" }))).toBe(false);
    expect(pulseProfileReady(settings({ host_voltage: "" }))).toBe(false);
    expect(pulseProfileReady(settings({ drawer_profile: "escpos-dk-12v", host_voltage: "24" }))).toBe(false);
    expect(pulseProfileReady(settings({ drawer_profile: "escpos-dk-12v", host_voltage: "12" }))).toBe(true);
    expect(pulseProfileReady(settings({ drawer_profile: "usb-direct", host_voltage: "24" }))).toBe(false);
    expect(pulseProfileReady(settings({ drawer_profile: "trigger-adapter" }))).toBe(false);
  });

  it("does not offer a test pulse for a text-only COM port or an unconfirmed voltage", () => {
    expect(canTestDrawer(settings(), [epson])).toBe(true);
    expect(canTestDrawer(settings({ host_voltage: "" }), [epson])).toBe(false);
    expect(canTestDrawer(settings({ drawer_profile: "" }), [epson])).toBe(false);
    const textOnly: InstalledPrinter = {
      ...epson,
      name: "Generic / Text Only",
      driver: "Generic / Text Only",
      port: "COM4:",
      supportsDrawerKick: false,
      compatibility: "candidate",
    };
    expect(lacksKickCircuit(textOnly)).toBe(true);
    expect(canTestDrawer(settings({ address: textOnly.name }), [textOnly])).toBe(false);
    expect(canTestDrawer(settings({ transport: "serial", address: "COM4" }), [epson])).toBe(false);
  });
});
