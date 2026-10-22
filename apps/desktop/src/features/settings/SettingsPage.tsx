import { Capability, formatMoney, profileSpec } from "@ai-pos/shared-types";
import { AlertTriangle, Banknote, Check, Palette, Printer, RotateCcw, Search, ShoppingCart, Store } from "lucide-react";
import { useCallback, useId, useState } from "react";
import type { SyncState } from "../../components/shell/HeaderBar";
import { HeaderBar } from "../../components/shell/HeaderBar";
import { useShell, useShellPage } from "../../components/shell/ShellContext";
import { ui } from "../../components/shell/tokens";
import {
  DEFAULT_PRIMARY,
  PRIMARY_PRESETS,
  contrastWithWhite,
  normalizeHex,
  savePrimaryColor,
  storedPrimaryColor,
} from "../../lib/theme";
import { useBusinessCurrency } from "../checkout/currency";
import { useSyncEngine } from "../checkout/useSyncEngine";
import { useCapabilities } from "../../lib/capabilities";
import { PrinterSettingsModal } from "../printing/PrinterSettingsModal";
import { sampleReceipt } from "../printing/saleReceipt";
import { BusinessTypeCard } from "./BusinessTypeCard";
import { ScaleSettingsCard } from "./ScaleSettingsCard";

/** Below 3:1, white labels on active pills and the Charge button become hard to read. */
const MIN_CONTRAST = 3;

