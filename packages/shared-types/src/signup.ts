/** Self-service signup on the bare domain (tenant-free /api/v1/signup). Mirrors app/schemas/signup.py. */

import type { Capability } from "./capabilities.js";
import { COUNTRY_CURRENCIES, currencyForCountry } from "./countries.js";

export type SignupStatus = "PENDING_OTP" | "VERIFIED" | "WAITLIST" | "PROVISIONING" | "READY" | "FAILED";
export type ProvisionStepState = "pending" | "running" | "done" | "failed";
export type SignupOtpChannel = "log" | "whatsapp" | "sms" | "email";

export const SIGNUP_PASSWORD_MIN_LENGTH = 10;

export interface SignupPasswordRule {
  id: string;
  label: string;
  met: boolean;
}

/** Live checks for a new signup password: length, an uppercase letter, a number, and a special character. */
export function signupPasswordRules(password: string): SignupPasswordRule[] {
  return [
    {
      id: "length",
      label: `At least ${SIGNUP_PASSWORD_MIN_LENGTH} characters`,
      met: password.length >= SIGNUP_PASSWORD_MIN_LENGTH,
    },
    { id: "upper", label: "One uppercase letter", met: /[A-Z]/.test(password) },
    { id: "number", label: "One number", met: /\d/.test(password) },
    { id: "special", label: "One special character", met: /[^A-Za-z0-9]/.test(password) },
  ];
}

export function signupPasswordReady(password: string): boolean {
  return signupPasswordRules(password).every((rule) => rule.met);
}

/** Exact comparison. Empty stays neutral so a blank box is not treated as a mismatch. */
export function signupPasswordConfirmation(password: string, confirmation: string): "empty" | "match" | "mismatch" {
  if (confirmation === "") return "empty";
  return confirmation === password ? "match" : "mismatch";
}

/** Both the policy and an exact confirmation are required before signup can start. */
export function signupPasswordsAccepted(password: string, confirmation: string): boolean {
  return signupPasswordReady(password) && signupPasswordConfirmation(password, confirmation) === "match";
}

/** Query flag for the landing-page card. It carries no account data. */
export const SIGNUP_EMBED_PARAM = "embed";

/** Height reports from the embedded wizard to the marketing page. */
export const SIGNUP_EMBED_MESSAGE = "ai-pos.signup-embed";

export function isSignupEmbedSearch(search: string): boolean {
  const query = search.startsWith("?") ? search.slice(1) : search;
  return query.split("&").some((part) => part === `${SIGNUP_EMBED_PARAM}=1`);
}

export interface SignupStart {
  email: string;
  phone: string;
  full_name: string;
  password: string;
}

/** Log in to a signup that was already started with this email. */
export interface SignupResume {
  email: string;
  password: string;
}

export interface SignupStarted {
  id: string;
  /** Sent back as X-Signup-Token on every later step. */
  token: string;
  channel: SignupOtpChannel;
  sent_to: string;
  resend_after_seconds: number;
  /** Seconds until the emailed code stops working. */
  expires_in_seconds: number;
  /** Only in development with the log channel. */
  dev_code: string | null;
}

export interface SignupBusiness {
  profile: string;
  sub_type: string | null;
}

export interface SignupStore {
  store_name: string;
  slug: string;
  address: string;
  currency: string;
  country: string;
  trn: string | null;
}

export interface SlugCheck {
  slug: string;
  available: boolean;
  reason: string | null;
  suggestion: string | null;
}

/** Public availability answer. It never includes the other account. */
export interface AvailabilityResult {
  available: boolean;
  code: "available" | "taken";
}

export interface ProvisionStep {
  key: string;
  label: string;
  state: ProvisionStepState;
}

export interface SignupState {
  id: string;
  status: SignupStatus;
  email: string;
  phone: string;
  profile: string | null;
  sub_type: string | null;
  store_name: string | null;
  slug: string | null;
  steps: ProvisionStep[];
  error: string | null;
  portal_url: string | null;
  owner_username: string | null;
  /** Five-minute single-use sign-in for the new store, once it is READY. */
  handoff_token: string | null;
}

