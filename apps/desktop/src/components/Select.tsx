import { Check, ChevronDown, Search } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";

export interface SelectOption<T extends string = string> {
  value: T;
  label: string;
  hint?: string;
  disabled?: boolean;
}

export interface SelectProps<T extends string> {
  value: T;
  options: readonly SelectOption<T>[];
  onChange: (value: T) => void;
  /** Shown when `value` matches no option, e.g. `""` before anything is picked. */
  placeholder?: string;
  disabled?: boolean;
  id?: string;
  /** Id of the visible label; the trigger announces it together with the current value. */
  labelledBy?: string;
  "aria-label"?: string;
  /** Adds a filter box to the menu. Defaults to on for lists longer than eight options. */
  searchable?: boolean;
  className?: string;
}

const SEARCH_THRESHOLD = 8;
const GAP = 8;
const EDGE = 8;
const MAX_MENU_HEIGHT = 320;
const MIN_MENU_WIDTH = 200;

interface Placement {
  left: number;
  width: number;
  top?: number;
  bottom?: number;
  maxHeight: number;
}

/** The menu is portalled with fixed coordinates so scrolling modals and tables cannot clip it. */
function place(trigger: HTMLElement): Placement {
  const rect = trigger.getBoundingClientRect();
  const width = Math.max(rect.width, MIN_MENU_WIDTH);
  const left = Math.max(EDGE, Math.min(rect.left, window.innerWidth - width - EDGE));
  const below = window.innerHeight - rect.bottom - GAP - EDGE;
  const above = rect.top - GAP - EDGE;
  if (below >= Math.min(MAX_MENU_HEIGHT, 220) || below >= above) {
    return { left, width, top: rect.bottom + GAP, maxHeight: Math.min(MAX_MENU_HEIGHT, below) };
  }
  return { left, width, bottom: window.innerHeight - rect.top + GAP, maxHeight: Math.min(MAX_MENU_HEIGHT, above) };
}

function step<T extends string>(options: readonly SelectOption<T>[], from: number, direction: 1 | -1): number {
  for (let index = from + direction; index >= 0 && index < options.length; index += direction) {
    if (!options[index]?.disabled) return index;
  }
  return from;
}

function matching<T extends string>(options: readonly SelectOption<T>[], query: string): readonly SelectOption<T>[] {
  const needle = query.trim().toLowerCase();
  if (needle === "") return options;
  return options.filter((option) => `${option.label} ${option.hint ?? ""}`.toLowerCase().includes(needle));
}

