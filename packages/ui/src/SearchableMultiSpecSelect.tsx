import { Check, ChevronDown, Plus, Search, X, type LucideIcon } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";

export interface SearchableMultiSpecSelectProps {
  label: string;
  options: readonly string[];
  values: readonly string[];
  onChange: (values: string[]) => void;
  /** Adds the typed name to the option list. The parent also selects it. */
  onCreateOption: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  icon?: LucideIcon;
}

const GAP = 8;
const EDGE = 8;
const MAX_MENU_HEIGHT = 320;

interface Placement {
  left: number;
  width: number;
  top?: number;
  bottom?: number;
  maxHeight: number;
}

function place(trigger: HTMLElement): Placement {
  const rect = trigger.getBoundingClientRect();
  const width = Math.max(rect.width, 220);
  const left = Math.max(EDGE, Math.min(rect.left, window.innerWidth - width - EDGE));
  const below = window.innerHeight - rect.bottom - GAP - EDGE;
  const above = rect.top - GAP - EDGE;
  if (below >= 180 || below >= above) {
    return { left, width, top: rect.bottom + GAP, maxHeight: Math.min(MAX_MENU_HEIGHT, below) };
  }
  return { left, width, bottom: window.innerHeight - rect.top + GAP, maxHeight: Math.min(MAX_MENU_HEIGHT, above) };
}

function clean(value: string): string {
  return value.trim().replace(/\s+/g, " ");
}

function same(left: string, right: string): boolean {
  return left.trim().toLowerCase() === right.trim().toLowerCase();
}

