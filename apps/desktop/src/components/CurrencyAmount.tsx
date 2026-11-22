import { formatMoney } from "@ai-pos/shared-types";

const sizeClass = {
  summary: { code: "text-[0.625rem]", amount: "text-lg" },
  line: { code: "text-[0.625rem]", amount: "text-xl" },
  card: { code: "text-[0.6875rem]", amount: "text-2xl" },
  pay: { code: "text-xs", amount: "text-4xl" },
  hero: { code: "text-2xl", amount: "text-8xl" },
} as const;

export type CurrencyAmountSize = keyof typeof sizeClass;

/** Currency code sits in subscript. The numeric amount is the large text. */
export function CurrencyAmount({
  cents,
  currency,
  size = "card",
  sign = "",
  className = "",
}: {
  cents: number;
  currency: string;
  size?: CurrencyAmountSize;
  /** Shown before the amount, for example a savings minus. */
  sign?: string;
  className?: string;
}) {
  const absolute = Math.abs(cents);
  const label = `${sign}${formatMoney(absolute, currency)}`;
  const parts = moneyParts(absolute, currency);
  const scale = sizeClass[size];

  return (
    <span dir="ltr" className={`inline-flex items-end gap-0.5 whitespace-nowrap tabular-nums leading-none ${className}`} aria-label={label}>
      <span className={`${scale.code} font-semibold leading-none`}>{parts.code}</span>
      <span className={`${scale.amount} font-bold leading-none tracking-tight`}>{sign}{parts.amount}</span>
    </span>
  );
}

function moneyParts(cents: number, currency: string): { code: string; amount: string } {
  try {
    const parts = new Intl.NumberFormat("en-AE", {
      style: "currency",
      currency,
      currencyDisplay: "code",
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).formatToParts(cents / 100);
    const code = parts.find((part) => part.type === "currency")?.value ?? currency;
    const amount = parts
      .filter((part) => part.type === "integer" || part.type === "group" || part.type === "decimal" || part.type === "fraction")
      .map((part) => part.value)
      .join("");
    if (code && amount) return { code, amount };
  } catch {
    // Invalid currency codes fall through to the plain formatted string.
  }
  return { code: currency, amount: (cents / 100).toFixed(2) };
}