export interface SignupSubType {
  id: string;
  label: string;
  description: string;
  /** Starter modules for this signup choice. The ids match SUB_TYPES in app/core/capabilities.py. */
  modules: readonly Capability[];
  /** Combined operating model for this category. Still a real sub_type, not a label. */
  allInOne?: boolean;
  /** Hardware or a paid add-on that this choice does not switch on. */
  note?: string;
}

export interface SignupBusinessCard {
  /** A BusinessProfile id; cards without sub-types are "coming soon" and put the signup on the waitlist. */
  profile: string;
  label: string;
  description: string;
  subTypes: readonly SignupSubType[];
}

/** The cards on the business step; sub-type ids and modules match SUB_TYPES in app/core/capabilities.py. */
export const SIGNUP_BUSINESS_CARDS: readonly SignupBusinessCard[] = [
  {
    profile: "electronics_wholesale",
    label: "Electronics",
    description: "Devices, accessories, serial numbers and warranties.",
    subTypes: [
      {
        id: "electronics_retail",
        label: "Electronics retail store",
        description: "Sell individual products with serial numbers, warranties and repairs.",
        modules: ["promotions", "multi_currency", "serial_tracking", "loyalty", "repairs", "warranty", "trade_in", "card_terminals", "bnpl"],
      },
      {
        id: "electronics_mobile",
        label: "Mobile and accessories",
        description: "Phones, IMEI tracking, accessories and warranty records.",
        modules: ["promotions", "multi_currency", "serial_tracking", "loyalty", "repairs", "warranty", "trade_in", "card_terminals", "bnpl"],
      },
      {
        id: "electronics_computer",
        label: "Computer and IT store",
        description: "Computers and accessories with serial numbers and warranties.",
        modules: ["promotions", "multi_currency", "serial_tracking", "loyalty", "repairs", "warranty", "trade_in", "card_terminals", "bnpl"],
      },
      {
        id: "electronics_b2b",
        label: "Electronics wholesale",
        description: "Bulk orders, customer-specific prices and a credit ledger.",
        modules: ["wholesale_pricing", "quotes_layaway", "promotions", "multi_currency", "serial_tracking", "variants_matrix", "consignment", "b2b_credit", "cheques", "loyalty", "repairs", "warranty", "trade_in", "card_terminals", "bnpl"],
      },
      {
        id: "electronics_both",
        label: "All-in-one electronics",
        description: "Retail, wholesale, accessories and device tracking in one setup.",
        modules: ["wholesale_pricing", "quotes_layaway", "promotions", "multi_currency", "serial_tracking", "variants_matrix", "consignment", "b2b_credit", "cheques", "loyalty", "repairs", "warranty", "trade_in", "card_terminals", "bnpl"],
        allInOne: true,
      },
    ],
  },
  {
    profile: "wholesale_retail",
    label: "Wholesale & Retail",
    description: "Bulk orders, counter sales, customer prices and deliveries.",
    subTypes: [
      {
        id: "wholesale_trade",
        label: "Wholesale business",
        description: "Bulk quantities, customer-specific prices and a credit ledger.",
        modules: ["wholesale_pricing", "b2b_credit", "quotes_layaway", "sales_orders", "promotions", "loyalty", "cheques", "card_terminals"],
      },
      {
        id: "retail_shop",
        label: "Retail store",
        description: "Individual sales, product stock and customer accounts.",
        modules: ["promotions", "loyalty", "quotes_layaway", "card_terminals", "customer_reorders", "multi_currency"],
      },
      {
        id: "wholesale_both",
        label: "Wholesale and retail",
        description: "Bulk and individual sales, with different price levels and one stock record.",
        modules: ["wholesale_pricing", "sales_orders", "b2b_credit", "quotes_layaway", "promotions", "loyalty", "multi_currency", "card_terminals", "customer_reorders"],
      },
      {
        id: "wholesale_distribution",
        label: "Distribution business",
        description: "Customer deliveries, bulk orders and stock on account.",
        modules: ["wholesale_pricing", "sales_orders", "customer_reorders", "b2b_credit", "promotions", "loyalty", "card_terminals"],
      },
      {
        id: "wholesale_distributor",
        label: "Account wholesale",
        description: "The full wholesale kit, including repeat customer deliveries.",
        modules: ["wholesale_pricing", "sales_orders", "b2b_credit", "quotes_layaway", "promotions", "loyalty", "multi_currency", "card_terminals", "customer_reorders"],
      },
      {
        id: "wholesale_all",
        label: "All-in-one wholesale and retail",
        description: "Wholesale, retail, deliveries and customer accounts together.",
        modules: ["wholesale_pricing", "sales_orders", "b2b_credit", "quotes_layaway", "promotions", "loyalty", "multi_currency", "card_terminals", "customer_reorders"],
        allInOne: true,
      },
    ],
  },
  {
    profile: "retail_fashion",
    label: "Retail & Fashion",
    description: "Clothing and footwear with size and colour grids.",
    subTypes: [
      {
        id: "fashion_clothing",
        label: "Clothing store",
        description: "Size and colour variants, with stock kept per variant.",
        modules: ["quotes_layaway", "loyalty", "promotions", "multi_currency", "variants_matrix", "gift_cards", "alterations"],
      },
      {
        id: "fashion_footwear",
        label: "Footwear store",
        description: "Shoe sizes and colours, with stock kept per variant.",
        modules: ["quotes_layaway", "loyalty", "promotions", "multi_currency", "variants_matrix", "gift_cards", "alterations"],
      },
      {
        id: "fashion_boutique",
        label: "Fashion boutique",
        description: "Collections, variant pricing and customer purchase history.",
        modules: ["quotes_layaway", "loyalty", "promotions", "multi_currency", "variants_matrix", "gift_cards", "alterations"],
      },
      {
        id: "fashion_multi",
        label: "Multi-category retail",
        description: "Several product categories in one inventory and sales setup.",
        modules: ["quotes_layaway", "loyalty", "promotions", "multi_currency", "variants_matrix", "consignment", "gift_cards"],
      },
      {
        id: "fashion_chain",
        label: "Several branches",
        description: "The same variant catalogue, plus consignment stock.",
        modules: ["quotes_layaway", "loyalty", "promotions", "multi_currency", "variants_matrix", "consignment", "gift_cards"],
      },
      {
        id: "fashion_all",
        label: "All-in-one retail",
        description: "Variants, alterations and consignment in one retail setup.",
        modules: ["quotes_layaway", "loyalty", "promotions", "multi_currency", "variants_matrix", "gift_cards", "alterations", "consignment"],
        allInOne: true,
      },
    ],
  },
  {
    profile: "grocery",
    label: "Supermarket",
    description: "Barcode checkout, weighed items and expiry dates.",
    subTypes: [
      {
        id: "grocery_shop",
        label: "Neighborhood grocery",
        description: "Barcode scanning, fast checkout and daily grocery stock.",
        modules: ["loyalty", "promotions", "weighed_items", "fefo", "card_terminals"],
        note: "Selling by weight needs a scale.",
      },
      {
        id: "grocery_supermarket",
        label: "Supermarket",
        description: "Many categories, barcode checkout and stock replenishment.",
        modules: ["loyalty", "promotions", "weighed_items", "fefo", "card_terminals", "gift_cards", "multi_currency"],
        note: "Selling by weight needs a scale.",
      },
      {
        id: "grocery_mini",
        label: "Mini mart",
        description: "Fast checkout for everyday products in a compact shop.",
        modules: ["loyalty", "promotions", "fefo", "card_terminals"],
      },
      {
        id: "grocery_fresh",
        label: "Fresh food and weighed items",
        description: "Produce and other items sold by weight, with expiry-first stock.",
        modules: ["loyalty", "promotions", "weighed_items", "fefo", "card_terminals"],
        note: "Selling by weight needs a scale.",
      },
      {
        id: "grocery_all",
        label: "All-in-one supermarket",
        description: "Grocery, fresh food, weighed items and general merchandise.",
        modules: ["loyalty", "promotions", "weighed_items", "fefo", "card_terminals", "gift_cards", "multi_currency"],
        allInOne: true,
        note: "Selling by weight needs a scale.",
      },
      {
        id: "grocery_cash_carry",
        label: "Cash and carry",
        description: "Trade customers with tier prices, credit, cheques and deliveries.",
        modules: ["loyalty", "promotions", "weighed_items", "fefo", "wholesale_pricing", "quotes_layaway", "b2b_credit", "cheques", "sales_orders", "card_terminals"],
        note: "Selling by weight needs a scale.",
      },
    ],
  },
  {
    profile: "restaurant",
    label: "Restaurant",
    description: "Tables, kitchen tickets, split bills and tips.",
    subTypes: [
      {
        id: "full_service",
        label: "Full-service restaurant",
        description: "Table management, waiter ordering, kitchen tickets, split bills and tips.",
        modules: ["loyalty", "promotions", "multi_currency", "tables", "open_orders", "menu_modifiers", "kds", "recipes", "split_bills", "tips_service_charge", "card_terminals"],
      },
      {
        id: "restaurant_counter",
        label: "Quick-service restaurant",
        description: "Guests order and pay first, then collect from the counter.",
        modules: ["loyalty", "promotions", "multi_currency", "menu_modifiers", "kds", "recipes", "card_terminals"],
      },
      {
        id: "fine_dining",
        label: "Fine dining",
        description: "Staff take the order at the table and the bill can be split.",
        modules: ["loyalty", "promotions", "multi_currency", "tables", "open_orders", "menu_modifiers", "kds", "recipes", "split_bills", "tips_service_charge", "card_terminals"],
      },
      {
        id: "cloud_kitchen",
        label: "Cloud kitchen",
        description: "Delivery orders and kitchen tickets, without a dine-in floor.",
        modules: ["loyalty", "promotions", "multi_currency", "open_orders", "menu_modifiers", "kds", "recipes", "delivery_channels", "card_terminals"],
        note: "Connecting a delivery app is a separate add-on.",
      },
      {
        id: "restaurant_delivery",
        label: "Restaurant with delivery",
        description: "Dine-in, takeaway and delivery orders on one kitchen.",
        modules: ["loyalty", "promotions", "multi_currency", "tables", "open_orders", "menu_modifiers", "kds", "recipes", "split_bills", "tips_service_charge", "delivery_channels", "card_terminals"],
        note: "Connecting a delivery app is a separate add-on.",
      },
      {
        id: "restaurant_all",
        label: "All-in-one restaurant",
        description: "Dine-in, counter service, takeaway and delivery orders together.",
        modules: ["loyalty", "promotions", "multi_currency", "tables", "open_orders", "menu_modifiers", "kds", "recipes", "split_bills", "tips_service_charge", "delivery_channels", "card_terminals"],
        allInOne: true,
        note: "Connecting a delivery app is a separate add-on.",
      },
    ],
  },
  {
    profile: "cafe",
    label: "Cafe",
    description: "Coffee, bakery and sandwiches with sizes and add-ons.",
    subTypes: [
      {
        id: "counter_cafe",
        label: "Counter cafe",
        description: "Guests order and pay at the counter. The barista prepares the drinks.",
        modules: ["loyalty", "promotions", "menu_modifiers", "open_orders", "kds", "recipes", "card_terminals"],
      },
      {
        id: "sit_down_cafe",
        label: "Sit-down cafe",
        description: "Table service, with split bills and tips for guests who stay.",
        modules: ["loyalty", "promotions", "menu_modifiers", "open_orders", "kds", "recipes", "tables", "split_bills", "tips_service_charge", "card_terminals"],
      },
      {
        id: "bakery_cafe",
        label: "Bakery and coffee shop",
        description: "Bakery items, drinks and takeaway, with sizes and add-ons.",
        modules: ["loyalty", "promotions", "menu_modifiers", "open_orders", "kds", "recipes", "card_terminals"],
      },
      {
        id: "cafe_quick",
        label: "Quick-service cafe",
        description: "Guests pay first. The order goes to the barista after payment.",
        modules: ["loyalty", "promotions", "menu_modifiers", "kds", "recipes", "card_terminals"],
      },
      {
        id: "cafe_delivery",
        label: "Cafe with delivery",
        description: "Counter sales plus delivery orders on the same menu.",
        modules: ["loyalty", "promotions", "menu_modifiers", "open_orders", "kds", "recipes", "card_terminals", "delivery_channels"],
        note: "Connecting a delivery app is a separate add-on.",
      },
      {
        id: "cafe_all",
        label: "All-in-one cafe",
        description: "Counter, dine-in, takeaway and delivery on one setup.",
        modules: ["loyalty", "promotions", "menu_modifiers", "open_orders", "kds", "recipes", "tables", "split_bills", "tips_service_charge", "card_terminals", "delivery_channels"],
        allInOne: true,
        note: "Connecting a delivery app is a separate add-on.",
      },
    ],
  },
  {
    profile: "quick_service",
    label: "Quick Service",
    description: "Pay first, then the kitchen prepares the order.",
    subTypes: [
      {
        id: "qsr_counter",
        label: "Fast-food counter",
        description: "Order and pay at the counter, then collect when the kitchen is done.",
        modules: ["loyalty", "promotions", "menu_modifiers", "open_orders", "kds", "recipes", "card_terminals"],
      },
      {
        id: "qsr_burger",
        label: "Burger and sandwich shop",
        description: "Add-ons, combo choices and kitchen tickets.",
        modules: ["loyalty", "promotions", "menu_modifiers", "open_orders", "kds", "recipes", "card_terminals"],
      },
      {
        id: "qsr_truck",
        label: "Food truck",
        description: "A compact counter for fast service away from a full dining room.",
        modules: ["promotions", "menu_modifiers", "open_orders", "kds", "recipes", "card_terminals"],
      },
      {
        id: "qsr_delivery",
        label: "Takeaway and delivery",
        description: "Prepaid orders for pickup and delivery, with order status.",
        modules: ["loyalty", "promotions", "menu_modifiers", "open_orders", "kds", "recipes", "delivery_channels", "card_terminals"],
        note: "Connecting a delivery app is a separate add-on.",
      },
      {
        id: "qsr_all",
        label: "All-in-one quick service",
        description: "Counter, takeaway, pickup and delivery on one kitchen.",
        modules: ["loyalty", "promotions", "menu_modifiers", "open_orders", "kds", "recipes", "delivery_channels", "card_terminals"],
        allInOne: true,
        note: "Connecting a delivery app is a separate add-on.",
      },
    ],
  },
];

export interface SignupCountry {
  code: string;
  name: string;
  currency: string;
}

function englishRegionName(code: string): string {
  const DisplayNames = typeof Intl === "undefined" ? undefined : Intl.DisplayNames;
  if (typeof DisplayNames !== "function") return code;
  try {
    return new DisplayNames(["en"], { type: "region" }).of(code) ?? code;
  } catch {
    return code;
  }
}

/** Every country the signup form can store, with the currency that country selects. */
export const SIGNUP_COUNTRIES: readonly SignupCountry[] = Object.keys(COUNTRY_CURRENCIES)
  .map((code) => ({
    code,
    name: englishRegionName(code),
    currency: currencyForCountry(code),
  }))
  .sort((left, right) => left.name.localeCompare(right.name));
