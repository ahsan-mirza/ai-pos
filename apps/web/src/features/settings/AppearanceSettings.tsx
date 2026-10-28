import type { BusinessSettings } from "@ai-pos/shared-types";
import { AlertTriangle, Check, LayoutDashboard, Palette, RotateCcw } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { ErrorNote, GhostButton, PrimaryButton } from "../../components/ui/Field";
import { apiPut } from "../../lib/api";
import { useCurrency } from "../../lib/currency";
import { DEFAULT_PRIMARY, PRIMARY_PRESETS, applyPrimaryColor, contrastWithWhite, normalizeHex } from "../../lib/theme";
import { errorMessage } from "../users/api";

/** Below 3:1, white button labels and active pills on the primary color become hard to read. */
const MIN_CONTRAST = 3;

export function AppearanceSettings() {
  const { settings, applySettings } = useCurrency();
  const saved = settings?.primary_color ?? null;
  const [draft, setDraft] = useState<string | null>(saved);
  const [hexText, setHexText] = useState(saved ?? DEFAULT_PRIMARY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const savedRef = useRef(saved);
  const hexId = useId();

  savedRef.current = saved;
  const effective = draft ?? DEFAULT_PRIMARY;
  const dirty = draft !== saved;
  const typed = normalizeHex(hexText);
  const contrast = contrastWithWhite(effective);

  useEffect(() => {
    if (!dirty) {
      setDraft(saved);
      setHexText(saved ?? DEFAULT_PRIMARY);
    }
    // Only follow the server value while the admin has nothing pending.
  }, [saved]);

  useEffect(() => {
    applyPrimaryColor(draft);
  }, [draft]);

  useEffect(() => () => applyPrimaryColor(savedRef.current), []);

  const choose = (hex: string | null) => {
    setDraft(hex);
    setHexText(hex ?? DEFAULT_PRIMARY);
    setNotice(null);
    setError(null);
  };

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const next = await apiPut<BusinessSettings>("/api/v1/settings/appearance", { primary_color: draft });
      applySettings(next);
      setNotice(
        next.primary_color
          ? `${next.primary_color} is now the primary color for every administrator.`
          : "The AxizPOS brand color is restored for every administrator.",
      );
    } catch (caught) {
      setError(errorMessage(caught, "Could not save the primary color."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-card border border-line bg-white p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-accent text-white transition-colors">
            <Palette size={20} aria-hidden="true" />
          </span>
          <div>
            <h2 className="text-2xl font-semibold">Brand Appearance &amp; Primary Color</h2>
            <p className="text-sm text-charcoal/60">
              Accent for buttons, active navigation, filters, KPI cards and charts across the admin portal.
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <GhostButton disabled={!dirty || busy} onClick={() => choose(saved)}>
            Discard
          </GhostButton>
          <PrimaryButton disabled={!dirty || busy || settings === null} onClick={() => void save()}>
            {busy ? "Saving…" : "Save color"}
          </PrimaryButton>
        </div>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-6">
          <fieldset>
            <legend className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-[#6B7280]">Presets</legend>
            <div className="grid grid-cols-[repeat(auto-fill,minmax(176px,1fr))] gap-3">
              {PRIMARY_PRESETS.map((preset) => {
                const selected = draft === preset.hex;
                return (
                  <button
                    key={preset.hex}
                    type="button"
                    aria-pressed={selected}
                    onClick={() => choose(preset.hex)}
                    className={`flex items-center gap-3 rounded-2xl border p-3 text-left transition ${
                      selected ? "border-charcoal ring-2 ring-charcoal/10" : "border-line hover:border-charcoal/30"
                    }`}
                  >
                    <span
                      aria-hidden="true"
                      className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-white shadow-inner"
                      style={{ background: preset.hex }}
                    >
                      {selected ? <Check size={16} strokeWidth={3} /> : null}
                    </span>
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-semibold">{preset.name}</span>
                      <span className="block font-mono text-[11px] text-charcoal/50">{preset.hex}</span>
                    </span>
                  </button>
                );
              })}
            </div>
            <button
              type="button"
              onClick={() => choose(null)}
              disabled={draft === null}
              className="mt-3 inline-flex items-center gap-1.5 text-xs font-semibold text-charcoal/60 hover:text-charcoal disabled:text-charcoal/30"
            >
              <RotateCcw size={13} aria-hidden="true" />
              {draft === null ? "Using the AxizPOS brand color" : "Reset to the AxizPOS brand color"} ({DEFAULT_PRIMARY})
            </button>
          </fieldset>

          <div>
            <label htmlFor={hexId} className="mb-3 block text-[11px] font-semibold uppercase tracking-wider text-[#6B7280]">
              Custom brand color
            </label>
            <div className="flex flex-wrap items-center gap-3">
              <input
                type="color"
                aria-label="Pick a custom color"
                value={effective.toLowerCase()}
                onChange={(event) => choose(event.target.value.toUpperCase())}
                className="h-11 w-14 cursor-pointer rounded-xl border border-line bg-white p-1"
              />
              <input
                id={hexId}
                value={hexText}
                maxLength={7}
                spellCheck={false}
                autoComplete="off"
                onChange={(event) => {
                  const next = event.target.value;
                  setHexText(next);
                  const hex = normalizeHex(next);
                  if (hex && next.replace("#", "").length === 6) {
                    setDraft(hex);
                    setNotice(null);
                  }
                }}
                onBlur={() => {
                  if (typed) choose(typed);
                  else setHexText(effective);
                }}
                placeholder="#F26A21"
                aria-invalid={typed === null}
                className={`h-11 w-36 rounded-full border bg-white px-4 font-mono text-sm uppercase tabular-nums focus:outline-none focus:ring-2 ${
                  typed === null
                    ? "border-red-400 focus:ring-red-200"
                    : "border-line focus:border-accent focus:ring-accent/20"
                }`}
              />
              <span className="text-xs text-charcoal/50">Any hex code, e.g. #0EA5E9</span>
            </div>
            {typed === null ? (
              <p className="mt-2 text-xs font-medium text-red-600">Enter a hex color such as #2563EB.</p>
            ) : null}
            {contrast < MIN_CONTRAST ? (
              <p className="mt-3 flex items-start gap-2 rounded-2xl bg-amber-50 px-4 py-3 text-xs text-amber-800">
                <AlertTriangle size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
                White labels on {effective} have a contrast of {contrast.toFixed(1)}:1, below the {MIN_CONTRAST}:1 needed
                for buttons to stay readable. Consider a darker shade.
              </p>
            ) : null}
          </div>
        </div>

        <PreviewPanel color={effective} dirty={dirty} />
      </div>

      {notice ? (
        <p role="status" className="mt-4 rounded-2xl bg-surface px-4 py-3 text-sm text-charcoal/80">
          {notice}
        </p>
      ) : null}
      <ErrorNote message={error} />
    </div>
  );
}

function PreviewPanel({ color, dirty }: { color: string; dirty: boolean }) {
  return (
    <div className="rounded-2xl border border-line bg-[#f8fafc] p-4" aria-label="Live preview">
      <div className="flex items-center justify-between">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-[#6B7280]">Live preview</p>
        <span
          className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
            dirty ? "bg-amber-100 text-amber-800" : "bg-emerald-50 text-emerald-700"
          }`}
        >
          {dirty ? "Not saved" : "Saved"}
        </span>
      </div>
      <div className="mt-3 space-y-3">
        <div className="flex items-center gap-2 rounded-lg bg-accent/[0.08] px-3 py-2 text-[13px] font-semibold text-accent shadow-[inset_3px_0_0_rgb(var(--primary-rgb))]">
          <LayoutDashboard size={16} aria-hidden="true" /> Dashboard
        </div>
        <div className="flex gap-2">
          <span className="rounded-full bg-accent px-4 py-1.5 text-xs font-semibold text-white">All time</span>
          <span className="rounded-full border border-line bg-white px-4 py-1.5 text-xs font-semibold">Weekly</span>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex-1 rounded-2xl bg-accent p-3 text-white">
            <p className="text-[11px] text-white/80">Units sold</p>
            <p className="text-2xl font-semibold tabular-nums">189</p>
          </div>
          <div
            aria-hidden="true"
            className="h-16 w-16 shrink-0 rounded-full"
            style={{
              background: `conic-gradient(var(--primary) 0 62%, #222026 62% 84%, #CBCECE 84% 100%)`,
              mask: "radial-gradient(circle, transparent 55%, black 56%)",
              WebkitMask: "radial-gradient(circle, transparent 55%, black 56%)",
            }}
          />
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-charcoal/10">
          <div className="h-full w-2/3 rounded-full bg-accent" />
        </div>
        <button
          type="button"
          tabIndex={-1}
          className="w-full rounded-full bg-accent py-2.5 text-sm font-medium text-white shadow-sm hover:bg-accent-hover"
        >
          Import purchases
        </button>
        <p className="text-center font-mono text-[11px] text-charcoal/50">{color}</p>
      </div>
    </div>
  );
}
