import { Select } from "@ai-pos/ui";
import { Printer, X } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { inTauri, savePrinterSettings, type PrinterSettings } from "../../lib/tauri";
import { BROWSER_PRINTER, loadPrinter, printReceipt } from "./print";
import type { ReceiptDoc } from "@ai-pos/receipt";

interface PrinterSettingsModalProps {
  sample: ReceiptDoc;
  onClose: () => void;
  onSaved: (message: string) => void;
}

const transports: { id: PrinterSettings["transport"]; label: string }[] = [
  { id: "tcp", label: "Network (LAN)" },
  { id: "windows", label: "Windows printer" },
  { id: "none", label: "None" },
];

export function PrinterSettingsModal({ sample, onClose, onSaved }: PrinterSettingsModalProps) {
  const titleId = useId();
  const desktop = inTauri();
  const [draft, setDraft] = useState<PrinterSettings>(BROWSER_PRINTER);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    void loadPrinter().then(setDraft);
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

  const save = async (): Promise<boolean> => {
    if (!desktop) {
      setError("Printer settings are stored on the register. Open the desktop app to change them.");
      return false;
    }
    setBusy(true);
    try {
      setDraft(await savePrinterSettings(draft));
      return true;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
      return false;
    } finally {
      setBusy(false);
    }
  };

  const testPrint = async () => {
    if (desktop && !(await save())) return;
    setBusy(true);
    const outcome = await printReceipt(sample, { kickDrawer: false, manual: true });
    setBusy(false);
    if (outcome.message) setError(outcome.message);
    else setStatus("Test receipt sent.");
  };

  const addressLabel = draft.transport === "windows" ? "Windows printer name" : "Printer IP address";

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
            void save().then((ok) => {
              if (ok) {
                onSaved("Printer settings saved on this register.");
                onClose();
              }
            });
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

          {draft.transport !== "none" ? (
            <label className="block text-sm font-medium" htmlFor="printer-address">
              {addressLabel}
              <input
                id="printer-address"
                autoComplete="off"
                spellCheck={false}
                value={draft.address}
                onChange={(event) => patch({ address: event.target.value })}
                placeholder={draft.transport === "windows" ? "EPSON TM-T20III Receipt" : "192.168.1.50 (port 9100)"}
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
                  onChange={(event) => patch({ [key]: event.target.checked })}
                  className="h-5 w-5 accent-primary"
                />
              </label>
            ))}
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
              disabled={busy}
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
