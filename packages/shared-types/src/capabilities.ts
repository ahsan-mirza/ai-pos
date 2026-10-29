/**
 * Business profiles and the capabilities they switch on. Code checks capabilities, never profiles: a profile is only
 * the preset a merchant starts from. Mirrored by apps/api/app/core/capabilities.py (a test keeps the two in step).
 */

export const Capability = {
  SerialTracking: "serial_tracking",
  WholesalePricing: "wholesale_pricing",
  B2bCredit: "b2b_credit",
  QuotesLayaway: "quotes_layaway",
  MultiCurrency: "multi_currency",
  Cheques: "cheques",
  Repairs: "repairs",
  Warranty: "warranty",
  TradeIn: "trade_in",
  Loyalty: "loyalty",
  Promotions: "promotions",
  VariantsMatrix: "variants_matrix",
  Consignment: "consignment",
  WeighedItems: "weighed_items",
  Fefo: "fefo",
  MenuModifiers: "menu_modifiers",
  OpenOrders: "open_orders",
  Tables: "tables",
  Kds: "kds",
  Recipes: "recipes",
  SplitBills: "split_bills",
  TipsServiceCharge: "tips_service_charge",
  DeliveryChannels: "delivery_channels",
  SalesOrders: "sales_orders",
  CardTerminals: "card_terminals",
  Bnpl: "bnpl",
  GiftCards: "gift_cards",
  TaxFree: "tax_free",
  Alterations: "alterations",
  OnlineStore: "online_store",
  CustomerReorders: "customer_reorders",
  DeepAnalytics: "deep_analytics",
} as const;
export type Capability = (typeof Capability)[keyof typeof Capability];

export type CapabilityGroup = "selling" | "inventory" | "customers" | "service" | "food_beverage";

export interface CapabilitySpec {
  id: Capability;
  label: string;
  description: string;
  group: CapabilityGroup;
  /** False while the module is still on the roadmap: it can be planned but never enabled. */
  available: boolean;
  requires: readonly Capability[];
}

export const CAPABILITY_GROUP_LABELS: Record<CapabilityGroup, string> = {
  selling: "Selling",
  inventory: "Inventory",
  customers: "Customers & credit",
  service: "Service",
  food_beverage: "Food & Beverage",
};

