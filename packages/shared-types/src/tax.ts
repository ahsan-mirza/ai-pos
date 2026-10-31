/** UAE VAT arithmetic. Mirrors apps/api/app/services/tax.py; both are checked against fixtures/tax-cases.json. */

export type TaxCategory = "STANDARD" | "ZERO" | "EXEMPT";

export interface TaxPolicy {
  /** False keeps the legacy behaviour where the API accepts the register's line tax as sent. */
  enforced: boolean;
  prices_include_vat: boolean;
  standard_rate_bps: number;
  /** The attached customer's treatment when it relieves standard-rated lines (see forCustomer). */
  treatment?: TaxTreatment;
}

export type TaxTreatment = "STANDARD" | "ZERO_EXPORT" | "EXEMPT" | "DESIGNATED_ZONE";

export const TAX_TREATMENT_LABELS: Record<TaxTreatment, string> = {
  STANDARD: "Standard VAT",
  ZERO_EXPORT: "Zero-rated export",
  EXEMPT: "Exempt",
  DESIGNATED_ZONE: "Designated zone (zero-rated)",
};

/** The customer's treatment on `on` (YYYY-MM-DD); an expired certificate falls back to STANDARD. */
export function treatmentOf(
  customer: { tax_treatment?: TaxTreatment | null; tax_certificate_expiry?: string | null } | null | undefined,
  on: string = new Date().toISOString().slice(0, 10),
): TaxTreatment {
  const treatment = customer?.tax_treatment ?? "STANDARD";
  const expiry = customer?.tax_certificate_expiry ?? null;
  if (treatment !== "STANDARD" && expiry !== null && expiry < on) return "STANDARD";
  return treatment;
}

export function forCustomer(
  policy: TaxPolicy,
  customer: Parameters<typeof treatmentOf>[0],
  on?: string,
): TaxPolicy {
  return { ...policy, treatment: treatmentOf(customer, on) };
}

export interface LineTax {
  net_cents: number;
  tax_cents: number;
  line_total_cents: number;
}

export const DEFAULT_TAX_POLICY: TaxPolicy = { enforced: false, prices_include_vat: false, standard_rate_bps: 500 };

/** Integer division rounding halves away from zero, identical to the API. */
export function divHalfUp(numerator: number, denominator: number): number {
  const sign = numerator < 0 ? -1 : 1;
  return sign * Math.floor((Math.abs(numerator) * 2 + denominator) / (2 * denominator));
}

export function rateFor(policy: TaxPolicy, category: TaxCategory | undefined | null): number {
  if ((category ?? "STANDARD") !== "STANDARD") return 0;
  return (policy.treatment ?? "STANDARD") === "STANDARD" ? policy.standard_rate_bps : 0;
}

/** The product's entered price already contains tax. Missing means exclusive, not the business-wide switch. */
export function enteredIncludesTax(product: { price_includes_tax?: boolean | null } | null | undefined): boolean {
  return product?.price_includes_tax === true;
}

export function lineTax(unitPriceCents: number, quantity: number, rateBps: number, inclusive: boolean): LineTax {
  const gross = unitPriceCents * quantity;
  if (inclusive) {
    const tax = divHalfUp(gross * rateBps, 10_000 + rateBps);
    return { net_cents: gross - tax, tax_cents: tax, line_total_cents: gross };
  }
  const tax = divHalfUp(gross * rateBps, 10_000);
  return { net_cents: gross, tax_cents: tax, line_total_cents: gross + tax };
}
