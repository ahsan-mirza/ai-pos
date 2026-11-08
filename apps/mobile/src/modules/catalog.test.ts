/// <reference types="jest" />
import { breakpointOf, gridColumns } from "@/hooks/breakpoints";
import { unpackCache } from "@/api/cacheFormat";
import { collectRows, recordTitle, unwrapProductHits } from "@/modules/records";
import { parseErrorBody } from "@/api/errors";
import { modules } from "@/modules/catalog";
import { moduleVisible } from "@/modules/access";
import { parityFor, parityIds } from "@/modules/parity";
import { Permission, PROFILE_PRESETS, profileAllows } from "@ai-pos/shared-types";

const portalRoutes = [
  "/",
  "/insights",
  "/sales-insights",
  "/assistant",
  "/m",
  "/customers",
  "/returns",
  "/payments",
  "/promotions",
  "/store-credit",
  "/gift-cards",
  "/margin",
  "/shifts",
  "/sales/quotations",
  "/sales-orders",
  "/deliveries/:noteId",
  "/reorders",
  "/cheques",
  "/consignment",
  "/repairs",
  "/warranties",
  "/trade-ins",
  "/rentals",
  "/inventory/stock",
  "/inventory/products",
  "/inventory/categories",
  "/inventory/brands",
  "/inventory/models",
  "/inventory/units",
  "/inventory/pricing",
  "/inventory/price-lists",
  "/inventory/price-changes",
  "/inventory/purchase-orders",
  "/inventory/batches",
  "/inventory/replenishment",
  "/inventory/counts",
  "/inventory/transfers",
  "/inventory/expiring",
  "/inventory/waste",
  "/inventory/serials",
  "/inventory/markdowns",
  "/inventory/size-curve",
  "/inventory/modifiers",
  "/inventory/meals",
  "/inventory/floor-plan",
  "/inventory/reservations",
  "/inventory/kitchen",
  "/inventory/recipes",
  "/inventory/recipe-usage",
  "/inventory/kitchen-agent",
  "/payables",
  "/expenses",
  "/accounting",
  "/bank",
  "/reports/vat",
  "/reports/exports",
  "/reports/management",
  "/reports/cancellations",
  "/analytics/deep",
  "/reports/tips",
  "/einvoicing",
  "/reach",
  "/users",
  "/roles",
  "/staff",
  "/settings",
  "/stores",
  "/settings/addons",
  "/settings/addon-access",
  "/subscription",
  "/registers",
  "/downloads",
  "/settings/currencies",
  "/settings/channels",
  "/delivery",
  "/settings/audit-logs",
  "/account",
];

describe("responsive breakpoints", () => {
  it("classifies widths from the shared scale", () => {
    expect(breakpointOf(320)).toBe("smallPhone");
    expect(breakpointOf(390)).toBe("phone");
    expect(breakpointOf(480)).toBe("largePhone");
    expect(breakpointOf(768)).toBe("tablet");
    expect(breakpointOf(1024)).toBe("largeTablet");
  });

  it("uses one column on a small phone and more on a tablet", () => {
    expect(gridColumns(320)).toBe(1);
    expect(gridColumns(390)).toBe(2);
    expect(gridColumns(1024)).toBe(4);
  });
});

describe("records", () => {
  it("reads list payloads and summary numbers", () => {
    const collected = collectRows({ rows: [{ id: "1", name: "Tea" }], units_on_hand: 4 }, null);
    expect(collected.rows).toHaveLength(1);
    expect(collected.summary?.units_on_hand).toBe(4);
    expect(recordTitle(collected.rows[0] ?? {})).toBe("Tea");
  });

  it("unwraps barcode search hits to products", () => {
    const collected = unwrapProductHits([{ product: { id: "p1", name: "Rice", plu_code: "1234" }, match: "identifier" }]);
    expect(collected.rows[0]?.name).toBe("Rice");
    expect(collected.rows[0]?.plu_code).toBe("1234");
  });

  it("parses the API error envelope", () => {
    const error = parseErrorBody(422, { error: { message: "Invalid", code: "invalid", field_errors: { name: "Required" } } });
    expect(error.message).toBe("Invalid");
    expect(error.fieldErrors?.name).toBe("Required");
  });
});

describe("portal inventory", () => {
  it("covers every business portal route", () => {
    const routes = new Set(modules.map((item) => item.webRoute));
    for (const route of portalRoutes) expect(routes.has(route)).toBe(true);
  });

  it("hides a module the role cannot open", () => {
    const products = modules.find((item) => item.id === "products");
    expect(products).toBeDefined();
    if (!products) return;
    expect(
      moduleVisible(products, {
        can: () => false,
        superAdmin: false,
        storeId: null,
        profile: "grocery",
        capabilities: [],
        capabilitiesKnown: true,
        profileReady: true,
      }),
    ).toBe(false);
    expect(
      moduleVisible(products, {
        can: (permission) => permission === Permission.PortalAccess,
        superAdmin: false,
        storeId: null,
        profile: "grocery",
        capabilities: [],
        capabilitiesKnown: true,
        profileReady: true,
      }),
    ).toBe(true);
  });

  it("classifies every overridden route and keeps write screens incomplete", () => {
    const ids = new Set(modules.map((item) => item.id));
    for (const id of parityIds()) expect(ids.has(id)).toBe(true);
    const customers = modules.find((item) => item.id === "customers");
    const floor = modules.find((item) => item.id === "floor-plan");
    const kitchen = modules.find((item) => item.id === "kitchen");
    expect(customers && parityFor(customers).status).toBe("native-partial-write");
    expect(floor && parityFor(floor).status).toBe("specialized-web");
    expect(kitchen && parityFor(kitchen).status).toBe("device-or-public");
    const sales = modules.find((item) => item.id === "sales");
    expect(sales && parityFor(sales).status).toBe("native-read");
  });
});

describe("business type defaults", () => {
  it("turns B2B credit on for electronics and leaves grocery, fashion and restaurants off until configured", () => {
    expect(PROFILE_PRESETS.electronics_wholesale.capabilities).toContain("b2b_credit");
    expect(PROFILE_PRESETS.grocery.capabilities).not.toContain("b2b_credit");
    expect(PROFILE_PRESETS.retail_fashion.capabilities).not.toContain("b2b_credit");
    expect(PROFILE_PRESETS.restaurant.capabilities).not.toContain("b2b_credit");
    expect(PROFILE_PRESETS.cafe.capabilities).not.toContain("b2b_credit");
    expect(profileAllows("grocery", "b2b_credit")).toBe(true);
    expect(profileAllows("retail_fashion", "b2b_credit")).toBe(true);
    expect(profileAllows("restaurant", "b2b_credit")).toBe(false);
    expect(profileAllows("cafe", "b2b_credit")).toBe(false);
  });
});

describe("read cache", () => {
  it("keeps a timestamp on new entries and still reads an older payload", () => {
    expect(unpackCache({ savedAt: "2026-11-08T12:00:00.000Z", value: { rows: [] } })?.savedAt).toBe("2026-11-08T12:00:00.000Z");
    expect(unpackCache({ rows: [{ id: "1" }] })?.savedAt).toBe("");
    expect(unpackCache({ rows: [{ id: "1" }] })?.value).toEqual({ rows: [{ id: "1" }] });
  });
});
