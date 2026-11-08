import {
  PRICE_TIER_LABELS,
  comboSummary,
  formatMoney,
  formatWeight,
  nextVolumeBreak,
  unitFactor,
  unitLabel,
  variantAttributeLabel,
  type PriceTier,
  type ProductUpsert,
  type UnitType,
} from "@ai-pos/shared-types";
import { useLocale } from "@ai-pos/ui";
import { motion, useAnimation, useReducedMotion } from "framer-motion";
import {
  ChevronDown,
  Copy,
  Minus,
  MoreHorizontal,
  PencilLine,
  Percent,
  Plus,
  Scale,
  ScanLine,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  Trash2,
  Undo2,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useState } from "react";
import { lineGross, manualDiscountCents, unitsFor, type CartRow } from "./cart";

export interface CartItemCardProps {
  row: CartRow;
  currency: string;
  tier: PriceTier;
  disabled: boolean;
  onPacks: (lineId: string, packs: number) => void;
  onUnit: (lineId: string, unitType: UnitType) => void;
  onRemove: (row: CartRow) => void;
  onOverride: (row: CartRow) => void;
  onClearOverride: (row: CartRow) => void;
  onAddSerials: (row: CartRow) => void;
  /** Margin floor for this product at this branch, when a margin policy applies. */
  floorCents?: number | null;
  onApproveFloor?: (row: CartRow) => void;
  /** Cashier discount on the line (with a reason); absent when discounts are not offered. */
  onDiscount?: (row: CartRow) => void;
  onClearDiscount?: (row: CartRow) => void;
  /** Reopen the modifier panel for a line that has not been sent to the kitchen. */
  onCustomize?: (row: CartRow) => void;
  /** True when this product has modifier groups, even if none are chosen yet. */
  modifierMenu?: (productId: string) => boolean;
  onDuplicate?: (row: CartRow) => void;
}

function sourceLabel(row: CartRow): string {
  const line = row.lines[0];
  if (!line) return "";
  if (line.override) return "Manual";
  if (line.priceSource === "volume") return "Bulk";
  if (line.priceSource === "tier") return PRICE_TIER_LABELS[line.tier];
  return "Retail";
}

/** Variant, SKU, scale, or expiry text. Plain items stay blank so unrelated codes are not shown. */
export function cartItemDetail(product: ProductUpsert): string {
  const attributes = Object.entries(product.variant_attributes ?? {})
    .filter(([, value]) => value.trim() !== "")
    .map(([key, value]) => `${variantAttributeLabel(key)} ${value}`);
  const parts = [...attributes];
  if (product.sold_by_weight) {
    if (product.plu_code) parts.push(`PLU ${product.plu_code}`);
    else if (product.barcode) parts.push(product.barcode);
  } else if ((product.is_serialized || attributes.length > 0) && product.sku) {
    parts.push(product.sku);
  }
  if (product.nearest_expiry) parts.push(`Exp ${product.nearest_expiry}`);
  return parts.join(" · ");
}

const actionClass =
  "cart-action inline-flex h-11 w-11 shrink-0 flex-col items-center justify-center rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 disabled:opacity-40";
const stepButton =
  "flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-zinc-700 transition-colors hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 active:bg-white disabled:opacity-30 dark:text-white/80 dark:hover:bg-white/10 dark:active:bg-white/15";

function LineAction({
  icon: Icon,
  label,
  accessible,
  onClick,
  disabled,
  destructive = false,
}: {
  icon: LucideIcon;
  label: string;
  accessible?: string;
  onClick: () => void;
  disabled: boolean;
  destructive?: boolean;
}) {
  const name = accessible ?? label;
  return (
    <button
      type="button"
      disabled={disabled}
      title={name}
      aria-label={name}
      onClick={onClick}
      className={`${actionClass} ${
        destructive
          ? "text-red-600 hover:bg-red-50 hover:text-red-700 dark:text-red-400 dark:hover:bg-red-500/10 dark:hover:text-red-300"
          : "text-zinc-600 hover:bg-zinc-200/80 hover:text-zinc-900 active:bg-zinc-200 dark:text-white/70 dark:hover:bg-white/10 dark:hover:text-white dark:active:bg-white/15"
      }`}
    >
      <Icon size={15} aria-hidden="true" />
      <span className="cart-action-label">{label}</span>
    </button>
  );
}