export const CAPABILITIES: readonly CapabilitySpec[] = [
  { id: "wholesale_pricing", label: "Wholesale mode & tier pricing", description: "Retail/wholesale toggle at the register, price tiers and volume breaks.", group: "selling", available: true, requires: [] },
  { id: "quotes_layaway", label: "Quotations, holds & layaway", description: "Proforma quotes, items held for a customer with a deposit, and layaway pickups.", group: "selling", available: true, requires: [] },
  { id: "promotions", label: "Promotions", description: "Automatic discounts and bundle offers at checkout.", group: "selling", available: true, requires: [] },
  { id: "multi_currency", label: "Foreign currency cash", description: "Accept cash in other currencies at live exchange rates.", group: "selling", available: true, requires: [] },
  { id: "serial_tracking", label: "IMEI / serial tracking", description: "Scan and trace individual units by IMEI or serial number.", group: "inventory", available: true, requires: [] },
  { id: "variants_matrix", label: "Size & colour matrix", description: "Create and sell product grids by size, colour and style.", group: "inventory", available: true, requires: [] },
  { id: "consignment", label: "Consignment stock", description: "Sell supplier-owned stock and settle what sold.", group: "inventory", available: true, requires: [] },
  { id: "weighed_items", label: "Weighed items & scales", description: "Sell by weight with a connected scale and price-embedded barcodes.", group: "inventory", available: true, requires: [] },
  { id: "fefo", label: "Expiry-first stock (FEFO)", description: "Sell the batch that expires soonest first, with expiry alerts.", group: "inventory", available: true, requires: [] },
  { id: "b2b_credit", label: "B2B credit accounts", description: "On-account sales, credit limits, statements and collections.", group: "customers", available: true, requires: [] },
  { id: "cheques", label: "Cheques & PDCs", description: "Take cheques and post-dated cheques and track their clearing.", group: "customers", available: true, requires: [] },
  { id: "loyalty", label: "Loyalty points", description: "Earn and redeem points on every sale.", group: "customers", available: true, requires: [] },
  { id: "repairs", label: "Repairs", description: "Repair tickets, technician workflow and parts.", group: "service", available: true, requires: [] },
  { id: "warranty", label: "Warranties", description: "Extended warranty plans and claim lookup.", group: "service", available: true, requires: [] },
  { id: "trade_in", label: "Trade-ins", description: "Buy used devices with grading and payout.", group: "service", available: true, requires: [] },
  { id: "menu_modifiers", label: "Menu modifiers", description: "Sizes, milk options, extra shots and add-ons priced per item.", group: "food_beverage", available: true, requires: [] },
  { id: "open_orders", label: "Open orders & tabs", description: "Take the order first and settle the bill later.", group: "food_beverage", available: true, requires: [] },
  { id: "tables", label: "Tables & floor plan", description: "Seat guests, track table status and move or merge tables.", group: "food_beverage", available: true, requires: ["open_orders"] },
  { id: "kds", label: "Kitchen display", description: "Route tickets to kitchen and bar screens by station.", group: "food_beverage", available: true, requires: [] },
  { id: "recipes", label: "Recipes & ingredients", description: "Deduct ingredients from stock for every item sold.", group: "food_beverage", available: true, requires: ["menu_modifiers"] },
  { id: "split_bills", label: "Split bills", description: "Split a bill by item, seat or amount.", group: "food_beverage", available: true, requires: ["open_orders"] },
  { id: "tips_service_charge", label: "Tips & service charge", description: "Add tips and an automatic service charge to bills.", group: "food_beverage", available: true, requires: ["open_orders"] },
  { id: "delivery_channels", label: "Delivery channels", description: "Orders from delivery apps alongside walk-in sales.", group: "food_beverage", available: true, requires: ["open_orders"] },
  { id: "sales_orders", label: "Sales orders & deliveries", description: "Wholesale orders picked, delivered in parts with proof of delivery, and invoiced per delivery.", group: "selling", available: true, requires: [] },
  { id: "card_terminals", label: "Integrated card terminals", description: "Send the amount to the card machine and confirm the payment automatically; refunds go back to the card.", group: "selling", available: true, requires: [] },
  { id: "bnpl", label: "Buy now, pay later (Tabby, Tamara)", description: "Instalment checkout at the till on the customer's phone, captured and refunded through the provider.", group: "selling", available: true, requires: [] },
  { id: "gift_cards", label: "Gift cards", description: "Sell gift cards at the till and accept them as payment at every branch.", group: "selling", available: true, requires: [] },
  { id: "tax_free", label: "Tax-free for tourists", description: "Issue tax-free forms to tourists and report the refunds in VAT box 2.", group: "customers", available: true, requires: [] },
  { id: "alterations", label: "Alterations & tailoring", description: "Alteration tickets with measurements, due dates and a ready-for-collection message.", group: "service", available: true, requires: [] },
  { id: "online_store", label: "Online store", description: "Web-store orders (Shopify or any shop) reserve stock and are shipped or collected in store.", group: "selling", available: true, requires: [] },
  { id: "customer_reorders", label: "Customer reorder plans", description: "Recurring customer deliveries with a reminder before anyone confirms the order.", group: "customers", available: true, requires: [] },
  { id: "deep_analytics", label: "Deep analytics", description: "Sales, margin, inventory, and the reports for this business type.", group: "selling", available: true, requires: [] },
];

const SPECS = new Map(CAPABILITIES.map((spec) => [spec.id, spec]));

export function capabilitySpec(capability: Capability): CapabilitySpec {
  const spec = SPECS.get(capability);
  if (!spec) throw new Error(`Unknown capability ${capability}`);
  return spec;
}

export const CAPABILITY_DEPENDENCIES: Record<Capability, readonly Capability[]> = Object.fromEntries(
  CAPABILITIES.map((spec) => [spec.id, spec.requires]),
) as Record<Capability, readonly Capability[]>;

export const BusinessProfile = {
  ElectronicsWholesale: "electronics_wholesale",
  WholesaleRetail: "wholesale_retail",
  RetailFashion: "retail_fashion",
  Grocery: "grocery",
  Restaurant: "restaurant",
  Cafe: "cafe",
  QuickService: "quick_service",
} as const;
export type BusinessProfile = (typeof BusinessProfile)[keyof typeof BusinessProfile];

export type ProfileGroup = "retail_trade" | "food_beverage";

export interface ProfileSpec {
  id: BusinessProfile;
  label: string;
  /** Compact name for chips and the register's store line, e.g. "Electronics". */
  shortLabel: string;
  /** What the business-wide settings are called for this business type, e.g. "Restaurant settings". */
  settingsLabel: string;
  description: string;
  group: ProfileGroup;
  capabilities: readonly Capability[];
}

export const PROFILE_GROUP_LABELS: Record<ProfileGroup, string> = {
  retail_trade: "Retail & Trade",
  food_beverage: "Food & Beverage",
};

