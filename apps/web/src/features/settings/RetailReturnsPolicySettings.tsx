import { RETURNS_PRESETS, type PosPolicy, type ReturnConditionRule } from "@ai-pos/shared-types";
import { Plus, Trash2 } from "lucide-react";
import { TextField } from "../../components/ui/Field";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { Select } from "../../components/ui/Select";
import { ChoiceList, SERIAL_STATUS, keyOf, percent, toBps } from "./policyFields";

type Preset = PosPolicy["returns"]["preset"];

const PRESET_OPTIONS = [
  { value: "electronics" as const, label: "Electronics" },
  { value: "fashion" as const, label: "Fashion" },
  { value: "custom" as const, label: "Custom" },
];

/** Retail return window, restocking fees, and (for electronics) where a serialized unit goes. */
export function RetailReturnsPolicySettings({
  returns,
  showElectronicsPreset,
  showFashionPreset,
  showSerialRouting,
  onPreset,
  onPatch,
  onCondition,
}: {
  returns: PosPolicy["returns"];
  showElectronicsPreset: boolean;
  showFashionPreset: boolean;
  showSerialRouting: boolean;
  onPreset: (preset: Exclude<Preset, "custom">) => void;
  onPatch: (patch: Partial<PosPolicy["returns"]>) => void;
  onCondition: (index: number, patch: Partial<ReturnConditionRule>) => void;
}) {
  const options = PRESET_OPTIONS.filter(
    (option) =>
      option.value === "custom" ||
      (option.value === "electronics" && showElectronicsPreset) ||
      (option.value === "fashion" && showFashionPreset),
  );
  const showPresets = options.length > 1;
  return (
    <section className="space-y-4 rounded-2xl border border-line p-4 lg:col-span-2">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 className="font-semibold">Returns policy</h3>
          <p className="text-sm text-charcoal/60">
            Refund to the original payment inside the return window, then an exchange or store credit only.
          </p>
        </div>
        {showPresets ? (
          <SegmentedControl
            label="Returns preset"
            value={options.some((option) => option.value === returns.preset) ? returns.preset : "custom"}
            options={options}
            onChange={(preset) => (preset === "custom" ? onPatch({ preset: "custom" }) : onPreset(preset))}
          />
        ) : null}
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:max-w-lg">
        <TextField
          label="Refund window (days)"
          type="number"
          min={0}
          max={365}
          value={returns.window_days}
          onChange={(event) => onPatch({ window_days: Math.max(0, Math.min(365, Number(event.target.value) || 0)) })}
        />
        <TextField
          label="Exchange-only days after"
          type="number"
          min={0}
          max={365}
          value={returns.exchange_window_days}
          onChange={(event) =>
            onPatch({ exchange_window_days: Math.max(0, Math.min(365, Number(event.target.value) || 0)) })
          }
        />
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-charcoal/50">
            <tr>
              <th className="pb-2 font-medium">Condition</th>
              <th className="pb-2 font-medium">Restock</th>
              <th className="pb-2 font-medium">Fee %</th>
              {showSerialRouting ? <th className="pb-2 font-medium">Serialized unit goes to</th> : null}
              <th className="pb-2" />
            </tr>
          </thead>
          <tbody>
            {returns.conditions.map((condition, index) => (
              <tr key={condition.key} className="border-t border-line">
                <td className="py-2 pr-3">
                  <input
                    aria-label={`Condition ${index + 1}`}
                    value={condition.label}
                    maxLength={60}
                    onChange={(event) => onCondition(index, { label: event.target.value })}
                    className="w-full rounded-xl bg-surface px-3 py-2 focus:bg-white focus:outline-none focus:ring-1 focus:ring-accent"
                  />
                </td>
                <td className="py-2 pr-3">
                  <input
                    type="checkbox"
                    aria-label={`Restock ${condition.label}`}
                    checked={condition.restock}
                    onChange={(event) => onCondition(index, { restock: event.target.checked })}
                    className="h-4 w-4 accent-accent"
                  />
                </td>
                <td className="py-2 pr-3">
                  <input
                    aria-label={`Restocking fee for ${condition.label}`}
                    inputMode="decimal"
                    value={percent(condition.fee_bps)}
                    onChange={(event) => {
                      const bps = toBps(event.target.value || "0", 5000);
                      if (bps !== null) onCondition(index, { fee_bps: bps });
                    }}
                    className="w-20 rounded-xl bg-surface px-3 py-2 tabular-nums focus:bg-white focus:outline-none focus:ring-1 focus:ring-accent"
                  />
                </td>
                {showSerialRouting ? (
                  <td className="py-2 pr-3">
                    <Select
                      aria-label={`Serial status for ${condition.label}`}
                      value={condition.serial_status}
                      options={SERIAL_STATUS}
                      onChange={(status) => onCondition(index, { serial_status: status })}
                      className="w-44"
                    />
                  </td>
                ) : null}
                <td className="py-2 text-right">
                  <button
                    type="button"
                    aria-label={`Remove ${condition.label}`}
                    disabled={returns.conditions.length <= 1}
                    onClick={() => onPatch({ conditions: returns.conditions.filter((_, at) => at !== index) })}
                    className="flex h-9 w-9 items-center justify-center rounded-full text-charcoal/50 hover:bg-surface hover:text-accent disabled:opacity-30"
                  >
                    <Trash2 size={15} aria-hidden="true" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <button
          type="button"
          disabled={returns.conditions.length >= 10}
          onClick={() =>
            onPatch({
              conditions: [
                ...returns.conditions,
                {
                  key: keyOf("condition", new Set(returns.conditions.map((condition) => condition.key))),
                  label: "New condition",
                  restock: false,
                  fee_bps: 0,
                  serial_status: "quarantine",
                },
              ],
            })
          }
          className="mt-2 inline-flex items-center gap-1 text-sm font-semibold text-accent disabled:opacity-40"
        >
          <Plus size={15} aria-hidden="true" /> Add condition
        </button>
      </div>
      <div className="lg:max-w-lg">
        <ChoiceList title="Return reasons" items={returns.reasons} locked={() => false} onChange={(reasons) => onPatch({ reasons })} />
      </div>
    </section>
  );
}

/** Applies a named preset without marking the policy custom. */
export function presetReturns(preset: Exclude<Preset, "custom">): PosPolicy["returns"] {
  return structuredClone(RETURNS_PRESETS[preset]);
}
