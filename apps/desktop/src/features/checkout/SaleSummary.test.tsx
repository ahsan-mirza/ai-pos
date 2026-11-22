import { formatMoney } from "@ai-pos/shared-types";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { CartTotals } from "./cart";
import { SaleSummary } from "./SaleSummary";

const totals: CartTotals = {
  subtotal: 10_000,
  tax: 500,
  inclusiveTax: 0,
  exclusiveTax: 500,
  total: 10_500,
  retailSubtotal: 10_000,
  chargedSubtotal: 10_000,
  pieces: 1,
};

describe("sale summary", () => {
  it("keeps subtotal and tax and does not repeat the payable total", () => {
    const html = renderToStaticMarkup(
      <SaleSummary totals={totals} currency="AED" taxRateBps={500} promotionCents={0} discountCents={200} />,
    );
    expect(html).toContain("Subtotal:");
    expect(html).toContain(formatMoney(10_000, "AED"));
    expect(html).toContain("Tax (5%):");
    expect(html).toContain(formatMoney(500, "AED"));
    expect(html).toContain(`−${formatMoney(200, "AED")}`);
    expect(html).not.toContain("Total");
    expect(html).not.toContain(formatMoney(10_500, "AED"));
  });

  it("names the tab being paid without a total label", () => {
    const html = renderToStaticMarkup(
      <SaleSummary totals={totals} currency="AED" taxRateBps={null} promotionCents={0} settling="Table 4" />,
    );
    expect(html).toContain("Table 4");
    expect(html).not.toContain("Total");
  });
});