export function Select<T extends string>({
  value,
  options,
  onChange,
  placeholder = "Select…",
  disabled = false,
  id,
  labelledBy,
  "aria-label": ariaLabel,
  searchable,
  className = "",
}: SelectProps<T>) {
  const baseId = useId();
  const triggerId = id ?? `${baseId}-trigger`;
  const valueId = `${baseId}-value`;
  const listId = `${baseId}-list`;
  const optionId = (index: number) => `${baseId}-option-${index}`;
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const typeahead = useRef({ text: "", at: 0 });
  const [open, setOpen] = useState(false);
  const [shown, setShown] = useState(false);
  const [placement, setPlacement] = useState<Placement | null>(null);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(-1);
  const withSearch = searchable ?? options.length > SEARCH_THRESHOLD;
  const visible = useMemo(() => matching(options, query), [options, query]);
  const selected = options.find((option) => option.value === value);

  const close = (refocus: boolean) => {
    setOpen(false);
    setShown(false);
    if (refocus) triggerRef.current?.focus();
  };

  const openMenu = () => {
    if (disabled || triggerRef.current === null) return;
    const current = options.findIndex((option) => option.value === value);
    setPlacement(place(triggerRef.current));
    setQuery("");
    setActive(current >= 0 ? current : step(options, -1, 1));
    setOpen(true);
  };

  const choose = (option: SelectOption<T> | undefined) => {
    if (option === undefined || option.disabled) return;
    if (option.value !== value) onChange(option.value);
    close(true);
  };

  useEffect(() => {
    if (!open) return;
    (withSearch ? searchRef.current : listRef.current)?.focus({ preventScroll: true });
    const frame = window.requestAnimationFrame(() => setShown(true));
    const reposition = (event: Event) => {
      if (event.target instanceof Node && menuRef.current?.contains(event.target)) return;
      if (triggerRef.current) setPlacement(place(triggerRef.current));
    };
    const dismiss = (event: PointerEvent) => {
      const target = event.target as Node;
      if (menuRef.current?.contains(target) || triggerRef.current?.contains(target)) return;
      setOpen(false);
      setShown(false);
    };
    window.addEventListener("resize", reposition);
    window.addEventListener("scroll", reposition, true);
    document.addEventListener("pointerdown", dismiss);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", reposition);
      window.removeEventListener("scroll", reposition, true);
      document.removeEventListener("pointerdown", dismiss);
    };
  }, [open, withSearch]);

  useEffect(() => {
    if (open && active >= 0) document.getElementById(`${baseId}-option-${active}`)?.scrollIntoView({ block: "nearest" });
  }, [open, active, baseId]);

  const onTriggerKey = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      openMenu();
    }
  };

  const onMenuKey = (event: KeyboardEvent<HTMLDivElement>) => {
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        setActive((index) => step(visible, index, 1));
        return;
      case "ArrowUp":
        event.preventDefault();
        setActive((index) => step(visible, index, -1));
        return;
      case "Home":
        event.preventDefault();
        setActive(step(visible, -1, 1));
        return;
      case "End":
        event.preventDefault();
        setActive(step(visible, visible.length, -1));
        return;
      case "Enter":
        event.preventDefault();
        choose(visible[active]);
        return;
      case "Escape":
        event.preventDefault();
        event.stopPropagation();
        close(true);
        return;
      case "Tab":
        close(true);
        return;
    }
    if (withSearch || event.key.length !== 1 || event.ctrlKey || event.metaKey || event.altKey) return;
    const now = Date.now();
    const text = (now - typeahead.current.at < 600 ? typeahead.current.text : "") + event.key.toLowerCase();
    typeahead.current = { text, at: now };
    if (text === " ") {
      event.preventDefault();
      typeahead.current.text = "";
      choose(visible[active]);
      return;
    }
    const start = text.length === 1 ? active + 1 : Math.max(active, 0);
    for (let offset = 0; offset < visible.length; offset += 1) {
      const index = (start + offset) % visible.length;
      const option = visible[index];
      if (option && !option.disabled && option.label.toLowerCase().startsWith(text)) {
        setActive(index);
        return;
      }
    }
  };

  return (
    <div className={`relative w-full ${className}`}>
      <button
        ref={triggerRef}
        id={triggerId}
        type="button"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        aria-labelledby={labelledBy ? `${labelledBy} ${valueId}` : undefined}
        aria-label={labelledBy ? undefined : ariaLabel}
        onClick={() => (open ? close(false) : openMenu())}
        onKeyDown={onTriggerKey}
        className={`flex h-11 w-full items-center rounded-full border bg-white py-2.5 pl-5 pr-11 text-left text-sm font-medium tracking-normal text-charcoal normal-case transition-all focus:outline-none disabled:cursor-not-allowed disabled:bg-surface disabled:text-charcoal/50 dark:bg-zinc-900 dark:text-zinc-100 dark:disabled:bg-zinc-800 dark:disabled:text-zinc-500 ${
          open
            ? "border-primary ring-2 ring-primary/20"
            : "border-line hover:border-gray-400 focus:border-primary focus-visible:ring-2 focus-visible:ring-primary/20 disabled:hover:border-line dark:border-zinc-700 dark:hover:border-zinc-500"
        }`}
      >
        <span id={valueId} className={`block min-w-0 truncate ${selected ? "" : "text-charcoal/40"}`}>
          {selected?.label ?? placeholder}
        </span>
      </button>
      <ChevronDown
        aria-hidden="true"
        strokeWidth={2}
        className={`pointer-events-none absolute right-4 top-1/2 h-4 w-4 -translate-y-1/2 transition-transform duration-200 ${
          open ? "rotate-180" : ""
        } ${disabled ? "text-charcoal/30 dark:text-zinc-600" : "text-charcoal dark:text-zinc-300"}`}
      />
      {open && placement
        ? createPortal(
            <div
              ref={menuRef}
              onKeyDown={onMenuKey}
              style={{
                left: placement.left,
                width: placement.width,
                top: placement.top,
                bottom: placement.bottom,
                maxHeight: placement.maxHeight,
              }}
              className={`fixed z-[60] flex min-w-[200px] flex-col overflow-hidden rounded-2xl border border-line bg-white p-1.5 font-sans shadow-xl transition duration-150 ease-out motion-reduce:transition-none dark:border-zinc-800 dark:bg-zinc-900 ${
                placement.top !== undefined ? "origin-top" : "origin-bottom"
              } ${shown ? "scale-100 opacity-100" : "scale-95 opacity-0"}`}
            >
              {withSearch ? (
                <div className="relative mb-1.5 shrink-0">
                  <Search
                    size={15}
                    aria-hidden="true"
                    className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-charcoal/40"
                  />
                  <input
                    ref={searchRef}
                    role="combobox"
                    aria-expanded="true"
                    aria-controls={listId}
                    aria-autocomplete="list"
                    aria-activedescendant={active >= 0 && visible[active] ? optionId(active) : undefined}
                    aria-label="Filter options"
                    value={query}
                    placeholder="Search…"
                    onChange={(event) => {
                      setQuery(event.target.value);
                      setActive(step(matching(options, event.target.value), -1, 1));
                    }}
                    className="h-10 w-full rounded-xl bg-surface pl-9 pr-3 text-sm text-charcoal placeholder:text-charcoal/40 focus:outline-none focus:ring-2 focus:ring-primary/20"
                  />
                </div>
              ) : null}
              <ul
                ref={listRef}
                id={listId}
                role="listbox"
                tabIndex={-1}
                aria-labelledby={labelledBy}
                aria-label={labelledBy ? undefined : ariaLabel}
                aria-activedescendant={!withSearch && active >= 0 ? optionId(active) : undefined}
                className="min-h-0 flex-1 space-y-0.5 overflow-y-auto focus:outline-none"
              >
                {visible.map((option, index) => {
                  const isSelected = option.value === value;
                  const isActive = index === active;
                  return (
                    <li
                      key={option.value}
                      id={optionId(index)}
                      role="option"
                      aria-selected={isSelected}
                      aria-disabled={option.disabled || undefined}
                      onPointerMove={() => (option.disabled || isActive ? undefined : setActive(index))}
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() => choose(option)}
                      className={`flex items-center justify-between gap-3 rounded-xl px-4 py-2.5 text-sm transition-colors ${
                        isSelected
                          ? `font-semibold text-primary ${isActive ? "bg-primary/15" : "bg-primary/10"}`
                          : `font-medium text-charcoal dark:text-zinc-100 ${
                              isActive ? "bg-surface dark:bg-white/10" : "hover:bg-surface dark:hover:bg-white/10"
                            }`
                      } ${option.disabled ? "cursor-not-allowed opacity-40" : "cursor-pointer"}`}
                    >
                      <span className="min-w-0">
                        <span className="block truncate">{option.label}</span>
                        {option.hint ? (
                          <span className="block truncate text-xs font-normal text-charcoal/50">{option.hint}</span>
                        ) : null}
                      </span>
                      {isSelected ? (
                        <Check size={16} strokeWidth={2.5} aria-hidden="true" className="shrink-0 text-primary" />
                      ) : null}
                    </li>
                  );
                })}
                {visible.length === 0 ? (
                  <li role="presentation" className="px-4 py-2.5 text-sm text-charcoal/50">
                    No matches
                  </li>
                ) : null}
              </ul>
            </div>,
            triggerRef.current?.closest<HTMLElement>('[data-theme], .dark') ?? document.body,
          )
        : null}
    </div>
  );
}