export function SettingsPage() {
  const { session } = useShell();
  const capabilities = useCapabilities();
  const currency = useBusinessCurrency();
  const { report, desktop } = useSyncEngine(0);
  const [color, setColor] = useState(() => storedPrimaryColor() ?? DEFAULT_PRIMARY);
  const [hexText, setHexText] = useState(color);
  const [printer, setPrinter] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const hexId = useId();
  useShellPage(false, useCallback((message: string) => setNotice(message), []));

  const choose = (hex: string) => {
    const next = normalizeHex(hex);
    if (next === null) return;
    setColor(next);
    setHexText(next);
    savePrimaryColor(next);
    setNotice(null);
  };

  const typed = normalizeHex(hexText);
  const contrast = contrastWithWhite(color);
  const sync: SyncState = desktop
    ? {
        tone: report.pending > 0 ? "pending" : "synced",
        label: report.pending > 0 ? `${report.pending} unsynced` : "Synced",
        title: report.message,
      }
    : { tone: "live", label: "Live", title: report.message };

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      <HeaderBar title={profileSpec(capabilities.profile).settingsLabel} sync={sync} />
      <main className="custom-scrollbar min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto grid max-w-6xl gap-5 p-5 lg:p-8 xl:grid-cols-[minmax(0,1fr)_340px]">
          <BusinessTypeCard />

          <section aria-labelledby="accent-title" className={`rounded-2xl border p-6 ${ui.panel} ${ui.border}`}>
            <div className="flex items-start gap-3">
              <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary text-white">
                <Palette size={20} aria-hidden="true" />
              </span>
              <div>
                <h2 id="accent-title" className="text-lg font-semibold">
                  Primary Accent Color
                </h2>
                <p className={`text-sm ${ui.muted}`}>
                  One color for every highlight on this terminal: navigation, mode toggle, tenders, totals and the Charge
                  button. Saved on this register and applied instantly.
                </p>
              </div>
            </div>

            <fieldset className="mt-6">
              <legend className={`mb-3 ${ui.label}`}>Presets</legend>
              <div className="grid grid-cols-[repeat(auto-fill,minmax(168px,1fr))] gap-3">
                {PRIMARY_PRESETS.map((preset) => {
                  const selected = color === preset.hex;
                  return (
                    <button
                      key={preset.hex}
                      type="button"
                      aria-pressed={selected}
                      onClick={() => choose(preset.hex)}
                      className={`flex h-16 items-center gap-3 rounded-xl border px-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 ${
                        selected
                          ? "border-primary bg-primary/10"
                          : "border-zinc-200 hover:border-zinc-300 dark:border-zinc-800 dark:hover:border-zinc-700"
                      }`}
                    >
                      <span
                        aria-hidden="true"
                        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-white ring-1 ring-black/10 dark:ring-white/15"
                        style={{ background: preset.hex }}
                      >
                        {selected ? <Check size={16} strokeWidth={3} /> : null}
                      </span>
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-semibold">{preset.name}</span>
                        <span className={`block font-mono text-[11px] ${ui.muted}`}>{preset.hex}</span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </fieldset>

            <div className="mt-6">
              <label htmlFor={hexId} className={`mb-3 block ${ui.label}`}>
                Custom color
              </label>
              <div className="flex flex-wrap items-center gap-3">
                <input
                  type="color"
                  aria-label="Pick a custom accent color"
                  value={color.toLowerCase()}
                  onChange={(event) => choose(event.target.value)}
                  className="h-12 w-16 cursor-pointer rounded-xl border border-zinc-200 bg-white p-1 dark:border-zinc-700 dark:bg-zinc-900"
                />
                <input
                  id={hexId}
                  value={hexText}
                  maxLength={7}
                  spellCheck={false}
                  autoComplete="off"
                  aria-invalid={typed === null}
                  onChange={(event) => {
                    setHexText(event.target.value);
                    if (event.target.value.replace("#", "").length === 6) choose(event.target.value);
                  }}
                  onBlur={() => (typed ? choose(typed) : setHexText(color))}
                  placeholder={DEFAULT_PRIMARY}
                  className={`h-12 w-36 rounded-xl px-3.5 font-mono text-sm uppercase tabular-nums ${ui.input}`}
                />
                <button
                  type="button"
                  disabled={color === DEFAULT_PRIMARY}
                  onClick={() => choose(DEFAULT_PRIMARY)}
                  className={`h-12 px-4 ${ui.secondaryAction}`}
                >
                  <RotateCcw size={15} aria-hidden="true" /> Reset to Vibrant Orange
                </button>
              </div>
              {typed === null ? (
                <p role="alert" className="mt-2 text-xs font-medium text-red-600 dark:text-red-400">
                  Enter a hex color such as #2563EB.
                </p>
              ) : null}
              {contrast < MIN_CONTRAST ? (
                <p className="mt-3 flex items-start gap-2 rounded-xl bg-amber-500/10 px-4 py-3 text-xs text-amber-800 ring-1 ring-amber-500/25 dark:text-amber-200">
                  <AlertTriangle size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
                  White labels on {color} have a contrast of {contrast.toFixed(1)}:1, below the {MIN_CONTRAST}:1 cashiers
                  need to read buttons at a glance. Consider a darker shade.
                </p>
              ) : null}
            </div>
          </section>

          <aside aria-label="Live preview" className="rounded-2xl border border-zinc-800 bg-zinc-950 p-5 text-zinc-100">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400">Live preview</p>
            <div className="mt-4 space-y-3">
              <div className="flex h-11 items-center gap-3 rounded-xl bg-primary-500 px-3 text-sm font-medium text-white shadow-md shadow-primary-500/25">
                <ShoppingCart size={18} aria-hidden="true" /> Checkout
              </div>
              <div className="flex rounded-full bg-zinc-900 p-1 ring-1 ring-zinc-800">
                <span className="inline-flex h-10 flex-1 items-center justify-center gap-1.5 rounded-full bg-primary text-xs font-semibold text-white">
                  <Store size={14} aria-hidden="true" /> Retail Mode
                </span>
                <span className="inline-flex h-10 flex-1 items-center justify-center text-xs font-semibold text-white/60">
                  Wholesale
                </span>
              </div>
              <div className="flex h-11 overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900">
                <span className="flex flex-1 items-center gap-2 px-3 text-xs text-zinc-500">
                  <Search size={14} aria-hidden="true" /> Scan or search…
                </span>
                <span className="flex items-center bg-primary-500 px-3 text-xs font-semibold text-white">Search Catalog</span>
              </div>
              <div className="flex gap-2">
                <span className="h-9 rounded-full bg-primary-500 px-4 text-xs font-semibold leading-9 text-white">All products</span>
                <span className="h-9 rounded-full border border-zinc-800 px-4 text-xs font-semibold leading-9 text-zinc-300">
                  Phones
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2 rounded-xl bg-zinc-900 p-1 ring-1 ring-zinc-800">
                <span className="flex h-12 flex-col items-center justify-center gap-0.5 rounded-lg bg-primary text-[11px] font-semibold text-white">
                  <Banknote size={15} aria-hidden="true" /> Cash
                </span>
                <span className="flex h-12 items-center justify-center text-[11px] font-semibold text-white/60">Card</span>
              </div>
              <div className="flex items-baseline justify-between border-t border-zinc-800 pt-3">
                <span className="text-sm font-semibold">Total</span>
                <span className="text-3xl font-bold tabular-nums text-primary-500">{formatMoney(0, currency)}</span>
              </div>
              <span className="flex h-12 w-full items-center justify-center rounded-xl bg-primary-500 text-sm font-bold text-white shadow-lg shadow-primary-500/25">
                Charge {formatMoney(0, currency)}
              </span>
            </div>
          </aside>

          <section aria-labelledby="printer-title" className={`rounded-2xl border p-6 xl:col-span-2 ${ui.panel} ${ui.border}`}>
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-start gap-3">
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-200">
                  <Printer size={20} aria-hidden="true" />
                </span>
                <div>
                  <h2 id="printer-title" className="text-lg font-semibold">
                    Receipt printer &amp; cash drawer
                  </h2>
                  <p className={`text-sm ${ui.muted}`}>Printer connection, paper width, auto-print and drawer kick.</p>
                </div>
              </div>
              <button type="button" onClick={() => setPrinter(true)} className={`h-11 px-5 ${ui.secondaryAction}`}>
                Open printer settings
              </button>
            </div>
          </section>

          {capabilities.enabled.has(Capability.WeighedItems) ? <ScaleSettingsCard /> : null}

          {notice ? (
            <p role="status" className={`rounded-xl px-4 py-3 text-sm xl:col-span-2 ${ui.surface}`}>
              {notice}
            </p>
          ) : null}
        </div>
      </main>
      {printer ? (
        <PrinterSettingsModal
          sample={sampleReceipt(session.user.full_name)}
          onClose={() => setPrinter(false)}
          onSaved={(message) => {
            setPrinter(false);
            setNotice(message);
          }}
        />
      ) : null}
    </div>
  );
}
