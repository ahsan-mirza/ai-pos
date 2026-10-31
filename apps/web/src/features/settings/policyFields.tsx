import type { PolicyChoice } from "@ai-pos/shared-types";
import { actionHoverClass } from "@ai-pos/ui";
import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";

/** A stable key for a label the owner typed: lower snake case, starting with a letter, as the API requires. */
export function keyOf(label: string, taken: Set<string>): string {
  const base = `r_${label.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "")}`.slice(0, 28) || "r_reason";
  let key = /^[a-z]/.test(base) ? base : `r_${base}`;
  let suffix = 2;
  while (taken.has(key)) key = `${base.slice(0, 26)}_${suffix++}`;
  return key;
}

export const percent = (bps: number) => String(bps / 100);

export const toBps = (value: string, max: number): number | null => {
  const trimmed = value.trim();
  if (!/^\d+(\.\d{1,2})?$/.test(trimmed)) return null;
  const bps = Math.round(Number(trimmed) * 100);
  return bps <= max ? bps : null;
};

export const SERIAL_STATUS = [
  { value: "in_stock", label: "Back to stock" },
  { value: "quarantine", label: "Quarantine" },
  { value: "repair", label: "Send to repair" },
] as const;

export function ChoiceList({
  title,
  items,
  locked,
  onChange,
}: {
  title: string;
  items: PolicyChoice[];
  locked: (key: string) => boolean;
  onChange: (items: PolicyChoice[]) => void;
}) {
  const [draft, setDraft] = useState("");
  const add = () => {
    const label = draft.trim();
    if (!label) return;
    onChange([...items, { key: keyOf(label, new Set(items.map((item) => item.key))), label }]);
    setDraft("");
  };
  return (
    <div>
      <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-charcoal/50">{title}</p>
      <ul className="space-y-2">
        {items.map((item, index) => (
          <li key={item.key} className="flex items-center gap-2">
            <input
              aria-label={`${title} ${index + 1}`}
              value={item.label}
              maxLength={60}
              onChange={(event) =>
                onChange(items.map((row, at) => (at === index ? { ...row, label: event.target.value } : row)))
              }
              className="w-full rounded-xl bg-surface px-3 py-2 text-sm focus:bg-white focus:outline-none focus:ring-1 focus:ring-accent"
            />
            <button
              type="button"
              aria-label={`Remove ${item.label}`}
              disabled={items.length <= 1 || locked(item.key)}
              onClick={() => onChange(items.filter((_, at) => at !== index))}
              className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-charcoal/50 disabled:opacity-30 ${actionHoverClass("danger")}`}
            >
              <Trash2 size={15} aria-hidden="true" />
            </button>
          </li>
        ))}
      </ul>
      <div className="mt-2 flex gap-2">
        <input
          aria-label={`New ${title.toLowerCase()}`}
          placeholder="Add another…"
          value={draft}
          maxLength={60}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              add();
            }
          }}
          className="w-full rounded-xl border border-dashed border-line px-3 py-2 text-sm focus:border-accent focus:outline-none"
        />
        <button
          type="button"
          aria-label={`Add ${title.toLowerCase()}`}
          disabled={!draft.trim() || items.length >= 20}
          onClick={add}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-charcoal text-white disabled:opacity-30"
        >
          <Plus size={15} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
