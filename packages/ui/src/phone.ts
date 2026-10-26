import {
  formatIncompletePhoneNumber,
  getCountryCallingCode,
  getExampleNumber,
  isValidPhoneNumber,
  parsePhoneNumberFromString,
  type CountryCode,
} from "libphonenumber-js";
import examples from "libphonenumber-js/mobile/examples";

const trunkCache = new Map<CountryCode, string>();

/** Domestic trunk prefix printed in front of a national number, usually "0". Empty when the country has none. */
export function trunkPrefix(country: CountryCode): string {
  const cached = trunkCache.get(country);
  if (cached !== undefined) return cached;
  const example = getExampleNumber(country, examples);
  const national = example?.formatNational() ?? "";
  const trunk = national.startsWith("0") && example && !example.nationalNumber.startsWith("0") ? "0" : "";
  trunkCache.set(country, trunk);
  return trunk;
}

/**
 * Digits the subscriber typed, with the selected country's trunk prefix removed once.
 * A leading zero stays when that country does not use a trunk prefix.
 * A pasted calling code is removed only when the remainder is a valid number for this country.
 */
export function nationalDigits(raw: string, country: CountryCode): string {
  let digits = raw.replace(/\D/g, "");
  const trunk = trunkPrefix(country);
  if (trunk && digits.startsWith(trunk)) digits = digits.slice(trunk.length);
  const calling = getCountryCallingCode(country);
  if (digits.startsWith(calling)) {
    const rest = digits.slice(calling.length);
    const parsed = parsePhoneNumberFromString(`+${calling}${rest}`);
    if (parsed?.isValid() && parsed.country === country) return rest;
  }
  return digits;
}

export function formatLocal(country: CountryCode, digits: string): string {
  if (!digits) return "";
  const trunk = trunkPrefix(country);
  const formatted = formatIncompletePhoneNumber(`${trunk}${digits}`, country);
  if (trunk && formatted.startsWith(trunk)) return formatted.slice(trunk.length).trimStart();
  return formatted;
}

export function placeholderFor(country: CountryCode): string {
  const example = getExampleNumber(country, examples);
  if (!example) return "";
  return formatLocal(country, example.nationalNumber);
}

/** True when `value` is a complete E.164 number, for example `+971501234567`. */
export function isValidE164(value: string): boolean {
  return value.startsWith("+") && isValidPhoneNumber(value);
}

/** Canonical E.164 for a valid number, or "" when it cannot be parsed for `country`. */
export function toE164(raw: string, country: CountryCode = "AE"): string {
  const text = raw.trim();
  if (!text) return "";
  if (text.startsWith("+") || text.startsWith("00")) {
    const international = text.startsWith("00") ? `+${text.slice(2).replace(/\D/g, "")}` : text;
    const parsed = parsePhoneNumberFromString(international);
    return parsed?.isValid() ? parsed.number : "";
  }
  const digits = nationalDigits(text, country);
  if (!digits) return "";
  const parsed = parsePhoneNumberFromString(`+${getCountryCallingCode(country)}${digits}`);
  return parsed?.isValid() ? parsed.number : "";
}

export function readPhone(value: string, fallback: CountryCode): { country: CountryCode; national: string } {
  const text = value.trim();
  if (!text) return { country: fallback, national: "" };
  const international = text.startsWith("00") ? `+${text.slice(2)}` : text;
  const parsed = parsePhoneNumberFromString(international);
  if (parsed?.country && parsed.nationalNumber) {
    return { country: parsed.country, national: formatLocal(parsed.country, parsed.nationalNumber) };
  }
  const digits = nationalDigits(text, fallback);
  return { country: fallback, national: formatLocal(fallback, digits) };
}

export function phoneError(value: string, required = false): string | undefined {
  if (!value.trim()) return required ? "Enter a phone number." : undefined;
  if (!isValidE164(value)) return "Enter a valid phone number.";
  return undefined;
}
