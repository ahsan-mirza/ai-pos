import { Capability, Permission } from "@ai-pos/shared-types";
import { useEffect, useState, type ReactNode } from "react";
import { AppVersionMark } from "./components/AppVersionMark";
import { ConfirmProvider } from "./components/ConfirmDialog";
import { useRegisterLayout, type CatalogDensity } from "./components/RegisterLayout";
import { RegisterErrorBoundary } from "./components/RegisterErrorBoundary";
import { RegisterShell } from "./components/shell/RegisterShell";
import { FullscreenHotkey } from "./components/shell/ScreenToggle";
import type { RegisterView } from "./components/shell/ShellContext";
import { isSettingsHash } from "./components/shell/settingsEntry";
import { needsActivation, terminal } from "./config/terminal";
import { ActivationScreen } from "./features/activation/ActivationScreen";
import { PinUnlock } from "./features/auth/PinUnlock";
import { acceptStoredSession, browserCashier, currentAccessToken, lock, restore, type CashierSession } from "./features/auth/session";
import { clearCataloguePreferenceMemory } from "./features/checkout/cataloguePreference";
import { CheckoutPage } from "./features/checkout/CheckoutPage";
import { InventoryPage } from "./features/inventory/InventoryPage";
import { canOpenInventory } from "./features/inventory/tabs";
import { CustomerDisplay } from "./features/display/CustomerDisplay";
import { OrdersPage } from "./features/orders/OrdersPage";
import { LaundryWorkspace } from "./features/laundry/LaundryWorkspace";
import { RepairsPage } from "./features/repairs/RepairsPage";
import { ReordersPage } from "./features/reorders/ReordersPage";
import { ExpensesPage } from "./features/expenses/ExpensesPage";
import { BillHistoryPage } from "./features/restaurant/BillHistoryPage";
import { CustomerCreditPage } from "./features/restaurant/CustomerCreditPage";
import { ReturnsPage } from "./features/returns/ReturnsPage";
import { SettingsPage } from "./features/settings/SettingsPage";
import { OpenShiftScreen } from "./features/shifts/OpenShiftScreen";
import { reloadShift, useShift } from "./features/shifts/shift";
import { applySignedInAddons, useCapabilities } from "./lib/capabilities";
import { UpdatePrompt } from "./features/updates/UpdatePrompt";
import { VirtualKeyboardProvider } from "./hooks/useVirtualKeyboard";
import { env } from "./config/env";
import { CatalogSkeleton } from "./features/checkout/CatalogSkeleton";
import { syncBusinessCurrency } from "./features/checkout/currency";
import { useAutoReconnect } from "./features/sync/autoReconnect";
import { inTauri, openDemoSession, takeDemoNotice } from "./lib/tauri";

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

function DemoWait({ message }: { message: string | null }) {
  return (
    <div className="flex h-screen items-center justify-center bg-slate-50 p-6 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      <div className="max-w-md rounded-3xl border border-orange-200 bg-white p-8 shadow-xl dark:border-orange-500/30 dark:bg-zinc-900">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-orange-600">Demo mode</p>
        <h1 className="mt-2 text-2xl font-semibold">Waiting for the demo session</h1>
        <p className="mt-3 text-sm text-zinc-500 dark:text-zinc-400">
          {message ?? "The register is asking the server for this demo. A cashier PIN is not used for a demo session."}
        </p>
      </div>
    </div>
  );
}

export function App() {
  return (
    <>
      <FullscreenHotkey />
      {customerDisplay ? <CustomerDisplay /> : <RegisterApp />}
    </>
  );
}

function rememberedCashier(): CashierSession | null {
  if (inTauri() || typeof localStorage === "undefined") return null;
  return browserCashier(
    acceptStoredSession(localStorage.getItem("axiz.pos.cashier"), Math.floor(Date.now() / 1000), env.storeId),
    currentAccessToken(),
  );
}

