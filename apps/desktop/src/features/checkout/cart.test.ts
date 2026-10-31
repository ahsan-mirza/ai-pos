import {
  comboChoiceOf,
  comboDefaults,
  comboSelectionError,
  comboSummary,
  type ComboSlot,
  type ProductUpsert,
} from "@ai-pos/shared-types";
import { describe, expect, it } from "vitest";
import type { RegisterCustomer } from "../../lib/tauri";
import {
  GIFT_CARD_SKU,
  applyCart,
  cartRows,
  cartTotals,
  emptyCart,
  lineCharge,
  lineGross,
  manualDiscountCents,
  type CartAction,
  type CartState,
} from "./cart";
import { planTenders, emptyPayment } from "./tenders";

const cable: ProductUpsert = {
  id: "cable",
  store_id: "store",
  sku: "ACC-CABLE-USBC",
  barcode: "100000000001",
  name: "USB-C Cable",
  category: "Accessories",
  price_cents: 1500,
  currency: "USD",
  is_serialized: false,
  stock_quantity: 500,
  sellable_units: ["PIECE", "BOX_10"],
  prices: [
    {
      price_tier: "TIER_1",
      price_cents: 1200,
      min_order_quantity: 5,
      volume_discounts: [{ min_qty: 25, price_cents: 1000 }],
    },
  ],
};

const phone: ProductUpsert = {
  ...cable,
  id: "phone",
  sku: "PHN-PIXEL-9",
  name: "Pixel 9",
  price_cents: 79900,
  is_serialized: true,
  stock_quantity: 0,
  sellable_units: ["PIECE"],
  prices: [{ price_tier: "TIER_1", price_cents: 74900, min_order_quantity: 2, volume_discounts: [] }],
};

const wholesaleCustomer: RegisterCustomer = {
  id: "customer",
  code: "ALNR-0001",
  name: "Omar Haddad",
  phone: null,
  email: null,
  customer_type: "WHOLESALE",
  company_name: "Al Noor Mobiles LLC",
  trn_vat_number: null,
  price_tier: "TIER_1",
  credit_limit_cents: 50_000,
  current_balance_cents: 20_000,
  available_credit_cents: 30_000,
  payment_terms: "NET_30",
  address: null,
  is_active: true,
  overdue_cents: 0,
  open_invoice_count: 1,
  created_at: "",
  updated_at: "",
};

function run(...actions: CartAction[]): CartState {
  return actions.reduce((state, action) => {
    const result = applyCart(state, action);
    expect(result.error).toBeNull();
    return result.state;
  }, emptyCart);
}

const meal: ProductUpsert = { ...cable, id: "meal", sku: "MEAL-1", name: "Burger Meal", price_cents: 2500, is_service: true, prices: [] };
const mealSlots: ComboSlot[] = [
  {
    id: "main",
    name: "Main",
    min_select: 1,
    max_select: 1,
    position: 0,
    options: [{ product_id: "burger", name: "Burger", category: "Mains", price_cents: 1800, surcharge_cents: 0, is_default: true, position: 0 }],
  },
  {
    id: "side",
    name: "Side",
    min_select: 1,
    max_select: 1,
    position: 1,
    options: [
      { product_id: "fries", name: "Fries", category: "Sides", price_cents: 900, surcharge_cents: 0, is_default: true, position: 0 },
      { product_id: "rings", name: "Onion rings", category: "Sides", price_cents: 1100, surcharge_cents: 300, is_default: false, position: 1 },
    ],
  },
];

describe("selling quantity", () => {
  it("adds the quantity typed when a product is tapped", () => {
    const state = run({ type: "add_product", product: cable, quantity: 4 });
    expect(state.lines[0]?.quantity).toBe(4);
    const more = applyCart(state, { type: "add_product", product: cable, quantity: 2 }).state;
    expect(more.lines[0]?.quantity).toBe(6);
  });

  it("sells an open-price item without a description", () => {
    const labour: ProductUpsert = { ...cable, id: "labour", sku: "SRV-LABOUR", name: "Repair labour", is_open_price: true, price_cents: 0 };
    const refused = applyCart(emptyCart, { type: "add_open_price", product: labour, unitPriceCents: 2500, description: "", quantity: 0 });
    expect(refused.error).toBe("Quantity must be at least 1.");
    const state = run({ type: "add_open_price", product: labour, unitPriceCents: 2500, description: "", quantity: 3 });
    expect(state.lines[0]?.description).toBeUndefined();
    expect(state.lines[0]?.quantity).toBe(3);
    expect(state.lines[0]?.unitPriceCents).toBe(2500);
  });
});

