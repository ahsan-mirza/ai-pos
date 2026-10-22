import { createContext, useContext, useEffect } from "react";
import type { CashierSession } from "../../features/auth/session";

export type RegisterView = "checkout" | "returns" | "settings" | "orders" | "repairs";

export interface ShellValue {
  session: CashierSession;
  view: RegisterView;
  /** Pages report long-running work so the sidebar can block navigation mid-sale. */
  setBusy: (busy: boolean) => void;
  /** Pages register where sidebar tools (printer settings, etc.) post their status messages. */
  setNotifier: (notify: ((message: string) => void) | null) => void;
  /** Switches page, e.g. Returns hands an exchange over to Checkout. */
  navigate: (view: RegisterView) => void;
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
