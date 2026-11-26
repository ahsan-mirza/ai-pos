/** Cash-drawer profiles shared by the register settings. The desktop service is the source of the pulse. */

export type DrawerMatrix = "supported" | "requires_adapter" | "not_supported";
export type DrawerConnection = "printer" | "separate" | "none";

/** Empty keeps the printer kick path used by registers saved before a connection was chosen. */
export function drawerConnection(value: string | undefined): DrawerConnection {
  if (value === "separate" || value === "none") return value;
  return "printer";
}

export interface DrawerProfile {
  id: string;
  label: string;
  /** Required printer drawer-port voltage. Empty when this profile never pulses. */
  voltage: "" | "12" | "24";
  pulse: boolean;
  matrix: DrawerMatrix;
  /** ESC/POS pin locked by the profile. 0 is connector pin 2. */
  lockedPin?: 0 | 1;
  on?: number;
  off?: number;
  note: string;
  /** Which connection can use this profile. */
  connection: DrawerConnection | "any";
}

export const DRAWER_PROFILES: readonly DrawerProfile[] = [
  {
    id: "",
    label: "Not configured",
    voltage: "",
    pulse: false,
    matrix: "not_supported",
    note: "Choose the drawer that is connected to this register. No pulse is sent until the profile and the drawer-port voltage match.",
    connection: "any",
  },
  {
    id: "hp-vb400-bl1616",
    label: "HP Standard Duty Cash Drawer (VB400-BL1616, 24V)",
    voltage: "24",
    pulse: true,
    matrix: "supported",
    lockedPin: 0,
    on: 25,
    off: 250,
    note: "Assembly 661672-001, spare 661843-001. Opens from a 24V receipt-printer drawer port. The drawer connector is RJ45; an Epson printer needs an RJ12-to-RJ45 cable. It is not a USB device. A 12V port, including an MTP-3 drawer port labelled DC12V/1A, is refused. Physical open is not confirmed from the command.",
    connection: "printer",
  },
  {
    id: "escpos-dk-24v",
    label: "ESC/POS printer drawer port (24V)",
    voltage: "24",
    pulse: true,
    matrix: "supported",
    note: "RJ11/RJ12 drawer kick through a receipt printer whose drawer port is 24V. Not interchangeable with a 12V drawer.",
    connection: "printer",
  },
  {
    id: "escpos-dk-12v",
    label: "ESC/POS printer drawer port (12V)",
    voltage: "12",
    pulse: true,
    matrix: "supported",
    note: "RJ11/RJ12 drawer kick through a receipt printer whose drawer port is 12V. The MTP-3 drawer output is labelled DC12V/1A. Not interchangeable with a 24V drawer.",
    connection: "printer",
  },
  {
    id: "usb-direct",
    label: "Direct USB drawer",
    voltage: "",
    pulse: false,
    matrix: "not_supported",
    note: "No verified USB cash-drawer controller is installed. An RJ11/RJ12 plug does not go into a PC USB port. The command stays off.",
    connection: "separate",
  },
  {
    id: "serial-direct",
    label: "Serial / COM drawer",
    voltage: "",
    pulse: false,
    matrix: "not_supported",
    note: "No verified serial open command is configured. Choosing a COM port does not open it and does not send a pulse.",
    connection: "separate",
  },
  {
    id: "opos",
    label: "OPOS cash drawer",
    voltage: "",
    pulse: false,
    matrix: "not_supported",
    note: "No OPOS cash-drawer service is installed. AxizPOS will not claim the drawer opened.",
    connection: "separate",
  },
  {
    id: "trigger-adapter",
    label: "USB or serial trigger adapter",
    voltage: "",
    pulse: false,
    matrix: "requires_adapter",
    note: "A compatible trigger adapter is required, and no verified adapter command is configured. The command stays off.",
    connection: "separate",
  },
];

export function profilesFor(connection: DrawerConnection): readonly DrawerProfile[] {
  return DRAWER_PROFILES.filter((profile) => profile.connection === "any" || profile.connection === connection || connection === "none");
}

export function drawerProfile(id: string | undefined): DrawerProfile {
  const fallback = DRAWER_PROFILES[0];
  if (!fallback) {
    throw new Error("No drawer profile is configured.");
  }
  return DRAWER_PROFILES.find((item) => item.id === (id ?? "")) ?? fallback;
}

/** True only when a pulse-capable profile and the matching drawer-port voltage are both saved. */
export function pulseProfileReady(settings: { drawer_profile?: string; host_voltage?: string }): boolean {
  const profile = drawerProfile(settings.drawer_profile);
  return profile.pulse && settings.host_voltage === profile.voltage;
}

export function lacksKickCircuit(device: { driver?: string | null; port?: string | null }): boolean {
  const driver = (device.driver ?? "").toLowerCase();
  const port = (device.port ?? "").trim().toLowerCase();
  return driver.includes("text only") || driver.includes("generic text") || port.startsWith("com");
}