/** Spelled out rather than "everything built": grocery and restaurant modules stay out of electronics shops. */
const electronicsWholesale: Capability[] = [
  "wholesale_pricing",
  "quotes_layaway",
  "promotions",
  "multi_currency",
  "serial_tracking",
  "variants_matrix",
  "consignment",
  "b2b_credit",
  "cheques",
  "loyalty",
  "repairs",
  "warranty",
  "trade_in",
  "card_terminals",
  "bnpl",
];

const wholesaleRetail: Capability[] = [
  "wholesale_pricing",
  "sales_orders",
  "b2b_credit",
  "quotes_layaway",
  "promotions",
  "loyalty",
  "multi_currency",
  "card_terminals",
  "customer_reorders",
];

export const PROFILE_PRESETS: Record<BusinessProfile, ProfileSpec> = {
  electronics_wholesale: {
    id: "electronics_wholesale",
    label: "Electronics",
    shortLabel: "Electronics",
    settingsLabel: "Store settings",
    description: "Electronics products, IMEI and serial tracking, warranties and accessories.",
    group: "retail_trade",
    capabilities: electronicsWholesale,
  },
  wholesale_retail: {
    id: "wholesale_retail",
    label: "Wholesale & Retail",
    shortLabel: "Wholesale",
    settingsLabel: "Store settings",
    description: "Manage bulk orders, individual sales, customer pricing, inventory, and recurring customer deliveries.",
    group: "retail_trade",
    capabilities: wholesaleRetail,
  },
  retail_fashion: {
    id: "retail_fashion",
    label: "Fashion & Retail",
    shortLabel: "Fashion",
    settingsLabel: "Store settings",
    description: "Loyalty and promotions, with size and colour grids and consignment.",
    group: "retail_trade",
    capabilities: ["quotes_layaway", "loyalty", "promotions", "multi_currency", "variants_matrix", "consignment", "gift_cards"],
  },
  grocery: {
    id: "grocery",
    label: "Grocery & Supermarket",
    shortLabel: "Grocery",
    settingsLabel: "Store settings",
    description: "Fast scanning with weighed items and expiry-first stock.",
    group: "retail_trade",
    capabilities: ["loyalty", "promotions", "weighed_items", "fefo"],
  },
  restaurant: {
    id: "restaurant",
    label: "Restaurant",
    shortLabel: "Restaurant",
    settingsLabel: "Restaurant settings",
    description: "Dine-in service with tables, kitchen display and split bills.",
    group: "food_beverage",
    capabilities: [
      "loyalty",
      "promotions",
      "multi_currency",
      "tables",
      "open_orders",
      "menu_modifiers",
      "kds",
      "recipes",
      "split_bills",
      "tips_service_charge",
    ],
  },
  cafe: {
    id: "cafe",
    label: "Cafe",
    shortLabel: "Cafe",
    settingsLabel: "Cafe settings",
    description: "Counter service with drink modifiers, open tabs and a barista screen.",
    group: "food_beverage",
    capabilities: ["loyalty", "promotions", "menu_modifiers", "open_orders", "kds", "recipes"],
  },
  quick_service: {
    id: "quick_service",
    label: "Quick Service",
    shortLabel: "Quick service",
    settingsLabel: "Quick service settings",
    description: "Pay-first takeaway with kitchen routing and delivery orders.",
    group: "food_beverage",
    capabilities: ["loyalty", "promotions", "menu_modifiers", "open_orders", "kds", "recipes", "delivery_channels"],
  },
};

/**
 * Every module a business type may use. The preset is the starter set; anything else here is an optional add-on.
 * Mirrors COMPATIBLE in apps/api/app/core/capabilities.py.
 */
