import { lineTax } from "@ai-pos/shared-types";
import { describe, expect, it } from "vitest";
import fixture from "../../../../../packages/shared-types/fixtures/tax-cases.json";

describe("lineTax matches the API's VAT fixture", () => {
  for (const item of fixture.cases) {
    it(item.name, () => {
      const result = lineTax(item.unit, item.quantity, item.rate_bps, item.inclusive);
      expect([result.net_cents, result.tax_cents, result.line_total_cents]).toEqual([item.net, item.tax, item.total]);
    });
  }
});