/** Searchable multi-select. Chosen values are chips. A value cannot be selected twice. */
export function SearchableMultiSpecSelect({
  label,
  options,
  values,
  onChange,
  onCreateOption,
  placeholder,
  disabled = false,
  icon: Icon,
}: SearchableMultiSpecSelectProps) {
  const baseId = useId();
  const listId = `${baseId}-list`;
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const draftRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [placement, setPlacement] = useState<Placement | null>(null);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState("");
  const prompt = placeholder ?? `Select ${label.toLowerCase()}`;
  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (needle === "") return options;
    return options.filter((option) => option.toLowerCase().includes(needle));
  }, [options, query]);

  const close = (refocus: boolean) => {
    setOpen(false);
    setCreating(false);
    setDraft("");
    if (refocus) triggerRef.current?.focus();
  };

  const openMenu = () => {
    if (disabled || triggerRef.current === null) return;
    setPlacement(place(triggerRef.current));
    setQuery("");
    setActive(0);
    setCreating(false);
    setOpen(true);
  };

  const choose = (option: string) => {
    if (values.some((value) => same(value, option))) return;
    onChange([...values, option]);
    setQuery("");
    setActive(0);
  };

  const remove = (option: string) => {
    onChange(values.filter((value) => !same(value, option)));
  };

  const startCreate = () => {
    setDraft(query.trim());
    setCreating(true);
  };

  const commitCreate = () => {
    const name = clean(draft);
    if (name === "") return;
    const existing = options.find((option) => same(option, name)) ?? values.find((value) => same(value, name));
    if (existing) {
      choose(existing);
      setCreating(false);
      setDraft("");
      return;
    }
    onCreateOption(name);
    setCreating(false);
    setDraft("");
    setQuery("");
  };

  useEffect(() => {
    if (!open) return;
    const focusTarget = creating ? draftRef.current : searchRef.current;
    focusTarget?.focus({ preventScroll: true });
    const reposition = (event: Event) => {
      if (event.target instanceof Node && menuRef.current?.contains(event.target)) return;
      if (triggerRef.current) setPlacement(place(triggerRef.current));
    };
    const dismiss = (event: PointerEvent) => {
      const target = event.target as Node;
      if (menuRef.current?.contains(target) || triggerRef.current?.contains(target)) return;
      setOpen(false);
      setCreating(false);
    };
    window.addEventListener("resize", reposition);
    window.addEventListener("scroll", reposition, true);
    document.addEventListener("pointerdown", dismiss);
    return () => {
      window.removeEventListener("resize", reposition);
      window.removeEventListener("scroll", reposition, true);
      document.removeEventListener("pointerdown", dismiss);
    };
  }, [open, creating]);

  useEffect(() => {
    if (!open || active < 0) return;
    document.getElementById(`${baseId}-option-${active}`)?.scrollIntoView({ block: "nearest" });
  }, [open, active, baseId]);

  const onSearchKey = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((index) => Math.min(visible.length - 1, index + 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((index) => Math.max(0, index - 1));
    } else if (event.key === "Enter") {
      event.preventDefault();
      const picked = visible[active];
      if (picked) choose(picked);
      else if (query.trim() !== "") startCreate();
    } else if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      close(true);
    }
  };

  return (
    <div className="block text-sm font-medium text-charcoal dark:text-white">
      <span id={`${baseId}-label`}>{label}</span>
      {values.length > 0 ? (
        <ul className="mt-1.5 flex flex-wrap gap-1.5" aria-label={`Selected ${label.toLowerCase()}`}>
          {values.map((value) => (
            <li key={value}>
              <span className="inline-flex h-8 max-w-full items-center gap-1 rounded-full bg-orange-50 pl-3 pr-1 text-xs font-semibold text-orange-700">
                <span className="truncate">{value}</span>
                <button
                  type="button"
                  disabled={disabled}
                  aria-label={`Remove ${value}`}
                  onClick={() => remove(value)}
                  className="flex h-6 w-6 items-center justify-center rounded-full text-orange-700 hover:bg-orange-100 disabled:opacity-40"
                >
                  <X aria-hidden="true" className="h-3.5 w-3.5" />
                </button>
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      <span className="relative mt-1.5 block">
        <button
          ref={triggerRef}
          id={`${baseId}-trigger`}
          type="button"
          disabled={disabled}
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-controls={open ? listId : undefined}
          aria-labelledby={`${baseId}-label`}
          onClick={() => (open ? close(false) : openMenu())}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown" || event.key === "ArrowUp" || event.key === "Enter") {
              event.preventDefault();
              openMenu();
            }
          }}
          className={`flex h-12 w-full items-center rounded-xl border border-slate-200 bg-slate-50 px-4 pr-10 text-left text-sm font-medium transition focus:bg-white focus:outline-none focus:ring-2 focus:ring-orange-500 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-700/80 dark:bg-[#2D2A32] dark:text-white dark:focus:bg-[#2D2A32] ${
            open ? "border-orange-500 bg-white ring-2 ring-orange-500" : "hover:border-slate-300"
          } ${values.length === 0 ? "text-slate-400" : ""}`}
        >
          {Icon ? <Icon aria-hidden="true" className="mr-2 h-4 w-4 shrink-0 text-slate-400" /> : null}
          <span className="truncate">{values.length === 0 ? prompt : `Add ${label.toLowerCase()}`}</span>
        </button>
        <ChevronDown
          aria-hidden="true"
          className={`pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </span>
      {open && placement
        ? createPortal(
            <div
              ref={menuRef}
              style={{
                left: placement.left,
                width: placement.width,
                top: placement.top,
                bottom: placement.bottom,
                maxHeight: placement.maxHeight,
              }}
              className="fixed z-[90] flex flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl dark:border-gray-700 dark:bg-[#222026]"
            >
              <div className="relative shrink-0 p-2">
                <Search aria-hidden="true" className="pointer-events-none absolute left-5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  ref={searchRef}
                  role="combobox"
                  aria-expanded="true"
                  aria-controls={listId}
                  aria-autocomplete="list"
                  aria-label={`Search ${label}`}
                  value={query}
                  placeholder={`Search ${label.toLowerCase()}`}
                  onChange={(event) => {
                    setQuery(event.target.value);
                    setActive(0);
                  }}
                  onKeyDown={onSearchKey}
                  className="h-10 w-full rounded-xl border border-slate-200 bg-slate-50 pl-9 pr-3 text-sm text-charcoal placeholder:text-slate-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-orange-500 dark:border-gray-700 dark:bg-[#2D2A32] dark:text-white"
                />
              </div>
              <ul id={listId} role="listbox" aria-label={label} aria-multiselectable="true" className="min-h-0 flex-1 space-y-0.5 overflow-y-auto px-1.5 pb-1">
                {visible.map((option, index) => {
                  const selected = values.some((value) => same(value, option));
                  const highlighted = index === active;
                  return (
                    <li key={option} role="presentation">
                      <button
                        id={`${baseId}-option-${index}`}
                        type="button"
                        role="option"
                        aria-selected={selected}
                        disabled={selected}
                        onMouseEnter={() => setActive(index)}
                        onMouseDown={(event) => event.preventDefault()}
                        onClick={() => choose(option)}
                        className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition-colors hover:bg-orange-50 hover:text-orange-600 disabled:cursor-default ${
                          selected || highlighted ? "bg-orange-50 text-orange-600" : "text-charcoal dark:text-white"
                        }`}
                      >
                        {Icon ? <Icon aria-hidden="true" className="h-4 w-4 shrink-0 text-slate-400" /> : null}
                        <span className="min-w-0 flex-1 truncate">{option}</span>
                        {selected ? <Check aria-hidden="true" className="h-4 w-4 shrink-0 text-orange-600" /> : null}
                      </button>
                    </li>
                  );
                })}
                {visible.length === 0 ? <li className="px-3 py-2 text-sm text-slate-400">No matches</li> : null}
              </ul>
              <div className="sticky bottom-0 shrink-0 border-t border-slate-200 bg-white p-1.5 dark:border-gray-700 dark:bg-[#222026]">
                {creating ? (
                  <form
                    className="flex gap-2"
                    onSubmit={(event) => {
                      event.preventDefault();
                      commitCreate();
                    }}
                  >
                    <input
                      ref={draftRef}
                      value={draft}
                      aria-label={`New ${label}`}
                      placeholder={`New ${label.toLowerCase()}`}
                      maxLength={60}
                      onChange={(event) => setDraft(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Escape") {
                          event.preventDefault();
                          event.stopPropagation();
                          setCreating(false);
                          searchRef.current?.focus();
                        }
                      }}
                      className="h-10 min-w-0 flex-1 rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm focus:bg-white focus:outline-none focus:ring-2 focus:ring-accent dark:border-gray-700 dark:bg-[#2D2A32] dark:text-white"
                    />
                    <button type="submit" className="h-10 shrink-0 rounded-xl bg-accent px-3 text-sm font-semibold text-white">
                      Add
                    </button>
                  </form>
                ) : (
                  <button
                    type="button"
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={startCreate}
                    className="flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left text-sm font-semibold text-orange-600 transition-colors hover:bg-orange-50"
                  >
                    <Plus aria-hidden="true" className="h-4 w-4 shrink-0" />
                    Add new {label}
                  </button>
                )}
              </div>
            </div>,
            document.body,
          )
        : null}
    </div>
  );
}
