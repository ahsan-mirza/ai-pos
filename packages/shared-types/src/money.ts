export function formatMoney(cents: number, currency: string, locale?: string): string {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(cents / 100);
}

export function lineTaxCents(unitPriceCents: number, quantity: number, taxRateBps: number): number {
  return Math.round((unitPriceCents * quantity * taxRateBps) / 10_000);
}

export function isValidImei(value: string): boolean {
  if (!/^\d{15}$/.test(value)) return false;
  let total = 0;
  for (let index = 0; index < value.length; index += 1) {
    const fromRight = value.length - 1 - index;
    const char = value[fromRight];
    if (char === undefined) return false;
    let digit = Number(char);
    if (index % 2 === 1) {
      digit *= 2;
      if (digit > 9) digit -= 9;
    }
    total += digit;
  }
  return total % 10 === 0;
}
