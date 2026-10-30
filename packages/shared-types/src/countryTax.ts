import type { TaxAuthority } from "./settings.js";

/** Tax metadata for a country. Rates are set only where a verified default exists. */
export interface CountryTax {
  code: string;
  tax_name: string;
  registration_label: string;
  secondary_registration_label: string | null;
  legal_local_language: "ar" | "ur" | null;
  legal_local_label: string | null;
  region_label: string | null;
  rate_known: boolean;
  standard_rate_bps: number | null;
  prices_include_vat: boolean;
  tax_authority: TaxAuthority;
  categories: Array<"STANDARD" | "ZERO" | "EXEMPT">;
}

const CATEGORIES: CountryTax["categories"] = ["STANDARD", "ZERO", "EXEMPT"];

function row(
  code: string,
  taxName: string,
  registration: string,
  secondary: string | null,
  language: CountryTax["legal_local_language"],
  localLabel: string | null,
  region: string | null,
  known: boolean,
  rate: number | null,
  inclusive: boolean,
  authority: TaxAuthority,
): CountryTax {
  return {
    code,
    tax_name: taxName,
    registration_label: registration,
    secondary_registration_label: secondary,
    legal_local_language: language,
    legal_local_label: localLabel,
    region_label: region,
    rate_known: known,
    standard_rate_bps: rate,
    prices_include_vat: inclusive,
    tax_authority: authority,
    categories: CATEGORIES,
  };
}

const KNOWN: Record<string, CountryTax> = {
  AE: row("AE", "VAT", "TRN", null, "ar", "Legal name (Arabic)", "Emirate", true, 500, true, "fta"),
  SA: row("SA", "VAT", "VAT registration number", null, "ar", "Legal name (Arabic)", null, true, 1500, false, "zatca"),
  BH: row("BH", "VAT", "VAT registration number", null, "ar", "Legal name (Arabic)", null, true, 1000, false, "fta"),
  OM: row("OM", "VAT", "VAT registration number", null, "ar", "Legal name (Arabic)", null, true, 500, false, "fta"),
  PK: row(
    "PK",
    "Sales tax",
    "NTN",
    "Sales tax registration number (STRN)",
    "ur",
    "Legal name (Urdu)",
    "Province",
    false,
    null,
    false,
    "fta",
  ),
  GB: row("GB", "VAT", "VAT registration number", null, null, null, null, false, null, false, "fta"),
  US: row("US", "Sales tax", "Sales tax registration", null, null, null, "State", false, null, false, "fta"),
};

export function countryTax(iso: string): CountryTax {
  const code = iso.toUpperCase();
  return (
    KNOWN[code] ??
    row(code, "Tax", "Tax registration number", null, null, null, null, false, null, false, "fta")
  );
}