export const PROFILE_ELIGIBLE: Record<BusinessProfile, readonly Capability[]> = {
  electronics_wholesale: [
    "wholesale_pricing",
    "quotes_layaway",
    "promotions",
    "multi_currency",
    "b2b_credit",
    "cheques",
    "loyalty",
    "sales_orders",
    "card_terminals",
    "bnpl",
    "gift_cards",
    "tax_free",
    "online_store",
    "serial_tracking",
    "variants_matrix",
    "consignment",
    "repairs",
    "warranty",
    "trade_in",
    "deep_analytics",
  ],
  wholesale_retail: [
    "wholesale_pricing",
    "quotes_layaway",
    "promotions",
    "multi_currency",
    "b2b_credit",
    "cheques",
    "loyalty",
    "sales_orders",
    "card_terminals",
    "bnpl",
    "gift_cards",
    "tax_free",
    "online_store",
    "customer_reorders",
    "repairs",
    "deep_analytics",
  ],
  retail_fashion: [
    "wholesale_pricing",
    "quotes_layaway",
    "promotions",
    "multi_currency",
    "b2b_credit",
    "cheques",
    "loyalty",
    "sales_orders",
    "card_terminals",
    "bnpl",
    "gift_cards",
    "tax_free",
    "online_store",
    "variants_matrix",
    "consignment",
    "serial_tracking",
    "alterations",
    "deep_analytics",
  ],
  grocery: [
    "wholesale_pricing",
    "quotes_layaway",
    "promotions",
    "multi_currency",
    "b2b_credit",
    "cheques",
    "loyalty",
    "sales_orders",
    "card_terminals",
    "bnpl",
    "gift_cards",
    "tax_free",
    "online_store",
    "weighed_items",
    "fefo",
    "consignment",
    "variants_matrix",
    "deep_analytics",
  ],
  restaurant: [
    "loyalty",
    "promotions",
    "multi_currency",
    "fefo",
    "menu_modifiers",
    "open_orders",
    "tables",
    "kds",
    "recipes",
    "split_bills",
    "tips_service_charge",
    "delivery_channels",
    "card_terminals",
    "deep_analytics",
  ],
  cafe: [
    "loyalty",
    "promotions",
    "multi_currency",
    "fefo",
    "menu_modifiers",
    "open_orders",
    "tables",
    "kds",
    "recipes",
    "split_bills",
    "tips_service_charge",
    "delivery_channels",
    "card_terminals",
    "deep_analytics",
  ],
  quick_service: [
    "loyalty",
    "promotions",
    "multi_currency",
    "fefo",
    "menu_modifiers",
    "open_orders",
    "tables",
    "kds",
    "recipes",
    "split_bills",
    "tips_service_charge",
    "delivery_channels",
    "card_terminals",
    "deep_analytics",
  ],
};

export const DEFAULT_BUSINESS_PROFILE: BusinessProfile = "electronics_wholesale";

export function isBusinessProfile(value: string): value is BusinessProfile {
  return value in PROFILE_PRESETS;
}

/** True when this business type is allowed to use the module. An unknown type is allowed nothing. */
export function profileAllows(profile: string | null | undefined, capability: Capability): boolean {
  if (!profile || !isBusinessProfile(profile)) return false;
  return PROFILE_ELIGIBLE[profile].includes(capability);
}

/** The preset for a stored profile name; unknown names fall back to the default business type. */
export function profileSpec(profile: string | null | undefined): ProfileSpec {
  return PROFILE_PRESETS[profile && isBusinessProfile(profile) ? profile : DEFAULT_BUSINESS_PROFILE];
}

export function isCapability(value: string): value is Capability {
  return SPECS.has(value as Capability);
}

/** Capabilities in `selected` whose prerequisites are not also selected. */
export function missingDependencies(selected: Iterable<Capability>): { capability: Capability; missing: Capability[] }[] {
  const set = new Set(selected);
  const problems: { capability: Capability; missing: Capability[] }[] = [];
  for (const capability of set) {
    const missing = (CAPABILITY_DEPENDENCIES[capability] ?? []).filter((required) => !set.has(required));
    if (missing.length > 0) problems.push({ capability, missing });
  }
  return problems;
}

export interface ResolvedCapabilities {
  /** Switched on and usable now. */
  enabled: Capability[];
  /** Chosen for this business but still on the roadmap. */
  planned: Capability[];
}

/**
 * The profile preset, or the merchant's own selection when `selection` is set. Unavailable modules become planned,
 * and anything whose prerequisites are missing stays off.
 */
export function resolveCapabilities(profile: BusinessProfile, selection?: readonly string[] | null): ResolvedCapabilities {
  const eligible = new Set(PROFILE_ELIGIBLE[profile] ?? []);
  const chosen = (selection ?? PROFILE_PRESETS[profile]?.capabilities ?? []).filter(
    (id): id is Capability => isCapability(id) && eligible.has(id),
  );
  const unique = [...new Set(chosen)];
  const blocked = new Set(missingDependencies(unique).map((problem) => problem.capability));
  const order = (list: Capability[]) =>
    list.sort((a, b) => CAPABILITIES.findIndex((spec) => spec.id === a) - CAPABILITIES.findIndex((spec) => spec.id === b));
  return {
    enabled: order(unique.filter((capability) => capabilitySpec(capability).available && !blocked.has(capability))),
    planned: order(unique.filter((capability) => !capabilitySpec(capability).available)),
  };
}

export interface ProfileUpdate {
  business_profile: BusinessProfile;
  /** Explicit selection; omit or null to use the profile preset. */
  capabilities?: Capability[] | null;
  complete_onboarding?: boolean;
}
