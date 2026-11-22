import { Grid3x3, LayoutGrid, List } from "lucide-react";
import type { KeyboardEvent } from "react";
import { CATALOGUE_VIEWS, type CatalogueView } from "./cataloguePreference";

const OPTIONS: { id: CatalogueView; label: string; icon: typeof LayoutGrid }[] = [
  { id: "grid", label: "Grid view", icon: LayoutGrid },
  { id: "list", label: "List view", icon: List },
  { id: "compact", label: "Compact view", icon: Grid3x3 },
];

/**
 * Catalogue layout switch. It does not listen on the window, so barcode wedges and F2
 * keep going to the search field.
 */
export function CatalogueViewToggle({ value, onChange }: { value: CatalogueView; onChange: (view: CatalogueView) => void }) {
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    const target = event.target;
    if (!(target instanceof HTMLElement) || target.tagName !== "BUTTON") return;
    event.preventDefault();
    const index = CATALOGUE_VIEWS.indexOf(value);
    const delta = event.key === "ArrowRight" ? 1 : -1;
    const next = CATALOGUE_VIEWS[(index + delta + CATALOGUE_VIEWS.length) % CATALOGUE_VIEWS.length] ?? "grid";
    onChange(next);
  };

  return (
    <div
      role="radiogroup"
      aria-label="Product catalogue view"
      onKeyDown={onKeyDown}
      className="inline-flex h-14 shrink-0 items-center gap-1 rounded-xl border border-zinc-200 bg-white p-1 dark:border-zinc-700 dark:bg-zinc-900"
    >
      {OPTIONS.map((option) => {
        const selected = value === option.id;
        const Icon = option.icon;
        return (
          <button
            key={option.id}
            type="button"
            role="radio"
            aria-checked={selected}
            aria-label={option.label}
            title={option.label}
            onClick={() => onChange(option.id)}
            className={`inline-flex h-full w-11 items-center justify-center rounded-lg border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/70 ${
              selected
                ? "border-primary-500 bg-primary-500 text-white"
                : "border-transparent text-zinc-700 hover:border-zinc-300 hover:bg-zinc-50 dark:text-zinc-200 dark:hover:border-zinc-600 dark:hover:bg-zinc-800"
            }`}
          >
            <Icon size={18} aria-hidden="true" />
          </button>
        );
      })}
    </div>
  );
}