describe("meals", () => {
  it("preselects defaults and validates every slot", () => {
    const defaults = comboDefaults(mealSlots);
    expect(defaults.map((part) => part.name)).toEqual(["Burger", "Fries"]);
    expect(comboSelectionError(mealSlots, defaults)).toBeNull();
    expect(comboSelectionError(mealSlots, defaults.slice(0, 1))).toBe("Choose a side.");
    expect(comboSummary(defaults)).toBe("Burger, Fries");
  });

  it("prices surcharges into the line and never merges meal lines", () => {
    const rings = [comboChoiceOf(mealSlots[0]!, mealSlots[0]!.options[0]!), comboChoiceOf(mealSlots[1]!, mealSlots[1]!.options[1]!)];
    const state = run(
      { type: "add_product", product: meal, components: comboDefaults(mealSlots) },
      { type: "add_product", product: meal, components: rings },
    );
    expect(state.lines.map((line) => line.unitPriceCents)).toEqual([2500, 2800]);
    expect(state.lines[1]?.components?.map((part) => part.name)).toEqual(["Burger", "Onion rings"]);
  });
});

describe("cashier discounts and gift cards", () => {
  const staff = { reason: "staff", reasonLabel: "Staff discount", approvedById: null, approverName: null, note: "" };

  it("takes a percent or an amount off the line and the totals", () => {
    const start = run({ type: "add_product", product: cable }, { type: "add_product", product: cable });
    const lineId = start.lines[0]?.lineId ?? "";
    const percent = start;
    const discounted = applyCart(percent, {
      type: "set_discounts",
      discounts: [{ lineId: percent.lines[0]?.lineId ?? "", discount: { mode: "percent", value: 1000, ...staff } }],
    }).state;
    expect(manualDiscountCents(discounted.lines[0]!)).toBe(300);
    const noTax = { enforced: false, prices_include_vat: false, standard_rate_bps: 0 };
    expect(cartTotals(discounted.lines, noTax).total).toBe(cartTotals(percent.lines, noTax).total - 300);
    const amount = applyCart(start, {
      type: "set_discounts",
      discounts: [{ lineId, discount: { mode: "amount", value: 99_999, ...staff } }],
    }).state;
    expect(manualDiscountCents(amount.lines[0]!)).toBe(3000);
    const cleared = applyCart(amount, { type: "clear_discounts", lineIds: [lineId] }).state;
    expect(manualDiscountCents(cleared.lines[0]!)).toBe(0);
  });

  it("sells a gift card as its own line that cannot be discounted", () => {
    const card: ProductUpsert = { ...cable, id: "gift", sku: GIFT_CARD_SKU, name: "Gift card", is_service: true, prices: [] };
    const state = run({ type: "add_gift_card", product: card, amountCents: 20_000, code: "GC-AAAA-BBBB-CCCC" });
    expect(state.lines[0]?.giftCardCode).toBe("GC-AAAA-BBBB-CCCC");
    expect(state.lines[0]?.unitPriceCents).toBe(20_000);
    const refused = applyCart(state, {
      type: "set_discounts",
      discounts: [{ lineId: state.lines[0]?.lineId ?? "", discount: { mode: "percent", value: 1000, ...staff } }],
    });
    expect(refused.error).toContain("cannot be discounted");
    expect(applyCart(emptyCart, { type: "add_product", product: card }).error).not.toBeNull();
  });
});

