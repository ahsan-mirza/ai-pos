import { formatWeight } from "@ai-pos/shared-types";
import { Select } from "@ai-pos/ui";
import { Loader2, RefreshCw, Scale } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { ui } from "../../components/shell/tokens";
import { inTauri, readScale, scalePorts, type ScaleConfig } from "../../lib/tauri";
import { DEFAULT_SCALE_CONFIG, SCALE_BAUD_RATES, loadScaleConfig, saveScaleConfig } from "./scaleConfig";

/** Weighing scale connection for this register; shown only when the business sells weighed items. */
export function ScaleSettingsCard() {
  const native = inTauri();
  const portId = useId();
  const baudId = useId();
  const protocolId = useId();
  const [config, setConfig] = useState<ScaleConfig>(() => loadScaleConfig() ?? DEFAULT_SCALE_CONFIG);
  const [ports, setPorts] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    if (native) void scalePorts().then(setPorts).catch(() => setPorts([]));
  }, [native]);

  const update = (next: ScaleConfig) => {
    setConfig(next);
    setResult(null);
    if (next.port !== "") saveScaleConfig(next);
  };

  const test = async () => {
    setBusy(true);
    setResult(null);
    try {
      const reading = await readScale(config);
      setResult({ ok: true, text: `${formatWeight(reading.grams)}${reading.stable ? "" : " (still settling)"}` });
    } catch (caught) {
      setResult({ ok: false, text: caught instanceof Error ? caught.message : String(caught) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-labelledby="scale-title" className={`rounded-2xl border p-6 xl:col-span-2 ${ui.panel} ${ui.border}`}>
      <div className="flex items-start gap-3">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-200">
          <Scale size={20} aria-hidden="true" />
        </span>
        <div>
          <h2 id="scale-title" className="text-lg font-semibold">
            Weighing scale
          </h2>
          <p className={`text-sm ${ui.muted}`}>
            The scale weighed items are read from. Saved on this register; cashiers can still type a weight by hand.
          </p>
        </div>
      </div>
      {native ? (
        <div className="mt-5 grid gap-3 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,2fr)_auto] sm:items-end">
          <label htmlFor={portId} className={`block ${ui.label}`}>
            Port
            <Select
              id={portId}
              className="mt-1.5"
              aria-label="Port"
              placeholder="Choose a port…"
              value={config.port}
              onChange={(port) => update({ ...config, port })}
              options={[{ value: "", label: "Choose a port…" }, ...ports.map((port) => ({ value: port, label: port }))]}
            />
          </label>
          <label htmlFor={baudId} className={`block ${ui.label}`}>
            Baud rate
            <Select
              id={baudId}
              className="mt-1.5"
              aria-label="Baud rate"
              value={String(config.baud)}
              onChange={(value) => update({ ...config, baud: Number(value) })}
              options={SCALE_BAUD_RATES.map((baud) => ({ value: String(baud), label: String(baud) }))}
            />
          </label>
          <label htmlFor={protocolId} className={`block ${ui.label}`}>
            Protocol
            <Select
              id={protocolId}
              className="mt-1.5"
              aria-label="Protocol"
              value={config.protocol}
              onChange={(protocol) => update({ ...config, protocol: protocol as ScaleConfig["protocol"] })}
              options={[
                { value: "continuous", label: "Continuous output" },
                { value: "request", label: "Request (Toledo / CAS)" },
              ]}
            />
          </label>
          <button
            type="button"
            onClick={() => void test()}
            disabled={busy || config.port === ""}
            className={`h-11 px-4 ${ui.secondaryAction}`}
          >
            {busy ? <Loader2 size={15} className="animate-spin" aria-hidden="true" /> : <RefreshCw size={15} aria-hidden="true" />}
            Test read
          </button>
        </div>
      ) : (
        <p className={`mt-4 rounded-xl px-4 py-3 text-sm ${ui.surface}`}>
          Scales connect in the desktop register app. In the browser, cashiers type the weight.
        </p>
      )}
      {result ? (
        <p
          role="status"
          className={`mt-3 text-sm font-medium ${result.ok ? "text-emerald-700 dark:text-emerald-300" : "text-red-600 dark:text-red-400"}`}
        >
          {result.ok ? `Scale reads ${result.text}.` : result.text}
        </p>
      ) : null}
    </section>
  );
}
