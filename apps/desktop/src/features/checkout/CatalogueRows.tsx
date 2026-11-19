import { formatMoney, type ProductUpsert } from "@ai-pos/shared-types";
import { Building2, Info, Package, Plus } from "lucide-react";
import type { ReactNode } from "react";
import { stockPill } from "../../components/shell/tokens";
import { stockTone } from "./catalogCard";
import { blocksCatalogueAdd, catalogueIdentity, catalogueStockLabel, catalogueTracked } from "./cataloguePresentation";
import { ProductPhoto } from "./ProductPhoto";
import type { Hit } from "./useProductSearch";
import type { ModelGroup } from "./variants";

function stockClass(product: ProductUpsert): string {
  const tone = stockTone({ tracked: catalogueTracked(product), available: product.stock_quantity });
  const pill = tone === "out" ? "out" : tone === "low" ? "low" : "in";
  return stockPill[pill];
}

function Price({ product, currency, amount }: { product: ProductUpsert; currency: string; amount: number }) {
  return (
    <span className="whitespace-nowrap text-sm font-bold tabular-nums text-zinc-900 dark:text-white">
      {formatMoney(amount, currency)}
      {product.sold_by_weight ? <span className="text-xs font-semibold text-zinc-500 dark:text-white/50"> /kg</span> : null}
    </span>
  );
}

function BranchButton({ name, out, onCheckBranches }: { name: string; out: boolean; onCheckBranches: () => void }) {
  const label = out ? `Find ${name} in other branches` : `Branch stock for ${name}`;
  return (
    <button
      type="button"
      aria-label={label}
      title={out ? "Find in other branches" : "Branch stock"}
      onClick={onCheckBranches}
      className={`inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/70 ${
        out
          ? "border-primary-200 text-primary"
          : "border-zinc-200 text-zinc-500 hover:text-zinc-900 dark:border-zinc-700 dark:text-zinc-300"
      }`}
    >
      <Building2 size={16} aria-hidden="true" />
    </button>
  );
}

function InfoButton({ name, onInfo }: { name: string; onInfo: () => void }) {
  return (
    <button
      type="button"
      aria-label={`Details for ${name}`}
      title="Product details"
      onClick={(event) => {
        event.stopPropagation();
        onInfo();
      }}
      className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-zinc-200 bg-zinc-50 text-zinc-600 hover:border-primary hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/70 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
    >
      <Info size={16} aria-hidden="true" />
    </button>
  );
}

function Thumb({ src, dimmed }: { src?: string | null; dimmed: boolean }) {
  return (
    <span className={`relative block h-12 w-12 shrink-0 overflow-hidden rounded-lg bg-zinc-100 dark:bg-zinc-900 ${dimmed ? "opacity-60" : ""}`}>
      <span className="absolute inset-0 flex items-center justify-center text-zinc-400">
        <Package size={18} aria-hidden="true" />
      </span>
      <ProductPhoto src={src} className="absolute inset-0 h-full w-full object-cover" />
    </span>
  );
}