describe("cart pricing", () => {
  it("prices at retail in retail mode", () => {
    const state = run({ type: "add_product", product: cable });
    expect(state.lines[0]?.unitPriceCents).toBe(1500);
  });

  it("attaching a wholesale customer switches mode and applies the tier", () => {
    const state = run(
      { type: "add_product", product: cable, unitType: "BOX_10" },
      { type: "attach_customer", customer: wholesaleCustomer },
    );
    expect(state.mode).toBe("WHOLESALE");
    expect(state.lines[0]?.unitPriceCents).toBe(1200);
    expect(state.lines[0]?.priceSource).toBe("tier");
  });

  it("applies the bulk price once quantity crosses the break", () => {
    const start = run({ type: "set_mode", mode: "WHOLESALE" }, { type: "add_product", product: cable });
    const lineId = start.lines[0]?.lineId ?? "";
    expect(start.lines[0]?.unitPriceCents).toBe(1500);
    expect(start.lines[0]?.moqShortfall).toBe(4);
    const bulk = applyCart(start, { type: "set_packs", lineId, packs: 25 }).state;
    expect(bulk.lines[0]?.unitPriceCents).toBe(1000);
    expect(bulk.lines[0]?.priceSource).toBe("volume");
  });

  it("switching to cartons keeps whole packs and stays within stock", () => {
    const state = run({ type: "add_product", product: cable });
    const lineId = state.lines[0]?.lineId ?? "";
    const boxed = applyCart(state, { type: "set_unit", lineId, unitType: "BOX_10" }).state;
    expect(boxed.lines[0]?.quantity).toBe(10);
    const refused = applyCart(boxed, { type: "set_packs", lineId, packs: 51 });
    expect(refused.error).toContain("in stock");
    const carton = applyCart(boxed, { type: "set_unit", lineId, unitType: "CARTON_100" });
    expect(carton.error).toContain("not sold that way");
  });

  it("counts a business's own pack by the factor the product carries", () => {
    const water: ProductUpsert = {
      ...cable,
      id: "water",
      name: "Water 500 ml",
      prices: [],
      stock_quantity: 60,
      sellable_units: ["PIECE", "CASE_24"],
      unit_options: [
        { code: "PIECE", name: "Piece", short_name: "Pcs", factor: 1 },
        { code: "CASE_24", name: "Case of 24", short_name: "Case", factor: 24 },
      ],
    };
    const state = run({ type: "add_product", product: water, unitType: "CASE_24" });
    expect(state.lines[0]?.quantity).toBe(24);
    const lineId = state.lines[0]?.lineId ?? "";
    expect(applyCart(state, { type: "set_packs", lineId, packs: 2 }).state.lines[0]?.quantity).toBe(48);
    expect(applyCart(state, { type: "set_packs", lineId, packs: 3 }).error).toContain("in stock");
  });

  it("keeps a manager override through repricing", () => {
    const state = run({ type: "add_product", product: cable });
    const lineId = state.lines[0]?.lineId ?? "";
    const kept = applyCart(state, {
      type: "override_price",
      lineIds: [lineId],
      override: { approvedById: "manager", approverName: "Mona", note: "match", unitPriceCents: 1100 },
    }).state;
    const repriced = applyCart(kept, { type: "set_mode", mode: "WHOLESALE" }).state;
    expect(repriced.lines[0]?.unitPriceCents).toBe(1100);
    expect(repriced.lines[0]?.listPriceCents).toBe(1500);
  });

  it("groups bulk IMEIs and prices serialized units by the product total", () => {
    const state = run(
      { type: "set_mode", mode: "WHOLESALE" },
      {
        type: "add_serials",
        product: phone,
        serials: [
          { value: "356938035643809", kind: "imei" },
          { value: "490154203237518", kind: "imei" },
        ],
      },
    );
    expect(cartRows(state.lines)).toHaveLength(1);
    expect(state.lines.every((line) => line.unitPriceCents === 74900)).toBe(true);
    const duplicate = applyCart(state, {
      type: "add_serials",
      product: phone,
      serials: [{ value: "356938035643809", kind: "imei" }],
    });
    expect(duplicate.error).not.toBeNull();
  });

  it("prices a customized line from its modifiers and keeps the preparation note when copied", () => {
    const cheese = { group_id: "g", option_id: "o", group: "Cheese", option: "Cheddar", price_delta_cents: 300 };
    const added = applyCart(emptyCart, {
      type: "add_product",
      product: cable,
      modifiers: [cheese],
      quantity: 2,
      instruction: "No onions",
    });
    expect(added.error).toBeNull();
    expect(added.state.lines[0]?.unitPriceCents).toBe(1800);
    expect(added.state.lines[0]?.instruction).toBe("No onions");
    const plain = applyCart(added.state, { type: "add_product", product: cable });
    expect(plain.state.lines).toHaveLength(2);
    const lineId = added.state.lines[0]?.lineId ?? "";
    const copy = applyCart(added.state, { type: "duplicate_line", lineId });
    expect(copy.state.lines).toHaveLength(2);
    expect(copy.state.lines[1]?.modifiers?.[0]?.option).toBe("Cheddar");
    expect(copy.state.lines[1]?.instruction).toBe("No onions");
    expect(copy.state.lines[1]?.unitPriceCents).toBe(1800);
    const edited = applyCart(added.state, {
      type: "set_customization",
      lineId,
      modifiers: [cheese],
      quantity: 1,
      instruction: "Sauce on the side",
    });
    expect(edited.state.lines[0]?.quantity).toBe(1);
    expect(edited.state.lines[0]?.instruction).toBe("Sauce on the side");
  });

  it("keeps a plain burger apart from a customized one and prices each modifier once", () => {
    const burger: ProductUpsert = { ...cable, id: "burger", name: "Chicken Patty Burger", price_cents: 10_000, stock_quantity: 20 };
    const cheese = { group_id: "cheese", option_id: "cheddar", group: "Add-ons", option: "Extra Cheese", price_delta_cents: 1_000 };
    const sauce = { group_id: "sauce", option_id: "bbq", group: "Sauces", option: "Extra Sauce", price_delta_cents: 500 };
    const customized = applyCart(emptyCart, { type: "add_product", product: burger, quantity: 2, modifiers: [cheese, sauce] });
    expect(customized.error).toBeNull();
    expect(customized.state.lines[0]?.unitPriceCents).toBe(11_500);
    expect(lineGross(customized.state.lines[0]!)).toBe(23_000);
    const plain = applyCart(customized.state, { type: "add_product", product: burger });
    expect(plain.state.lines).toHaveLength(2);
    expect(plain.state.lines[1]?.modifiers).toBeUndefined();
    expect(lineGross(plain.state.lines[1]!)).toBe(10_000);
    const removed = applyCart(plain.state, { type: "remove_line", lineId: customized.state.lines[0]!.lineId });
    expect(removed.state.lines).toHaveLength(1);
    expect(removed.state.lines[0]?.modifiers).toBeUndefined();
  });
});

