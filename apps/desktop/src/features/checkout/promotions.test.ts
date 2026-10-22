import { applyPromotions, type Promotion, type PromotionLine, type PromotionRule } from "@ai-pos/shared-types";
import { describe, expect, it } from "vitest";
import fixture from "../../../../../packages/shared-types/fixtures/promotion-cases.json";
import { lineCharge, type CartLine } from "./cart";
import { withPromotions } from "./promotions";

describe("applyPromotions matches the API's promotion fixture", () => {
  it("applies promotions to retail carts only, with VAT on the discounted amount", () => {
    const product = { id: "cable", sku: "C", name: "Cable", price_cents: 1500, category_id: "acc", tax_category: "STANDARD" } as never;
    const line = {
      lineId: "L1",
      product,
      quantity: 2,
      unitType: "PIECE",
      serialValue: null,
      serialKind: null,
      groupId: null,
      listPriceCents: 1500,
      unitPriceCents: 1500,
      priceSource: "retail",
      tier: "RETAIL",
      moqShortfall: 0,
      override: null,
    } as CartLine;
    const promo = {
      id: "P1",
      name: "Cable week",
      kind: "PERCENT_OFF",
      percent_bps: 1000,
      product_ids: [],
      category_ids: [],
      store_ids: [],
      min_spend_cents: 0,
      is_active: true,
      starts_at: null,
      ends_at: null,
      coupon_code: null,
      max_uses: null,
      uses_count: 0,
    } as unknown as Promotion;
    const [priced] = withPromotions({ mode: "RETAIL", lines: [line] }, [promo], null);
    expect(priced?.promotion).toEqual({ id: "P1", name: "Cable week", discountCents: 300 });
    expect(lineCharge(priced!, { enforced: true, prices_include_vat: false, standard_rate_bps: 500 })).toMatchObject({
      tax_cents: 135,
      line_total_cents: 2835,
    });
    expect(withPromotions({ mode: "WHOLESALE", lines: [line] }, [promo], null)[0]?.promotion ?? null).toBeNull();
  });

  const cases = fixture.cases as unknown as { name: string; lines: PromotionLine[]; rules: PromotionRule[]; awards: unknown[] }[];
  for (const testCase of cases) {
    it(testCase.name, () => {
      expect(applyPromotions(testCase.lines, testCase.rules)).toEqual(testCase.awards);
    });
  }
});
