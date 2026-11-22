import type { ReactNode } from "react";
import { CurrencyAmount } from "../../components/CurrencyAmount";
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

/** One subtle line for subtotal, tax, and savings. The payable amount lives on the Pay button. */
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
    { label: "Subtotal", cents: includedOnly ? totals.total : totals.subtotal, sign: "" },
    { label: taxLabel, cents: totals.tax + serviceChargeTaxCents, sign: "" },
    ...(serviceChargeCents > 0 ? [{ label: "Service", cents: serviceChargeCents, sign: "" }] : []),
    ...(tipCents > 0 ? [{ label: "Tip", cents: tipCents, sign: "" }] : []),
    ...(promotionCents > 0 ? [{ label: "Promotions", cents: promotionCents, sign: "−" }] : []),
    ...(discountCents > 0 ? [{ label: "Discounts", cents: discountCents, sign: "−" }] : []),
    ...(wholesaleSavings > 0 ? [{ label: "Saved vs retail", cents: wholesaleSavings, sign: "−" }] : []),
  ];

  return (
    <dl className="font-sans tabular-nums">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-zinc-500 dark:text-zinc-400">
        {parts.map((part, index) => (
          <div key={part.label} className="flex items-end gap-1.5">
            {index > 0 ? (
              <span aria-hidden="true" className="text-zinc-300 dark:text-zinc-600">
                |
              </span>
            ) : null}
            <dt>{part.label}:</dt>
            <dd className={part.sign ? "text-primary" : "text-zinc-800 dark:text-zinc-200"}>
              <CurrencyAmount cents={part.cents} currency={currency} size="summary" sign={part.sign ?? ""} />
            </dd>
          </div>
        ))}
        {action ? <div className="ml-auto">{action}</div> : null}
      </div>
      {settling ? <p className="mt-1 truncate text-xs font-medium text-primary">{settling}</p> : null}
    </dl>
  );
}
