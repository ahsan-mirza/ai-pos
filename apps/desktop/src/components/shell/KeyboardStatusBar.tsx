import { profileSpec } from "@ai-pos/shared-types";
import { useLocale } from "@ai-pos/ui";
import {
  ChefHat,
  CreditCard,
  Keyboard,
  Loader2,
  Monitor,
  Printer,
  Scale,
  Tablet,
  Wallet,
  Wifi,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useState } from "react";
import { terminal } from "../../config/terminal";
import { env } from "../../config/env";
import { store } from "../../features/checkout/catalog";
import { openDisplayWindow } from "../../features/display/displayChannel";
import { listenForTableEvents } from "../../features/orders/tableSync";
import { sampleReceipt } from "../../features/printing/saleReceipt";
import { printReceipt } from "../../features/printing/print";
import { loadScaleConfig } from "../../features/settings/scaleConfig";
import { useVirtualKeyboard } from "../../hooks/useVirtualKeyboard";
import { ApiRejectedError, ApiUnavailableError, checkCardTerminal, peripheralSnapshot } from "../../lib/api";
import { useAppVersion } from "../../lib/appVersion";
import { capabilitiesAvailable, subscriptionHold, useCapabilities } from "../../lib/capabilities";
import { noteSyncCounts, subscribeSyncActivity, type SyncSnapshot } from "../../lib/syncActivity";
import { bootstrapReadiness, conflictCount, exitDemo, inTauri, openCashDrawer, pendingCount, probePrinter, readScale, rejectedCount, type PrinterProbe } from "../../lib/tauri";
import { VirtualKeyboard } from "../common/VirtualKeyboard";
import { openHardwareSettings } from "./settingsEntry";
import { useShell } from "./ShellContext";
import {
  LIGHT_CLASS,
  footerIndicators,
  type Indicator,
  type IndicatorAction,
  type IndicatorKind,
  type RemotePeripheral,
  type ScaleResult,
} from "./deviceStatus";
import { statusBarModel, type StatusTone } from "./statusBar";

const ICONS: Record<IndicatorKind, LucideIcon> = {
  api: Wifi,
  receipt_printer: Printer,
  cash_drawer: Wallet,
  scale: Scale,
  keyboard: Keyboard,
  customer_display: Monitor,
  kds: ChefHat,
  table_apps: Tablet,
  card_terminal: CreditCard,
};

const STATUS_TEXT: Record<StatusTone, string> = {
  live: "text-emerald-300",
  pending: "text-amber-300",
  offline: "text-red-300",
  neutral: "text-slate-400",
};

const STATUS_DOT: Record<StatusTone, string> = {
  live: "bg-emerald-400",
  pending: "bg-amber-400",
  offline: "bg-red-500",
  neutral: "bg-slate-500",
};

const ACTION_LABEL: Record<IndicatorAction, string> = {
  test_printer: "Test connection",
  test_print: "Test print",
  test_kick: "Test drawer kick",
  read_scale: "Read scale",
  reconnect_display: "Open display",
  toggle_keyboard: "Touch keyboard",
  configure: "Register settings",
  check_terminal: "Test connection",
};

