/** A foreign currency registers may take as cash. */
export interface AcceptedCurrency {
  code: string;
  name: string;
  is_active: boolean;
  base_currency: string;
  /** Business-currency units per one foreign unit, times 1,000,000; null until a rate is set. */
  rate_micros: number | null;
  source: string | null;
  effective_at: string | null;
}
