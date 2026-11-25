import { createContext, useContext, useEffect } from "react";
import type { CashierSession } from "../../features/auth/session";
import type { SyncState } from "./syncState";

export type RegisterView = "checkout" | "returns" | "settings" | "orders" | "repairs" | "reorders" | "inventory" | "laundry" | "bills" | "customers" | "expenses";

export interface ShellValue {
  session: CashierSession;
  view: RegisterView;
  /** True while the open page is mid-sale or mid-request. The navbar drawer follows this. */
  busy: boolean;
  /** Pages report long-running work so the sidebar can block navigation mid-sale. */
  setBusy: (busy: boolean) => void;
  /** Extra hold for the navbar drawer when a page is busy but the sidebar should stay usable. */
  drawerHeld: boolean;
  setDrawerHeld: (held: boolean) => void;
  /** Pages register where sidebar tools (printer settings, etc.) post their status messages. */
  setNotifier: (notify: ((message: string) => void) | null) => void;
  /** Checkout posts the visible product count for the register status bar. */
  catalogSummary: string | null;
  setCatalogSummary: (summary: string | null) => void;
  /** The open page's connection reading. The bottom bar turns it into separate status words. */
  registerStatus: SyncState | null;
  setRegisterStatus: (status: SyncState | null) => void;
  /** Switches page, e.g. Returns hands an exchange over to Checkout. */
  navigate: (view: RegisterView) => void;
  /** Replaces the unlocked cashier after the server reports a new permission list. */
  onSession: (session: CashierSession) => void;
}

export const ShellContext = createContext<ShellValue | null>(null);

export function useShell(): ShellValue {
  const value = useContext(ShellContext);
  if (value === null) throw new Error("RegisterShell is missing.");
  return value;
}

/** Connects a page to the persistent shell: its busy flag and where tool messages should appear. */
export function useShellPage(busy: boolean, notify: (message: string) => void): void {
  const { setBusy, setNotifier } = useShell();
  useEffect(() => {
    setBusy(busy);
  }, [busy, setBusy]);
  useEffect(() => {
    setNotifier(notify);
    return () => setNotifier(null);
  }, [notify, setNotifier]);
}

/** Disables the shared navbar drawer without blocking sidebar navigation. */
export function useDrawerHold(held: boolean): void {
  const { setDrawerHeld } = useShell();
  useEffect(() => {
    setDrawerHeld(held);
    return () => setDrawerHeld(false);
  }, [held, setDrawerHeld]);
}
