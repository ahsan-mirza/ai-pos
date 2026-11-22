import type { SerialKind, UnitType } from "./enums.js";

export interface SaleItem {
  id: string;
  sale_id: string;
  product_id: string;
  serial_number_id: string | null;
  serial_value: string | null;
  quantity: number;
  unit_price_cents: number;
  tax_cents: number;
  line_total_cents: number;
  unit_type: UnitType;
  list_price_cents: number | null;
  price_override_by_id: string | null;
  tax_rate_bps?: number | null;
  description?: string | null;
  cost_cents?: number | null;
}

/** quantity and unit_price_cents are per piece; unit_type records the pack the cashier sold in. */
export interface SaleItemUpsert {
  id: string;
  product_id: string;
  quantity: number;
  unit_price_cents: number;
  tax_cents: number;
  line_total_cents: number;
  /** Basis points used when the line was priced. Absent on older queued sales. */
  tax_rate_bps?: number | null;
  serial_value: string | null;
  serial_kind: SerialKind | null;
  unit_type?: UnitType;
  list_price_cents?: number;
  price_override?: { approved_by_id: string; note: string } | null;
  /** What was sold on an open-price line. */
  description?: string | null;
  below_floor_override?: { approved_by_id: string; note: string } | null;
  /** Promotion discount off unit_price_cents * quantity, before VAT. */
  discount_cents?: number;
  promotion_id?: string | null;
  /** Cashier discount after the promotion, before VAT, with a reason from the till rules. */
  manual_discount_cents?: number;
  discount_reason?: string | null;
  /** The manager who approved a discount above the cashier's limit. */
  discount_override?: { approved_by_id: string; note: string } | null;
  /** Selling a gift card: the code the register generated. */
  gift_card_code?: string | null;
  /** Sent when the product has a minimum age. The sale is refused without it. */
  age_check?: { confirmed: boolean; override_by_id?: string | null; reason?: string | null } | null;
  /** Menu modifiers; unit_price_cents and list_price_cents include their price deltas. */
  modifiers?: ModifierChoice[];
  /** Serving option when the menu item has more than one base price. */
  price_option_id?: string | null;
  /** True only when this line was sold without consuming its recipe. */
  skip_recipe?: boolean;
  /** Meal components of a combo line; unit_price_cents and list_price_cents include their surcharges. */
  components?: ComboChoice[];
}

/** One part picked for a meal, e.g. Side: Fries. Names and surcharges are informational; the API prices them. */
export interface ComboChoice {
  slot_id: string;
  product_id: string;
  slot?: string | null;
  name?: string | null;
  surcharge_cents: number;
}

export interface ModifierChoice {
  group_id: string;
  option_id: string;
  group?: string | null;
  option?: string | null;
  price_delta_cents: number;
}
