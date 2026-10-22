import { lineTax, type Order, type ServiceChargeSettings, type TaxPolicy } from "@ai-pos/shared-types";

/** A tab (or a split check of it) handed from the Orders screen to Checkout for payment. */
export interface SettlementIntent {
  order: Order;
  /** Tab lines this payment covers. */
  itemIds: string[];
  label: string;
  /** "Split equally into N": one sale, paid guest by guest with N tenders. */
  guests?: number;
}

let pending: SettlementIntent | null = null;

export function startSettlement(intent: SettlementIntent): void {
  pending = intent;
}

/** Checkout takes the intent once, like an exchange from Returns. */
export function takeSettlement(): SettlementIntent | null {
  const intent = pending;
  pending = null;
  return intent;
}

/** Automatic service charge on the net bill, and its VAT; zero when the rules exclude this order. */
export function serviceCharge(
  rules: ServiceChargeSettings,
  order: Pick<Order, "service_type" | "covers"> | null,
  netCents: number,
  policy: TaxPolicy,
): { charge: number; tax: number } {
  if (order === null || rules.service_charge_bps <= 0 || netCents <= 0) return { charge: 0, tax: 0 };
  if (rules.dine_in_only && order.service_type !== "DINE_IN") return { charge: 0, tax: 0 };
  if (order.covers < rules.min_covers) return { charge: 0, tax: 0 };
  const charge = Math.floor((netCents * rules.service_charge_bps + 5000) / 10_000);
  const tax = rules.service_charge_taxable && policy.enforced ? lineTax(charge, 1, policy.standard_rate_bps, false).tax_cents : 0;
  return { charge, tax };
}
