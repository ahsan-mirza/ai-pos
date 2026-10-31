import { specKey, type SpecSchema } from "@ai-pos/shared-types";
import { SearchableMultiSpecSelect, SearchableSpecSelect } from "@ai-pos/ui";
import {
  Battery,
  Box,
  Cpu,
  HardDrive,
  Layers,
  Monitor,
  Palette,
  Ruler,
  Shirt,
  Snowflake,
  Smartphone,
  Tag,
  User,
  Wifi,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useState } from "react";

const control =
  "mt-1.5 h-12 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 text-sm tabular-nums text-charcoal focus:border-orange-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-orange-500 dark:border-gray-700/80 dark:bg-[#2D2A32] dark:text-white";

const FIELD_ICONS: Record<string, LucideIcon> = {
  processor: Cpu,
  ram: Layers,
  storage: HardDrive,
  graphics: Monitor,
  screen_size: Monitor,
  os: Smartphone,
  color: Palette,
  network: Wifi,
  battery: Battery,
  capacity_litres: Box,
  defrost_type: Snowflake,
  energy_rating: Zap,
  compressor: Zap,
  door_style: Box,
  display_tech: Monitor,
  resolution: Monitor,
  refresh_rate: Zap,
  size: Ruler,
  fabric: Shirt,
  gender_fit: User,
  length: Ruler,
  sleeve: Shirt,
  neckline: Shirt,
  material: Layers,
  width: Ruler,
};

function labelFor(key: string): string {
  return key.replace(/_/g, " ").replace(/^\w/, (letter) => letter.toUpperCase());
}

function withCurrent(options: readonly string[], extras: readonly string[], current: string): string[] {
  const seen = new Set<string>();
  const next: string[] = [];
  for (const option of [...options, ...extras, current]) {
    const name = option.trim();
    if (name === "") continue;
    const key = name.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    next.push(name);
  }
  return next;
}

/** The specification inputs for the category the merchant picked, or a free key/value list. */
export function SpecFields({
  schema,
  specs,
  onChange,
  multiKeys = [],
  multiValues = {},
  onMultiChange,
}: {
  schema: SpecSchema;
  specs: Record<string, string>;
  onChange: (next: Record<string, string>) => void;
  /** Fashion size and color. Other business types keep a single value. */
  multiKeys?: readonly string[];
  multiValues?: Record<string, string[]>;
  onMultiChange?: (key: string, values: string[]) => void;
}) {
  const [draftName, setDraftName] = useState("");
  const [draftValue, setDraftValue] = useState("");
  const [added, setAdded] = useState<Record<string, string[]>>({});
  const draftKey = specKey(draftName);
  const draftProblem = draftName.trim() !== "" && draftKey === "" ? "Use letters and numbers." : "";

  useEffect(() => {
    setDraftName("");
    setDraftValue("");
    setAdded({});
  }, [schema.id]);

  if (schema.id === "OTHER") {
    const rows = Object.entries(specs);
    return (
      <div className="space-y-3">
        <p className="text-sm text-charcoal/60">Add the details that matter for this item. Each row is a name and a value.</p>
        {rows.map(([key, value]) => (
          <div key={key} className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_1fr_auto]">
            <label className="block text-sm font-medium">
              Attribute
              <input value={labelFor(key)} disabled className={`${control} disabled:text-charcoal/50`} />
            </label>
            <label className="block text-sm font-medium">
              Value
              <input
                value={value}
                onChange={(event) => onChange({ ...specs, [key]: event.target.value })}
                className={control}
              />
            </label>
            <button
              type="button"
              onClick={() => {
                const next = { ...specs };
                delete next[key];
                onChange(next);
              }}
              className="h-12 self-end rounded-xl border border-slate-200 px-4 text-sm font-semibold text-charcoal/70 hover:bg-slate-50"
            >
              Remove
            </button>
          </div>
        ))}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_1fr_auto]">
          <label className="block text-sm font-medium">
            Attribute name
            <input
              value={draftName}
              placeholder="Attribute name"
              autoComplete="off"
              onChange={(event) => setDraftName(event.target.value)}
              className={control}
            />
          </label>
          <label className="block text-sm font-medium">
            Value
            <input
              value={draftValue}
              placeholder="Value"
              autoComplete="off"
              onChange={(event) => setDraftValue(event.target.value)}
              className={control}
            />
          </label>
          <button
            type="button"
            disabled={draftKey === "" || draftValue.trim() === ""}
            onClick={() => {
              onChange({ ...specs, [draftKey]: draftValue.trim() });
              setDraftName("");
              setDraftValue("");
            }}
            className="h-12 self-end rounded-xl bg-charcoal px-4 text-sm font-semibold text-white disabled:opacity-40"
          >
            Add
          </button>
        </div>
        {draftProblem ? (
          <p role="alert" className="text-xs font-medium text-danger">
            {draftProblem}
          </p>
        ) : null}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      {schema.fields.map((field) => {
        const current = specs[field.key] ?? "";
        if (multiKeys.includes(field.key)) {
          const selected = multiValues[field.key] ?? [];
          return (
            <SearchableMultiSpecSelect
              key={field.key}
              label={field.label}
              icon={FIELD_ICONS[field.key] ?? Tag}
              placeholder={field.placeholder}
              values={selected}
              options={withCurrent(field.options, [...(added[field.key] ?? []), ...selected], "")}
              onChange={(next) => onMultiChange?.(field.key, next)}
              onCreateOption={(next) => {
                setAdded((previous) => ({ ...previous, [field.key]: [...(previous[field.key] ?? []), next] }));
                const already = selected.some((value) => value.toLowerCase() === next.toLowerCase());
                if (!already) onMultiChange?.(field.key, [...selected, next]);
              }}
            />
          );
        }
        return (
          <SearchableSpecSelect
            key={field.key}
            label={field.label}
            icon={FIELD_ICONS[field.key] ?? Tag}
            placeholder={field.placeholder}
            value={current}
            options={withCurrent(field.options, added[field.key] ?? [], current)}
            onSelect={(next) => onChange({ ...specs, [field.key]: next })}
            onCreateOption={(next) => {
              setAdded((previous) => ({ ...previous, [field.key]: [...(previous[field.key] ?? []), next] }));
              onChange({ ...specs, [field.key]: next });
            }}
          />
        );
      })}
    </div>
  );
}
