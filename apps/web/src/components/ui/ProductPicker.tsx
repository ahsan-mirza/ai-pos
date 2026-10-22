import type { ProductSearchHit } from "@ai-pos/shared-types";
import { useEffect, useState } from "react";
import { apiGet } from "../../lib/api";
import { TextField } from "./Field";

/** Search-as-you-type product finder (name, SKU, barcode, IMEI) that hands back the picked catalogue row. */
export function ProductPicker({
  onPick,
  label = "Add a product",
}: {
  onPick: (hit: ProductSearchHit) => void;
  label?: string;
}) {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<ProductSearchHit[]>([]);

  useEffect(() => {
    const term = query.trim();
    if (term.length < 2) {
      setHits([]);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void apiGet<ProductSearchHit[]>(`/api/v1/products/search?${new URLSearchParams({ q: term, limit: "8" }).toString()}`)
        .then((found) => {
          if (!cancelled) setHits(found);
        })
        .catch(() => undefined);
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query]);

  return (
    <div className="relative">
      <TextField label={label} value={query} placeholder="Name, SKU or barcode" onChange={(event) => setQuery(event.target.value)} />
      {hits.length ? (
        <ul className="absolute z-10 mt-1 max-h-64 w-full overflow-y-auto rounded-2xl border border-line bg-white py-1 shadow-lg">
          {hits.map((hit) => (
            <li key={hit.product.id}>
              <button
                type="button"
                onClick={() => {
                  onPick(hit);
                  setQuery("");
                  setHits([]);
                }}
                className="flex w-full items-center justify-between gap-3 px-4 py-2 text-left text-sm hover:bg-surface"
              >
                <span>
                  <span className="block font-medium">{hit.product.name}</span>
                  <span className="block font-mono text-xs text-charcoal/50">{hit.product.sku}</span>
                </span>
                <span className="text-xs tabular-nums text-charcoal/60">{hit.product.stock_quantity} in stock</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
