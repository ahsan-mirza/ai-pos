import { Select } from "@ai-pos/ui";
import { Printer, RefreshCw, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import {
  inTauri,
  listWindowsPrinters,
  probePrinter,
  savePrinterSettings,
  type InstalledPrinter,
  type PrinterSettings,
} from "../../lib/tauri";
import { BROWSER_PRINTER, loadPrinter, printReceipt } from "./print";
import {
  CONNECTED,
  DISCOVERING,
  NONE_FOUND,
  acceptsSavedName,
  applySelection,
  canTestPrint,
  connectionMessage,
  dedupePrinters,
  foundMessage,
  printerDetail,
  selectionWarning,
} from "./printerSelection";
import type { ReceiptDoc } from "@ai-pos/receipt";

interface PrinterSettingsModalProps {
  sample: ReceiptDoc;
  onClose: () => void;
  onSaved: (message: string) => void;
  /** Used by tests so the first render shows a known register without waiting for the desktop shell. */
  initialDraft?: PrinterSettings;
  initialQueues?: InstalledPrinter[];
  initialLoading?: boolean;
}

const transports: { id: PrinterSettings["transport"]; label: string }[] = [
  { id: "tcp", label: "Network (LAN)" },
  { id: "windows", label: "Windows printer" },
  { id: "none", label: "None" },
];

export function PrinterSettingsModal({
  sample,
  onClose,
  onSaved,
  initialDraft,
  initialQueues,
  initialLoading,
}: PrinterSettingsModalProps) {
  const titleId = useId();
  const queueLabelId = useId();
  const desktop = inTauri();
  const request = useRef(0);
  const [draft, setDraft] = useState<PrinterSettings>(initialDraft ?? BROWSER_PRINTER);
  const [persisted, setPersisted] = useState(initialDraft?.address ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [queues, setQueues] = useState<InstalledPrinter[]>(() => dedupePrinters(initialQueues ?? []));
  const [queuesError, setQueuesError] = useState<string | null>(null);
  const [loading, setLoading] = useState(initialLoading ?? desktop);

  const refreshQueues = async () => {
    if (!desktop) return;
    const ticket = ++request.current;
    setLoading(true);
    setQueuesError(null);
    try {
      const listed = dedupePrinters(await listWindowsPrinters());
      if (ticket !== request.current) return;
      setQueues(listed);
    } catch (caught) {
      if (ticket !== request.current) return;
      setQueuesError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      if (ticket === request.current) setLoading(false);
    }
  };

  useEffect(() => {
    if (initialDraft) return;
    void loadPrinter().then((loaded) => {
      setDraft(loaded);
      setPersisted(loaded.address);
    });
    void refreshQueues();
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  const patch = (next: Partial<PrinterSettings>) => {
    setDraft((current) => ({ ...current, ...next }));
    setError(null);
    setStatus(null);
  };

  const persist = async (): Promise<PrinterSettings | null> => {
    if (!desktop) {
      setError("Printer settings are stored on the register. Open the desktop app to change them.");
      return null;
    }
    if (draft.transport === "windows" && !acceptsSavedName(draft.address, queues, persisted)) {
      setError(draft.address.trim() ? "Select an installed Windows printer." : "Select a printer.");
      return null;
    }
    setBusy(true);
    try {
      const saved = await savePrinterSettings(draft);
      setDraft(saved);
      setPersisted(saved.address);
      return saved;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      setBusy(false);
      return null;
    }
  };

  const save = async (): Promise<boolean> => {
    const saved = await persist();
    if (!saved) return false;
    if (saved.transport === "windows") {
      try {
        const probe = await probePrinter();
        const message = connectionMessage(probe);
        if (message === CONNECTED) {
          setBusy(false);
          onSaved(message);
          onClose();
          return true;
        }
        setError(message);
        setBusy(false);
        return false;
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : String(caught));
        setBusy(false);
        return false;
      }
    }
    setBusy(false);
    onSaved("Printer settings saved on this register.");
    onClose();
    return true;
  };

  const testPrint = async () => {
    if (desktop && !(await persist())) return;
    setBusy(true);
    const outcome = await printReceipt(sample, { kickDrawer: false, manual: true });
    setBusy(false);
    if (outcome.message) setError(outcome.message);
    else setStatus("Test receipt sent.");
  };

  const addressLabel = "Printer IP address";
  const warning = draft.transport === "windows" && !loading ? selectionWarning(draft.address, queues) : null;
  const selected = queues.find((queue) => queue.name === draft.address.trim());
  const missingName = warning && !selected ? draft.address.trim() : "";
  const discovery =
    loading ? DISCOVERING : queuesError ? queuesError : queues.length === 0 ? NONE_FOUND : foundMessage(queues.length);
  const printDisabled = busy || (draft.transport === "windows" && !canTestPrint(draft, queues));
  const drawerDisabled = draft.transport === "none";

  return (
    <div className="modal-backdrop" role="presentation">
      <div role="dialog" aria-modal="true" aria-labelledby={titleId} className="modal-card max-w-lg">
        <div className="flex items-start gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-charcoal text-white dark:bg-zinc-100 dark:text-zinc-900">
            <Printer size={20} aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-xl font-semibold">
              Register settings
            </h2>
            <p className="text-sm text-charcoal/60 dark:text-zinc-400">Receipt printer and cash drawer for this register only.</p>
          </div>
          <button type="button" aria-label="Close" onClick={onClose} disabled={busy} className="modal-close">
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        <form
          className="mt-5 space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          <div className="grid grid-cols-3 gap-1 rounded-full bg-charcoal p-1" role="tablist" aria-label="Printer connection">
            {transports.map(({ id, label }) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={draft.transport === id}
                onClick={() => patch({ transport: id })}
                className={`rounded-full px-3 py-2 text-sm font-semibold transition ${
                  draft.transport === id ? "bg-primary text-white" : "text-white/70 hover:text-white"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {draft.transport === "windows" ? (
            <div className="space-y-2">
              <div className="flex items-end gap-2">
                <div className="min-w-0 flex-1">
                  <span id={queueLabelId} className="mb-1.5 block text-sm font-medium">
                    Select Windows printer
                  </span>
                  <Select
                    labelledBy={queueLabelId}
                    icon={Printer}
                    searchable
                    placeholder="Select a printer"
                    disabled={busy}
                    value={draft.address}
                    onChange={(value) => {
                      const chosen = queues.find((queue) => queue.name === value);
                      if (!chosen) return;
                      patch(applySelection(chosen));
                    }}
                    options={[
                      ...queues.map((queue) => ({
                        value: queue.name,
                        label: queue.name,
                        hint: printerDetail(queue),
                        badge: (
                          <span className="shrink-0 text-xs font-semibold text-charcoal/70 dark:text-zinc-300">{queue.statusLabel}</span>
                        ),
                      })),
                      ...(missingName
                        ? [
                            {
                              value: missingName,
                              label: missingName,
                              hint: "Not installed",
                              badge: (
                                <span className="shrink-0 text-xs font-semibold text-red-600 dark:text-red-400">Not installed</span>
                              ),
                            },
                          ]
                        : []),
                    ]}
                  />
                </div>
                <button
                  type="button"
                  aria-label="Refresh printers"
                  title="Refresh printers"
                  onClick={() => void refreshQueues()}
                  disabled={busy || loading}
                  className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-line text-charcoal hover:border-primary hover:text-primary disabled:opacity-40 dark:border-zinc-800 dark:text-zinc-100"
                >
                  <RefreshCw size={18} aria-hidden="true" className={loading ? "animate-spin" : ""} />
                </button>
              </div>
              <p role="status" aria-live="polite" aria-busy={loading} className="text-sm text-charcoal/70 dark:text-zinc-300">
                {discovery}
              </p>
              {selected ? <p className="text-sm text-charcoal/60 dark:text-zinc-400">{printerDetail(selected)}</p> : null}
              <ul className="sr-only">
                {queues.map((queue) => (
                  <li key={queue.name}>
                    {queue.name} {queue.statusLabel} {printerDetail(queue)}
                  </li>
                ))}
              </ul>
              {warning ? (
                <p role="alert" className="text-sm font-medium text-red-600 dark:text-red-400">
                  {warning}
                </p>
              ) : null}
              <label className="flex items-center justify-between gap-3 text-sm font-medium">
                Automatic discovery
                <input
                  type="checkbox"
                  checked={draft.auto_discover !== false}
                  onChange={(event) => patch({ auto_discover: event.target.checked })}
                  className="h-5 w-5 accent-primary"
                />
              </label>
              <p className="text-sm text-charcoal/60 dark:text-zinc-400">
                The cash drawer connects to the receipt printer drawer port. AxizPOS does not treat a separate USB device as a drawer.
              </p>
            </div>
          ) : draft.transport !== "none" ? (
            <label className="block text-sm font-medium" htmlFor="printer-address">
              {addressLabel}
              <input
                id="printer-address"
                autoComplete="off"
                spellCheck={false}
                value={draft.address}
                onChange={(event) => patch({ address: event.target.value })}
                placeholder="192.168.1.50 (port 9100)"
                className="modal-input mt-1.5 font-normal tabular-nums"
              />
            </label>
          ) : (
            <p className="rounded-2xl bg-surface dark:bg-zinc-800/60 px-4 py-3 text-sm text-charcoal/70 dark:text-zinc-300">
              Without a receipt printer, Print receipt opens the system print dialog instead.
            </p>
          )}

          <fieldset>
            <legend className="text-sm font-medium">Paper width</legend>
            <div className="mt-2 flex gap-2">
              {(
                [
                  [576, "80 mm"],
                  [384, "58 mm"],
                ] as const
              ).map(([dots, label]) => (
                <button
                  key={dots}
                  type="button"
                  aria-pressed={draft.paper_dots === dots}
                  onClick={() => patch({ paper_dots: dots })}
                  className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                    draft.paper_dots === dots ? "bg-charcoal text-white dark:bg-zinc-100 dark:text-zinc-900" : "bg-surface dark:bg-zinc-800/60 text-charcoal dark:text-zinc-100 hover:bg-charcoal/10 dark:hover:bg-white/10"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </fieldset>

          <div className="space-y-2 rounded-2xl bg-surface dark:bg-zinc-800/60 p-3">
            {(
              [
                ["auto_print", "Print a receipt after every sale"],
                ["drawer_kick", "Open the cash drawer for cash payments"],
              ] as const
            ).map(([key, label]) => (
              <label key={key} className="flex items-center justify-between gap-3 px-1 text-sm font-medium">
                {label}
                <input
                  type="checkbox"
                  checked={draft[key]}
                  disabled={key === "drawer_kick" && drawerDisabled}
                  onChange={(event) => patch({ [key]: event.target.checked })}
                  className="h-5 w-5 accent-primary disabled:opacity-40"
                />
              </label>
            ))}
            <label className="flex items-center justify-between gap-3 px-1 text-sm font-medium">
              Drawer connector
              <Select
                size="sm"
                className="w-36"
                aria-label="Drawer connector"
                disabled={drawerDisabled}
                value={String(draft.drawer_pin ?? 0)}
                onChange={(value) => patch({ drawer_pin: Number(value) })}
                options={[
                  { value: "0", label: "Pin 2" },
                  { value: "1", label: "Pin 5" },
                ]}
              />
            </label>
            <label className="flex items-center justify-between gap-3 px-1 text-sm font-medium">
              Copies per sale
              <Select
                size="sm"
                className="w-24"
                aria-label="Copies"
                value={String(draft.copies)}
                onChange={(value) => patch({ copies: Number(value) })}
                options={[1, 2, 3].map((count) => ({ value: String(count), label: String(count) }))}
              />
            </label>
          </div>

          {error ? (
            <p role="alert" className="text-sm font-medium text-red-600 dark:text-red-400">
              {error}
            </p>
          ) : null}
          {status ? (
            <p role="status" className="text-sm font-medium">
              {status}
            </p>
          ) : null}

          <div className="flex items-center justify-between gap-3 pt-2">
            <button
              type="button"
              onClick={() => void testPrint()}
              disabled={printDisabled}
              className="rounded-full border border-line dark:border-zinc-800 px-4 py-2 text-sm font-semibold hover:border-primary hover:text-primary disabled:opacity-40"
            >
              Test print
            </button>
            <div className="flex gap-3">
              <button type="button" onClick={onClose} disabled={busy} className="modal-cancel">
                Cancel
              </button>
              <button type="submit" disabled={busy} className="modal-save">
                {busy ? "Saving…" : "Save"}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
