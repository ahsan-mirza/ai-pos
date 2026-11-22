import { daysUntil, formatMoney, formatWeight, fromPriceCents, type ProductUpsert } from "@ai-pos/shared-types";
import { CurrencyAmount } from "../../components/CurrencyAmount";
import { useLocale } from "@ai-pos/ui";
import { motion, useReducedMotion } from "framer-motion";
import { Building2, Info, Package, Scale, ScanLine, SlidersHorizontal, UtensilsCrossed } from "lucide-react";
import type { ReactNode } from "react";
import { useRegisterLayout } from "../../components/RegisterLayout";
import { stockPill } from "../../components/shell/tokens";
import { allocationLabel } from "./allocationBalance";
import { cardKind, catalogCardClass, stockTone, stockUnit } from "./catalogCard";
import { useCapabilities } from "../../lib/capabilities";
import { PosIconButton } from "../../components/shell/posControls";
import { ProductPhotoFrame, productImageWellClass } from "./ProductPhoto";
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

const badgeClass =
  "inline-flex h-7 max-w-full shrink-0 items-center gap-1 whitespace-nowrap rounded-full px-2.5 text-[0.6875rem] font-semibold leading-4";

/** Soonest batch expiry at this branch, shown inside two weeks. */
function ExpiryChip({ date }: { date: string }) {
  const days = daysUntil(date);
  if (days > 14) return null;
  const label = days < 0 ? "Expired" : days === 0 ? "Exp today" : `Exp ${days}d`;
  return (
    <span
      title={`Soonest batch expires ${date}`}
      className={`shrink-0 rounded-full px-2 py-0.5 text-[0.625rem] font-semibold uppercase ${
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
  const { t } = useLocale();
  const reduced = useReducedMotion() === true;
  const frame = selected
    ? "border-primary bg-primary/5 shadow-lg shadow-primary/10"
    : "border-zinc-200 bg-white hover:border-zinc-300 dark:border-zinc-800 dark:bg-zinc-800/40 dark:hover:border-zinc-700";
  const selectClass =
    "text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary/70 disabled:opacity-50";
  const titleClass = titleMuted ? "text-zinc-600 dark:text-white/60" : "text-zinc-900 dark:text-white";
  const details = (
    <PosIconButton
      shape="circle"
      size="xs"
      variant="secondary"
      label={`Details for ${title}`}
      title={t("Product details")}
      className={`${showImages ? "absolute end-2 top-2 z-[2]" : "shrink-0"} border border-zinc-200 bg-white/95 text-zinc-500 hover:border-primary hover:text-primary dark:border-zinc-700 dark:bg-zinc-900/95 dark:text-zinc-300`}
      onClick={(event) => {
        event.stopPropagation();
        onInfo?.();
      }}
    >
      <Info className="h-4 w-4" aria-hidden="true" />
    </PosIconButton>
  );
  return (
    <li className={`group flex h-auto min-h-0 w-full min-w-0 flex-col overflow-hidden rounded-xl border transition-colors ${frame} ${disabled ? "opacity-50" : ""}`}>
      {showImages ? (
        <span className={productImageWellClass}>
          <button type="button" disabled={disabled} onClick={onSelect} className={`${selectClass} block h-full w-full overflow-hidden`}>
            <ProductPhotoFrame src={imageSrc} dimmed={imageDimmed} compact={density === "compact"} flush icon={imageIcon} />
          </button>
          {details}
        </span>
      ) : null}
      <span className="flex min-h-0 min-w-0 flex-col gap-1.5 px-3 py-2.5">
        <button type="button" disabled={disabled} onClick={onSelect} className={`${selectClass} flex min-w-0 items-center justify-between gap-2`}>
          <span className="min-w-0 truncate text-[0.6875rem] font-semibold uppercase tracking-[0.12em] text-zinc-500 dark:text-white/40">
            {category}
          </span>
          {marker ? <span className="flex h-5 shrink-0 items-center">{marker}</span> : null}
          {showImages ? null : details}
        </button>
        <button type="button" disabled={disabled} title={title} aria-label={title} onClick={onSelect} className={`${selectClass} ${catalogCardClass.name} ${titleClass}`}>
          {title}
        </button>
        <button type="button" disabled={disabled} onClick={onSelect} className={`${selectClass} ${catalogCardClass.priceRow}`}>
          {badge ? (
            <motion.span
              className="inline-flex max-w-full"
              initial={reduced ? false : { opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: reduced ? 0 : 0.16 }}
            >
              {badge}
            </motion.span>
          ) : null}
          {priceNote ? (
            <span className="whitespace-nowrap text-[0.75rem] tabular-nums leading-4 text-zinc-500 line-through dark:text-white/40">{priceNote}</span>
          ) : null}
          <span className="inline-flex min-w-0 items-baseline whitespace-nowrap">{price}</span>
        </button>
        {footnote ? (
          <span className="block min-w-0 truncate text-[0.6875rem] leading-4 text-zinc-500 dark:text-white/50">{footnote}</span>
        ) : null}
      </span>
      {action}
    </li>
  );
}

export function ProductCard({ hit, preview, currency, disabled, hasModifiers = false, onSelect, onCheckBranches, onInfo }: ProductCardProps) {
  const { t } = useLocale();
  const menu = cardKind(useCapabilities().profile) === "menu";
  const { product, match, serial_status: serialStatus } = hit;
  const from = menu ? fromPriceCents(product.price_options) : null;
  const out = product.stock_quantity <= 0 && !product.has_recipe;
  const strike =
    preview != null
      ? formatMoney(product.price_cents, currency)
      : product.compare_at_cents != null && product.compare_at_cents > product.price_cents
        ? formatMoney(product.compare_at_cents, currency)
        : null;
  const amount = preview ? preview.base : (from ?? product.price_cents);
  const priceClass = preview || strike ? "text-primary" : out ? "text-zinc-600 dark:text-white/60" : "text-zinc-900 dark:text-white";
  const marker =
    match === "identifier" ? (
      <span className="shrink-0 rounded-full bg-primary px-2 py-0.5 text-[0.625rem] font-semibold uppercase text-white">
        IMEI {serialStatus === "in_stock" ? "match" : (serialStatus ?? "match")}
      </span>
    ) : product.is_serialized ? (
      <ScanLine aria-label="Serialized" className="h-3.5 w-3.5 shrink-0 text-zinc-500 dark:text-white/40" />
    ) : product.nearest_expiry ? (
      <ExpiryChip date={product.nearest_expiry} />
    ) : product.sold_by_weight ? (
      <Scale aria-label="Sold by weight" className="h-3.5 w-3.5 shrink-0 text-zinc-500 dark:text-white/40" />
    ) : null;
  const tracked = product.is_stock_tracked !== false && !product.is_service && !product.has_recipe;
  const tone = stockTone({ tracked, available: product.stock_quantity });
  const registerAllocation = allocationLabel(product);
  const stockText =
    tone === "untracked"
      ? "Not tracked"
      : tone === "out"
        ? "Out of stock"
        : product.sold_by_weight
          ? formatWeight(product.stock_quantity)
          : `${product.stock_quantity} ${stockUnit(product)}`;
  const stockCaption = registerAllocation ? `Branch ${stockText}. ${registerAllocation}` : stockText;
  const stockPillTone = tone === "out" ? "out" : tone === "low" ? "low" : "in";
  const badge = menu ? (
    hasModifiers ? (
      <span title={t("Modifiers available")} aria-label={t("Modifiers available")} className={`${badgeClass} bg-primary/10 text-primary ring-1 ring-primary/20`}>
        <SlidersHorizontal className="h-3 w-3" aria-hidden="true" />
        {t("+ Modifiers")}
      </span>
    ) : null
  ) : (
    <span title={stockCaption} aria-label={stockCaption} className={`${badgeClass} tabular-nums ${stockPill[stockPillTone]}`}>
      {stockText}
    </span>
  );

  return (
    <CatalogTile
      imageSrc={product.thumb_url ?? product.image_url}
      imageIcon={menu ? <UtensilsCrossed className="h-8 w-8" aria-hidden="true" /> : <Package className="h-8 w-8" aria-hidden="true" />}
      imageDimmed={out}
      category={product.season ? `${product.category ?? "Uncategorized"} · ${product.season}` : (product.category ?? "Uncategorized")}
      marker={marker}
      title={product.name}
      titleMuted={out}
      priceNote={strike}
      footnote={preview ? `${preview.label}${preview.best ? ` · bulk ${preview.best}` : ""}` : null}
      price={
        <span className={`inline-flex items-end gap-1 ${priceClass}`}>
          {from != null ? <span className="mb-0.5 text-xs font-semibold">From</span> : null}
          <CurrencyAmount cents={amount} currency={currency} size="card" />
          {product.sold_by_weight ? <span className="mb-0.5 text-xs font-semibold text-zinc-500 dark:text-white/50">/kg</span> : null}
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
            className={`flex h-[var(--pos-product-footer-height)] max-h-[var(--pos-product-footer-height)] shrink-0 grow-0 items-center justify-center gap-1.5 border-t border-zinc-200 px-3 text-[0.75rem] font-semibold transition-colors hover:bg-zinc-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary/70 dark:border-zinc-800 dark:hover:bg-white/5 ${
              out ? "text-primary" : "text-zinc-500 hover:text-zinc-900 dark:text-white/50 dark:hover:text-white"
            }`}
          >
            <Building2 className="h-4 w-4" aria-hidden="true" />
            {out ? "Find in other branches" : "Branch stock"}
          </button>
        )
      }
    />
  );
}
