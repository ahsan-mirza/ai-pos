import { getCountries, getCountryCallingCode, type CountryCode } from "libphonenumber-js";
import * as flagIcons from "country-flag-icons/react/3x2";
import { type ComponentType, type SVGProps } from "react";

/** Countries shown before the alphabetical list. Gulf first, then the other numbers people type here. */
export const PINNED_COUNTRIES: CountryCode[] = ["AE", "SA", "QA", "KW", "BH", "OM", "PK", "IN", "US", "GB"];

const ALIASES: Partial<Record<CountryCode, string[]>> = {
  AE: ["uae", "emirates"],
  SA: ["ksa", "saudi"],
  QA: ["qat"],
  OM: ["omn"],
  BH: ["bhr"],
  KW: ["kwt"],
  PK: ["pak"],
  IN: ["ind"],
  US: ["usa"],
  GB: ["uk", "britain"],
};

export interface CountryOption {
  iso: CountryCode;
  name: string;
  dial: string;
}

const regionNames = new Intl.DisplayNames(["en"], { type: "region" });

function flagEmoji(iso: string): string {
  return [...iso.toUpperCase()].map((char) => String.fromCodePoint(127397 + char.charCodeAt(0))).join("");
}

export function CountryFlag({ iso }: { iso: string }) {
  const icons = flagIcons as unknown as Record<string, ComponentType<SVGProps<SVGSVGElement>> | undefined>;
  const Icon = icons[iso];
  if (!Icon) {
    return (
      <span aria-hidden="true" className="text-base leading-none">
        {flagEmoji(iso)}
      </span>
    );
  }
  return <Icon className="h-3.5 w-5 shrink-0 rounded-[2px]" />;
}

export const COUNTRY_OPTIONS: CountryOption[] = getCountries()
  .map((iso) => ({
    iso,
    name: regionNames.of(iso) ?? iso,
    dial: getCountryCallingCode(iso),
  }))
  .sort((left, right) => left.name.localeCompare(right.name));

const BY_ISO = new Map(COUNTRY_OPTIONS.map((country) => [country.iso, country]));

export function countryOption(iso: string): CountryOption | undefined {
  return BY_ISO.get(iso as CountryCode);
}

function matches(country: CountryOption, query: string): boolean {
  if (!query) return true;
  const text = query.toLowerCase();
  const digits = text.replace(/\D/g, "");
  if (country.name.toLowerCase().includes(text)) return true;
  if (country.iso.toLowerCase().includes(text)) return true;
  if (digits && country.dial.includes(digits)) return true;
  return (ALIASES[country.iso] ?? []).some((alias) => alias.includes(text));
}

export function filterCountries(query: string): { pinned: CountryOption[]; rest: CountryOption[] } {
  const pinned = PINNED_COUNTRIES.map((iso) => BY_ISO.get(iso)).filter((country): country is CountryOption => country !== undefined);
  if (!query.trim()) {
    const pinnedSet = new Set<CountryCode>(PINNED_COUNTRIES);
    return { pinned, rest: COUNTRY_OPTIONS.filter((country) => !pinnedSet.has(country.iso)) };
  }
  return { pinned: [], rest: COUNTRY_OPTIONS.filter((country) => matches(country, query)) };
}
