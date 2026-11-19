import type { Availability, PharmacyProductDetail, Product } from "@ai-pos/shared-types";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { DetailsTab, ProductDetailDrawer } from "./ProductDetailDrawer";
import type { Resource } from "./useProductDetails";

vi.mock("../../lib/auth", () => ({
  useAuth: () => ({ can: () => false }),
}));

vi.mock("../../lib/capabilities", () => ({
  useCapabilities: () => ({ has: () => false }),
}));

vi.mock("../../lib/api", () => ({
  apiGet: vi.fn(() => new Promise(() => undefined)),
}));

vi.mock("./useProductDetails", () => ({
  useProductDetails: () => ({
    product: { state: "loading" },
    availability: {
      state: "ready",
      data: { branches: [], serial: null },
    },
    purchases: { state: "loading" },
    costing: { state: "loading" },
    sales: { state: "loading" },
    serials: { state: "loading" },
    movements: { state: "loading" },
    reload: () => undefined,
  }),
}));

const product: Product = {
  id: "ad4a5ebe-9cdd-49f9-9787-910fc68009fe",
  store_id: "00000000-0000-4000-8000-000000000001",
  sku: "PAN-ACCEPT",
  barcode: "2006908574245",
  name: "Panadol Accept 500",
  brand: "Acme",
  category: "Over-the-Counter Medicines",
  price_cents: 450,
  currency: "USD",
  is_serialized: false,
  stock_quantity: 0,
  created_at: "2026-11-18T00:00:00Z",
  updated_at: "2026-11-18T00:00:00Z",
};

const ready: Resource<Availability> = {
  state: "ready",
  data: {
    product: { id: product.id, sku: product.sku, name: product.name, is_serialized: false },
    branches: [],
    serial: null,
  },
};
const loading: Resource<never> = { state: "loading" };

const pharmacy: PharmacyProductDetail = {
  product_id: product.id,
  name: product.name,
  sku: product.sku,
  barcode: product.barcode,
  brand: "Acme",
  category: "Over-the-Counter Medicines",
  sub_category: "",
  price_cents: 450,
  tax_category: "STANDARD",
  is_active: true,
  updated_at: "2026-11-18T00:00:00Z",
  product_kind: "MEDICINE",
  dispensing_class: "OTC",
  classification_source: "TENANT_DECLARED",
  generic_name: "Paracetamol",
  manufacturer: "Acme Pharma",
  marketing_authorization_holder: "",
  country_of_origin: "AE",
  description: "",
  gtin: "01234567890128",
  manufacturer_product_ref: "",
  dosage_form: "tablet",
  route: "Oral",
  strength_amount: "500",
  strength_unit: "mg",
  strength_display: "500 mg",
  concentration: "",
  pack_size_label: "Box of 10",
  units_per_pack: 10,
  base_unit_code: "PIECE",
  selling_unit_code: "BOX_10",
  dispense_unit_code: "PIECE",
  storage_condition: "",
  temp_min_c: null,
  temp_max_c: null,
  cold_chain: false,
  handling_instructions: "",
  warnings_text: "",
  registration_number: null,
  registration_authority: null,
  price_control: "MINIMUM",
  min_price_cents: null,
  max_price_cents: null,
  discount_eligible: true,
  promotion_eligible: true,
  official_price_state: "MISSING",
  sale_blocked: true,
  offline_policy: "BLOCK",
  ingredients: [
    { id: "ing-1", position: 0, name: "Paracetamol", strength_amount: "500", strength_unit: "mg", is_active_ingredient: true },
    { id: "ing-2", position: 1, name: "Caffeine", strength_amount: "65", strength_unit: "mg", is_active_ingredient: true },
  ],
  documents: [],
  lot_on_product_master: false,
};

function details(detail: PharmacyProductDetail | null | undefined) {
  return renderToStaticMarkup(
    <MemoryRouter>
      <DetailsTab
        product={product}
        availability={ready}
        purchases={loading}
        costing={loading}
        canManagePhotos={false}
        {...(detail === undefined ? {} : { pharmacy: detail })}
      />
    </MemoryRouter>,
  );
}

describe("product detail drawer pharmacy section", () => {
  it("renders the drawer without a pharmacy section when the catalogue module is off", () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <ProductDetailDrawer
          product={product}
          closing={false}
          escapeEnabled={false}
          refreshKey={0}
          onClose={() => undefined}
          onEdit={null}
        />
      </MemoryRouter>,
    );
    expect(html).toContain("Panadol Accept 500");
    expect(html).toContain("PAN-ACCEPT");
    expect(html).toContain("Specifications");
    expect(html).not.toContain(">Pharmacy<");
    expect(html).not.toContain("Manufacturer lot and expiry are stock-batch facts");
  });

  it("renders saved pharmacy metadata only when the detail prop is present", () => {
    const html = details(pharmacy);
    expect(html).toContain(">Pharmacy<");
    expect(html).toContain("Paracetamol 500 mg");
    expect(html).toContain("Caffeine 65 mg");
    expect(html).toContain("Acme Pharma");
    expect(html).toContain("01234567890128");
    expect(html).toContain("Box of 10");
    expect(html).toContain("Missing — a sale that requires this price stays blocked");
    expect(html).toContain("Manufacturer lot and expiry are stock-batch facts. They are not stored on this product.");
    expect(html).toContain("Specifications");
  });

  it("keeps the existing details when pharmacy detail is missing or still loading", () => {
    for (const detail of [null, undefined]) {
      const html = details(detail);
      expect(html).toContain("Specifications");
      expect(html).toContain("2006908574245");
      expect(html).not.toContain(">Pharmacy<");
    }
  });
});
