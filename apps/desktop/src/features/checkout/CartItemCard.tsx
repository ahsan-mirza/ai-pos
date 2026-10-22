import {
  PRICE_TIER_LABELS,
  comboSummary,
  formatMoney,
  formatWeight,
  modifierSummary,
  nextVolumeBreak,
  unitFactor,
  unitLabel,
  type PriceTier,
  type UnitType,
} from "@ai-pos/shared-types";
import {
  ChevronDown,
  Minus,
  PencilLine,
  Percent,
  Plus,
  Scale,
  ScanLine,
  ShieldAlert,
  ShieldCheck,
  Undo2,
  X,
} from "lucide-react";
import { useState } from "react";
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
}

function sourceLabel(row: CartRow): string {
  const line = row.lines[0];
  if (!line) return "";
  if (line.override) return "Manual";
  if (line.priceSource === "volume") return "Bulk";
  if (line.priceSource === "tier") return PRICE_TIER_LABELS[line.tier];
  return "Retail";
}

const microAction =
  "inline-flex h-7 items-center gap-1 rounded-lg px-1.5 text-[11px] font-medium text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-zinc-900 disabled:opacity-40 dark:text-white/55 dark:hover:bg-white/10 dark:hover:text-white";
const stepButton =
  "flex h-7 w-6 items-center justify-center rounded-md transition-colors hover:bg-white/60 disabled:opacity-30 dark:hover:bg-white/10";

