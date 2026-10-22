import type {
  AnalyticsTimeframe,
  OverrideReason,
  PaymentMethod,
  RefundMethod,
  ReturnCondition,
  ReturnReason,
  SaleStatus,
  SerialKind,
  SerialStatus,
} from "./enums.js";

export interface ReturnConditionRule {
  key: string;
  label: string;
  /** Goes back on the shelf as sellable stock. */
  restock: boolean;
  /** Restocking fee kept, basis points of the line. */
  fee_bps: number;
  serial_status: SerialStatus;
}

export interface ReturnPolicy {
  window_days: number;
  /** After window_days, this many more days accept the return as an exchange voucher only. */
  exchange_window_days?: number;
  open_box_fee_bps: number;
  serial_status_by_condition: Record<ReturnCondition, SerialStatus>;
  preset?: "electronics" | "fashion" | "custom" | string;
  conditions?: ReturnConditionRule[];
  reasons?: { key: string; label: string }[];
}

export interface ReceiptItem {
  sale_item_id: string;
  product_id: string;
  sku: string;
  name: string;
  category: string;
  is_serialized: boolean;
  serial_kind: SerialKind | null;
  serial_last4: string | null;
  quantity: number;
  returned_quantity: number;
  unit_price_cents: number;
  tax_cents: number;
  refunded_tax_cents: number;
  line_total_cents: number;
  /** End of the unit's warranty cover, when one was registered. */
  warranty_expires_at?: string | null;
  /** Weighed lines: quantity counts grams and unit_price_cents is per kilogram. */
  sold_by_weight?: boolean;
  /** Promotion plus cashier discount on the whole line, before VAT; refunds carry their share. */
  discount_cents?: number;
  /** Returns only with a manager. */
  final_sale?: boolean;
  /** Gift card lines never return. */
  gift_card?: boolean;
  /** Size and colour, e.g. "M · Black". */
  variant?: string | null;
}

export interface Receipt {
  sale_id: string;
  invoice: string;
  store_id: string;
  cashier_id: string;
  status: SaleStatus;
  currency: string;
  payment_method: PaymentMethod;
  subtotal_cents: number;
  tax_cents: number;
  total_cents: number;
  refunded_cents: number;
  card_refundable_cents: number;
  created_at: string;
  policy: ReturnPolicy;
  items: ReceiptItem[];
}

export interface ReturnItemUpsert {
  id: string;
  sale_item_id: string;
  product_id: string;
  quantity: number;
  unit_price_cents: number;
  tax_refund_cents: number;
  restocking_fee_cents: number;
  refund_cents: number;
  condition_status: ReturnCondition;
  reason_code: ReturnReason;
  serial_value: string | null;
  serial_kind: SerialKind | null;
}

export interface ReturnTenderUpsert {
  method: RefundMethod;
  amount_cents: number;
  store_credit_code: string | null;
}

export interface ReturnOverride {
  approved_by_id: string;
  reasons: OverrideReason[];
  note: string;
}

export interface ReturnUpsert {
  id: string;
  original_sale_id: string;
  store_id: string;
  cashier_id: string;
  currency: string;
  processed_at: string;
  subtotal_cents: number;
  tax_refund_cents: number;
  restocking_fee_cents: number;
  total_refund_cents: number;
  reason_notes: string;
  items: ReturnItemUpsert[];
  tenders: ReturnTenderUpsert[];
  override: ReturnOverride | null;
  credit_note_number?: string | null;
  shift_id?: string | null;
}

export interface ConditionSlice {
  condition: ReturnCondition;
  units: number;
}

export interface TenderSlice {
  method: RefundMethod;
  amount_cents: number;
}

export interface ReturnedProductRow {
  product_id: string;
  sku: string;
  name: string;
  category: string;
  units_sold: number;
  units_returned: number;
  defective_units: number;
  return_rate_bps: number;
  refund_cents: number;
  last_returned_at: string;
}

export interface CashierReturnRow {
  cashier_id: string;
  full_name: string;
  role_name: string;
  return_count: number;
  refund_cents: number;
  override_count: number;
  outside_window_count: number;
  last_return_at: string;
  flagged: boolean;
}

export interface OverrideLogRow {
  id: string;
  return_id: string;
  created_at: string;
  cashier_name: string;
  approver_name: string | null;
  reasons: OverrideReason[];
  refund_cents: number;
  note: string;
}

export interface ReturnsAnalytics {
  timeframe: AnalyticsTimeframe;
  currency: string;
  return_count: number;
  units_returned: number;
  units_sold: number;
  return_rate_bps: number;
  refund_cents: number;
  restocking_fee_cents: number;
  defective_units: number;
  defective_rate_bps: number;
  override_count: number;
  refund_series: number[];
  conditions: ConditionSlice[];
  tenders: TenderSlice[];
  top_products: ReturnedProductRow[];
  cashiers: CashierReturnRow[];
  overrides: OverrideLogRow[];
}

/** The condition rules of a policy; receipts cached before policies carried them get the electronics rules. */
export function policyConditions(policy: ReturnPolicy): ReturnConditionRule[] {
  if (policy.conditions && policy.conditions.length > 0) return policy.conditions;
  return [
    { key: "unopened_resealable", label: "Unopened / resealable", restock: true, fee_bps: 0, serial_status: "in_stock" },
    { key: "open_box", label: "Open box", restock: false, fee_bps: policy.open_box_fee_bps, serial_status: "quarantine" },
    { key: "defective_doa", label: "Defective / DOA", restock: false, fee_bps: 0, serial_status: "repair" },
  ];
}

/** Mirrors restocking_fee in apps/api/app/services/returns_service.py. */
export function restockingFeeCents(unitPriceCents: number, quantity: number, feeBps: number): number {
  if (!feeBps) return 0;
  return Math.floor((unitPriceCents * quantity * feeBps + 5_000) / 10_000);
}

/** Mirrors discount_share in apps/api/app/services/returns_service.py. */
export function discountShareCents(
  discountCents: number,
  itemQuantity: number,
  quantity: number,
  priorQuantity: number,
): number {
  if (!discountCents || itemQuantity <= 0) return 0;
  const before = Math.floor((discountCents * priorQuantity) / itemQuantity);
  return Math.floor((discountCents * (priorQuantity + quantity)) / itemQuantity) - before;
}

/** Mirrors prorated_tax in apps/api/app/services/returns_service.py. */
export function proratedTaxCents(
  itemTaxCents: number,
  itemQuantity: number,
  quantity: number,
  priorQuantity: number,
  priorTaxCents: number,
): number {
  const remaining = itemTaxCents - priorTaxCents;
  if (quantity >= itemQuantity - priorQuantity) return remaining;
  const share = Math.floor((itemTaxCents * quantity * 2 + itemQuantity) / (itemQuantity * 2));
  return Math.min(share, remaining);
}