describe("tenders", () => {
  it("splits a deposit and the balance on account", () => {
    const state = run({ type: "attach_customer", customer: wholesaleCustomer }, { type: "add_product", product: cable });
    const total = cartTotals(state.lines, { enforced: false, prices_include_vat: false, standard_rate_bps: 0 }).total;
    const plan = planTenders({ ...emptyPayment, choice: "on_account", deposit: "5.00" }, total, state.customer);
    expect(plan.tenders).toEqual([
      { method: "cash", amount_cents: 500, reference: "" },
      { method: "on_account", amount_cents: total - 500, reference: "" },
    ]);
    expect(plan.paymentMethod).toBe("on_account");
    expect(plan.overLimitCents).toBe(0);
  });

  it("flags sales that would exceed the credit limit", () => {
    const plan = planTenders({ ...emptyPayment, choice: "on_account" }, 40_000, wholesaleCustomer);
    expect(plan.overLimitCents).toBe(10_000);
  });

  it("requires a wholesale customer for on-account sales", () => {
    const plan = planTenders({ ...emptyPayment, choice: "on_account" }, 1000, null);
    expect(plan.blocker).not.toBeNull();
  });
});

describe("price includes tax", () => {
  const policy = { enforced: true, prices_include_vat: true, standard_rate_bps: 500 };

  it("extracts tax from an inclusive price and adds it to an exclusive one", () => {
    const inclusive = run({ type: "add_product", product: { ...cable, id: "in", price_cents: 10_000, price_includes_tax: true } });
    const exclusive = run({ type: "add_product", product: { ...cable, id: "ex", price_cents: 10_000, price_includes_tax: false } });
    expect(lineCharge(inclusive.lines[0]!, policy)).toMatchObject({ net_cents: 9524, tax_cents: 476, line_total_cents: 10_000 });
    expect(lineCharge(exclusive.lines[0]!, policy)).toMatchObject({ net_cents: 10_000, tax_cents: 500, line_total_cents: 10_500 });
    const mixed = cartTotals([...inclusive.lines, ...exclusive.lines], policy);
    expect(mixed).toMatchObject({ subtotal: 19524, tax: 976, inclusiveTax: 476, exclusiveTax: 500, total: 20500 });
  });

  it("takes a percent discount off the inclusive price before extracting tax", () => {
    const start = run({ type: "add_product", product: { ...cable, price_cents: 10_000, price_includes_tax: true } });
    const discounted = applyCart(start, {
      type: "set_discounts",
      discounts: [
        {
          lineId: start.lines[0]!.lineId,
          discount: { mode: "percent", value: 1000, reason: "staff", reasonLabel: "Staff", approvedById: null, approverName: null, note: "" },
        },
      ],
    }).state;
    expect(lineCharge(discounted.lines[0]!, policy)).toMatchObject({ net_cents: 8571, tax_cents: 429, line_total_cents: 9000 });
  });

  it("charges no tax on a zero-rated inclusive price", () => {
    const state = run({
      type: "add_product",
      product: { ...cable, price_cents: 10_000, price_includes_tax: true, tax_category: "ZERO" },
    });
    expect(lineCharge(state.lines[0]!, policy)).toMatchObject({ net_cents: 10_000, tax_cents: 0, line_total_cents: 10_000 });
  });
});
