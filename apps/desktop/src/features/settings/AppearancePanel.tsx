import { Capability, formatMoney } from "@ai-pos/shared-types";
import { AlertTriangle, Banknote, Check, Palette, RotateCcw, Search, ShoppingCart, Store } from "lucide-react";
import { useId, useState } from "react";
import { useRegisterLayout } from "../../components/RegisterLayout";
import { ui } from "../../components/shell/tokens";
import { DEFAULT_PRIMARY, PRIMARY_PRESETS, contrastWithWhite, normalizeHex, savePrimaryColor, storedPrimaryColor } from "../../lib/theme";
import { useCapabilities } from "../../lib/capabilities";
import { useBusinessCurrency } from "../checkout/currency";
import { PrinterSettingsModal } from "../printing/PrinterSettingsModal";
import { ReceiptHardwareCard } from "../printing/ReceiptHardwareCard";
import { sampleReceipt } from "../printing/saleReceipt";
import { ScaleSettingsCard } from "./ScaleSettingsCard";
import { SettingsSectionCard } from "./settingsUi";

const MIN_CONTRAST = 3;

export function AppearancePanel({ cashier, part, canConfigure = false }: { cashier: string; part: "appearance" | "hardware"; canConfigure?: boolean }) {
  const { theme, setTheme, density, setDensity, showImages, setShowImages } = useRegisterLayout();
  const capabilities = useCapabilities();
  const currency = useBusinessCurrency();
  const [color, setColor] = useState(() => storedPrimaryColor() ?? DEFAULT_PRIMARY);
  const [hexText, setHexText] = useState(color);
  const [printer, setPrinter] = useState(false);
  const [hardwareTick, setHardwareTick] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);
  const hexId = useId();
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
  return (
    <div className="space-y-4">
      {part === "appearance" ? <>
      <SettingsSectionCard>
        <div className="flex items-start gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary text-white"><Palette size={20} aria-hidden="true" /></span>
          <div>
            <h2 className="text-lg font-semibold text-zinc-900">Primary accent color</h2>
            <p className="text-sm text-zinc-500">Saved on this register and applied immediately. It does not change prices or tax.</p>
          </div>
        </div>
        <div className="mt-5 grid grid-cols-[repeat(auto-fill,minmax(10.5rem,1fr))] gap-3">
          {PRIMARY_PRESETS.map((preset) => {
            const selected = color === preset.hex;
            return (
              <button key={preset.hex} type="button" aria-pressed={selected} onClick={() => choose(preset.hex)} className={`flex h-16 items-center gap-3 rounded-xl border px-3 text-left ${selected ? "border-primary bg-primary/10" : "border-zinc-200"}`}>
                <span className="flex h-9 w-9 items-center justify-center rounded-full text-white" style={{ background: preset.hex }}>{selected ? <Check size={16} /> : null}</span>
                <span><span className="block text-sm font-semibold">{preset.name}</span><span className="font-mono text-[0.6875rem] text-zinc-500">{preset.hex}</span></span>
              </button>
            );
          })}
        </div>
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <input type="color" aria-label="Pick a custom accent color" value={color.toLowerCase()} onChange={(event) => choose(event.target.value)} className="h-12 w-16 rounded-xl border border-zinc-200 bg-white p-1" />
          <input id={hexId} value={hexText} maxLength={7} spellCheck={false} aria-invalid={typed === null} onChange={(event) => { setHexText(event.target.value); if (event.target.value.replace("#", "").length === 6) choose(event.target.value); }} onBlur={() => (typed ? choose(typed) : setHexText(color))} className={`h-12 w-36 rounded-xl px-3 font-mono text-sm uppercase ${ui.input}`} />
          <button type="button" disabled={color === DEFAULT_PRIMARY} onClick={() => choose(DEFAULT_PRIMARY)} className={`h-12 px-4 ${ui.secondaryAction}`}><RotateCcw size={15} aria-hidden="true" /> Reset</button>
        </div>
        {typed === null ? <p role="alert" className="mt-2 text-xs text-red-600">Enter a hex color such as #F26A21.</p> : null}
        {contrast < MIN_CONTRAST ? <p className="mt-3 flex gap-2 rounded-xl bg-amber-500/10 px-4 py-3 text-xs text-amber-800"><AlertTriangle size={14} className="mt-0.5 shrink-0" /> White labels on {color} are below {MIN_CONTRAST}:1 contrast.</p> : null}
      </SettingsSectionCard>
      <SettingsSectionCard>
        <h2 className="text-lg font-semibold">Checkout layout</h2>
        <p className="mt-1 text-sm text-zinc-500">Saved on this register. These choices change how the catalog is drawn.</p>
        <div className="mt-4 flex flex-wrap gap-2">
          {(["light", "dark"] as const).map((id) => (
            <button key={id} type="button" aria-pressed={theme === id} onClick={() => setTheme(id)} className={`h-12 rounded-xl px-5 text-sm font-semibold capitalize ${theme === id ? "bg-primary text-white" : ui.secondaryAction}`}>{id}</button>
          ))}
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {(["compact", "comfortable", "large"] as const).map((id) => (
            <button key={id} type="button" aria-pressed={density === id} onClick={() => setDensity(id)} className={`h-12 rounded-xl px-5 text-sm font-semibold capitalize ${density === id ? "bg-primary text-white" : ui.secondaryAction}`}>{id === "large" ? "Large touch" : id}</button>
          ))}
        </div>
        <label className="mt-4 flex h-12 items-center justify-between rounded-xl border border-zinc-200 px-4 text-sm font-semibold">
          Show product photos
          <input type="checkbox" className="h-5 w-5 accent-primary" checked={showImages} onChange={(event) => setShowImages(event.target.checked)} />
        </label>
        <div className="mt-4 rounded-2xl bg-zinc-950 p-4 text-zinc-100">
          <p className="text-[0.6875rem] font-semibold uppercase tracking-wider text-zinc-400">Live preview</p>
          <div className="mt-3 flex h-11 items-center gap-2 rounded-xl bg-primary px-3 text-sm text-white"><ShoppingCart size={16} /> Checkout</div>
          <div className="mt-2 flex h-11 items-center gap-2 rounded-xl border border-zinc-800 px-3 text-xs text-zinc-500"><Search size={14} /> Scan or search…</div>
          <div className="mt-2 flex gap-2"><span className="inline-flex h-9 items-center gap-1 rounded-full bg-primary px-3 text-xs"><Store size={14} /> Retail</span><span className="inline-flex h-9 items-center rounded-full border border-zinc-800 px-3 text-xs"><Banknote size={14} /> Pay {formatMoney(0, currency)}</span></div>
        </div>
      </SettingsSectionCard>
      </> : null}
      {part === "hardware" ? <ReceiptHardwareCard sample={sampleReceipt(cashier)} refreshToken={hardwareTick} canConfigure={canConfigure} onChangePrinter={() => setPrinter(true)} /> : null}
      {part === "hardware" && capabilities.enabled.has(Capability.WeighedItems) ? <ScaleSettingsCard /> : null}
      {notice ? <p role="status" className="rounded-xl bg-white px-4 py-3 text-sm">{notice}</p> : null}
      {printer ? <PrinterSettingsModal sample={sampleReceipt(cashier)} canSave={canConfigure} onClose={() => { setPrinter(false); setHardwareTick((tick) => tick + 1); }} onSaved={(message) => { setPrinter(false); setNotice(message); setHardwareTick((tick) => tick + 1); }} /> : null}
    </div>
  );
}
