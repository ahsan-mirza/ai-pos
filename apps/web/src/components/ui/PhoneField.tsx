import {
  formatIncompletePhoneNumber,
  getCountries,
  getCountryCallingCode,
  getExampleNumber,
  isValidPhoneNumber,
  parsePhoneNumberFromString,
  type CountryCode,
} from "libphonenumber-js";
import examples from "libphonenumber-js/mobile/examples";
import * as flagIcons from "country-flag-icons/react/3x2";
import { ChevronDown } from "lucide-react";
import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type ComponentType, type SVGProps } from "react";
import { createPortal } from "react-dom";

/** Countries shown before the alphabetical list. Gulf first, then the other numbers people type here. */
const PINNED: CountryCode[] = ["AE", "SA", "QA", "OM", "BH", "PK", "IN", "US", "GB"];

const ALIASES: Partial<Record<CountryCode, string[]>> = {
  AE: ["uae", "emirates"],
  SA: ["ksa", "saudi"],
  QA: ["qat"],
  OM: ["omn"],
  BH: ["bhr"],
  PK: ["pak"],
  IN: ["ind"],
  US: ["usa"],
  GB: ["uk", "britain"],
};

interface CountryOption {
  iso: CountryCode;
  name: string;
  dial: string;
}

const regionNames = new Intl.DisplayNames(["en"], { type: "region" });

function flagEmoji(iso: string): string {
  return [...iso.toUpperCase()].map((char) => String.fromCodePoint(127397 + char.charCodeAt(0))).join("");
}

