import { Capability } from "@ai-pos/shared-types";
import { useEffect, useState, type ReactNode } from "react";
import { ConfirmProvider } from "./components/ConfirmDialog";
import { useRegisterLayout, type CatalogDensity } from "./components/RegisterLayout";
import { RegisterShell } from "./components/shell/RegisterShell";
import type { RegisterView } from "./components/shell/ShellContext";
import { needsActivation } from "./config/terminal";
import { ActivationScreen } from "./features/activation/ActivationScreen";
import { PinUnlock } from "./features/auth/PinUnlock";
import { acceptStoredSession, lock, restore, type CashierSession } from "./features/auth/session";
import { CheckoutPage } from "./features/checkout/CheckoutPage";
import { CustomerDisplay } from "./features/display/CustomerDisplay";
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
import { env } from "./config/env";
import { CatalogSkeleton } from "./features/checkout/CatalogSkeleton";
import { inTauri } from "./lib/tauri";

const customerDisplay = new URLSearchParams(window.location.search).get("display") === "1";

function BootCatalog({ density, framed = false }: { density: CatalogDensity; framed?: boolean }) {
  const grid = (
    <div className="min-h-0 flex-1 overflow-hidden p-4">
      <CatalogSkeleton density={density} />
    </div>
  );
  if (framed) return grid;
  return (
    <div className="flex h-screen bg-slate-50 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      <div className="hidden w-72 shrink-0 border-e border-zinc-200 md:block dark:border-zinc-800" />
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="h-16 shrink-0 border-b border-zinc-200 dark:border-zinc-800" />
        {grid}
      </div>
    </div>
  );
}

export function App() {
  if (customerDisplay) return <CustomerDisplay />;
  return <RegisterApp />;
}

function rememberedCashier(): CashierSession | null {
  if (inTauri() || typeof localStorage === "undefined") return null;
  return acceptStoredSession(localStorage.getItem("axiz.pos.cashier"), Math.floor(Date.now() / 1000), env.storeId);
}

function RegisterApp() {
  const remembered = rememberedCashier();
  const [session, setSession] = useState<CashierSession | null>(remembered);
  const [ready, setReady] = useState(remembered !== null);
  const [activating, setActivating] = useState(false);
  const [view, setView] = useState<RegisterView>("checkout");
  const shiftState = useShift();
  const { foodAndBeverage, enabled } = useCapabilities();
  const { density } = useRegisterLayout();

  useEffect(() => {
    if (view === "returns" && foodAndBeverage) setView("checkout");
    if (view === "orders" && !foodAndBeverage) setView("checkout");
    if (view === "repairs" && !enabled.has(Capability.Repairs)) setView("checkout");
    if (view === "reorders" && !enabled.has(Capability.CustomerReorders)) setView("checkout");
  }, [enabled, foodAndBeverage, view]);

  useEffect(() => {
    let cancelled = false;
    void restore()
      .then((next) => {
        if (!cancelled) setSession(next);
      })
      .catch(() => {
        if (!cancelled) setSession(null);
      })
      .finally(() => {
        if (!cancelled) setReady(true);
      });
    void reloadShift();
    return () => {
      cancelled = true;
    };
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
      <BootCatalog density={density} />
    ) : (
      <PinUnlock onUnlocked={setSession} onActivate={() => setActivating(true)} />
    );
  } else if (inTauri() && !shiftState.loaded) {
    screen = (
      <ConfirmProvider>
        <VirtualKeyboardProvider>
          <RegisterShell session={session} view={view} onNavigate={setView} onLock={onLock}>
            <BootCatalog density={density} framed />
          </RegisterShell>
        </VirtualKeyboardProvider>
      </ConfirmProvider>
    );
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
