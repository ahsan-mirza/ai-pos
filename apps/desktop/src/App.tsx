import { useEffect, useState } from "react";
import { RegisterShell } from "./components/shell/RegisterShell";
import type { RegisterView } from "./components/shell/ShellContext";
import { needsActivation } from "./config/terminal";
import { ActivationScreen } from "./features/activation/ActivationScreen";
import { PinUnlock } from "./features/auth/PinUnlock";
import { lock, restore, type CashierSession } from "./features/auth/session";
import { CheckoutPage } from "./features/checkout/CheckoutPage";
import { OrdersPage } from "./features/orders/OrdersPage";
import { RepairsPage } from "./features/repairs/RepairsPage";
import { ReturnsPage } from "./features/returns/ReturnsPage";
import { SettingsPage } from "./features/settings/SettingsPage";
import { OpenShiftScreen } from "./features/shifts/OpenShiftScreen";
import { reloadShift, useShift } from "./features/shifts/shift";
import { inTauri } from "./lib/tauri";

export function App() {
  const [session, setSession] = useState<CashierSession | null>(null);
  const [ready, setReady] = useState(false);
  const [view, setView] = useState<RegisterView>("checkout");
  const shiftState = useShift();

  useEffect(() => {
    restore()
      .then(setSession)
      .catch(() => setSession(null))
      .finally(() => setReady(true));
  }, []);

  useEffect(() => {
    if (session !== null) void reloadShift();
  }, [session]);

  if (needsActivation()) return <ActivationScreen />;
  if (!ready) return <div className="min-h-screen bg-zinc-950" />;
  if (session === null) return <PinUnlock onUnlocked={setSession} />;
  const onLock = () => {
    void lock().finally(() => {
      setSession(null);
      setView("checkout");
    });
  };
  if (inTauri() && !shiftState.loaded) return <div className="min-h-screen bg-zinc-950" />;
  if (inTauri() && shiftState.shift === null) return <OpenShiftScreen session={session} onLock={onLock} />;
  return (
    <RegisterShell session={session} view={view} onNavigate={setView} onLock={onLock}>
      {view === "returns" ? (
        <ReturnsPage session={session} />
      ) : view === "settings" ? (
        <SettingsPage />
      ) : view === "orders" ? (
        <OrdersPage session={session} />
      ) : view === "repairs" ? (
        <RepairsPage session={session} />
      ) : (
        <CheckoutPage session={session} />
      )}
    </RegisterShell>
  );
}