function when(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

/** Bottom register bar: branch identity, activation, connection, sync, and device lights. Details open above the bar. */
export function KeyboardStatusBar() {
  const { t } = useLocale();
  const version = useAppVersion();
  const { status, enabled, layout, toggle, hide, press } = useVirtualKeyboard();
  const { profile } = useCapabilities();
  const { session, navigate, catalogSummary, registerStatus } = useShell();
  const activation = terminal();
  const spec = profileSpec(profile);
  const restaurantName = activation?.tenant_name || store.name;
  const [printer, setPrinter] = useState<PrinterProbe | null>(null);
  const [scalePort, setScalePort] = useState("");
  const [scale, setScale] = useState<ScaleResult>(null);
  const [displayLocal, setDisplayLocal] = useState<"open" | "closed" | "absent">("absent");
  const [remotes, setRemotes] = useState<RemotePeripheral[]>([]);
  const [apiUp, setApiUp] = useState(false);
  const [apiKnown, setApiKnown] = useState(false);
  const [apiDetail, setApiDetail] = useState("Checking the register API.");
  const [syncSnap, setSyncSnap] = useState<SyncSnapshot>({ syncing: false, pending: null, failed: null, conflicts: null });
  const [openId, setOpenId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [readiness, setReadiness] = useState("");
  const [readinessDetail, setReadinessDetail] = useState("");

  useEffect(() => {
    if (!inTauri()) return;
    let stopped = false;
    const load = () => {
      void bootstrapReadiness(capabilitiesAvailable(), subscriptionHold() === "server")
        .then((report) => {
          if (stopped) return;
          setReadiness(report.readiness);
          setReadinessDetail(report.message);
        })
        .catch(() => {
          if (!stopped) setReadiness("");
        });
    };
    load();
    const timer = window.setInterval(load, 10_000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    let stopped = false;
    const loadRemote = async () => {
      try {
        const items = await peripheralSnapshot();
        if (stopped) return;
        setApiKnown(true);
        setApiUp(true);
        setApiDetail("The register can reach the AxizPOS API. This light does not mean the cashier is signed in or that laundry sync succeeded.");
        setRemotes(items);
      } catch (error) {
        if (stopped) return;
        setApiKnown(true);
        if (error instanceof ApiRejectedError) {
          setApiUp(true);
          setApiDetail(error.message);
          setRemotes([]);
          return;
        }
        if (error instanceof ApiUnavailableError || error instanceof Error) setApiUp(false);
      }
    };
    void loadRemote();
    const timer = window.setInterval(() => void loadRemote(), 30_000);
    const stopLive = env.storeId
      ? listenForTableEvents(env.storeId, (event) => {
          if (event.type === "peripherals:changed") void loadRemote();
        })
      : () => undefined;
    return () => {
      stopped = true;
      window.clearInterval(timer);
      stopLive();
    };
  }, []);

  useEffect(() => {
    if (!inTauri()) return;
    let stopped = false;
    let seen = false;
    const look = async () => {
      const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow");
      const existing = await WebviewWindow.getByLabel("customer-display");
      if (stopped) return;
      if (existing) seen = true;
      setDisplayLocal(existing ? "open" : seen ? "closed" : "absent");
    };
    void look();
    let stopReady = () => {};
    void import("@tauri-apps/api/event").then(async ({ listen }) => {
      const unlisten = await listen("customer-display-ready", () => {
        seen = true;
        setDisplayLocal("open");
      });
      if (stopped) unlisten();
      else stopReady = unlisten;
    });
    const timer = window.setInterval(() => void look(), 15_000);
    return () => {
      stopped = true;
      stopReady();
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (!inTauri()) return;
    let stopped = false;
    const probe = async () => {
      try {
        const next = await probePrinter();
        if (!stopped) setPrinter(next);
      } catch {
        if (!stopped) setPrinter(null);
      }
    };
    void probe();
    const timer = window.setInterval(() => void probe(), 30_000);
    let stopHardware = () => {};
    void import("@tauri-apps/api/event").then(async ({ listen }) => {
      const unlisten = await listen("printer-hardware-change", () => {
        if (!stopped) void probe();
      });
      if (stopped) unlisten();
      else stopHardware = unlisten;
    });
    return () => {
      stopped = true;
      stopHardware();
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    const config = loadScaleConfig();
    setScalePort(config?.port ?? "");
    if (!inTauri() || !config?.port) return;
    let stopped = false;
    const read = async () => {
      try {
        const reading = await readScale(config);
        if (!stopped) setScale({ ok: true, stable: reading.stable, grams: reading.grams });
      } catch (error) {
        if (!stopped) setScale({ ok: false, message: error instanceof Error ? error.message : String(error) });
      }
    };
    void read();
    const timer = window.setInterval(() => void read(), 60_000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => subscribeSyncActivity(setSyncSnap), []);

  useEffect(() => {
    if (!inTauri()) return;
    let stopped = false;
    const poll = () => {
      void Promise.all([pendingCount(), rejectedCount(), conflictCount()])
        .then(([pending, failed, conflicts]) => {
          if (!stopped) noteSyncCounts({ pending, failed, conflicts });
        })
        .catch(() => undefined);
    };
    poll();
    const timer = window.setInterval(poll, 5_000);
    const again = () => poll();
    window.addEventListener("online", again);
    return () => {
      stopped = true;
      window.clearInterval(timer);
      window.removeEventListener("online", again);
    };
  }, []);

  useEffect(() => {
    if (!openId) return;
    const close = (event: PointerEvent) => {
      const target = event.target;
      if (target instanceof Element && target.closest("[data-device-status]")) return;
      setOpenId(null);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [openId]);

  const bar = statusBarModel({
    activated: activation?.activated === true,
    demo: activation?.demo === true,
    desktop: inTauri(),
    sessionMode: session.mode,
    apiKnown,
    apiReachable: apiUp,
    page: registerStatus,
    syncing: syncSnap.syncing,
    pending: syncSnap.pending,
    failed: syncSnap.failed,
    conflicts: syncSnap.conflicts,
    catalogSummary,
    readiness,
    readinessDetail,
  });
  const indicators = footerIndicators({
    apiUp,
    apiDetail,
    printer,
    scalePort,
    scale,
    keyboard: status,
    keyboardReliable: inTauri(),
    displayLocal,
    remotes,
  });
  const open = indicators.find((item) => item.id === openId) ?? null;

  const run = async (_item: Indicator, action: IndicatorAction) => {
    setNotice(null);
    try {
      if (action === "toggle_keyboard") {
        toggle();
        return;
      }
      if (action === "configure") {
        if (_item.kind === "receipt_printer" || _item.kind === "cash_drawer") openHardwareSettings(navigate);
        else navigate("settings");
        setOpenId(null);
        return;
      }
      if (action === "reconnect_display") {
        await openDisplayWindow();
        setDisplayLocal("open");
        setNotice("Opening the customer display.");
        return;
      }
      if (action === "test_printer") {
        setPrinter(await probePrinter());
        setNotice("Checked the printer connection. A successful open is not a successful print.");
        return;
      }
      if (action === "test_print") {
        const outcome = await printReceipt(sampleReceipt(session.user.full_name), { kickDrawer: false, manual: true });
        setPrinter(await probePrinter());
        setNotice(outcome.message || (outcome.printed ? "Test receipt sent." : "The printer did not print."));
        return;
      }
      if (action === "test_kick") {
        await openCashDrawer();
        setPrinter(await probePrinter());
        setNotice("Drawer kick command submitted. Open/closed state: Not reported.");
        return;
      }
      if (action === "read_scale") {
        const config = loadScaleConfig();
        if (!config?.port) return;
        const reading = await readScale(config);
        setScale({ ok: true, stable: reading.stable, grams: reading.grams });
        setNotice(reading.stable ? `Stable reading ${reading.grams} g.` : "The scale answered, but the weight is moving.");
        return;
      }
      if (action === "check_terminal") {
        const result = await checkCardTerminal();
        const items = await peripheralSnapshot();
        setRemotes(items);
        setNotice(result.message);
      }
    } catch (error) {
      if (action === "read_scale") {
        setScale({ ok: false, message: error instanceof Error ? error.message : String(error) });
      }
      setNotice(error instanceof Error ? error.message : String(error));
    }
  };

  return (
    <>
      <footer data-readiness={readiness || "unchecked"} className="relative grid h-9 shrink-0 grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-3 border-t border-slate-800 bg-slate-900 px-3">
        <p
          className="min-w-0 truncate text-xs text-slate-300"
          title={
            (activation?.demo
              ? `DEMO MODE — ${restaurantName}. Session active. ${catalogSummary ?? ""}`
              : `${restaurantName} · ${spec.label} · ${store.code} · ${store.name}${activation?.register_code ? ` · ${activation.register_code}` : ""}`) +
            (readiness ? ` · ${readiness}. A remote change applies after sync. Stock is not split between tills.` : "")
          }
        >
          {activation?.demo ? (
            <button
              type="button"
              className="me-2 rounded bg-orange-500 px-1.5 py-0.5 text-[0.625rem] font-bold uppercase tracking-wide text-white"
              onClick={() => {
                if (!window.confirm("Leave this demo on this register? The demo token and this PC's demo data will be cleared.")) return;
                void exitDemo().catch((error: unknown) => {
                  setNotice(error instanceof Error ? error.message : "The demo could not be closed.");
                });
              }}
            >
              Exit Demo
            </button>
          ) : null}
          <span className="font-semibold text-slate-100">
            {activation?.demo ? `DEMO MODE — ${restaurantName}` : restaurantName}
          </span>
          <span className="text-slate-500"> · </span>
          <span>{spec.shortLabel}</span>
        </p>
        <div
          className="flex items-center justify-center gap-2 overflow-x-auto px-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
          role="status"
          aria-live="polite"
        >
          {bar.chips.map((chip) => (
            <span
              key={chip.id}
              title={chip.title}
              data-status-chip={chip.id}
              className={`inline-flex shrink-0 items-center gap-1 text-[0.6875rem] font-semibold uppercase tracking-wide ${STATUS_TEXT[chip.tone]}`}
            >
              {chip.spin ? (
                <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
              ) : (
                <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${STATUS_DOT[chip.tone]}`} />
              )}
              {t(chip.label, chip.vars)}
            </span>
          ))}
          {bar.summary ? (
            <span className="min-w-0 truncate text-[0.6875rem] font-semibold uppercase tracking-wider text-slate-500" title={bar.summary}>
              {bar.summary}
            </span>
          ) : null}
        </div>
        <div
          className="flex min-w-0 flex-nowrap items-center justify-end gap-0.5 justify-self-end overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
          role="group"
          aria-label="Device status"
          data-device-status="strip"
        >
          {indicators.filter((item) => item.kind !== "api").map((item) => {
            const Icon = ICONS[item.kind];
            return (
              <button
                key={item.id}
                type="button"
                title={`${item.name}. ${item.status}`}
                aria-label={`${item.name}. ${item.status}`}
                aria-pressed={openId === item.id}
                onClick={() => {
                  setNotice(null);
                  if (item.kind === "receipt_printer" || item.kind === "cash_drawer") {
                    openHardwareSettings(navigate);
                    setOpenId(null);
                    return;
                  }
                  setOpenId((current) => (current === item.id ? null : item.id));
                }}
                className="inline-flex h-7 shrink-0 items-center gap-1.5 px-1.5 text-xs text-slate-300 hover:bg-slate-800"
              >
                <Icon className="h-3.5 w-3.5 shrink-0 text-slate-400" aria-hidden="true" />
                <span className="hidden sm:inline">{item.label}</span>
                <span className={`h-2 w-2 shrink-0 rounded-full ${LIGHT_CLASS[item.light]}`} aria-hidden="true" />
              </button>
            );
          })}
          <span className="ms-2 shrink-0 text-xs tabular-nums text-slate-400" data-app-version={version}>
            v{version}
          </span>
        </div>
        {open ? (
          <div
            role="dialog"
            aria-label={open.name}
            data-device-status="details"
            className="absolute bottom-9 right-2 z-40 w-80 max-w-[calc(100vw-1rem)] border border-slate-700 bg-slate-900 p-3 text-xs text-slate-200 shadow-lg"
          >
            <p className="text-sm font-semibold text-slate-100">{open.name}</p>
            <dl className="mt-2 space-y-1">
              <Detail label="Type" value={open.name} />
              <Detail label="Connection" value={open.connection} />
              <Detail label="Status" value={open.status} />
              <Detail label="Last communication" value={when(open.lastOkAt || open.lastSeenAt)} />
              <Detail label="Address" value={open.address || "—"} />
              <Detail label="Last error" value={open.lastError || "—"} />
              {open.pending != null ? <Detail label="Pending" value={String(open.pending)} /> : null}
              {open.failed != null ? <Detail label="Failed" value={String(open.failed)} /> : null}
              {open.connected != null ? <Detail label="Connected" value={String(open.connected)} /> : null}
            </dl>
            {open.actions.length > 0 ? (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {open.actions.map((action) => (
                  <button
                    key={action}
                    type="button"
                    onClick={() => void run(open, action)}
                    className="h-7 bg-slate-800 px-2 text-xs font-medium text-slate-100 hover:bg-slate-700"
                  >
                    {action === "toggle_keyboard" ? (enabled ? "Hide touch keyboard" : "Show touch keyboard") : ACTION_LABEL[action]}
                  </button>
                ))}
              </div>
            ) : null}
            {notice ? <p className="mt-2 text-slate-400">{notice}</p> : null}
          </div>
        ) : null}
      </footer>
      {layout ? <VirtualKeyboard layout={layout} onKey={press} onHide={hide} /> : null}
    </>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2">
      <dt className="w-28 shrink-0 text-slate-500">{label}</dt>
      <dd className="min-w-0 flex-1 break-words">{value}</dd>
    </div>
  );
}
