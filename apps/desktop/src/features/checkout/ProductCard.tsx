import { daysUntil, formatMoney, formatWeight, type ProductUpsert } from "@ai-pos/shared-types";
import { Building2, Scale, ScanLine } from "lucide-react";
import { stockPill } from "../../components/shell/tokens";
import { ProductPhoto } from "./ProductPhoto";
import type { Hit } from "./useProductSearch";

export interface TierPreview {
  base: number;
  label: string;
  best: string | null;
}

interface ProductCardProps {
  hit: Hit;
  preview: TierPreview | null;
  currency: string;
  disabled: boolean;
  onSelect: (product: ProductUpsert) => void;
  onCheckBranches: (product: ProductUpsert) => void;
}

function StockBadge({ product }: { product: ProductUpsert }) {
  if (product.has_recipe) {
    return <span className={`shrink-0 whitespace-nowrap rounded-full px-2.5 py-1 text-[11px] font-semibold ${stockPill.in}`}>Made to order</span>;
  }
  const out = product.stock_quantity <= 0;
  const amount = product.sold_by_weight ? formatWeight(product.stock_quantity) : `${product.stock_quantity}${product.is_serialized ? " units" : ""}`;
  return (
    <span
      className={`shrink-0 whitespace-nowrap rounded-full px-2.5 py-1 text-[11px] font-semibold tabular-nums ${stockPill[out ? "out" : "in"]}`}
    >
      {out ? "Out of stock" : `In Stock · ${amount}`}
    </span>
  );
}

/** Soonest batch expiry at this branch, shown inside two weeks. */
function ExpiryChip({ date }: { date: string }) {
  const days = daysUntil(date);
  if (days > 14) return null;
  const label = days < 0 ? "Expired" : days === 0 ? "Exp today" : `Exp ${days}d`;
  return (
    <span
      title={`Soonest batch expires ${date}`}
      className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${
        days <= 3 ? "bg-primary text-white" : "bg-amber-500/15 text-amber-700 dark:text-amber-300"
      }`}
    >
      {label}
    </span>
  );
}

export function ProductCard({ hit, preview, currency, disabled, onSelect, onCheckBranches }: ProductCardProps) {
  const { product, match, serial_status: serialStatus } = hit;
  const highlighted = match === "identifier" || match === "exact";
  const out = product.stock_quantity <= 0 && !product.has_recipe;

  return (
    <li
      className={`group flex flex-col overflow-hidden rounded-2xl border bg-white dark:bg-zinc-800/40 transition-colors ${
        highlighted ? "border-primary shadow-lg shadow-primary/10" : "border-zinc-200 dark:border-zinc-800 hover:border-zinc-300 dark:hover:border-zinc-700"
      }`}
    >
      <button
        type="button"
        disabled={disabled}
        onClick={() => onSelect(product)}
        className="flex flex-1 flex-col p-4 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary/70 active:scale-[0.99] disabled:opacity-50"
      >
        <ProductPhoto
          src={product.thumb_url}
          className={`-mx-4 -mt-4 mb-3 aspect-[4/3] w-[calc(100%+2rem)] max-w-none bg-zinc-100 object-cover dark:bg-white/5 ${out ? "opacity-60" : ""}`}
        />
        <span className="flex min-h-6 items-center justify-between gap-2">
          <span className="truncate text-[11px] font-semibold uppercase tracking-[0.12em] text-zinc-500 dark:text-white/40">
            {product.season ? `${product.category ?? "Uncategorized"} · ${product.season}` : (product.category ?? "Uncategorized")}
          </span>
          {match === "identifier" ? (
            <span className="shrink-0 rounded-full bg-primary px-2 py-0.5 text-[10px] font-semibold uppercase text-white">
              IMEI {serialStatus === "in_stock" ? "match" : (serialStatus ?? "match")}
            </span>
          ) : product.is_serialized ? (
            <ScanLine size={14} aria-label="Serialized" className="shrink-0 text-zinc-500 dark:text-white/40" />
          ) : product.nearest_expiry ? (
            <ExpiryChip date={product.nearest_expiry} />
          ) : product.sold_by_weight ? (
            <Scale size={14} aria-label="Sold by weight" className="shrink-0 text-zinc-500 dark:text-white/40" />
          ) : null}
        </span>
        <span
          title={product.name}
          className={`mt-1.5 line-clamp-2 text-sm font-semibold leading-tight ${out ? "text-zinc-600 dark:text-white/60" : "text-zinc-900 dark:text-white"}`}
        >
          {product.name}
        </span>
        <span className="mt-1 truncate font-mono text-[11px] text-zinc-500 dark:text-white/40">
          {[product.sku, product.model_number].filter(Boolean).join(" · ")}
        </span>

        <span className="mt-auto flex flex-wrap items-center justify-between gap-x-2 gap-y-1.5 pt-3">
          <span className="min-w-0 max-w-full">
            {preview ? (
              <>
                <span className="block truncate text-xs tabular-nums text-zinc-500 dark:text-white/40 line-through">
                  {formatMoney(product.price_cents, currency)}
                </span>
                <span className="block truncate text-base font-bold tabular-nums text-primary">
                  {formatMoney(preview.base, currency)}
                </span>
              </>
            ) : product.compare_at_cents != null && product.compare_at_cents > product.price_cents ? (
              <>
                <span className="block truncate text-xs tabular-nums text-zinc-500 line-through dark:text-white/40">
                  {formatMoney(product.compare_at_cents, currency)}
                </span>
                <span className="block truncate text-base font-bold tabular-nums text-primary">
                  {formatMoney(product.price_cents, currency)}
                </span>
              </>
            ) : (
              <span className="block truncate text-base font-bold tabular-nums text-zinc-900 dark:text-white">
                {formatMoney(product.price_cents, currency)}
                {product.sold_by_weight ? <span className="text-xs font-semibold text-zinc-500 dark:text-white/50"> /kg</span> : null}
              </span>
            )}
          </span>
          <StockBadge product={product} />
        </span>
        {preview ? (
          <span className="mt-1 truncate text-[11px] text-zinc-500 dark:text-white/50">
            {preview.label}
            {preview.best ? ` · bulk ${preview.best}` : ""}
          </span>
        ) : null}
      </button>

      <button
        type="button"
        onClick={() => onCheckBranches(product)}
        className={`flex h-11 items-center justify-center gap-1.5 border-t border-zinc-200 dark:border-zinc-800 text-xs font-semibold transition-colors hover:bg-zinc-100 dark:hover:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary/70 ${
          out ? "text-primary" : "text-zinc-500 dark:text-white/50 hover:text-zinc-900 dark:hover:text-white"
        }`}
      >
        <Building2 size={14} aria-hidden="true" />
        {out ? "Find in other branches" : "Branch stock"}
      </button>
    </li>
  );
}
