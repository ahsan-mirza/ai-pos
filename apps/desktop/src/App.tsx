import { Capability } from "@ai-pos/shared-types";
import { useEffect, useState, type ReactNode } from "react";
import { ConfirmProvider } from "./components/ConfirmDialog";
import { RegisterShell } from "./components/shell/RegisterShell";
import type { RegisterView } from "./components/shell/ShellContext";
import { needsActivation } from "./config/terminal";
import { ActivationScreen } from "./features/activation/ActivationScreen";
import { PinUnlock } from "./features/auth/PinUnlock";
import { lock, restore, type CashierSession } from "./features/auth/session";
import { CheckoutPage } from "./features/checkout/CheckoutPage";
import { OrdersPage } from "./features/orders/OrdersPage";
import { RepairsPage } from "./features/repairs/RepairsPage";
import { ReordersPage } from "./features/reorders/ReordersPage";
import { ReturnsPage } from "./features/returns/ReturnsPage";
import { SettingsPage } from "./features/settings/SettingsPage";
import { OpenShiftScreen } from "./features/shifts/OpenShiftScreen";
import { reloadShift, useShift } from "./features/shifts/shift";
import { applySignedInAddons, useCapabilities } from "./lib/capabilities";
import { UpdatePrompt } from "./features/updates/UpdatePrompt";
import { VirtualKeyboardProvider } from "./hooks/useVirtualKeyboard";
import { inTauri } from "./lib/tauri";

export function App() {
  const [session, setSession] = useState<CashierSession | null>(null);
  const [ready, setReady] = useState(false);
  const [activating, setActivating] = useState(false);
  const [view, setView] = useState<RegisterView>("checkout");
  const shiftState = useShift();
  const { foodAndBeverage, enabled } = useCapabilities();

  useEffect(() => {
    if (view === "returns" && foodAndBeverage) setView("checkout");
    if (view === "orders" && !foodAndBeverage) setView("checkout");
    if (view === "repairs" && !enabled.has(Capability.Repairs)) setView("checkout");
    if (view === "reorders" && !enabled.has(Capability.CustomerReorders)) setView("checkout");
  }, [enabled, foodAndBeverage, view]);

  useEffect(() => {
    restore()
      .then(setSession)
      .catch(() => setSession(null))
      .finally(() => setReady(true));
  }, []);

  useEffect(() => {
    if (session !== null) void reloadShift();
    const syncedAt = session?.user.addon_synced_at;
    applySignedInAddons(session === null ? null : (session.user.addon_modules ?? []), {
      offline: session?.mode === "offline",
      syncedAt: syncedAt ?? session?.unlocked_at,
    });
  }, [session]);

  const onLock = () => {
    void lock().finally(() => {
      setSession(null);
      setView("checkout");
    });
  };

  let screen: ReactNode;
  if (needsActivation() || activating) {
    screen = <ActivationScreen onCancel={needsActivation() ? undefined : () => setActivating(false)} />;
  } else if (!ready || session === null) {
    screen = !ready ? (
      <div className="min-h-screen bg-zinc-950" />
    ) : (
      <PinUnlock onUnlocked={setSession} onActivate={() => setActivating(true)} />
    );
  } else if (inTauri() && !shiftState.loaded) {
    screen = <div className="min-h-screen bg-zinc-950" />;
  } else if (inTauri() && shiftState.shift === null) {
    screen = <OpenShiftScreen session={session} onLock={onLock} />;
  } else {
    screen = (
      <ConfirmProvider>
        <VirtualKeyboardProvider>
        <RegisterShell session={session} view={view} onNavigate={setView} onLock={onLock}>
          {view === "returns" ? (
            <ReturnsPage session={session} />
          ) : view === "settings" ? (
            <SettingsPage />
          ) : view === "orders" ? (
            <OrdersPage session={session} />
          ) : view === "repairs" ? (
            <RepairsPage session={session} />
          ) : view === "reorders" && enabled.has(Capability.CustomerReorders) ? (
            <ReordersPage session={session} />
          ) : (
            <CheckoutPage session={session} />
          )}
        </RegisterShell>
        </VirtualKeyboardProvider>
      </ConfirmProvider>
    );
  }
  return (
    <>
      {screen}
      <UpdatePrompt />
    </>
  );
}