/** One cart line in two compact rows: name + total, then badge, stepper, unit price and actions. */
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
}: CartItemCardProps) {
  const [showSerials, setShowSerials] = useState(false);
  const first = row.lines[0];
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
  const modifiers = [comboSummary(first.components), modifierSummary(first.modifiers)].filter(Boolean).join(" · ");
  const hasMeta =
    serialLabel !== null ||
    promoName !== null ||
    moqHint ||
    next !== null ||
    modifiers !== "" ||
    manualCents > 0 ||
    giftCode !== null;

  return (
    <li className="rounded-2xl border border-zinc-200 bg-zinc-50 px-3.5 py-2.5 font-sans tabular-nums dark:border-white/[0.06] dark:bg-[#1A191D]">
      <div className="flex items-baseline justify-between gap-3">
        <p className="min-w-0 truncate text-sm font-semibold leading-5" title={row.product.name}>
          {serialized && row.lines.length > 1 ? `${row.lines.length} × ` : ""}
          {row.product.name}
        </p>
        <p className="shrink-0 text-sm font-bold leading-5">
          {promoCents || manualCents ? (
            <span className="mr-1.5 text-[11px] font-normal text-zinc-500 line-through dark:text-white/40">{formatMoney(gross, currency)}</span>
          ) : null}
          {formatMoney(total, currency)}
        </p>
      </div>

      <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
        <span
          className={`rounded-full px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider ${
            overridden || first.priceSource !== "retail" ? "bg-primary text-white" : "bg-zinc-200/70 text-zinc-600 dark:bg-white/10 dark:text-white/70"
          }`}
        >
          {sourceLabel(row)}
        </span>

        {weighedLine ? (
          <span className="inline-flex h-7 items-center gap-1 rounded-lg bg-zinc-200/70 px-2 text-xs font-semibold dark:bg-[#2D2A32]">
            <Scale size={12} aria-hidden="true" />
            {formatWeight(first.quantity)}
          </span>
        ) : serialized ? (
          row.lines.length > 1 ? (
            <button type="button" aria-expanded={showSerials} onClick={() => setShowSerials((value) => !value)} className={microAction}>
              <ChevronDown size={12} aria-hidden="true" className={showSerials ? "rotate-180" : ""} />
              {row.lines.length} IMEIs
            </button>
          ) : null
        ) : (
          <div className="inline-flex h-7 items-center rounded-lg bg-zinc-200/70 px-0.5 text-xs font-semibold dark:bg-[#2D2A32]">
            <button
              type="button"
              aria-label={`One less ${unitName}`}
              disabled={disabled || packs <= 1}
              onClick={() => onPacks(first.lineId, packs - 1)}
              className={stepButton}
            >
              <Minus size={12} aria-hidden="true" />
            </button>
            <input
              aria-label="Quantity"
              inputMode="numeric"
              disabled={disabled}
              value={packs}
              onChange={(event) => {
                const value = Number(event.target.value.replace(/\D/g, ""));
                if (value >= 1) onPacks(first.lineId, value);
              }}
              className="h-7 w-8 bg-transparent text-center text-xs font-semibold focus:outline-none"
            />
            <button
              type="button"
              aria-label={`One more ${unitName}`}
              disabled={disabled}
              onClick={() => onPacks(first.lineId, packs + 1)}
              className={stepButton}
            >
              <Plus size={12} aria-hidden="true" />
            </button>
          </div>
        )}

        {!serialized && !weighedLine && units.length > 1 ? (
          <div className="inline-flex h-7 items-center rounded-lg bg-zinc-200/70 p-0.5 dark:bg-[#2D2A32]" role="group" aria-label="Unit">
            {units.map((unit) => (
              <button
                key={unit}
                type="button"
                aria-pressed={first.unitType === unit}
                disabled={disabled}
                onClick={() => onUnit(first.lineId, unit)}
                className={`h-6 rounded-md px-2 text-[11px] font-semibold ${
                  first.unitType === unit ? "bg-white text-charcoal" : "text-zinc-600 hover:text-zinc-900 dark:text-white/70 dark:hover:text-white"
                }`}
              >
                {unitLabel(row.product, unit, "short")}
              </button>
            ))}
          </div>
        ) : null}

        <span className="min-w-0 truncate text-[11px] text-zinc-500 dark:text-white/50">
          {weighedLine ? "@ " : factor > 1 ? `${packs} × ${unitLabel(row.product, first.unitType, "short")} · ${pieces} pcs @ ` : `${pieces} × `}
          <span className="text-zinc-700 dark:text-white/75">
            {formatMoney(first.unitPriceCents, currency)}
            {weighedLine ? "/kg" : ""}
          </span>
          {discounted ? (
            <span className="ml-1 line-through">{formatMoney(overridden ? first.listPriceCents : row.product.price_cents, currency)}</span>
          ) : null}
        </span>

        <span className="ml-auto flex shrink-0 items-center">
          {serialized ? (
            <button type="button" disabled={disabled} onClick={() => onAddSerials(row)} className={microAction}>
              <ScanLine size={12} aria-hidden="true" /> Units
            </button>
          ) : null}
          {giftCode ? null : overridden ? (
            <button type="button" disabled={disabled} onClick={() => onClearOverride(row)} className={microAction}>
              <Undo2 size={12} aria-hidden="true" /> List
            </button>
          ) : (
            <button type="button" disabled={disabled} onClick={() => onOverride(row)} className={microAction}>
              <PencilLine size={12} aria-hidden="true" /> Price
            </button>
          )}
          {onDiscount && !giftCode && !weighedLine ? (
            manualCents > 0 ? (
              <button type="button" disabled={disabled} onClick={() => onClearDiscount?.(row)} className={microAction}>
                <Undo2 size={12} aria-hidden="true" /> Undo
              </button>
            ) : (
              <button type="button" disabled={disabled} onClick={() => onDiscount(row)} className={microAction}>
                <Percent size={12} aria-hidden="true" /> Discount
              </button>
            )
          ) : null}
          <button
            type="button"
            disabled={disabled}
            aria-label={`Remove ${row.product.name}`}
            onClick={() => onRemove(row)}
            className={`${microAction} hover:!text-red-600 dark:hover:!text-red-400`}
          >
            <X size={12} aria-hidden="true" /> Remove
          </button>
        </span>
      </div>

      {hasMeta ? (
        <p className="mt-1 flex flex-wrap items-center gap-x-2 text-[11px] text-zinc-500 dark:text-white/50">
          {modifiers ? <span className="font-semibold text-zinc-700 dark:text-white/80">{modifiers}</span> : null}
          {serialLabel ? <span className="font-mono">{serialLabel}</span> : null}
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
              Add {first.moqShortfall} more pcs for the {PRICE_TIER_LABELS[tier]} price.
            </span>
          ) : next !== null ? (
            <span>
              Add {next.min_qty - pieces} more for {formatMoney(next.price_cents, currency)} each.
            </span>
          ) : null}
        </p>
      ) : null}

      {belowFloor && floorCents !== null ? (
        first.floorOverride ? (
          <p className="mt-1 flex items-center gap-1.5 text-[11px] text-zinc-600 dark:text-white/60">
            <ShieldCheck size={12} aria-hidden="true" className="text-primary" />
            Below the {formatMoney(floorCents, currency)} margin floor, approved by {first.floorOverride.approverName}.
          </p>
        ) : (
          <button
            type="button"
            disabled={disabled}
            onClick={() => onApproveFloor?.(row)}
            className="mt-1.5 flex w-full items-center gap-2 rounded-xl border border-primary/60 px-2.5 py-1.5 text-left text-[11px] font-medium text-zinc-900 hover:bg-primary/15 dark:text-white"
          >
            <ShieldAlert size={14} aria-hidden="true" className="shrink-0 text-primary" />
            Below the margin floor of {formatMoney(floorCents, currency)}. Manager approval needed.
          </button>
        )
      ) : null}

      {serialized && showSerials ? (
        <ul className="mt-1.5 grid grid-cols-2 gap-1 font-mono text-[11px] text-zinc-600 dark:text-white/70">
          {row.lines.map((line) => (
            <li key={line.lineId} className="truncate rounded-lg bg-zinc-100 px-2 py-1 dark:bg-white/5">
              {line.serialValue}
            </li>
          ))}
        </ul>
      ) : null}
    </li>
  );
}
