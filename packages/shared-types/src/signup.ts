/** Self-service signup on the bare domain (tenant-free /api/v1/signup). Mirrors app/schemas/signup.py. */

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
}

export interface SignupBusinessCard {
  /** A BusinessProfile id; cards without sub-types are "coming soon" and put the signup on the waitlist. */
  profile: string;
  label: string;
  description: string;
  subTypes: readonly SignupSubType[];
}

/** The cards on the business step; sub-type ids match SUB_TYPES in app/core/capabilities.py (a test checks). */
export const SIGNUP_BUSINESS_CARDS: readonly SignupBusinessCard[] = [
  {
    profile: "electronics_wholesale",
    label: "Electronics",
    description: "Electronics products, IMEI and serial tracking, warranties and accessories.",
    subTypes: [
      {
        id: "electronics_retail",
        label: "Retail shop",
        description: "Walk-in customers: IMEIs, repairs, warranty and trade-ins.",
      },
      {
        id: "electronics_b2b",
        label: "Wholesale & B2B",
        description: "Adds tier prices, customer credit, quotations and cheques.",
      },
      {
        id: "electronics_both",
        label: "Both",
        description: "A walk-in shop and wholesale: IMEIs, repairs, tier prices, credit and quotations.",
      },
    ],
  },
  {
    profile: "wholesale_retail",
    label: "Wholesale & Retail",
    description: "Manage bulk orders, individual sales, customer pricing, inventory, and recurring customer deliveries.",
    subTypes: [
      {
        id: "wholesale_distributor",
        label: "Wholesale & distribution",
        description: "Account customers, bulk pricing, and recurring deliveries.",
      },
      { id: "retail_shop", label: "Retail shop", description: "Counter sales with customer-specific repeat orders." },
    ],
  },
  {
    profile: "retail_fashion",
    label: "Retail & Fashion",
    description: "Clothing and footwear with size and colour grids.",
    subTypes: [
      { id: "fashion_boutique", label: "Boutique", description: "One shop: loyalty, promotions and size grids." },
      { id: "fashion_chain", label: "Chain", description: "Several branches; adds consignment stock." },
    ],
  },
  {
    profile: "grocery",
    label: "Supermarket",
    description: "Weighed items, expiry dates and fast scanning.",
    subTypes: [
      {
        id: "grocery_shop",
        label: "Neighborhood grocery",
        description: "One shop. Scan, weigh produce, and sell the batch that expires first.",
      },
      {
        id: "grocery_supermarket",
        label: "Supermarket",
        description: "Several lanes and a large catalogue. Adds gift cards and foreign cash.",
      },
      {
        id: "grocery_cash_carry",
        label: "Cash & carry",
        description: "Trade customers with tier prices, credit, cheques and deliveries.",
      },
    ],
  },
  {
    profile: "restaurant",
    label: "Restaurant",
    description: "Table service: floor plan, kitchen screens, split bills and tips.",
    subTypes: [
      {
        id: "full_service",
        label: "Dine-in restaurant",
        description: "Tables and covers, courses sent to the kitchen and bar, split bills.",
      },
      {
        id: "restaurant_delivery",
        label: "Dine-in + delivery",
        description: "Everything above, plus orders from delivery apps.",
      },
    ],
  },
  {
    profile: "cafe",
    label: "Cafe",
    description: "Coffee, bakery and sandwiches with sizes, milk choices and breakfast deals.",
    subTypes: [
      { id: "counter_cafe", label: "Counter cafe", description: "Order and pay at the counter; drinks go to the barista." },
      {
        id: "sit_down_cafe",
        label: "Sit-down cafe",
        description: "Adds tables, split bills and tips for guests who stay.",
      },
    ],
  },
  {
    profile: "quick_service",
    label: "Quick Service",
    description: "Burgers, wraps and combo meals: pay first, cooked to order.",
    subTypes: [
      { id: "qsr_counter", label: "Counter & takeaway", description: "Pay-first counter with kitchen tickets and meal deals." },
      { id: "qsr_delivery", label: "Counter + delivery apps", description: "Adds orders from Talabat, Deliveroo and the like." },
    ],
  },
];

export interface SignupCountry {
  code: string;
  name: string;
  currency: string;
}

const regionNames = new Intl.DisplayNames(["en"], { type: "region" });

/** Every country the signup form can store, with the currency that country selects. */
export const SIGNUP_COUNTRIES: readonly SignupCountry[] = Object.keys(COUNTRY_CURRENCIES)
  .map((code) => ({
    code,
    name: regionNames.of(code) ?? code,
    currency: currencyForCountry(code),
  }))
  .sort((left, right) => left.name.localeCompare(right.name));
