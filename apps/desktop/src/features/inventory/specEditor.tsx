import { specKey, type SpecSchema } from "@ai-pos/shared-types";
import { SearchableMultiSpecSelect, SearchableSpecSelect } from "@ai-pos/ui";
import { useEffect, useState } from "react";
import { control } from "./ui";

function labelFor(key: string): string {
  return key.replace(/_/g, " ").replace(/^\w/, (letter) => letter.toUpperCase());
}

/** Category specifications, or a free name/value list when the category has no template. */
export function SpecEditor({
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
  multiKeys?: readonly string[];
  multiValues?: Record<string, string[]>;
  onMultiChange?: (key: string, values: string[]) => void;
}) {
  const [draftName, setDraftName] = useState("");
  const [draftValue, setDraftValue] = useState("");
  const [added, setAdded] = useState<Record<string, string[]>>({});
  const draft = specKey(draftName);

  useEffect(() => {
    setDraftName("");
    setDraftValue("");
    setAdded({});
  }, [schema.id]);

  if (schema.id === "OTHER") {
    const rows = Object.entries(specs);
    return (
      <div className="space-y-3">
        <p className="text-sm text-zinc-500">Add the details that matter for this item. Each row is a name and a value.</p>
        {rows.map(([key, value]) => (
          <div key={key} className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_1fr_auto]">
            <label className="block text-sm font-medium">
              Attribute
              <input value={labelFor(key)} disabled className={`${control} mt-1.5 disabled:text-zinc-400`} />
            </label>
            <label className="block text-sm font-medium">
              Value
              <input value={value} onChange={(event) => onChange({ ...specs, [key]: event.target.value })} className={`${control} mt-1.5`} />
            </label>
            <button
              type="button"
              className="h-12 self-end rounded-xl border border-zinc-200 px-4 text-sm font-semibold"
              onClick={() => {
                const next = { ...specs };
                delete next[key];
                onChange(next);
              }}
            >
              Remove
            </button>
          </div>
        ))}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_1fr_auto]">
          <label className="block text-sm font-medium">
            Attribute name
            <input value={draftName} placeholder="Attribute name" onChange={(event) => setDraftName(event.target.value)} className={`${control} mt-1.5`} />
          </label>
          <label className="block text-sm font-medium">
            Value
            <input value={draftValue} placeholder="Value" onChange={(event) => setDraftValue(event.target.value)} className={`${control} mt-1.5`} />
          </label>
          <button
            type="button"
            disabled={draft === "" || draftValue.trim() === ""}
            className="h-12 self-end rounded-xl bg-zinc-900 px-4 text-sm font-semibold text-white disabled:opacity-40"
            onClick={() => {
              onChange({ ...specs, [draft]: draftValue.trim() });
              setDraftName("");
              setDraftValue("");
            }}
          >
            Add
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      {schema.fields.map((field) => {
        const options = [...field.options, ...(added[field.key] ?? []), specs[field.key] ?? ""].filter(
          (value, index, all) => value.trim() !== "" && all.findIndex((item) => item.toLowerCase() === value.toLowerCase()) === index,
        );
        if (multiKeys.includes(field.key)) {
          const selected = multiValues[field.key] ?? [];
          return (
            <SearchableMultiSpecSelect
              key={field.key}
              label={field.label}
              placeholder={field.placeholder}
              values={selected}
              options={[...options, ...selected]}
              onChange={(next) => onMultiChange?.(field.key, next)}
              onCreateOption={(next) => {
                setAdded((previous) => ({ ...previous, [field.key]: [...(previous[field.key] ?? []), next] }));
                if (!selected.some((value) => value.toLowerCase() === next.toLowerCase())) onMultiChange?.(field.key, [...selected, next]);
              }}
            />
          );
        }
        return (
          <SearchableSpecSelect
            key={field.key}
            label={field.label}
            placeholder={field.placeholder}
            value={specs[field.key] ?? ""}
            options={options}
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
