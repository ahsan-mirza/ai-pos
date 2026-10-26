import type { PosPolicy } from "./posPolicy.js";

export const SUPPORTED_CURRENCIES = ["USD", "EUR", "GBP", "AED", "SAR", "QAR", "PKR", "INR", "CNY"] as const;
export type CurrencyCode = (typeof SUPPORTED_CURRENCIES)[number];

export const CURRENCY_NAMES: Record<CurrencyCode, string> = {
  USD: "US dollar",
  EUR: "Euro",
  GBP: "British pound",
  AED: "UAE dirham",
  SAR: "Saudi riyal",
  QAR: "Qatari riyal",
  PKR: "Pakistani rupee",
  INR: "Indian rupee",
  CNY: "Chinese yuan",
};

/** Receipt branding (PUT /api/v1/settings/receipt). Names, TRN, address and phone come from elsewhere. */
export interface ReceiptSettings {
  /** Black-and-white PNG data URL, at most 64 KB and 576 x 320 pixels. */
  logo_png: string | null;
  header_text: string | null;
  header_text_ar: string | null;
  footer_text: string | null;
  footer_text_ar: string | null;
  email: string | null;
  website: string | null;
}

export interface ReceiptStore {
  id: string;
  name: string;
  address: string | null;
  phone: string | null;
}

/** GET /api/v1/settings/receipt?store_id=: the branding plus that branch's contact lines. */
export interface ReceiptProfile {
  settings: ReceiptSettings;
  store: ReceiptStore | null;
}

export interface BusinessSettings {
  currency: CurrencyCode;
  supported_currencies: CurrencyCode[];
  updated_at: string;
  updated_by_name: string | null;
  vat_registered?: boolean;
  trn?: string | null;
  legal_name?: string | null;
  legal_name_ar?: string | null;
  prices_include_vat?: boolean;
  standard_rate_bps?: number;
  /** Admin portal accent as "#RRGGBB"; null keeps the brand default. */
  primary_color?: string | null;
  business_profile?: string;
  /** Effective, switched-on capabilities (see capabilities.ts). */
  capabilities?: string[];
  /** Selected for this business but not built yet ("Coming soon"). */
  planned_capabilities?: string[];
  /** False until a business-wide admin finishes the onboarding wizard. */
  onboarded?: boolean;
  /** A self-service store before Go live: sample items and practice sales, cleared by Go live. */
  practice_mode?: boolean;
  /** Live, and e-invoicing has no production credential. Practice stamps were removed at Go live. */
  tax_portal_pending?: boolean;
  /** Whose invoicing rules apply; see taxAuthority.ts. */
  tax_authority?: TaxAuthority;
  /** Configuration of the optional modules (expiry alerts, scale labels, service charge, kitchen timers). */
  module_settings?: ModuleSettings;
  /** Till rules: discount reasons and limits, gift cards, the returns policy. */
  pos_policy?: PosPolicy;
}

export interface EmbeddedBarcodeSettings {
  /** Two-digit EAN-13 prefixes a scale prints, e.g. "20".."29". */
  prefixes: string[];
  /** "weight": the label carries grams; "price": it carries the line price in cents. */
  mode: "weight" | "price";
  plu_length: number;
}

export interface ServiceChargeSettings {
  service_charge_bps: number;
  service_charge_taxable: boolean;
  dine_in_only: boolean;
  min_covers: number;
  tip_presets_bps: number[];
}

export interface BagSettings {
  /** Off until an administrator turns it on. The till never adds a bag by itself. */
  enabled: boolean;
  fee_cents: number;
  tax_category: "STANDARD" | "ZERO" | "EXEMPT";
}

export interface DepartmentKey {
  category_id: string;
  label: string;
}

export interface ModuleSettings {
  fefo: { alert_days: number };
  weighed_items: { embedded_barcodes: EmbeddedBarcodeSettings };
  tips_service_charge: ServiceChargeSettings;
  kds: { warn_minutes: number; late_minutes: number };
  repairs: RepairSettings;
  bags: BagSettings;
  department_keys: { keys: DepartmentKey[] };
}

export interface RepairSettings {
  /** Our guarantee on an invoiced repair's parts and labour (0 = none). */
  warranty_days: number;
  approval_link_hours: number;
  /** Suggested intake deposit, basis points of the estimate. */
  deposit_bps: number;
  /** Printed on the job card the customer signs. */
  terms: string;
}

export const DEFAULT_MODULE_SETTINGS: ModuleSettings = {
  fefo: { alert_days: 14 },
  weighed_items: {
    embedded_barcodes: { prefixes: ["20", "21", "22", "23", "24", "25", "26", "27", "28", "29"], mode: "weight", plu_length: 5 },
  },
  tips_service_charge: {
    service_charge_bps: 0,
    service_charge_taxable: true,
    dine_in_only: true,
    min_covers: 0,
    tip_presets_bps: [1000, 1500, 2000],
  },
  kds: { warn_minutes: 8, late_minutes: 15 },
  repairs: {
    warranty_days: 90,
    approval_link_hours: 72,
    deposit_bps: 0,
    terms:
      "We are not responsible for data loss; back up your device before repair. Devices not collected within 90 days of the ready message may be disposed of. Repairs carry the warranty shown on the invoice.",
  },
  bags: { enabled: false, fee_cents: 0, tax_category: "STANDARD" },
  department_keys: { keys: [] },
};

export interface ExpiringStockRow {
  batch_item_id: string;
  batch_number: string;
  product_id: string;
  product_name: string;
  sku: string;
  store_id: string;
  store_code: string;
  expiry_date: string;
  /** Negative once expired. */
  days_left: number;
  quantity_remaining: number;
  unit_cost_cents: number;
  value_cents: number;
  expired: boolean;
}

export type TaxAuthority = "fta" | "zatca";

export interface TaxSettingsUpdate {
  vat_registered: boolean;
  trn: string | null;
  legal_name: string | null;
  legal_name_ar: string | null;
  prices_include_vat: boolean;
  standard_rate_bps: number;
  tax_authority: TaxAuthority;
}

export function isSupportedCurrency(value: string): value is CurrencyCode {
  return (SUPPORTED_CURRENCIES as readonly string[]).includes(value);
}