function Flag({ iso }: { iso: string }) {
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

const COUNTRIES: CountryOption[] = getCountries()
  .map((iso) => ({
    iso,
    name: regionNames.of(iso) ?? iso,
    dial: getCountryCallingCode(iso),
  }))
  .sort((left, right) => left.name.localeCompare(right.name));

const BY_ISO = new Map(COUNTRIES.map((country) => [country.iso, country]));

const trunkCache = new Map<CountryCode, string>();

/** Trunk "0" is part of the national print, not the number we store. */
function trunkPrefix(country: CountryCode): string {
  const cached = trunkCache.get(country);
  if (cached !== undefined) return cached;
  const example = getExampleNumber(country, examples);
  const national = example?.formatNational() ?? "";
  const trunk = national.startsWith("0") && example && !example.nationalNumber.startsWith("0") ? "0" : "";
  trunkCache.set(country, trunk);
  return trunk;
}

function nationalDigits(raw: string): string {
  return raw.replace(/\D/g, "").replace(/^0+/, "");
}

function formatLocal(country: CountryCode, digits: string): string {
  if (!digits) return "";
  const trunk = trunkPrefix(country);
  const formatted = formatIncompletePhoneNumber(`${trunk}${digits}`, country);
  if (trunk && formatted.startsWith(trunk)) return formatted.slice(trunk.length).trimStart();
  return formatted;
}

function placeholderFor(country: CountryCode): string {
  const example = getExampleNumber(country, examples);
  if (!example) return "";
  return formatLocal(country, example.nationalNumber);
}

function caretAfterDigits(formatted: string, digitCount: number): number {
  if (digitCount <= 0) return 0;
  let seen = 0;
  for (let index = 0; index < formatted.length; index += 1) {
    if (/\d/.test(formatted[index] ?? "")) {
      seen += 1;
      if (seen === digitCount) return index + 1;
    }
  }
  return formatted.length;
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

function listed(query: string): { pinned: CountryOption[]; rest: CountryOption[] } {
  const pinned = PINNED.map((iso) => BY_ISO.get(iso)).filter((country): country is CountryOption => country !== undefined);
  if (!query.trim()) {
    const pinnedSet = new Set<CountryCode>(PINNED);
    return { pinned: pinned.filter((country) => matches(country, query)), rest: COUNTRIES.filter((country) => !pinnedSet.has(country.iso)) };
  }
  const found = COUNTRIES.filter((country) => matches(country, query));
  return { pinned: [], rest: found };
}

/** True when `value` is a complete E.164 number, for example `+971501234567`. */
export function isValidE164(value: string): boolean {
  return value.startsWith("+") && isValidPhoneNumber(value);
}

function readValue(value: string, fallback: CountryCode): { country: CountryCode; national: string } {
  if (!value) return { country: fallback, national: "" };
  const parsed = parsePhoneNumberFromString(value);
  const country = parsed?.country ?? fallback;
  const digits = parsed?.nationalNumber ?? nationalDigits(value);
  return { country, national: formatLocal(country, digits) };
}

export function PhoneField({
  label,
  value,
  onChange,
  hint,
  required = false,
  disabled = false,
  defaultCountry = "AE",
}: {
  label: string;
  /** E.164, or an empty string when the visitor has not typed a number yet. */
  value: string;
  onChange: (value: string) => void;
  hint?: string;
  required?: boolean;
  disabled?: boolean;
  defaultCountry?: CountryCode;
}) {
  const inputId = useId();
  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const fieldRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const emitted = useRef(value);
  const caretDigits = useRef<number | null>(null);
  const initial = readValue(value, defaultCountry);
  const [country, setCountry] = useState<CountryCode>(initial.country);
  const [national, setNational] = useState(initial.national);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [highlight, setHighlight] = useState(0);
  const [touched, setTouched] = useState(false);
  const [menuBox, setMenuBox] = useState<{ top: number; left: number; width: number } | null>(null);

  const selected = BY_ISO.get(country) ?? COUNTRIES[0];
  const groups = useMemo(() => listed(query), [query]);
  const options = useMemo(() => [...groups.pinned, ...groups.rest], [groups]);
  const invalid = touched && value !== "" && !isValidE164(value);

  useEffect(() => {
    if (value === emitted.current) return;
    emitted.current = value;
    const next = readValue(value, defaultCountry);
    setCountry(next.country);
    setNational(next.national);
  }, [value, defaultCountry]);

  useLayoutEffect(() => {
    const digits = caretDigits.current;
    const input = inputRef.current;
    if (digits === null || !input) return;
    const position = caretAfterDigits(national, digits);
    input.setSelectionRange(position, position);
    caretDigits.current = null;
  }, [national]);

  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const rect = fieldRef.current?.getBoundingClientRect();
      if (!rect) return;
      setMenuBox({ top: rect.bottom + 4, left: rect.left, width: rect.width });
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    searchRef.current?.focus();
    const close = (event: MouseEvent) => {
      const target = event.target as Node;
      if (!rootRef.current?.contains(target) && !menuRef.current?.contains(target)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    menuRef.current?.querySelector<HTMLElement>(`[data-index="${highlight}"]`)?.scrollIntoView({ block: "nearest" });
  }, [highlight, open]);

  const emit = (nextCountry: CountryCode, digits: string) => {
    const calling = getCountryCallingCode(nextCountry);
    const limit = Math.max(1, 15 - calling.length);
    const body = digits.slice(0, limit);
    const next = body ? `+${calling}${body}` : "";
    emitted.current = next;
    setNational(formatLocal(nextCountry, body));
    onChange(next);
  };

  const choose = (next: CountryCode) => {
    setCountry(next);
    setOpen(false);
    setQuery("");
    emit(next, nationalDigits(national));
    inputRef.current?.focus();
  };

  const onNational = (raw: string, caret: number) => {
    if (raw.trim().startsWith("+") || raw.trim().startsWith("00")) {
      const parsed = parsePhoneNumberFromString(raw.trim().startsWith("00") ? `+${raw.trim().slice(2)}` : raw);
      if (parsed?.country) {
        setCountry(parsed.country);
        caretDigits.current = parsed.nationalNumber.length;
        emit(parsed.country, parsed.nationalNumber);
        return;
      }
    }
    const digits = nationalDigits(raw);
    caretDigits.current = nationalDigits(raw.slice(0, caret)).length;
    emit(country, digits);
  };

  if (!selected) return null;

  return (
    <div ref={rootRef} className="block text-sm font-medium">
      <label htmlFor={inputId}>{label}</label>
      <div
        ref={fieldRef}
        className={`relative mt-1.5 flex items-center rounded-xl border bg-surface focus-within:bg-white ${
          invalid ? "border-accent" : "border-transparent focus-within:border-accent"
        }`}
      >
        <button
          type="button"
          disabled={disabled}
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-controls={listId}
          onClick={() => {
            setOpen((current) => !current);
            setQuery("");
            setHighlight(0);
          }}
          className="flex shrink-0 items-center gap-1.5 px-3 py-3 text-sm disabled:cursor-not-allowed"
        >
          <Flag iso={selected.iso} />
          <span>+{selected.dial}</span>
          <ChevronDown className="w-4 h-4 text-gray-400" aria-hidden="true" />
        </button>
        <span className="h-5 w-px bg-charcoal/15" aria-hidden="true" />
        <input
          id={inputId}
          ref={inputRef}
          type="tel"
          inputMode="tel"
          autoComplete="tel-national"
          required={required}
          disabled={disabled}
          aria-invalid={invalid}
          placeholder={placeholderFor(country)}
          value={national}
          onBlur={() => setTouched(true)}
          onChange={(event) => onNational(event.target.value, event.target.selectionStart ?? event.target.value.length)}
          className="min-w-0 flex-1 bg-transparent px-3 py-3 text-sm font-normal text-charcoal outline-none placeholder:text-charcoal/40 disabled:cursor-not-allowed"
        />
        {open && menuBox
          ? createPortal(
              <div
                ref={menuRef}
                style={{ position: "fixed", top: menuBox.top, left: menuBox.left, width: menuBox.width }}
                className="z-50 overflow-hidden rounded-xl border border-line bg-white shadow-lg"
              >
            <div className="border-b border-line p-2">
              <input
                ref={searchRef}
                value={query}
                aria-label="Search countries"
                placeholder="Search country or code"
                onChange={(event) => {
                  setQuery(event.target.value);
                  setHighlight(0);
                }}
                onKeyDown={(event) => {
                  if (event.key === "ArrowDown") {
                    event.preventDefault();
                    setHighlight((index) => Math.min(index + 1, Math.max(options.length - 1, 0)));
                  } else if (event.key === "ArrowUp") {
                    event.preventDefault();
                    setHighlight((index) => Math.max(index - 1, 0));
                  } else if (event.key === "Enter") {
                    event.preventDefault();
                    const next = options[highlight];
                    if (next) choose(next.iso);
                  }
                }}
                className="w-full rounded-lg bg-surface px-3 py-2 text-sm font-normal outline-none placeholder:text-charcoal/40 focus:bg-white"
              />
            </div>
            <ul id={listId} role="listbox" aria-label="Countries" className="max-h-60 overflow-y-auto py-1">
              {options.length === 0 ? <li className="px-3 py-2 text-sm font-normal text-charcoal/50">No countries match.</li> : null}
              {options.map((option, index) => {
                const firstRest = groups.pinned.length > 0 && index === groups.pinned.length;
                return (
                  <li key={option.iso} className={firstRest ? "mt-1 border-t border-line pt-1" : undefined}>
                    <button
                      type="button"
                      role="option"
                      data-index={index}
                      aria-selected={option.iso === country}
                      onMouseEnter={() => setHighlight(index)}
                      onClick={() => choose(option.iso)}
                      className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm font-normal ${
                        index === highlight ? "bg-surface" : ""
                      }`}
                    >
                      <Flag iso={option.iso} />
                      <span className="min-w-0 flex-1 truncate">{option.name}</span>
                      <span className="text-charcoal/50">(+{option.dial})</span>
                    </button>
                  </li>
                );
              })}
            </ul>
              </div>,
              document.body,
            )
          : null}
      </div>
      {hint ? <p className="mt-1.5 text-xs font-normal text-charcoal/50">{hint}</p> : null}
    </div>
  );
}
