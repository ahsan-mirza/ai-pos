import { RETURNS_PRESETS, type Receipt, type ReturnPolicy } from "@ai-pos/shared-types";
import { describe, expect, it } from "vitest";
import {
  allowedRefundMethods,
  conditionOptions,
  defaultCondition,
  isExchangeOnly,
  isOutsideWindow,
  priceLines,
  requiredOverrides,
  restockInstruction,
} from "./returnMath";

const fashion: ReturnPolicy = {
  window_days: 14,
  exchange_window_days: 16,
  open_box_fee_bps: 0,
  serial_status_by_condition: {},
  preset: "fashion",
  conditions: [
    ...RETURNS_PRESETS.fashion.conditions,
    { key: "worn_fee", label: "Worn, with fee", restock: false, fee_bps: 1000, serial_status: "quarantine" },
  ],
  reasons: RETURNS_PRESETS.fashion.reasons,
};

function receipt(daysAgo: number, overrides: Partial<Receipt["items"][number]> = {}): Receipt {
  return {
    sale_id: "sale-1",
    invoice: "INV00001",
    store_id: "store",
    cashier_id: "cashier",
    status: "completed",
    currency: "AED",
    payment_method: "cash",
    subtotal_cents: 8000,
    tax_cents: 0,
    total_cents: 8000,
    refunded_cents: 0,
    card_refundable_cents: 0,
    created_at: new Date(Date.now() - daysAgo * 86_400_000).toISOString(),
    policy: fashion,
    items: [
      {
        sale_item_id: "line-1",
        product_id: "tee",
        sku: "TEE-M-BLK",
        name: "Classic Tee",
        category: "Apparel",
        is_serialized: false,
        serial_kind: null,
        serial_last4: null,
        quantity: 2,
        returned_quantity: 0,
        unit_price_cents: 5000,
        tax_cents: 0,
        refunded_tax_cents: 0,
        line_total_cents: 8000,
        discount_cents: 2000,
        ...overrides,
      },
    ],
  };
}

const draft = (condition: string, quantity = 1) => ({
  "line-1": { quantity, condition, reason: "size_fit", serialValue: null, serialKind: null },
});

describe("policy-driven returns", () => {
  it("refunds each unit net of its share of the discount", () => {
    const [line] = priceLines(receipt(1), draft("tags_attached"), false);
    expect(line?.subtotal).toBe(4000);
    expect(line?.refund).toBe(4000);
  });

  it("charges the restocking fee of the chosen condition", () => {
    const [line] = priceLines(receipt(1), draft("worn_fee", 2), false);
    expect(line?.policyFee).toBe(1000);
    expect(line?.refund).toBe(8000 - 1000);
    const [waived] = priceLines(receipt(1), draft("worn_fee", 2), true);
    expect(waived?.fee).toBe(0);
  });

  it("limits refunds to store credit inside the exchange-only window", () => {
    expect(isExchangeOnly(receipt(20), new Date())).toBe(true);
    expect(isOutsideWindow(receipt(20), new Date())).toBe(false);
    expect(allowedRefundMethods("cash", true)).toEqual(["store_credit"]);
    expect(isOutsideWindow(receipt(31), new Date())).toBe(true);
    expect(isExchangeOnly(receipt(5), new Date())).toBe(false);
  });

  it("asks a manager for final-sale lines", () => {
    const sale = receipt(1, { final_sale: true });
    const lines = priceLines(sale, draft("tags_attached"), false);
    expect(requiredOverrides(sale, lines, ["pos:refund"], new Date())).toEqual(["final_sale"]);
  });

  it("builds the condition choices and restock advice from the policy", () => {
    expect(conditionOptions(fashion).map((option) => option.value)).toEqual(["tags_attached", "worn", "damaged", "worn_fee"]);
    expect(defaultCondition(fashion)).toBe("tags_attached");
    const [line] = priceLines(receipt(1), draft("worn"), false);
    expect(line && restockInstruction(line, fashion)).toBe("Set aside, not restocked");
  });
});