export function ProductListRow({
  hit,
  currency,
  amount,
  menu,
  disabled,
  onSelect,
  onInfo,
  onCheckBranches,
}: {
  hit: Hit;
  currency: string;
  amount: number;
  menu: boolean;
  disabled: boolean;
  onSelect: () => void;
  onInfo: () => void;
  onCheckBranches?: () => void;
}) {
  const product = hit.product;
  const unavailable = blocksCatalogueAdd(product);
  const stock = catalogueStockLabel(product, menu);
  const identity = catalogueIdentity(product);
  const selected = hit.match === "identifier" || hit.match === "exact";
  const frame = selected
    ? "border-primary bg-primary/5"
    : "border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900/40";
  return (
    <li className={`grid min-h-16 min-w-0 grid-cols-1 items-center gap-2 rounded-xl border px-2 py-2 sm:grid-cols-[minmax(0,1.6fr)_auto_auto_auto] sm:gap-3 sm:px-3 ${frame}`}>
      <div className="flex min-w-0 items-center gap-3">
        <Thumb src={product.thumb_url ?? product.image_url} dimmed={unavailable} />
        <div className="min-w-0">
          <p className={`truncate text-sm font-semibold ${unavailable ? "text-zinc-500 dark:text-white/50" : "text-zinc-900 dark:text-white"}`} title={product.name}>
            {product.name}
          </p>
          {identity ? <p className="truncate text-xs text-zinc-500 dark:text-white/50">{identity}</p> : null}
        </div>
      </div>
      <Price product={product} currency={currency} amount={amount} />
      {stock ? (
        <span title={stock} className={`inline-flex h-7 max-w-full items-center truncate rounded-full px-2 text-[11px] font-semibold tabular-nums ${stockClass(product)}`}>
          {stock}
        </span>
      ) : (
        <span />
      )}
      <span className="flex items-center justify-end gap-1">
        {onCheckBranches ? <BranchButton name={product.name} out={unavailable} onCheckBranches={onCheckBranches} /> : null}
        <InfoButton name={product.name} onInfo={onInfo} />
        {unavailable ? null : (
          <button
            type="button"
            disabled={disabled}
            aria-label={`Add ${product.name}`}
            onClick={onSelect}
            className="inline-flex h-11 min-w-11 items-center justify-center gap-1 rounded-full bg-primary-500 px-3 text-sm font-semibold text-white hover:bg-primary-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/70 disabled:opacity-50"
          >
            <Plus size={16} aria-hidden="true" />
            <span className="hidden sm:inline">Add</span>
          </button>
        )}
      </span>
    </li>
  );
}

export function CompactProductCard({
  hit,
  currency,
  amount,
  menu,
  disabled,
  onSelect,
  onInfo,
  onCheckBranches,
}: {
  hit: Hit;
  currency: string;
  amount: number;
  menu: boolean;
  disabled: boolean;
  onSelect: () => void;
  onInfo: () => void;
  onCheckBranches?: () => void;
}) {
  const product = hit.product;
  const unavailable = blocksCatalogueAdd(product);
  const stock = catalogueStockLabel(product, menu);
  const selected = hit.match === "identifier" || hit.match === "exact";
  const frame = selected
    ? "border-primary bg-primary/5"
    : "border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900/40";
  return (
    <li className={`flex min-h-[4.5rem] min-w-0 flex-col rounded-xl border p-2 ${frame} ${unavailable ? "opacity-70" : ""}`}>
      <div className="flex min-w-0 items-start gap-2">
        <button
          type="button"
          disabled={disabled}
          onClick={onSelect}
          className="flex min-w-0 flex-1 items-start gap-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/70 disabled:opacity-50"
        >
          <Thumb src={product.thumb_url ?? product.image_url} dimmed={unavailable} />
          <span className="line-clamp-2 min-w-0 flex-1 text-sm font-semibold leading-5 text-zinc-900 dark:text-white" title={product.name}>
            {product.name}
          </span>
        </button>
        <InfoButton name={product.name} onInfo={onInfo} />
      </div>
      {onCheckBranches ? (
        <button
          type="button"
          onClick={onCheckBranches}
          className={`mt-1 inline-flex h-10 items-center gap-1 self-start rounded-full px-2 text-xs font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/70 ${
            unavailable ? "text-primary" : "text-zinc-500 dark:text-white/50"
          }`}
        >
          <Building2 size={14} aria-hidden="true" />
          {unavailable ? "Find in other branches" : "Branch stock"}
        </button>
      ) : null}
      <button
        type="button"
        disabled={disabled}
        onClick={onSelect}
        className="mt-1 flex min-w-0 items-center justify-between gap-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/70 disabled:opacity-50"
      >
        <Price product={product} currency={currency} amount={amount} />
        {stock ? <span className="truncate text-[11px] font-semibold text-zinc-500 dark:text-white/50">{stock}</span> : null}
      </button>
    </li>
  );
}

