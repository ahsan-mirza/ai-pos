/** Labels and checks for the signup tax field. Strict rules match the API for AE, SA, GB, and US only. */

export interface TaxIdField {
  label: string;
  hint: string;
  placeholder: string;
}

const SPECIFIC: Record<string, TaxIdField> = {
  AE: {
    label: "Tax registration number (TRN)",
    hint: "Optional. A UAE TRN is 15 digits. Leave this blank if the business is not VAT-registered.",
    placeholder: "100123456700003",
  },
  SA: {
    label: "VAT registration number",
    hint: "Optional. A Saudi VAT number is 15 digits starting and ending with 3. Leave this blank if you are not VAT-registered.",
    placeholder: "300000000000003",
  },
  GB: {
    label: "VAT registration number",
    hint: "Optional. A UK VAT number is 9 digits, with or without the GB prefix. Leave this blank if you are not VAT-registered.",
    placeholder: "GB123456789",
  },
  US: {
    label: "Employer Identification Number (EIN)",
    hint: "Optional. A US EIN is 9 digits. Leave this blank if you do not have one.",
    placeholder: "12-3456789",
  },
};

const GENERIC: TaxIdField = {
  label: "Tax or business registration number",
  hint: "Optional. Leave this blank if the business is not registered for tax.",
  placeholder: "",
};

const LOOSE = /^[A-Z0-9](?:[A-Z0-9 \-]{0,30}[A-Z0-9])?$/;

export function taxIdField(country: string): TaxIdField {
  return SPECIFIC[country.trim().toUpperCase()] ?? GENERIC;
}

/** Blank is allowed. A returned error is safe to show next to the field. */
export function taxIdError(country: string, value: string): string | null {
  const cleaned = value.replace(/\s+/g, " ").trim().toUpperCase();
  if (cleaned === "") return null;
  const iso = country.trim().toUpperCase();
  if (iso === "AE") {
    return /^\d{15}$/.test(cleaned.replace(/\D/g, ""))
      ? null
      : "A UAE TRN is 15 digits. Leave it blank if the business is not VAT-registered.";
  }
  if (iso === "SA") {
    const digits = cleaned.replace(/\D/g, "");
    return digits.length === 15 && digits.startsWith("3") && digits.endsWith("3")
      ? null
      : "A Saudi VAT number is 15 digits that start and end with 3. Leave it blank if the business is not VAT-registered.";
  }
  if (iso === "GB") {
    return /^(?:GB)?\d{9}(?:\d{3})?$/.test(cleaned.replace(/ /g, ""))
      ? null
      : "A UK VAT number is 9 digits, optionally starting with GB. Leave it blank if the business is not VAT-registered.";
  }
  if (iso === "US") {
    return cleaned.replace(/\D/g, "").length === 9
      ? null
      : "A US EIN is 9 digits. Leave it blank if you do not have one.";
  }
  return LOOSE.test(cleaned) ? null : "Enter the tax or business registration number, or leave it blank.";
}
