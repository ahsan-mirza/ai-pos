import { formatMoney, type GuestSuggestion } from "@ai-pos/shared-types";
import { Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { ordersApi } from "./ordersClient";

export function suggestsForGuests(profile: string): boolean {
  return profile === "restaurant" || profile === "cafe";
}

/** Dishes for this guest. A failed or empty reply leaves the check as it was. */
export function GuestSuggestions({
  storeId,
  customerId,
  productIds,
  disabled = false,
  onAdd,
}: {
  storeId: string;
  customerId: string | null;
  productIds: string[];
  disabled?: boolean;
  onAdd: (suggestion: GuestSuggestion) => void;
}) {
  const [items, setItems] = useState<GuestSuggestion[]>([]);
  const onCheck = [...new Set(productIds)].sort().join(",");

  useEffect(() => {
    let cancelled = false;
    setItems([]);
    void ordersApi
      .suggestions(storeId, customerId, onCheck ? onCheck.split(",") : [])
      .then((report) => {
        if (!cancelled) setItems(report.suggestions);
      })
      .catch(() => {
        if (!cancelled) setItems([]);
      });
    return () => {
      cancelled = true;
    };
  }, [storeId, customerId, onCheck]);

  if (items.length === 0) return null;
  return (
    <div className="space-y-1.5">
      <p className="flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-500 dark:text-white/50">
        <Sparkles size={12} aria-hidden="true" className="text-primary" /> Suggest
      </p>
      <div className="flex gap-1.5 overflow-x-auto">
        {items.map((item) => (
          <button
            key={`${item.kind}-${item.product_id}`}
            type="button"
            disabled={disabled}
            onClick={() => onAdd(item)}
            className="min-w-[9.5rem] max-w-[14rem] shrink-0 rounded-2xl border border-zinc-200 px-2.5 py-2 text-left hover:border-primary disabled:opacity-50 dark:border-white/10"
          >
            <span className="flex items-center gap-1 truncate text-xs font-semibold">
              <Sparkles size={12} aria-hidden="true" className="shrink-0 text-primary" />
              <span className="truncate">{item.name}</span>
            </span>
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
