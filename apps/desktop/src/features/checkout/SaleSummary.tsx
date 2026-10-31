import { formatMoney } from "@ai-pos/shared-types";
import type { ReactNode } from "react";
import type { CartTotals } from "./cart";

interface SaleSummaryProps {
  totals: CartTotals;
  currency: string;
  /** Standard VAT rate in basis points, or null when the business charges no VAT. */
  taxRateBps: number | null;
  promotionCents: number;
  /** Cashier discounts on the sale. */
  discountCents?: number;
  /** Rendered at the end of the subtotal line, e.g. the payment sheet's fold toggle. */
  action?: ReactNode;
  /** Restaurant bills: service charge (inside the total) and tip (on top), and which tab is being paid. */
  serviceChargeCents?: number;
  serviceChargeTaxCents?: number;
  tipCents?: number;
  settling?: string | null;
}

/** One subtle line for subtotal / tax / savings, then the total the customer pays. */
export function SaleSummary({
  totals,
  currency,
  taxRateBps,
  promotionCents,
  discountCents = 0,
  action,
  serviceChargeCents = 0,
  serviceChargeTaxCents = 0,
  tipCents = 0,
  settling = null,
}: SaleSummaryProps) {
  const wholesaleSavings = Math.max(totals.retailSubtotal - totals.chargedSubtotal - promotionCents - discountCents, 0);
  const includedOnly = totals.exclusiveTax === 0 && totals.inclusiveTax > 0;
  const taxLabel = includedOnly
    ? "VAT included"
    : taxRateBps
      ? `Tax (${(taxRateBps / 100).toLocaleString(undefined, { maximumFractionDigits: 2 })}%)`
      : "Tax";
  const parts = [
    { label: "Subtotal", value: formatMoney(includedOnly ? totals.total : totals.subtotal, currency) },
    { label: taxLabel, value: formatMoney(totals.tax + serviceChargeTaxCents, currency) },
    ...(serviceChargeCents > 0 ? [{ label: "Service", value: formatMoney(serviceChargeCents, currency) }] : []),
    ...(tipCents > 0 ? [{ label: "Tip", value: formatMoney(tipCents, currency) }] : []),
    ...(promotionCents > 0 ? [{ label: "Promotions", value: `−${formatMoney(promotionCents, currency)}`, accent: true }] : []),
    ...(discountCents > 0 ? [{ label: "Discounts", value: `−${formatMoney(discountCents, currency)}`, accent: true }] : []),
    ...(wholesaleSavings > 0 ? [{ label: "Saved vs retail", value: `−${formatMoney(wholesaleSavings, currency)}`, accent: true }] : []),
  ];

  return (
    <dl className="font-sans tabular-nums">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-zinc-500 dark:text-zinc-400">
        {parts.map((part, index) => (
          <div key={part.label} className="flex items-center gap-2">
            {index > 0 ? (
              <span aria-hidden="true" className="text-zinc-300 dark:text-zinc-600">
                |
              </span>
            ) : null}
            <dt>{part.label}:</dt>
            <dd className={`font-semibold ${part.accent ? "text-primary" : "text-zinc-800 dark:text-zinc-200"}`}>{part.value}</dd>
          </div>
        ))}
        {action ? <div className="ml-auto">{action}</div> : null}
      </div>
      <div className="mt-1 flex items-baseline justify-between gap-3">
        <dt className="min-w-0 truncate text-sm font-semibold text-zinc-900 dark:text-white">
          Total
          {settling ? <span className="ml-1.5 text-xs font-medium text-primary">· {settling}</span> : null}
        </dt>
        <dd className="text-[1.75rem] font-bold leading-8 tracking-tight text-primary" aria-live="polite">
          {formatMoney(totals.total + serviceChargeCents + serviceChargeTaxCents + tipCents, currency)}
        </dd>
      </div>
    </dl>
  );
}
