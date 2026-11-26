import { Printer } from "lucide-react";
import { useEffect, useState } from "react";
import { ui } from "../../components/shell/tokens";
import {
  inTauri,
  listWindowsPrinters,
  openCashDrawer,
  printerSettings,
  probePrinter,
  savePrinterSettings,
  type InstalledPrinter,
  type PrinterProbe,
  type PrinterSettings,
} from "../../lib/tauri";
import { useBusinessCurrency } from "../checkout/currency";
import { registerIdentity } from "./saleReceipt";
import { printExactReceipt } from "./print";
import { pulseProfileReady } from "./drawerProfiles";
import { MISSING, OFFLINE, SPOOLER_ACCEPTED, UNSUPPORTED_METHOD, candidateMessage, canTestDrawerFromProbe, canTestPrintFromProbe } from "./printerSelection";
import { ReceiptPreviewPanel } from "./ReceiptPreviewPanel";
import { detectionResult, layoutWidth, paperLabel, settingsPreviewReceipt, setupSteps } from "./settingsPreview";
import type { ReceiptDoc } from "@ai-pos/receipt";

function when(seconds: number | null | undefined): string {
  if (seconds == null || seconds <= 0) return "—";
  return new Date(seconds * 1000).toLocaleString();
}

export function ReceiptHardwareCard({
  sample: _sample,
  onChangePrinter,
  refreshToken = 0,
  initialProbe = null,
  initialQueues = [],
  initialPaperDots = 576,
  canConfigure = false,
}: {
  sample: ReceiptDoc;
  onChangePrinter: () => void;
  refreshToken?: number;
  initialProbe?: PrinterProbe | null;
  initialQueues?: InstalledPrinter[];
  initialPaperDots?: 384 | 576;
  canConfigure?: boolean;
}) {
  const desktop = inTauri();
  const currency = useBusinessCurrency();
  const [probe, setProbe] = useState<PrinterProbe | null>(initialProbe);
  const [queues, setQueues] = useState<InstalledPrinter[]>(initialQueues);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [paperDots, setPaperDots] = useState<384 | 576>(layoutWidth(initialPaperDots));
  const [stored, setStored] = useState<PrinterSettings | null>(null);
  void _sample;

  const refresh = async () => {
    if (!desktop) return;
    const [nextProbe, nextQueues] = await Promise.all([
      probePrinter().catch(() => null),
      listWindowsPrinters().catch(() => [] as InstalledPrinter[]),
    ]);
    setProbe(nextProbe);
    setQueues(nextQueues);
  };

  useEffect(() => {
    if (!desktop) return;
    void printerSettings()
      .then((loaded) => {
        setStored(loaded);
        if (loaded.paper_dots === 384 || loaded.paper_dots === 576) setPaperDots(loaded.paper_dots);
      })
      .catch(() => undefined);
  }, [desktop, refreshToken]);

  useEffect(() => {
    void refresh();
    if (!desktop) return;
    let stopped = false;
    let stop = () => {};
    void import("@tauri-apps/api/event").then(async ({ listen }) => {
      const unlisten = await listen("printer-hardware-change", () => {
        if (!stopped) void refresh();
      });
      if (stopped) unlisten();
      else stop = unlisten;
    });
    return () => {
      stopped = true;
      stop();
    };
  }, [refreshToken]);

  const missing = probe?.printerStatus === "missing";
  const selected = queues.find((queue) => queue.name === probe?.address);
  const profileReady = pulseProfileReady({ drawer_profile: probe?.drawerProfile, host_voltage: probe?.hostVoltage });
  const kickSupported = Boolean(selected?.supportsDrawerKick ?? probe?.supportsDrawerKick) && probe?.compatibility === "compatible";
  const canKick = canTestDrawerFromProbe(probe) && kickSupported;
  const canPrint = desktop && canTestPrintFromProbe(probe);
  const kickReason = !desktop
    ? "Test drawer kick is available on the desktop register."
    : !probe?.configured
      ? "Receipt printer not configured."
      : probe.compatibility === "unsupported"
        ? UNSUPPORTED_METHOD
        : !profileReady
          ? "Choose a cash drawer profile and confirm the printer drawer-port voltage. A command is not sent until both match."
        : probe.compatibility === "candidate" || probe.printerStatus === "candidate"
          ? "Drawer kick has not been verified for this printer. Receipt printing can still be tested."
        : missing
          ? MISSING
          : probe.printerStatus === "offline"
            ? OFFLINE
            : probe.printerStatus === "unavailable" || !probe.reachable
              ? "Receipt printer unavailable."
              : !kickSupported
                ? "This printer has no known drawer-kick profile."
                : !probe.drawerKick
                  ? "Cash drawer kicks are turned off for this register."
                  : "";

  const choosePaper = async (dots: 384 | 576) => {
    setPaperDots(dots);
    if (!desktop || !canConfigure || !stored) return;
    try {
      const saved = await savePrinterSettings({ ...stored, paper_dots: dots });
      setStored(saved);
      setNotice(`Paper width saved at ${paperLabel(dots)}. The preview uses that layout. Nothing was printed.`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
    }
  };

  const previewDoc = settingsPreviewReceipt(registerIdentity(), currency);

  const testPrint = async () => {
    setBusy(true);
    if (desktop && canConfigure && stored && stored.paper_dots !== paperDots) {
      try {
        setStored(await savePrinterSettings({ ...stored, paper_dots: paperDots }));
      } catch (error) {
        setBusy(false);
        setNotice(error instanceof Error ? error.message : String(error));
        return;
      }
    }
    const outcome = await printExactReceipt(previewDoc, paperDots);
    setBusy(false);
    setNotice(outcome.printed ? outcome.message || SPOOLER_ACCEPTED : outcome.message || "The printer did not print.");
    await refresh();
  };

  const testKick = async () => {
    setBusy(true);
    try {
      await openCashDrawer();
      setNotice("Drawer kick command submitted. Open/closed state: Not reported.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
      await refresh();
    }
  };

  return (
    <section className="rounded-2xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-zinc-100 dark:bg-zinc-800">
            <Printer size={20} aria-hidden="true" />
          </span>
          <div>
            <h2 className="text-lg font-semibold">Receipt Printer & Cash Drawer</h2>
            <p className="text-sm text-zinc-500">This register only. Opening this page does not kick the drawer.</p>
          </div>
        </div>
        <button type="button" onClick={() => void refresh()} className={`h-11 px-5 ${ui.secondaryAction}`}>
          Refresh printer list
        </button>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-zinc-200 p-4 text-sm dark:border-zinc-800">
          <h3 className="font-semibold">Receipt printer</h3>
          <dl className="mt-3 space-y-2">
            <Row label="Status" value={probe ? statusLabel(probe) : desktop ? "Checking…" : "Desktop register only"} />
            <Row label="Device" value={selected?.driver || probe?.model || probe?.driver || "—"} />
            <Row label="Windows queue" value={probe?.configured ? probe.address || "—" : "Not configured"} />
            <Row label="Driver" value={selected?.driver || probe?.driver || "—"} />
            <Row label="Connection" value={probe?.configured ? selected?.connection || probe.connection || "—" : "—"} />
            <Row label="Port" value={selected?.port || probe?.port || "—"} />
            <Row label="Automatic discovery" value={probe?.autoDiscover === false ? "Disabled" : "Enabled"} />
            <Row label="Last communication" value={when(probe?.lastOkAt || probe?.discoveredAt)} />
          </dl>
          {missing ? (
            <p role="alert" className="mt-3 text-sm font-medium text-red-600 dark:text-red-400">
              {MISSING}
            </p>
          ) : null}
          {probe?.printerStatus === "offline" ? (
            <p role="alert" className="mt-3 text-sm font-medium text-red-600 dark:text-red-400">
              {OFFLINE}
            </p>
          ) : null}
          {!missing && probe?.printerStatus !== "offline" && probe?.compatibility === "unsupported" ? (
            <p role="alert" className="mt-3 text-sm font-medium text-red-600 dark:text-red-400">
              {UNSUPPORTED_METHOD}
            </p>
          ) : null}
          {!missing && probe?.printerStatus !== "offline" && (probe?.compatibility === "candidate" || probe?.printerStatus === "candidate") ? (
            <p role="status" className="mt-3 text-sm font-medium text-charcoal/70 dark:text-zinc-300">
              {candidateMessage({ name: probe.address, driver: probe.driver ?? selected?.driver ?? "" })}
            </p>
          ) : null}
          <div className="mt-4 flex flex-wrap gap-2">
            <button type="button" onClick={onChangePrinter} className={`h-11 px-4 ${ui.secondaryAction}`}>
              Change printer
            </button>
            <button type="button" onClick={() => void testPrint()} disabled={busy || !canPrint} className={`h-11 px-4 ${ui.secondaryAction}`}>
              Print test receipt
            </button>
          </div>
        </div>

        <div className="rounded-xl border border-zinc-200 p-4 text-sm dark:border-zinc-800">
          <h3 className="font-semibold">Cash drawer</h3>
          <p className="mt-2 text-zinc-500">
            The drawer is controlled through the receipt printer. A USB device is not a drawer connection unless it is the printer's drawer-kick port.
          </p>
          <dl className="mt-3 space-y-2">
            <Row label="Status" value={canKick ? "Control available" : kickReason || "Control unavailable"} />
            <Row label="Connected through" value={probe?.configured ? probe.address || "—" : "No receipt printer"} />
            <Row label="Connection" value="Drawer kick port" />
            <Row label="Drawer-kick support" value={kickSupported ? "Available through selected printer" : "Not available"} />
            <Row label="Last kick attempt" value={when(probe?.lastKickAttemptAt || probe?.lastKickOkAt)} />
            <Row label="Last error" value={probe?.lastKickError || "—"} />
            <Row label="Open/closed state" value="Not reported" />
          </dl>
          <button
            type="button"
            onClick={() => void testKick()}
            disabled={busy || !canKick}
            title={canKick ? "Send one drawer-kick pulse" : kickReason}
            className="mt-4 h-11 rounded-xl bg-primary px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            Test drawer kick
          </button>
          {!canKick ? <p className="mt-2 text-sm text-zinc-500">{kickReason}</p> : null}
        </div>
      </div>
      {queues.length > 0 ? (
        <ul className="mt-4 space-y-1 text-sm text-zinc-600 dark:text-zinc-300">
          {queues.map((queue) => (
            <li key={queue.name}>
              {queue.name} · {queue.driver || "Unknown driver"} · {queue.port || "Port not reported"} · {queue.statusLabel}
              {queue.name === probe?.address ? " · selected" : ""}
            </li>
          ))}
        </ul>
      ) : null}
      {probe?.previousAddress && probe.previousAddress !== probe.address ? (
        <p className="mt-3 text-sm text-zinc-500">Previous configured printer: {probe.previousAddress}</p>
      ) : null}
      <p role="status" className="mt-4 text-sm font-medium">
        {detectionResult(probe, queues)}
      </p>
      <ol className="mt-4 space-y-2 text-sm" aria-label="Printer setup">
        {setupSteps({
          queue: probe?.configured ? probe.address : "",
          driver: selected?.driver || probe?.driver || "",
          port: selected?.port || probe?.port || "",
          compatibility: probe?.compatibility || "",
          transport: selected?.printTransport || probe?.printTransport || "",
          drawerVerified: Boolean(kickSupported && probe?.compatibility === "compatible"),
          paper: paperLabel(paperDots),
          reachable: Boolean(probe?.reachable),
        }).map((item) => (
          <li key={item.step}>
            <span className="font-semibold">Step {item.step} — {item.title}.</span> {item.detail}
          </li>
        ))}
      </ol>
      <div className="mt-4 flex flex-wrap gap-2" role="group" aria-label="Paper width">
        {([576, 384] as const).map((dots) => (
          <button
            key={dots}
            type="button"
            aria-pressed={paperDots === dots}
            onClick={() => void choosePaper(dots)}
            className={`h-11 rounded-full px-4 text-sm font-semibold ${paperDots === dots ? "bg-primary text-white" : ui.secondaryAction}`}
          >
            {paperLabel(dots)}
          </button>
        ))}
      </div>
      <div className="mt-4">
        <ReceiptPreviewPanel doc={previewDoc} width={paperDots} />
      </div>
      {notice ? (
        <p role="status" className="mt-4 rounded-xl bg-zinc-50 px-4 py-3 text-sm dark:bg-zinc-800">
          {notice}
        </p>
      ) : null}
    </section>
  );
}

function statusLabel(probe: PrinterProbe): string {
  if (probe.printerStatus === "missing") return "Printer not found";
  if (probe.printerStatus === "offline") return "Printer offline";
  if (probe.printerStatus === "unavailable") return "Printer unavailable";
  if (probe.printerStatus === "ready") return "Connected";
  if (probe.printerStatus === "candidate") return "Candidate";
  if (probe.printerStatus === "not_configured") return "Not configured";
  return probe.reachError || "Unknown";
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-3">
      <dt className="w-36 shrink-0 text-zinc-500">{label}</dt>
      <dd className="min-w-0 flex-1 break-words">{value}</dd>
    </div>
  );
}