function ModelActions({
  name,
  onOpen,
  onInfo,
  disabled,
  label,
}: {
  name: string;
  onOpen: () => void;
  onInfo: () => void;
  disabled: boolean;
  label: string;
}) {
  return (
    <span className="flex items-center justify-end gap-1">
      <InfoButton name={name} onInfo={onInfo} />
      <button
        type="button"
        disabled={disabled}
        onClick={onOpen}
        className="inline-flex h-11 items-center justify-center rounded-full border border-primary-500 px-3 text-sm font-semibold text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/70 disabled:opacity-50"
      >
        {label}
      </button>
    </span>
  );
}

export function ModelListRow({
  group,
  currency,
  disabled,
  onOpen,
  onInfo,
}: {
  group: ModelGroup;
  currency: string;
  disabled: boolean;
  onOpen: () => void;
  onInfo: () => void;
}) {
  const first = group.variants[0];
  const price =
    group.fromCents === group.toCents
      ? formatMoney(group.fromCents, currency)
      : `${formatMoney(group.fromCents, currency)} – ${formatMoney(group.toCents, currency)}`;
  const stock = group.stock <= 0 ? "Out of stock" : "In stock";
  return (
    <li className="grid min-h-16 min-w-0 grid-cols-1 items-center gap-2 rounded-xl border border-zinc-200 bg-white px-2 py-2 dark:border-zinc-800 dark:bg-zinc-900/40 sm:grid-cols-[minmax(0,1.6fr)_auto_auto_auto] sm:gap-3 sm:px-3">
      <div className="flex min-w-0 items-center gap-3">
        <Thumb src={group.variants.find((variant) => variant.thumb_url)?.thumb_url} dimmed={group.stock <= 0} />
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-zinc-900 dark:text-white">{group.name}</p>
          <p className="truncate text-xs text-zinc-500 dark:text-white/50">
            {[first?.category, "Sizes and colours"].filter(Boolean).join(" · ")}
          </p>
        </div>
      </div>
      <span className="whitespace-nowrap text-sm font-bold tabular-nums">{price}</span>
      <span className={`inline-flex h-7 items-center rounded-full px-2 text-[11px] font-semibold ${stockPill[group.stock <= 0 ? "out" : "in"]}`}>{stock}</span>
      <ModelActions name={group.name} onOpen={onOpen} onInfo={onInfo} disabled={disabled} label="Choose" />
    </li>
  );
}

export function ModelCompactCard({
  group,
  currency,
  disabled,
  onOpen,
  onInfo,
}: {
  group: ModelGroup;
  currency: string;
  disabled: boolean;
  onOpen: () => void;
  onInfo: () => void;
}): ReactNode {
  const price =
    group.fromCents === group.toCents
      ? formatMoney(group.fromCents, currency)
      : `${formatMoney(group.fromCents, currency)} – ${formatMoney(group.toCents, currency)}`;
  return (
    <li className="flex min-h-[4.5rem] min-w-0 flex-col rounded-xl border border-zinc-200 bg-white p-2 dark:border-zinc-800 dark:bg-zinc-900/40">
      <div className="flex min-w-0 items-start gap-2">
        <button
          type="button"
          disabled={disabled}
          onClick={onOpen}
          className="line-clamp-2 min-w-0 flex-1 text-left text-sm font-semibold leading-5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/70"
        >
          {group.name}
        </button>
        <InfoButton name={group.name} onInfo={onInfo} />
      </div>
      <button
        type="button"
        disabled={disabled}
        onClick={onOpen}
        className="mt-1 flex min-w-0 items-center justify-between gap-2 text-left text-sm font-bold tabular-nums focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/70"
      >
        <span className="truncate">{price}</span>
        <span className="shrink-0 text-[11px] font-semibold text-zinc-500">{group.stock <= 0 ? "Out of stock" : "In stock"}</span>
      </button>
    </li>
  );
}
