import { formatMoney, formatWeight, weighedLineCents, type ProductUpsert } from "@ai-pos/shared-types";
import { Select } from "@ai-pos/ui";
import { Loader2, RefreshCw, Scale, Settings2, X } from "lucide-react";
import { useCallback, useEffect, useId, useState } from "react";
import { inTauri, readScale, scalePorts, type ScaleConfig } from "../../lib/tauri";
import { SCALE_BAUD_RATES, loadScaleConfig, saveScaleConfig } from "../settings/scaleConfig";

interface WeighModalProps {
  product: ProductUpsert;
  currency: string;
  onClose: () => void;
  onConfirm: (grams: number) => void;
}

/** Sell a weighed product: live reading from the scale (tare taken off), or the weight typed by hand. */
export function WeighModal({ product, currency, onClose, onConfirm }: WeighModalProps) {
  const titleId = useId();
  const native = inTauri();
  const [config, setConfig] = useState<ScaleConfig | null>(loadScaleConfig);
  const [ports, setPorts] = useState<string[]>([]);
  const [setup, setSetup] = useState(false);
  const [reading, setReading] = useState<{ grams: number; stable: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const [manual, setManual] = useState("");
  const [error, setError] = useState<string | null>(null);
  const tare = product.tare_grams ?? 0;

  const weigh = useCallback(async () => {
    if (!native || config === null) return;
    setBusy(true);
    setError(null);
    try {
      const result = await readScale(config);
      setReading({ grams: result.grams, stable: result.stable });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }, [config, native]);

  useEffect(() => {
    void weigh();
  }, [weigh]);

  useEffect(() => {
    if (setup && native) void scalePorts().then(setPorts).catch(() => setPorts([]));
  }, [setup, native]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const typedGrams = Math.round(Number.parseFloat(manual.replace(",", ".") || "0") * 1000);
  const gross = manual.trim() !== "" ? typedGrams : (reading?.grams ?? 0);
  const net = Math.max(0, gross - (manual.trim() !== "" ? 0 : tare));
  const price = weighedLineCents(net, product.price_cents);

  function saveConfig(next: ScaleConfig) {
    setConfig(next);
    saveScaleConfig(next);
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <div role="dialog" aria-modal="true" aria-labelledby={titleId} className="modal-card max-w-md">
        <div className="flex items-start gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-charcoal text-white dark:bg-zinc-100 dark:text-zinc-900">
            <Scale size={20} aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-xl font-semibold">
              {product.name}
            </h2>
            <p className="text-sm text-charcoal/60 tabular-nums dark:text-zinc-400">
              {formatMoney(product.price_cents, currency)} per kg{tare ? ` · tare ${tare} g` : ""}
            </p>
          </div>
          <button type="button" aria-label="Close" onClick={onClose} className="modal-close">
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        <form
          className="mt-5 space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (net <= 0) {
              setError("Put the item on the scale, or type its weight.");
              return;
            }
            if (reading && !reading.stable && manual.trim() === "") {
              setError("The scale is still settling. Read it again.");
              return;
            }
            onConfirm(net);
          }}
        >
          <div className="rounded-2xl bg-surface px-4 py-4 text-center dark:bg-zinc-800/60">
            <p className="text-xs font-semibold uppercase tracking-wide text-charcoal/50 dark:text-zinc-400">Net weight</p>
            <p className="mt-1 text-4xl font-bold tabular-nums">{formatWeight(net)}</p>
            <p className="mt-1 text-lg font-semibold tabular-nums text-primary">{formatMoney(price, currency)}</p>
            {native && config ? (
              <button
                type="button"
                onClick={() => void weigh()}
                disabled={busy}
                className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-white px-3 py-1.5 text-xs font-semibold shadow-sm disabled:opacity-50 dark:bg-zinc-900"
              >
                {busy ? <Loader2 size={13} className="animate-spin" aria-hidden="true" /> : <RefreshCw size={13} aria-hidden="true" />}
                {reading && !reading.stable ? "Settling… read again" : "Read scale"}
              </button>
            ) : (
              <p className="mt-2 text-xs text-charcoal/50 dark:text-zinc-400">
                {native ? "No scale set up on this register yet." : "Scales connect in the register app; type the weight here."}
              </p>
            )}
          </div>

          <label className="block text-sm font-medium" htmlFor="weigh-manual">
            Or type the net weight (kg)
            <input
              id="weigh-manual"
              inputMode="decimal"
              autoComplete="off"
              autoFocus={!native || config === null}
              value={manual}
              onChange={(event) => {
                setManual(event.target.value.replace(/[^\d.,]/g, ""));
                setError(null);
              }}
              placeholder="0.000"
              className="modal-input mt-1.5 text-lg font-semibold tabular-nums"
            />
          </label>

          {native ? (
            <div>
              <button
                type="button"
                onClick={() => setSetup((value) => !value)}
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-charcoal/60 hover:text-charcoal dark:text-zinc-400 dark:hover:text-white"
              >
                <Settings2 size={13} aria-hidden="true" /> Scale settings
              </button>
              {setup ? (
                <div className="mt-2 grid grid-cols-3 gap-2">
                  <Select
                    className="col-span-3"
                    aria-label="Scale port"
                    placeholder="Choose a port…"
                    value={config?.port ?? ""}
                    onChange={(port) => saveConfig({ port, baud: config?.baud ?? 9600, protocol: config?.protocol ?? "continuous" })}
                    options={[{ value: "", label: "Choose a port…" }, ...ports.map((port) => ({ value: port, label: port }))]}
                  />
                  <Select
                    aria-label="Baud rate"
                    value={String(config?.baud ?? 9600)}
                    onChange={(value) => config && saveConfig({ ...config, baud: Number(value) })}
                    options={SCALE_BAUD_RATES.map((baud) => ({ value: String(baud), label: String(baud) }))}
                  />
                  <Select
                    className="col-span-2"
                    aria-label="Scale protocol"
                    value={config?.protocol ?? "continuous"}
                    onChange={(protocol) => config && saveConfig({ ...config, protocol: protocol as ScaleConfig["protocol"] })}
                    options={[
                      { value: "continuous", label: "Continuous output" },
                      { value: "request", label: "Request (Toledo / CAS)" },
                    ]}
                  />
                </div>
              ) : null}
            </div>
          ) : null}

          {error ? (
            <p role="alert" className="text-sm font-medium text-red-600 dark:text-red-400">
              {error}
            </p>
          ) : null}
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="modal-cancel">
              Cancel
            </button>
            <button type="submit" className="modal-save" disabled={net <= 0}>
              Add {net > 0 ? formatWeight(net) : ""}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