/** One cart line in two compact rows: name and total, then quantity and actions. */
export function CartItemCard({
  row,
  currency,
  tier,
  disabled,
  onPacks,
  onUnit,
  onRemove,
  onOverride,
  onClearOverride,
  onAddSerials,
  floorCents = null,
  onApproveFloor,
  onDiscount,
  onClearDiscount,
  onCustomize,
  modifierMenu,
  onDuplicate,
}: CartItemCardProps) {
  const { t } = useLocale();
  const reduced = useReducedMotion() === true;
  const qtyMotion = useAnimation();
  const [showSerials, setShowSerials] = useState(false);
  const [more, setMore] = useState(false);
  const first = row.lines[0];
  useEffect(() => {
    if (!more) return;
    const close = () => setMore(false);
    window.addEventListener("pointerdown", close);
    return () => window.removeEventListener("pointerdown", close);
  }, [more]);
  if (!first) return null;
  const serialized = first.serialValue !== null;
  const pieces = row.lines.reduce((sum, line) => sum + line.quantity, 0);
  const gross = row.lines.reduce((sum, line) => sum + lineGross(line), 0);
  const weighedLine = row.product.sold_by_weight;
  const promoCents = row.lines.reduce((sum, line) => sum + (line.promotion?.discountCents ?? 0), 0);
  const promoName = row.lines.find((line) => line.promotion)?.promotion?.name ?? null;
  const manualCents = row.lines.reduce((sum, line) => sum + manualDiscountCents(line), 0);
  const discountLabel = first?.discount
    ? `${first.discount.reasonLabel}${first.discount.mode === "percent" ? ` ${(first.discount.value / 100).toFixed(0)}%` : ""}`
    : null;
  const giftCode = first?.giftCardCode ?? null;
  const total = gross - promoCents - manualCents;
  const factor = unitFactor(row.product, first.unitType);
  const packs = Math.round(first.quantity / factor);
  const units = unitsFor(row.product);
  const overridden = first.override !== null;
  const discounted = overridden || first.unitPriceCents < row.product.price_cents;
  const next = first.override ? null : nextVolumeBreak(row.product.prices, first.tier, pieces);
  const unitName = unitLabel(row.product, first.unitType).toLowerCase();
  const belowFloor = floorCents !== null && first.unitPriceCents < floorCents;
  const moqHint = first.moqShortfall > 0 && tier !== "RETAIL";
  const serialLabel = serialized && row.lines.length === 1 ? first.serialValue : null;
  const combo = comboSummary(first.components);
  const choices = first.modifiers ?? [];
  const instruction = first.instruction?.trim() || "";
  const canEditModifiers =
    Boolean(onCustomize) && !first.orderItemId && !serialized && (choices.length > 0 || (modifierMenu?.(row.product.id) ?? false));
  const detail = [cartItemDetail(row.product), serialLabel].filter(Boolean).join(" · ");
  const summary = `${weighedLine ? "@ " : factor > 1 ? `${packs} × ${unitLabel(row.product, first.unitType, "short")} · ${pieces} pcs @ ` : `${pieces} × `}${formatMoney(first.unitPriceCents, currency)}${weighedLine ? "/kg" : ""}`;
  const priceAction = giftCode
    ? null
    : overridden
      ? { key: "list", label: t("List"), icon: Undo2, onClick: () => onClearOverride(row) }
      : { key: "price", label: t("Price"), icon: PencilLine, onClick: () => onOverride(row) };
  const discountAction =
    onDiscount && !giftCode && !weighedLine
      ? manualCents > 0
        ? { key: "undo", label: t("Undo"), icon: Undo2, onClick: () => onClearDiscount?.(row) }
        : { key: "discount", label: t("Discount"), icon: Percent, onClick: () => onDiscount(row) }
      : null;
  const extra = [
    serialized ? { key: "units", label: t("Units"), icon: ScanLine, onClick: () => onAddSerials(row) } : null,
    canEditModifiers ? { key: "modifiers", label: t("Edit modifiers"), icon: SlidersHorizontal, onClick: () => onCustomize?.(row) } : null,
    canEditModifiers && onDuplicate && (choices.length > 0 || instruction !== "")
      ? { key: "copy", label: t("Copy"), icon: Copy, onClick: () => onDuplicate(row) }
      : null,
  ].filter((action): action is { key: string; label: string; icon: LucideIcon; onClick: () => void } => action !== null);
  const inline = [...extra, priceAction, discountAction].filter(
    (action): action is { key: string; label: string; icon: LucideIcon; onClick: () => void } => action !== null,
  );
  const showBadge = overridden || first.priceSource !== "retail";
  const step = (nextPacks: number) => {
    onPacks(first.lineId, nextPacks);
    if (!reduced) void qtyMotion.start({ scale: [1, 1.08, 1], transition: { duration: 0.16 } });
  };

  return (
    <motion.li
      layout={reduced ? false : "position"}
      initial={reduced ? false : { opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      exit={reduced ? { opacity: 0 } : { opacity: 0, y: -4 }}
      transition={{ duration: reduced ? 0 : 0.16, ease: [0.4, 0, 0.2, 1] }}
      className="cart-item rounded-xl border border-zinc-200 bg-zinc-50 px-2.5 py-1.5 font-sans tabular-nums dark:border-white/[0.06] dark:bg-[#1A191D]"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          {canEditModifiers ? (
            <button
              type="button"
              disabled={disabled}
              onClick={() => onCustomize?.(row)}
              className="block w-full min-w-0 truncate text-left text-sm font-semibold leading-5"
              title={t("Edit modifiers for {name}", { name: row.product.name })}
            >
              {serialized && row.lines.length > 1 ? `${row.lines.length} × ` : ""}
              {row.product.name}
            </button>
          ) : (
            <p className="min-w-0 truncate text-sm font-semibold leading-5" title={row.product.name}>
              {serialized && row.lines.length > 1 ? `${row.lines.length} × ` : ""}
              {row.product.name}
            </p>
          )}
          {detail ? <p className="truncate font-mono text-[11px] leading-4 text-zinc-500 dark:text-white/50">{detail}</p> : null}
        </div>
        <p className="shrink-0 whitespace-nowrap text-sm font-bold leading-5">
          {promoCents || manualCents ? (
            <span className="mr-1.5 text-[11px] font-normal text-zinc-500 line-through dark:text-white/40">{formatMoney(gross, currency)}</span>
          ) : null}
          {formatMoney(total, currency)}
        </p>
      </div>

      <div className="mt-0.5 flex min-w-0 flex-nowrap items-center gap-1">
        {showBadge ? (
          <span
            className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase leading-4 tracking-wide ${
              overridden || first.priceSource !== "retail" ? "bg-primary text-white" : "bg-zinc-200/80 text-zinc-600 dark:bg-white/10 dark:text-white/70"
            }`}
          >
            {t(sourceLabel(row))}
          </span>
        ) : null}

        {weighedLine ? (
          <span className="inline-flex h-11 shrink-0 items-center gap-1 rounded-lg bg-zinc-200/70 px-2 text-xs font-semibold dark:bg-[#2D2A32]">
            <Scale size={14} aria-hidden="true" />
            {formatWeight(first.quantity)}
          </span>
        ) : serialized ? (
          row.lines.length > 1 ? (
            <button
              type="button"
              aria-expanded={showSerials}
              onClick={() => setShowSerials((value) => !value)}
              className="inline-flex h-11 shrink-0 items-center gap-1 rounded-lg bg-zinc-200/70 px-2 text-xs font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 dark:bg-[#2D2A32]"
            >
              <ChevronDown size={14} aria-hidden="true" className={showSerials ? "rotate-180" : ""} />
              {row.lines.length} {t("IMEIs")}
            </button>
          ) : null
        ) : (
          <div className="inline-flex h-11 shrink-0 items-center rounded-lg bg-zinc-200/70 dark:bg-[#2D2A32]">
            <motion.button
              type="button"
              aria-label={t("One less {unit}", { unit: unitName })}
              disabled={disabled || packs <= 1}
              onClick={() => step(packs - 1)}
              whileTap={reduced || disabled || packs <= 1 ? undefined : { scale: 0.92 }}
              className={stepButton}
            >
              <Minus size={16} aria-hidden="true" />
            </motion.button>
            <motion.input
              aria-label={t("Quantity")}
              inputMode="numeric"
              disabled={disabled}
              value={packs}
              animate={qtyMotion}
              onChange={(event) => {
                const value = Number(event.target.value.replace(/\D/g, ""));
                if (value >= 1) onPacks(first.lineId, value);
              }}
              className="h-11 w-8 bg-transparent text-center text-sm font-semibold tabular-nums focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
            />
            <motion.button
              type="button"
              aria-label={t("One more {unit}", { unit: unitName })}
              disabled={disabled}
              onClick={() => step(packs + 1)}
              whileTap={reduced || disabled ? undefined : { scale: 0.92 }}
              className={stepButton}
            >
              <Plus size={16} aria-hidden="true" />
            </motion.button>
          </div>
        )}

        {!serialized && !weighedLine && units.length > 1 ? (
          <div className="inline-flex h-11 shrink-0 items-center rounded-lg bg-zinc-200/70 p-0.5 dark:bg-[#2D2A32]" role="group" aria-label={t("Unit")}>
            {units.map((unit) => (
              <button
                key={unit}
                type="button"
                aria-pressed={first.unitType === unit}
                disabled={disabled}
                onClick={() => onUnit(first.lineId, unit)}
                className={`h-10 rounded-md px-2 text-xs font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 ${
                  first.unitType === unit ? "bg-white text-charcoal shadow-sm" : "text-zinc-600 hover:text-zinc-900 dark:text-white/70 dark:hover:text-white"
                }`}
              >
                {unitLabel(row.product, unit, "short")}
              </button>
            ))}
          </div>
        ) : null}

        <span className="cart-unit-summary min-w-0 flex-1 truncate text-[11px] leading-4 text-zinc-500 dark:text-white/50" title={summary}>
          {summary}
          {discounted ? (
            <span className="ml-1 line-through">{formatMoney(overridden ? first.listPriceCents : row.product.price_cents, currency)}</span>
          ) : null}
        </span>

        <span className="ml-auto flex shrink-0 items-center">
          <span className="cart-inline-actions flex items-center">
            {inline.map((action) => (
              <LineAction key={action.key} icon={action.icon} label={action.label} disabled={disabled} onClick={action.onClick} />
            ))}
          </span>
          <span className="cart-overflow relative">
            <button
              type="button"
              aria-label={t("More actions")}
              aria-expanded={more}
              aria-haspopup="menu"
              disabled={disabled}
              onPointerDown={(event) => event.stopPropagation()}
              onClick={() => setMore((open) => !open)}
              className={actionClass}
            >
              <MoreHorizontal size={16} aria-hidden="true" />
            </button>
            {more ? (
              <span
                role="menu"
                onPointerDown={(event) => event.stopPropagation()}
                className="absolute end-0 top-full z-20 mt-1 flex min-w-36 flex-col rounded-lg border border-zinc-200 bg-white p-1 shadow-lg dark:border-white/10 dark:bg-zinc-900"
              >
                {inline.map((action) => (
                  <button
                    key={action.key}
                    type="button"
                    role="menuitem"
                    disabled={disabled}
                    onClick={() => {
                      setMore(false);
                      action.onClick();
                    }}
                    className="flex h-10 items-center gap-2 rounded-md px-2 text-left text-sm font-medium hover:bg-zinc-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 dark:hover:bg-white/10"
                  >
                    <action.icon size={15} aria-hidden="true" />
                    {action.label}
                  </button>
                ))}
              </span>
            ) : null}
          </span>
          <LineAction
            icon={Trash2}
            label={t("Remove")}
            accessible={t("Remove {name}", { name: row.product.name })}
            disabled={disabled}
            destructive
            onClick={() => onRemove(row)}
          />
        </span>
      </div>

      {combo || instruction || giftCode || promoName || (manualCents > 0 && discountLabel) || moqHint || next !== null ? (
        <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[11px] leading-4 text-zinc-500 dark:text-white/50">
          {combo ? <span className="font-semibold text-zinc-700 dark:text-white/80">{combo}</span> : null}
          {instruction ? <span className="font-medium text-zinc-700 dark:text-white/80">“{instruction}”</span> : null}
          {giftCode ? <span className="font-mono font-semibold text-primary">{giftCode}</span> : null}
          {promoName ? <span className="font-semibold text-primary">{promoName}</span> : null}
          {manualCents > 0 && discountLabel ? (
            <span className="font-semibold text-primary">
              {discountLabel} −{formatMoney(manualCents, currency)}
              {first.discount?.approverName ? ` · ${first.discount.approverName}` : ""}
            </span>
          ) : null}
          {moqHint ? (
            <span className="font-medium text-zinc-800 dark:text-white/80">
              {t("Add {count} more pcs for the {tier} price.", { count: first.moqShortfall, tier: t(PRICE_TIER_LABELS[tier]) })}
            </span>
          ) : next !== null ? (
            <span>{t("Add {count} more for {price} each.", { count: next.min_qty - pieces, price: formatMoney(next.price_cents, currency) })}</span>
          ) : null}
        </p>
      ) : null}

      {choices.length > 0 ? (
        <ul className="mt-0.5" aria-label={t("Modifiers for {name}", { name: row.product.name })}>
          {choices.map((choice) => (
            <li key={`${choice.group_id}:${choice.option_id}`} className="flex items-baseline justify-between gap-2 text-[11px] leading-4">
              <span className="min-w-0 truncate font-medium text-zinc-800 dark:text-white/85">{choice.option || choice.group}</span>
              <span className="shrink-0 whitespace-nowrap tabular-nums text-zinc-500 dark:text-white/55">
                {choice.price_delta_cents === 0
                  ? t("No additional charge")
                  : `${choice.price_delta_cents > 0 ? "+" : "−"}${formatMoney(Math.abs(choice.price_delta_cents), currency)}`}
              </span>
            </li>
          ))}
        </ul>
      ) : null}

      {belowFloor && floorCents !== null ? (
        first.floorOverride ? (
          <p className="mt-0.5 flex items-center gap-1.5 text-[11px] leading-4 text-zinc-600 dark:text-white/60">
            <ShieldCheck size={12} aria-hidden="true" className="text-primary" />
            {t("Below the {amount} margin floor, approved by {name}.", {
              amount: formatMoney(floorCents, currency),
              name: first.floorOverride.approverName,
            })}
          </p>
        ) : (
          <button
            type="button"
            disabled={disabled}
            onClick={() => onApproveFloor?.(row)}
            className="mt-1 flex w-full items-center gap-2 rounded-lg border border-primary/60 px-2 py-1 text-left text-[11px] font-medium leading-4 text-zinc-900 hover:bg-primary/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 dark:text-white"
          >
            <ShieldAlert size={14} aria-hidden="true" className="shrink-0 text-primary" />
            {t("Below the margin floor of {amount}. Manager approval needed.", { amount: formatMoney(floorCents, currency) })}
          </button>
        )
      ) : null}

      {serialized && showSerials ? (
        <ul className="mt-1 grid grid-cols-2 gap-1 font-mono text-[11px] text-zinc-600 dark:text-white/70">
          {row.lines.map((line) => (
            <li key={line.lineId} className="truncate rounded-md bg-zinc-100 px-2 py-0.5 dark:bg-white/5">
              {line.serialValue}
            </li>
          ))}
        </ul>
      ) : null}
    </motion.li>
  );
}
