import { getCountryCallingCode, parsePhoneNumberFromString, type CountryCode } from "libphonenumber-js";
import { ChevronDown, Phone, Search } from "lucide-react";
import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { CountryFlag, countryOption, filterCountries } from "./countryOptions";
import { formatLocal, isValidE164, nationalDigits, placeholderFor, readPhone, toE164 } from "./phone";

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

export function PhoneField({
  label,
  value,
  onChange,
  hint,
  error,
  required = false,
  disabled = false,
  defaultCountry = "AE",
  selectedCountry,
  onCountryChange,
  tone = "default",
  endAdornment,
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
  /** When set, the dial code follows this country. Choosing a code reports it back. */
  selectedCountry?: CountryCode;
  onCountryChange?: (country: CountryCode) => void;
  /** Marketing forms sit on a white card. The portal keeps the default field. */
  tone?: "default" | "marketing";
  /** Sits inside the right edge. Room is reserved so the number does not move when it appears. */
  endAdornment?: ReactNode;
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
  const initial = readPhone(value, selectedCountry ?? defaultCountry);
  const [internalCountry, setInternalCountry] = useState<CountryCode>(initial.country);
  const country = selectedCountry ?? internalCountry;
  const [national, setNational] = useState(initial.national);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [highlight, setHighlight] = useState(0);
  const [touched, setTouched] = useState(false);
  const [menuBox, setMenuBox] = useState<{ top: number; left: number; width: number } | null>(null);

  const selected = countryOption(country) ?? countryOption("AE");
  const groups = useMemo(() => filterCountries(query), [query]);
  const options = useMemo(() => [...groups.pinned, ...groups.rest], [groups]);
  const ownError =
    touched && required && value === ""
      ? "Enter a phone number."
      : touched && value !== "" && !isValidE164(value)
        ? "Enter a valid phone number."
        : undefined;
  const message = error || ownError;
  const invalid = Boolean(message);

  useEffect(() => {
    if (value === emitted.current) return;
    const canonical = !value || isValidE164(value) ? value : toE164(value, defaultCountry);
    const shown = canonical || value;
    emitted.current = shown;
    const next = readPhone(shown, defaultCountry);
    setInternalCountry(next.country);
    setNational(next.national);
    if (canonical && canonical !== value) onChange(canonical);
  }, [value, defaultCountry, onChange]);

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

  const formattedFor = useRef(country);
  useEffect(() => {
    if (formattedFor.current === country) return;
    formattedFor.current = country;
    setInternalCountry(country);
    emit(country, nationalDigits(national, country));
  }, [country]);

  const choose = (next: CountryCode) => {
    formattedFor.current = next;
    setInternalCountry(next);
    setOpen(false);
    setQuery("");
    emit(next, nationalDigits(national, next));
    onCountryChange?.(next);
    inputRef.current?.focus();
  };

  const onNational = (raw: string, caret: number) => {
    if (raw.trim().startsWith("+") || raw.trim().startsWith("00")) {
      const parsed = parsePhoneNumberFromString(raw.trim().startsWith("00") ? `+${raw.trim().slice(2)}` : raw);
      if (parsed?.country) {
        formattedFor.current = parsed.country;
        setInternalCountry(parsed.country);
        onCountryChange?.(parsed.country);
        caretDigits.current = parsed.nationalNumber.length;
        emit(parsed.country, parsed.nationalNumber);
        return;
      }
    }
    const digits = nationalDigits(raw, country);
    caretDigits.current = nationalDigits(raw.slice(0, caret), country).length
    emit(country, digits);
  };

  if (!selected) return null;

  const marketing = tone === "marketing";

  return (
    <div ref={rootRef} className={marketing ? "block" : "block text-sm font-medium"}>
      <label htmlFor={inputId} className={marketing ? "mb-1.5 block text-xs font-semibold text-slate-700" : undefined}>
        {label}
        {required ? (
          <span className={marketing ? "text-red-600" : "text-danger"} aria-hidden="true">
            {" "}
            *
          </span>
        ) : null}
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
          <CountryFlag iso={selected.iso} />
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
          disabled={disabled}
          aria-required={required || undefined}
          aria-invalid={invalid || undefined}
          aria-describedby={message ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined}
          placeholder={placeholderFor(country)}
          value={national}
          onBlur={() => setTouched(true)}
          onChange={(event) => onNational(event.target.value, event.target.selectionStart ?? event.target.value.length)}
          className={
            marketing
              ? `min-w-0 w-full flex-1 appearance-none bg-transparent py-3 pl-3 text-sm text-slate-900 outline-none placeholder:text-slate-400 disabled:cursor-not-allowed [background:transparent] ${endAdornment ? "pr-11" : "pr-3"}`
              : `min-w-0 flex-1 bg-transparent py-3 pl-3 text-sm font-normal text-charcoal outline-none placeholder:text-charcoal/40 disabled:cursor-not-allowed ${endAdornment ? "pr-11" : "pr-3"}`
          }
        />
        {endAdornment}
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
                      <CountryFlag iso={option.iso} />
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
      {message ? (
        <p id={`${inputId}-error`} role="alert" className={marketing ? "mt-1.5 text-xs font-medium text-red-600" : "mt-1.5 text-xs font-normal text-danger"}>
          {message}
        </p>
      ) : hint ? (
        <p id={`${inputId}-hint`} className={marketing ? "mt-1.5 text-xs font-normal text-slate-500" : "mt-1.5 text-xs font-normal text-charcoal/50"}>
          {hint}
        </p>
      ) : null}
    </div>
  );
}
