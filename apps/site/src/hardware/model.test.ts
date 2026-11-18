import { describe, expect, it } from "vitest";
import { enquiryErrors, hardwareView, productJsonLd, readProduct, segmentProducts, type HardwareProduct } from "./model";

const terminal: HardwareProduct = {
  slug: "ax-15",
  name: "AX-15",
  sku: "AX-15",
  brand: "Axiz",
  model_number: "15",
  short_description: "Counter terminal",
  full_description: "A published terminal.",
  display_price_fils: 189900,
  currency: "AED",
  warranty_months: 12,
  stock_status: "in_stock",
  compatibility: "Restaurant and café counters",
  is_featured: true,
  category_slug: "terminals",
  category_name: "POS Touchscreen Terminals",
  specifications: [{ label: "Screen", value: "15 inch" }],
  images: [{ url: "https://cdn.example/ax.webp", thumb_url: "https://cdn.example/ax-thumb.webp", alt: "AX-15 terminal", is_primary: true }],
};

describe("public hardware catalogue", () => {
  it("reads a published product and drops a purchase price if one is ever present", () => {
    const product = readProduct({ ...terminal, purchase_price_fils: 100 });
    expect(product?.display_price_fils).toBe(189900);
    expect(product && "purchase_price_fils" in product).toBe(false);
  });

  it("routes product and package URLs", () => {
    expect(hardwareView("/hardware")).toEqual({ kind: "catalog" });
    expect(hardwareView("/hardware/products/ax-15")).toEqual({ kind: "product", slug: "ax-15" });
    expect(hardwareView("/hardware/packages/all-in-one/")).toEqual({ kind: "package", slug: "all-in-one" });
  });

  it("recommends a segment only from catalogue text", () => {
    expect(segmentProducts([terminal]).map((item) => item.title)).toEqual(["Restaurant & Café"]);
    expect(segmentProducts([{ ...terminal, compatibility: "", category_name: "Scanners", category_slug: "scanners" }])).toEqual([]);
  });

  it("adds product structured data only when a public price exists", () => {
    const linked = productJsonLd(terminal, "https://axizpos.com/hardware/products/ax-15");
    expect(linked?.offers).toMatchObject({ price: "1899.00", priceCurrency: "AED", availability: "https://schema.org/InStock" });
    expect(productJsonLd({ ...terminal, display_price_fils: null }, "https://axizpos.com/hardware")).toBeNull();
  });

  it("rejects an incomplete enquiry before it is sent", () => {
    const errors = enquiryErrors({
      customer_name: "A",
      business_name: "Cafe",
      email: "not-an-email",
      phone: "050",
      country: "UAE",
      business_type: "cafe",
      product_slug: "",
      package_slug: "",
      quantity: "0",
      message: "short",
    });
    expect(errors.email).toBeTruthy();
    expect(errors.phone).toBeTruthy();
    expect(errors.message).toBeTruthy();
  });
});
