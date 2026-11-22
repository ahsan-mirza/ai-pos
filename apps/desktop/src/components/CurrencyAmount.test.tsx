import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CurrencyAmount } from "./CurrencyAmount";

describe("CurrencyAmount", () => {
  it("puts the currency code in subscript and the amount in large type", () => {
    const html = renderToStaticMarkup(<CurrencyAmount cents={12_550} currency="AED" size="pay" />);
    expect(html).toContain(">AED<");
    expect(html).toContain(">125.50<");
    expect(html).toContain("text-xs");
    expect(html).toContain("text-4xl");
    expect(html).toContain('aria-label="AED');
  });

  it("keeps a savings sign on the large amount", () => {
    const html = renderToStaticMarkup(<CurrencyAmount cents={200} currency="AED" sign="−" />);
    expect(html).toContain("−2.00");
  });
});
