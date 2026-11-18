/** Pharmacy catalogue values. Category names stay in the taxonomy, not in this file. */

export const PHARMACY_PRODUCT_KINDS = [
  "MEDICINE",
  "DEVICE",
  "SUPPLY",
  "SUPPLEMENT",
  "PERSONAL_CARE",
  "COSMETIC",
  "NUTRITION",
  "ACCESSORY",
] as const;

export const PHARMACY_KIND_LABELS: Record<(typeof PHARMACY_PRODUCT_KINDS)[number], string> = {
  MEDICINE: "Medicine",
  DEVICE: "Medical device",
  SUPPLY: "Medical supply",
  SUPPLEMENT: "Supplement",
  PERSONAL_CARE: "Personal care",
  COSMETIC: "Cosmetic",
  NUTRITION: "Nutrition",
  ACCESSORY: "Accessory",
};

export const DISPENSING_CLASSES = [
  "OTC",
  "PRESCRIPTION",
  "CONTROLLED",
  "SEMI_CONTROLLED",
  "RESTRICTED",
  "SPECIAL_HANDLING",
] as const;

export const DISPENSING_CLASS_LABELS: Record<(typeof DISPENSING_CLASSES)[number], string> = {
  OTC: "OTC",
  PRESCRIPTION: "Prescription",
  CONTROLLED: "Controlled",
  SEMI_CONTROLLED: "Semi-controlled",
  RESTRICTED: "Restricted",
  SPECIAL_HANDLING: "Special handling",
};

export const DOSAGE_FORMS = [
  "tablet",
  "capsule",
  "syrup",
  "suspension",
  "oral drops",
  "cream",
  "ointment",
  "gel",
  "injection",
  "eye drops",
  "ear drops",
  "nasal spray",
  "inhaler",
  "suppository",
  "powder",
  "sachet",
  "patch",
  "solution",
] as const;

export const STRENGTH_UNITS = ["mg", "g", "mcg", "IU", "%", "mg/ml", "mcg/dose"] as const;

export const PRICE_CONTROLS = ["NONE", "MINIMUM", "MAXIMUM", "FIXED"] as const;

export const PRICE_CONTROL_LABELS: Record<(typeof PRICE_CONTROLS)[number], string> = {
  NONE: "No official price",
  MINIMUM: "Minimum official price",
  MAXIMUM: "Maximum official price",
  FIXED: "Fixed official price",
};

export interface PharmacyIngredient {
  name: string;
  strength_amount: string;
  strength_unit: string;
  is_active_ingredient: boolean;
}

export interface PharmacyDocumentDraft {
  kind: "leaflet" | "registration" | "supplier" | "other";
  title: string;
  reference: string;
}

export interface PharmacyDraft {
  product_kind: (typeof PHARMACY_PRODUCT_KINDS)[number];
  dispensing_class: (typeof DISPENSING_CLASSES)[number] | "";
  generic_name: string;
  manufacturer: string;
  marketing_authorization_holder: string;
  country_of_origin: string;
  description: string;
  gtin: string;
  manufacturer_product_ref: string;
  dosage_form: string;
  route: string;
  strength_amount: string;
  strength_unit: string;
  concentration: string;
  pack_size_label: string;
  units_per_pack: string;
  base_unit_code: string;
  selling_unit_code: string;
  storage_condition: string;
  temp_min_c: string;
  temp_max_c: string;
  cold_chain: boolean;
  handling_instructions: string;
  warnings_text: string;
  registration_number: string;
  registration_authority: string;
  price_control: (typeof PRICE_CONTROLS)[number];
  min_price_cents: string;
  max_price_cents: string;
  offline_policy: "ALLOW" | "BLOCK";
  ingredients: PharmacyIngredient[];
  documents: PharmacyDocumentDraft[];
}

export interface PharmacyIngredientDetail {
  id: string;
  position: number;
  name: string;
  strength_amount: string | number | null;
  strength_unit: string;
  is_active_ingredient: boolean;
}

export interface PharmacyDocumentDetail {
  id: string;
  kind: string;
  title: string;
  reference: string;
  storage_key: string | null;
}

export interface PharmacyProductDetail {
  product_id: string;
  name: string;
  sku: string;
  barcode: string;
  brand: string;
  category: string;
  sub_category: string;
  price_cents: number;
  tax_category: string;
  is_active: boolean;
  updated_at: string;
  product_kind: (typeof PHARMACY_PRODUCT_KINDS)[number];
  dispensing_class: (typeof DISPENSING_CLASSES)[number];
  classification_source: string;
  generic_name: string;
  manufacturer: string;
  marketing_authorization_holder: string;
  country_of_origin: string;
  description: string;
  gtin: string;
  manufacturer_product_ref: string;
  dosage_form: string;
  route: string;
  strength_amount: string | number | null;
  strength_unit: string;
  strength_display: string;
  concentration: string;
  pack_size_label: string;
  units_per_pack: number;
  base_unit_code: string;
  selling_unit_code: string;
  dispense_unit_code: string;
  storage_condition: string;
  temp_min_c: string | number | null;
  temp_max_c: string | number | null;
  cold_chain: boolean;
  handling_instructions: string;
  warnings_text: string;
  registration_number: string | null;
  registration_authority: string | null;
  price_control: (typeof PRICE_CONTROLS)[number];
  min_price_cents: number | null;
  max_price_cents: number | null;
  discount_eligible: boolean;
  promotion_eligible: boolean;
  official_price_state: "NOT_REQUIRED" | "MISSING" | "ENTERED";
  sale_blocked: boolean;
  offline_policy: "ALLOW" | "BLOCK";
  ingredients: PharmacyIngredientDetail[];
  documents: PharmacyDocumentDetail[];
  lot_on_product_master: boolean;
}

export function emptyPharmacyDraft(): PharmacyDraft {
  return {
    product_kind: "MEDICINE",
    dispensing_class: "",
    generic_name: "",
    manufacturer: "",
    marketing_authorization_holder: "",
    country_of_origin: "",
    description: "",
    gtin: "",
    manufacturer_product_ref: "",
    dosage_form: "",
    route: "",
    strength_amount: "",
    strength_unit: "",
    concentration: "",
    pack_size_label: "",
    units_per_pack: "1",
    base_unit_code: "PIECE",
    selling_unit_code: "PIECE",
    storage_condition: "",
    temp_min_c: "",
    temp_max_c: "",
    cold_chain: false,
    handling_instructions: "",
    warnings_text: "",
    registration_number: "",
    registration_authority: "",
    price_control: "NONE",
    min_price_cents: "",
    max_price_cents: "",
    offline_policy: "BLOCK",
    ingredients: [{ name: "", strength_amount: "", strength_unit: "mg", is_active_ingredient: true }],
    documents: [],
  };
}
