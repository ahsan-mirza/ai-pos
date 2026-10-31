import { daysUntil, formatMoney, formatWeight, type ProductUpsert } from "@ai-pos/shared-types";
import { Building2, Info, Package, Scale, ScanLine, UtensilsCrossed } from "lucide-react";
import type { ReactNode } from "react";
import { useRegisterLayout } from "../../components/RegisterLayout";
import { stockPill } from "../../components/shell/tokens";
import { cardKind, catalogCardClass, stockTone, stockUnit } from "./catalogCard";
import { useCapabilities } from "../../lib/capabilities";
import { ProductPhotoFrame } from "./ProductPhoto";
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
  /** Food registers sell made-to-order dishes: no shelf count and no branch lookup. */
  menuItem?: boolean;
  hasModifiers?: boolean;
  onSelect: (product: ProductUpsert) => void;
  onCheckBranches: (product: ProductUpsert) => void;
  onInfo: (product: ProductUpsert) => void;
}

const badgeClass = "inline-flex h-7 max-w-full items-center truncate rounded-full px-2.5 text-[11px] font-semibold";

/** Soonest batch expiry at this branch, shown inside two weeks. */
function ExpiryChip({ date }: { date: string }) {
  const days = daysUntil(date);
  if (days > 14) return null;
  const label = days < 0 ? "Expired" : days === 0 ? "Exp today" : `Exp ${days}d`;
  return (
    <span
      title={`Soonest batch expires ${date}`}
      className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${
        days <= 3 ? "bg-danger text-white" : "bg-warning/15 text-warning dark:text-warning"
      }`}
    >
      {label}
    </span>
  );
}

export function CatalogTile({
  imageSrc,
  imageIcon,
  imageDimmed = false,
  category,
  marker,
  title,
  price,
  priceNote,
  footnote,
  badge,
  action,
  disabled,
  selected = false,
  titleMuted = false,
  onSelect,
  onInfo,
}: {
  imageSrc?: string | null;
  imageIcon: ReactNode;
  imageDimmed?: boolean;
  category: string;
  marker?: ReactNode;
  title: string;
  price: ReactNode;
  priceNote?: string | null;
  footnote?: string | null;
  badge?: ReactNode;
  /** A separate control under the card. It does not also select the product. */
  action?: ReactNode;
  disabled: boolean;
  selected?: boolean;
  titleMuted?: boolean;
  onSelect: () => void;
  /** Opens details. It is not inside the card button, so it cannot add the product. */
  onInfo?: () => void;
}) {
  const { density, showImages } = useRegisterLayout();
  const frame = selected
    ? "border-primary bg-primary/5 shadow-lg shadow-primary/10"
    : "border-zinc-200 bg-white hover:border-zinc-300 dark:border-zinc-800 dark:bg-zinc-800/40 dark:hover:border-zinc-700";
  const pad = density === "compact" ? "px-2.5 pb-2" : "px-3 pb-2.5";
  const selectClass =
    "text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary/70 disabled:opacity-50";
  const titleClass = titleMuted ? "text-zinc-600 dark:text-white/60" : "text-zinc-900 dark:text-white";
  return (
    <li className={`group flex h-full min-w-0 flex-col overflow-hidden rounded-2xl border transition-colors ${frame} ${disabled ? "opacity-50" : ""}`}>
      {showImages ? (
        <button type="button" disabled={disabled} onClick={onSelect} className={`${selectClass} block w-full`}>
          <ProductPhotoFrame src={imageSrc} dimmed={imageDimmed} compact={density === "compact"} flush icon={imageIcon} />
        </button>
      ) : null}
      <span className={`flex min-h-0 min-w-0 flex-1 flex-col ${pad} ${showImages ? "pt-2" : "pt-2.5"}`}>
        <button type="button" disabled={disabled} onClick={onSelect} className={`${selectClass} flex h-5 min-w-0 items-center justify-between gap-2`}>
          <span className="min-w-0 truncate text-[11px] font-semibold uppercase tracking-[0.12em] text-zinc-500 dark:text-white/40">
            {category}
          </span>
          {marker ? <span className="flex h-5 shrink-0 items-center">{marker}</span> : <span className="h-5 w-4 shrink-0" aria-hidden="true" />}
        </button>
        <span className="mt-1 flex min-h-11 items-start gap-1">
          <button type="button" disabled={disabled} title={title} onClick={onSelect} className={`${selectClass} ${catalogCardClass.name} ${titleClass}`}>
            {title}
          </button>
          <button
            type="button"
            aria-label={`Details for ${title}`}
            onClick={(event) => {
              event.stopPropagation();
              onInfo?.();
            }}
            className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-zinc-200 text-zinc-500 transition-colors hover:border-primary hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 dark:border-zinc-700 dark:text-zinc-300"
          >
            <Info size={16} aria-hidden="true" />
          </button>
        </span>
        <button type="button" disabled={disabled} onClick={onSelect} className={`${selectClass} flex min-h-0 min-w-0 flex-1 flex-col`}>
          <span className={catalogCardClass.footer}>
            <span className="min-w-0 flex-1">
              {priceNote ? (
                <span className="block truncate text-xs tabular-nums leading-4 text-zinc-500 line-through dark:text-white/40">{priceNote}</span>
              ) : null}
              <span className="block min-w-0 truncate text-base font-bold leading-5 tabular-nums">{price}</span>
              {footnote ? (
                <span className="block truncate text-[11px] leading-4 text-zinc-500 dark:text-white/50">{footnote}</span>
              ) : null}
            </span>
            {badge ? <span className="flex h-7 max-w-[50%] min-w-0 items-center justify-end overflow-hidden">{badge}</span> : null}
          </span>
        </button>
      </span>
      {action}
    </li>
  );
}

export function ProductCard({ hit, preview, currency, disabled, hasModifiers = false, onSelect, onCheckBranches, onInfo }: ProductCardProps) {
  const menu = cardKind(useCapabilities().profile) === "menu";
  const { product, match, serial_status: serialStatus } = hit;
  const out = product.stock_quantity <= 0 && !product.has_recipe;
  const strike =
    preview != null
      ? formatMoney(product.price_cents, currency)
      : product.compare_at_cents != null && product.compare_at_cents > product.price_cents
        ? formatMoney(product.compare_at_cents, currency)
        : null;
  const amount = preview ? preview.base : product.price_cents;
  const priceClass = preview || strike ? "text-primary" : out ? "text-zinc-600 dark:text-white/60" : "text-zinc-900 dark:text-white";
  const marker =
    match === "identifier" ? (
      <span className="shrink-0 rounded-full bg-primary px-2 py-0.5 text-[10px] font-semibold uppercase text-white">
        IMEI {serialStatus === "in_stock" ? "match" : (serialStatus ?? "match")}
      </span>
    ) : product.is_serialized ? (
      <ScanLine size={14} aria-label="Serialized" className="shrink-0 text-zinc-500 dark:text-white/40" />
    ) : product.nearest_expiry ? (
      <ExpiryChip date={product.nearest_expiry} />
    ) : product.sold_by_weight ? (
      <Scale size={14} aria-label="Sold by weight" className="shrink-0 text-zinc-500 dark:text-white/40" />
    ) : null;
  const tracked = product.is_stock_tracked !== false && !product.is_service && !product.has_recipe;
  const tone = stockTone({ tracked, available: product.stock_quantity });
  const stockText =
    tone === "untracked"
      ? "Not tracked"
      : tone === "out"
        ? "Out of stock"
        : product.sold_by_weight
          ? formatWeight(product.stock_quantity)
          : `${product.stock_quantity} ${stockUnit(product)}`;
  const stockPillTone = tone === "out" ? "out" : tone === "low" ? "low" : "in";
  const badge = menu ? (
    hasModifiers ? (
      <span title="Modifiers available" className={`${badgeClass} ${stockPill.in}`}>Modifiers available</span>
    ) : null
  ) : (
    <span title={stockText} className={`${badgeClass} tabular-nums ${stockPill[stockPillTone]}`}>{stockText}</span>
  );

  return (
    <CatalogTile
      imageSrc={product.thumb_url ?? product.image_url}
      imageIcon={menu ? <UtensilsCrossed size={28} aria-hidden="true" /> : <Package size={28} aria-hidden="true" />}
      imageDimmed={out}
      category={product.season ? `${product.category ?? "Uncategorized"} · ${product.season}` : (product.category ?? "Uncategorized")}
      marker={marker}
      title={product.name}
      titleMuted={out}
      priceNote={strike}
      footnote={preview ? `${preview.label}${preview.best ? ` · bulk ${preview.best}` : ""}` : null}
      price={
        <span className={priceClass}>
          {formatMoney(amount, currency)}
          {product.sold_by_weight ? <span className="text-xs font-semibold text-zinc-500 dark:text-white/50"> /kg</span> : null}
        </span>
      }
      badge={badge}
      disabled={disabled}
      selected={match === "identifier" || match === "exact"}
      onSelect={() => onSelect(product)}
      onInfo={() => onInfo(product)}
      action={
        menu ? null : (
          <button
            type="button"
            onClick={() => onCheckBranches(product)}
            className={`flex h-12 shrink-0 items-center justify-center gap-1.5 border-t border-zinc-200 text-sm font-semibold transition-colors hover:bg-zinc-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary/70 dark:border-zinc-800 dark:hover:bg-white/5 ${
              out ? "text-primary" : "text-zinc-500 hover:text-zinc-900 dark:text-white/50 dark:hover:text-white"
            }`}
          >
            <Building2 size={14} aria-hidden="true" />
            {out ? "Find in other branches" : "Branch stock"}
          </button>
        )
      }
    />
  );
}
