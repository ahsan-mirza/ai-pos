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
import { ChevronDown, Phone, Search } from "lucide-react";
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
  error,
  required = false,
  disabled = false,
  defaultCountry = "AE",
  tone = "default",
}: {
  label: string;
  /** E.164, or an empty string when the visitor has not typed a number yet. */
  value: string;
  onChange: (value: string) => void;
  hint?: string;
  error?: string;
  required?: boolean;
  disabled?: boolean;
  defaultCountry?: CountryCode;
  /** Marketing forms sit on a white card. The portal keeps the default field. */
  tone?: "default" | "marketing";
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
  const invalid = Boolean(error) || (touched && value !== "" && !isValidE164(value));

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
      if (event.key !== "Escape") return;
      event.stopPropagation();
      setOpen(false);
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

  const marketing = tone === "marketing";

  return (
    <div ref={rootRef} className={marketing ? "block" : "block text-sm font-medium"}>
      <label htmlFor={inputId} className={marketing ? "mb-1.5 block text-xs font-semibold text-slate-700" : undefined}>
        {label}
      </label>
      <div
        ref={fieldRef}
        className={
          marketing
            ? `flex w-full items-center overflow-hidden rounded-xl border bg-slate-50/50 transition-all focus-within:bg-white focus-within:ring-4 ${
                invalid
                  ? "border-red-400 focus-within:border-red-400 focus-within:ring-red-500/10"
                  : "border-slate-200 focus-within:border-orange-500 focus-within:ring-orange-500/10"
              }`
            : `relative mt-1.5 flex items-center rounded-xl border bg-surface focus-within:bg-card ${
                invalid ? "border-danger" : "border-transparent focus-within:border-primary"
              }`
        }
      >
        <button
          type="button"
          disabled={disabled}
          aria-label={`Country code +${selected.dial}`}
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-controls={listId}
          onClick={() => {
            setOpen((current) => !current);
            setQuery("");
            setHighlight(0);
          }}
          className={
            marketing
              ? "flex shrink-0 cursor-pointer items-center gap-1.5 border-r border-slate-200 bg-slate-100/80 px-3 py-3 text-sm font-medium text-slate-700 disabled:cursor-not-allowed"
              : "flex shrink-0 items-center gap-1.5 px-3 py-3 text-sm disabled:cursor-not-allowed"
          }
        >
          <Flag iso={selected.iso} />
          <span>+{selected.dial}</span>
          <ChevronDown className={`h-4 w-4 ${marketing ? "text-slate-400" : "text-gray-400"}`} aria-hidden="true" />
        </button>
        {marketing ? <Phone className="pointer-events-none ml-3 h-4 w-4 shrink-0 text-slate-400" aria-hidden="true" /> : <span className="h-5 w-px bg-charcoal/15" aria-hidden="true" />}
        <input
          id={inputId}
          ref={inputRef}
          type="tel"
          inputMode="tel"
          autoComplete="tel-national"
          required={required}
          disabled={disabled}
          aria-invalid={invalid || undefined}
          aria-describedby={error ? `${inputId}-error` : undefined}
          placeholder={placeholderFor(country)}
          value={national}
          onBlur={() => setTouched(true)}
          onChange={(event) => onNational(event.target.value, event.target.selectionStart ?? event.target.value.length)}
          className={
            marketing
              ? "min-w-0 w-full flex-1 appearance-none bg-transparent px-3 py-3 text-sm text-slate-900 outline-none placeholder:text-slate-400 disabled:cursor-not-allowed [background:transparent]"
              : "min-w-0 flex-1 bg-transparent px-3 py-3 text-sm font-normal text-charcoal outline-none placeholder:text-charcoal/40 disabled:cursor-not-allowed"
          }
        />
        {open && menuBox
          ? createPortal(
              <div
                ref={menuRef}
                style={{ position: "fixed", top: menuBox.top, left: menuBox.left, width: menuBox.width }}
                className={`z-[80] overflow-hidden rounded-xl border shadow-lg ${
                  marketing ? "border-slate-200 bg-white text-slate-900" : "border-line bg-card text-charcoal"
                }`}
              >
            <div className={`relative border-b p-2 ${marketing ? "border-slate-200" : "border-line"}`}>
              <Search aria-hidden="true" className={`pointer-events-none absolute left-5 top-1/2 z-10 h-4 w-4 -translate-y-1/2 ${marketing ? "text-slate-400" : "text-charcoal/40"}`} />
              <input
                ref={searchRef}
                value={query}
                type="search"
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
                className={`w-full rounded-lg py-2 pl-9 pr-3 text-sm font-normal outline-none [&::-webkit-search-cancel-button]:hidden ${
                  marketing
                    ? "bg-slate-50 text-slate-900 placeholder:text-slate-400 focus:bg-white"
                    : "bg-surface text-charcoal placeholder:text-charcoal/40 focus:bg-card"
                }`}
              />
            </div>
            <ul id={listId} role="listbox" aria-label="Countries" className="max-h-60 overflow-y-auto py-1">
              {options.length === 0 ? (
                <li className={`px-3 py-2 text-sm font-normal ${marketing ? "text-slate-500" : "text-charcoal/50"}`}>No countries match.</li>
              ) : null}
              {options.map((option, index) => {
                const firstRest = groups.pinned.length > 0 && index === groups.pinned.length;
                return (
                  <li key={option.iso} className={firstRest ? `mt-1 border-t pt-1 ${marketing ? "border-slate-200" : "border-line"}` : undefined}>
                    <button
                      type="button"
                      role="option"
                      data-index={index}
                      aria-selected={option.iso === country}
                      onMouseEnter={() => setHighlight(index)}
                      onClick={() => choose(option.iso)}
                      className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm font-normal ${
                        index === highlight ? (marketing ? "bg-slate-50" : "bg-surface") : ""
                      }`}
                    >
                      <Flag iso={option.iso} />
                      <span className="min-w-0 flex-1 truncate">{option.name}</span>
                      <span className={marketing ? "text-slate-500" : "text-charcoal/50"}>(+{option.dial})</span>
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
      {error ? (
        <p id={`${inputId}-error`} className={marketing ? "mt-1.5 text-xs font-medium text-red-600" : "mt-1.5 text-xs font-normal text-danger"}>
          {error}
        </p>
      ) : hint ? (
        <p className={marketing ? "mt-1.5 text-xs font-normal text-slate-500" : "mt-1.5 text-xs font-normal text-charcoal/50"}>{hint}</p>
      ) : null}
    </div>
  );
}
