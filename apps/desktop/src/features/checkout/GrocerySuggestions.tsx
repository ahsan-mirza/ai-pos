import { formatMoney, type GuestSuggestion, type GuestSuggestions } from "@ai-pos/shared-types";
import { Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { retailCall } from "../../lib/retailClient";

/** Products bought with this basket. A failed or empty reply leaves the sale as it was. */
export function GrocerySuggestions({
  storeId,
  productIds,
  disabled = false,
  onAdd,
}: {
  storeId: string;
  productIds: string[];
  disabled?: boolean;
  onAdd: (suggestion: GuestSuggestion) => void;
}) {
  const [items, setItems] = useState<GuestSuggestion[]>([]);
  const onCheck = [...new Set(productIds)].sort().join(",");

  useEffect(() => {
    if (!onCheck) {
      setItems([]);
      return;
    }
    let cancelled = false;
    const params = new URLSearchParams({ store_id: storeId });
    for (const id of onCheck.split(",")) params.append("product_id", id);
    void retailCall<GuestSuggestions>("GET", `/api/v1/grocery/suggestions?${params.toString()}`)
      .then((report) => {
        if (!cancelled) setItems(report.suggestions);
      })
      .catch(() => {
        if (!cancelled) setItems([]);
      });
    return () => {
      cancelled = true;
    };
  }, [storeId, onCheck]);

  if (items.length === 0) return null;
  return (
    <div className="space-y-1.5">
      <p className="flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-500 dark:text-white/50">
        <Sparkles size={12} aria-hidden="true" className="text-primary" /> Often bought together
      </p>
      <div className="flex gap-1.5 overflow-x-auto">
        {items.map((item) => (
          <button
            key={item.product_id}
            type="button"
            disabled={disabled}
            onClick={() => onAdd(item)}
            className="min-w-[9.5rem] flex-1 rounded-2xl border border-zinc-200 px-3 py-2.5 text-left hover:border-primary disabled:opacity-50 dark:border-white/10"
          >
            <span className="block truncate text-xs font-semibold">{item.name}</span>
            <span className="block truncate text-[11px] text-zinc-500 dark:text-white/50">{item.pitch}</span>
            <span className="mt-0.5 block text-[11px] font-semibold tabular-nums text-primary">
              {formatMoney(item.price_cents, item.currency)}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