function RegisterApp() {
  const remembered = rememberedCashier();
  const [session, setSession] = useState<CashierSession | null>(remembered);
  const [ready, setReady] = useState(remembered !== null);
  const [activating, setActivating] = useState(false);
  const [demoNotice, setDemoNotice] = useState<string | null>(null);
  const [view, setView] = useState<RegisterView>(() => (isSettingsHash(window.location.hash) ? "settings" : "checkout"));
  const shiftState = useShift();
  const { foodAndBeverage, enabled, profile } = useCapabilities();
  const { density } = useRegisterLayout();
  useAutoReconnect();

  const laundryBusiness = profile === "laundry";
  useEffect(() => {
    if (laundryBusiness && view === "checkout") {
      setView("laundry");
      return;
    }
    if (view === "returns" && foodAndBeverage) setView("checkout");
    if (view === "orders" && !foodAndBeverage) setView("checkout");
    const reports = session?.user.permissions.includes(Permission.PortalReportsRead) === true;
    const customers = session?.user.permissions.includes(Permission.CustomersManage) === true;
    if (view === "bills" && (!foodAndBeverage || !reports)) setView("checkout");
    if (view === "customers" && (!foodAndBeverage || !customers)) setView("checkout");
    if (view === "expenses" && session?.user.permissions.includes(Permission.ExpensesManage) !== true) setView("checkout");
    if (view === "repairs" && !enabled.has(Capability.Repairs)) setView("checkout");
    if (view === "reorders" && !enabled.has(Capability.CustomerReorders)) setView("checkout");
    if (view === "inventory" && session && !canOpenInventory(profile, enabled, session.user.permissions)) setView("checkout");
  }, [enabled, foodAndBeverage, laundryBusiness, profile, session, view]);

  useEffect(() => {
    const sync = () => {
      if (isSettingsHash(window.location.hash)) setView("settings");
    };
    window.addEventListener("hashchange", sync);
    window.addEventListener("popstate", sync);
    return () => {
      window.removeEventListener("hashchange", sync);
      window.removeEventListener("popstate", sync);
    };
  }, []);

  useEffect(() => {
    if (!inTauri()) return;
    void takeDemoNotice().then((message) => {
      if (message) window.alert(message);
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    const opening = terminal()?.demo === true ? openDemoSession() : restore();
    void opening
      .then((next) => {
        if (!cancelled) setSession(next);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setSession(null);
          if (terminal()?.demo === true) {
            setDemoNotice(error instanceof Error ? error.message : "The demo session could not be opened.");
          }
        }
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
    if (session === null || session.mode === "offline") return;
    const timer = window.setInterval(() => {
      void syncBusinessCurrency();
    }, 20_000);
    return () => window.clearInterval(timer);
  }, [session]);

  useEffect(() => {
    if (inTauri() || session === null || currentAccessToken() !== null) return;
    void lock().finally(() => setSession(null));
  }, [session]);

  useEffect(() => {
    if (session !== null) void reloadShift();
    const syncedAt = session?.user.addon_synced_at;
    applySignedInAddons(session === null ? null : (session.user.addon_modules ?? []), {
      offline: session?.mode === "offline",
      syncedAt: syncedAt ?? session?.unlocked_at,
    });
  }, [session]);

  const onLock = () => {
    clearCataloguePreferenceMemory();
    void lock().finally(() => {
      setSession(null);
      setView("checkout");
    });
  };

  let screen: ReactNode;
  if (needsActivation() || activating) {
    screen = <ActivationScreen onCancel={needsActivation() ? undefined : () => setActivating(false)} />;
  } else if (!ready) {
    screen = <BootCatalog density={density} />;
  } else if (session === null && terminal()?.demo === true) {
    screen = <DemoWait message={demoNotice} />;
  } else if (session === null) {
    screen = <PinUnlock onUnlocked={setSession} onActivate={() => setActivating(true)} />;
  } else if (inTauri() && !shiftState.loaded) {
    screen = (
      <ConfirmProvider>
        <VirtualKeyboardProvider>
          <RegisterShell session={session} view={view} onNavigate={setView} onLock={onLock} onSession={setSession}>
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
        <RegisterShell session={session} view={view} onNavigate={setView} onLock={onLock} onSession={setSession}>
          {view === "inventory" ? <InventoryPage session={session} /> : null}
          {!laundryBusiness && (view === "checkout" || view === "inventory") ? (
            <div className={view === "checkout" ? "contents" : "hidden"} inert={view === "inventory" ? true : undefined}>
              <CheckoutPage session={session} />
            </div>
          ) : null}
          {view === "returns" ? (
            <ReturnsPage session={session} />
          ) : view === "settings" ? (
            <SettingsPage />
          ) : view === "orders" ? (
            <OrdersPage session={session} />
          ) : view === "bills" ? (
            <BillHistoryPage />
          ) : view === "customers" ? (
            <CustomerCreditPage />
          ) : view === "expenses" ? (
            <ExpensesPage session={session} />
          ) : view === "repairs" ? (
            <RepairsPage session={session} />
          ) : view === "laundry" || (laundryBusiness && view === "checkout") ? (
            <LaundryWorkspace session={session} onUnlocked={setSession} />
          ) : view === "reorders" && enabled.has(Capability.CustomerReorders) ? (
            <ReordersPage session={session} />
          ) : null}
        </RegisterShell>
        </VirtualKeyboardProvider>
      </ConfirmProvider>
    );
  }
  return (
    <RegisterErrorBoundary>
      {screen}
      <AppVersionMark />
      <UpdatePrompt />
    </RegisterErrorBoundary>
  );
}
