import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { PricingPortionsFields } from "./PricingPortionsFields";

describe("Pricing & Portions form", () => {
  it("shows a single price with no portion selector", () => {
    const html = renderToStaticMarkup(
      <PricingPortionsFields mode="single" rows={[]} currency="AED" errors={[]} onMode={() => undefined} onRows={() => undefined} />,
    );
    expect(html).toContain("Pricing &amp; Portions");
    expect(html).toContain("Single price");
    expect(html).toContain("without asking for a portion");
    expect(html).not.toContain("Add price option");
  });

  it("shows named portions, edit fields, and the add control", () => {
    const html = renderToStaticMarkup(
      <PricingPortionsFields
        mode="portions"
        currency="AED"
        errors={[{ key: "1.name", message: "Option name is required." }]}
        onMode={() => undefined}
        onRows={() => undefined}
        rows={[
          { id: "small", name: "Small Plate", price: "3.00", active: true },
          { name: "", price: "5.00", active: false },
        ]}
      />,
    );
    expect(html).toContain("Small Plate");
    expect(html).toContain("3.00");
    expect(html).toContain("Add price option");
    expect(html).toContain("Portion 1 name");
    expect(html).toContain("Portion 2 active");
    expect(html).toContain("Remove portion 1");
    expect(html).toContain("Move portion 2 up");
    expect(html).toContain("Option name is required.");
    expect(html).toContain("AED");
  });
});
