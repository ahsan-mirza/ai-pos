import { ChevronDown, Search } from "lucide-react";
import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { CountryFlag, countryOption, filterCountries } from "./countryOptions";

/** A searchable country list. The closed control shows the flag, the name, and an optional detail such as the currency. */
export function CountryField({
  label,
  value,
  onChange,
  required = false,
  disabled = false,
  detail,
}: {
  label: string;
  value: string;
  onChange: (iso: string) => void;
  required?: boolean;
  disabled?: boolean;
  detail?: (iso: string) => string;
}) {
  const inputId = useId();
  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const fieldRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [highlight, setHighlight] = useState(0);
  const [menuBox, setMenuBox] = useState<{ top: number; left: number; width: number } | null>(null);
  const selected = countryOption(value);
  const groups = useMemo(() => filterCountries(query), [query]);
  const options = useMemo(() => [...groups.pinned, ...groups.rest], [groups]);

  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const rect = fieldRef.current?.getBoundingClientRect();
      if (!rect) return;
      const width = Math.max(rect.width, 280);
      setMenuBox({ top: rect.bottom + 4, left: rect.left, width });
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

  const choose = (iso: string) => {
    onChange(iso);
    setOpen(false);
    setQuery("");
    fieldRef.current?.focus();
  };

  return (
    <div ref={rootRef} className="block text-sm font-medium">
      <label id={inputId}>
        {label}
        {required ? (
          <span className="text-danger" aria-hidden="true">
            {" "}
            *
          </span>
        ) : null}
      </label>
      <button
        ref={fieldRef}
        type="button"
        disabled={disabled}
        aria-labelledby={inputId}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => {
          setOpen((current) => !current);
          setQuery("");
          setHighlight(0);
        }}
        className="mt-1.5 flex w-full items-center gap-2 rounded-xl border border-transparent bg-surface px-3 py-3 text-left text-sm font-normal disabled:cursor-not-allowed"
      >
        {selected ? <CountryFlag iso={selected.iso} /> : null}
        <span className="min-w-0 flex-1 truncate">{selected?.name ?? "Choose a country"}</span>
        {selected && detail ? <span className="shrink-0 text-charcoal/50">{detail(selected.iso)}</span> : null}
        <ChevronDown className="h-4 w-4 shrink-0 text-gray-400" aria-hidden="true" />
      </button>
      {open && menuBox
        ? createPortal(
            <div
              ref={menuRef}
              style={{ position: "fixed", top: menuBox.top, left: menuBox.left, width: menuBox.width }}
              className="z-[80] overflow-hidden rounded-xl border border-line bg-card text-charcoal shadow-lg"
            >
              <div className="relative border-b border-line p-2">
                <Search aria-hidden="true" className="pointer-events-none absolute left-5 top-1/2 z-10 h-4 w-4 -translate-y-1/2 text-charcoal/40" />
                <input
                  ref={searchRef}
                  value={query}
                  type="search"
                  aria-label="Search countries"
                  placeholder="Search country"
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
                  className="w-full rounded-lg bg-surface py-2 pl-9 pr-3 text-sm font-normal text-charcoal outline-none placeholder:text-charcoal/40 focus:bg-card [&::-webkit-search-cancel-button]:hidden"
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
                        aria-selected={option.iso === value}
                        onMouseEnter={() => setHighlight(index)}
                        onClick={() => choose(option.iso)}
                        className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm font-normal ${index === highlight ? "bg-surface" : ""}`}
                      >
                        <CountryFlag iso={option.iso} />
                        <span className="min-w-0 flex-1 truncate">{option.name}</span>
                        {detail ? <span className="text-charcoal/50">{detail(option.iso)}</span> : null}
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
  );
}
