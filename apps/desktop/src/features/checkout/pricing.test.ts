import {
  resolveUnitPrice,
  resolveWithLists,
  type PriceListEntry,
  type PriceTier,
  type ProductPrice,
} from "@ai-pos/shared-types";
import { describe, expect, it } from "vitest";
import lists from "../../../../../packages/shared-types/fixtures/price-list-cases.json";
import fixture from "../../../../../packages/shared-types/fixtures/pricing-cases.json";

describe("resolveWithLists matches the API's price-list fixture", () => {
  for (const item of lists.cases) {
    it(item.name, () => {
      const result = resolveWithLists(
        lists.retail_cents,
        lists.prices as ProductPrice[],
        item.tier as PriceTier,
        item.pieces,
        lists.entries as PriceListEntry[],
        { customer_id: item.customer_id, group_id: item.group_id, store_id: item.store_id, at: item.at },
      );
      expect([result.price_cents, result.source, result.price_list_id]).toEqual([
        item.price_cents,
        item.source,
        item.price_list_id,
      ]);
    });
  }
});

describe("resolveUnitPrice matches the API's pricing fixture", () => {
  for (const item of fixture.cases) {
    it(item.name, () => {
      const result = resolveUnitPrice(
        fixture.retail_cents,
        fixture.prices as ProductPrice[],
        item.tier as PriceTier,
        item.pieces,
      );
      expect(result.price_cents).toBe(item.price_cents);
      expect(result.tier).toBe(item.resolved_tier);
      expect(result.source).toBe(item.source);
      expect(result.moq_shortfall).toBe(item.moq_shortfall);
    });
  }
});
