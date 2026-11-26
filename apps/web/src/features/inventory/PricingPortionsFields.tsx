import type { PortionFieldError, PriceDraft } from "@ai-pos/shared-types";
import { ChevronDown, ChevronUp, Plus, Trash2 } from "lucide-react";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { movePortion, type PortionMode } from "./portionPricing";

const control =
  "h-11 w-full rounded-xl border border-line bg-white px-3 text-sm text-charcoal focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-100";

/** Single price or named portions for one restaurant or cafe menu item. */
export function PricingPortionsFields({
  mode,
  rows,
  currency,
  errors,
  onMode,
  onRows,
}: {
  mode: PortionMode;
  rows: PriceDraft[];
  currency: string;
  errors: readonly PortionFieldError[];
  onMode: (mode: PortionMode) => void;
  onRows: (rows: PriceDraft[]) => void;
}) {
  const message = (key: string) => errors.find((issue) => issue.key === key)?.message;
  const listErrors = errors.filter((issue) => issue.key === "list");

  function patch(index: number, part: Partial<PriceDraft>) {
    onRows(rows.map((row, at) => (at === index ? { ...row, ...part } : row)));
  }

  return (
    <fieldset className="md:col-span-2 rounded-2xl border border-line p-4">
      <legend className="px-1 text-sm font-medium">Pricing & Portions</legend>
      <p className="text-xs text-charcoal/60">
        One selling price, or several named portions of this same item. Small, Medium and Full Plate stay on this product. Modifiers stay separate.
      </p>
      <div className="mt-3">
        <SegmentedControl
          label="Pricing mode"
          value={mode}
          options={[
            { value: "single", label: "Single price" },
            { value: "portions", label: "Multiple portions" },
          ]}
          onChange={onMode}
        />
      </div>
      {mode === "single" ? (
        <p className="mt-3 text-xs text-charcoal/60">The price above is the selling price. The register adds this item without asking for a portion.</p>
      ) : (
        <div className="mt-3 space-y-2">
          <p className="text-xs text-charcoal/60">
            The register shows From and the lowest active price, then asks the cashier to choose. Removing a portion that was already sold turns it off. The sale keeps the price that was charged.
          </p>
          {listErrors.map((issue) => (
            <p key={issue.message} role="alert" className="text-xs font-medium text-danger">
              {issue.message}
            </p>
          ))}
          {rows.map((row, index) => {
            const nameError = message(`${index}.name`);
            const priceError = message(`${index}.price`);
            return (
              <div key={row.id ?? `portion-${index}`} className="grid grid-cols-1 items-start gap-2 sm:grid-cols-[minmax(0,1fr)_8rem_auto]">
                <div>
                  <input
                    className={`${control} ${nameError ? "border-danger" : ""}`}
                    aria-label={`Portion ${index + 1} name`}
                    aria-invalid={nameError ? true : undefined}
                    placeholder="Small Plate"
                    value={row.name}
                    onChange={(event) => patch(index, { name: event.target.value })}
                  />
                  {nameError ? (
                    <span role="alert" className="mt-1 block text-xs font-medium text-danger">
                      {nameError}
                    </span>
                  ) : null}
                </div>
                <div>
                  <input
                    className={`${control} ${priceError ? "border-danger" : ""}`}
                    aria-label={`Portion ${index + 1} price`}
                    aria-invalid={priceError ? true : undefined}
                    inputMode="decimal"
                    placeholder="0.00"
                    value={row.price}
                    onChange={(event) => patch(index, { price: event.target.value })}
                  />
                  <span className="mt-1 block text-[11px] text-charcoal/50">{currency}</span>
                  {priceError ? (
                    <span role="alert" className="mt-1 block text-xs font-medium text-danger">
                      {priceError}
                    </span>
                  ) : null}
                </div>
                <div className="flex items-center gap-1">
                  <label className="flex h-11 items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      aria-label={`Portion ${index + 1} active`}
                      checked={row.active !== false}
                      onChange={(event) => patch(index, { active: event.target.checked })}
                    />
                    Active
                  </label>
                  <button
                    type="button"
                    className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-charcoal/70 hover:bg-surface disabled:opacity-40"
                    aria-label={`Move portion ${index + 1} up`}
                    disabled={index === 0}
                    onClick={() => onRows(movePortion(rows, index, -1))}
                  >
                    <ChevronUp size={16} aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-charcoal/70 hover:bg-surface disabled:opacity-40"
                    aria-label={`Move portion ${index + 1} down`}
                    disabled={index === rows.length - 1}
                    onClick={() => onRows(movePortion(rows, index, 1))}
                  >
                    <ChevronDown size={16} aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-charcoal/70 hover:bg-red-50 hover:text-red-700"
                    aria-label={`Remove portion ${index + 1}`}
                    onClick={() => onRows(rows.filter((_, at) => at !== index))}
                  >
                    <Trash2 size={16} aria-hidden="true" />
                  </button>
                </div>
              </div>
            );
          })}
          <button
            type="button"
            className="inline-flex h-11 items-center gap-2 rounded-xl border border-line px-4 text-sm font-semibold"
            onClick={() => onRows([...rows, { name: "", price: "", active: true }])}
          >
            <Plus size={16} aria-hidden="true" />
            Add price option
          </button>
        </div>
      )}
    </fieldset>
  );
}
