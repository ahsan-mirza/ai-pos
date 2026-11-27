import { Filter, Search, X } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { DateInput } from "./DateInput";
import { useLocale } from "./LocaleSwitch";
import { Select, type SelectOption } from "./Select";

export interface FilterControlProps {
  value: string;
  setValue: (value: string) => void;
  draft: Readonly<Record<string, string>>;
  setDraft: (patch: Record<string, string>) => void;
}

export interface TableFilter {
  id: string;
  label: string;
  value: string;
  /** Applied by Clear all. Defaults to an empty string. */
  clearedValue?: string;
  onChange: (value: string) => void;
  kind?: "select" | "text" | "date" | "toggle";
  options?:
    | readonly SelectOption[]
    | ((draft: Readonly<Record<string, string>>) => readonly SelectOption[]);
  placeholder?: string;
  hidden?: boolean | ((draft: Readonly<Record<string, string>>) => boolean);
  disabled?: boolean | ((draft: Readonly<Record<string, string>>) => boolean);
  /** Date bounds. A function can read the other draft values. */
  min?: string | ((draft: Readonly<Record<string, string>>) => string | undefined);
  max?: string | ((draft: Readonly<Record<string, string>>) => string | undefined);
  /** Other filter ids reset when this draft value changes. */
  clears?: readonly string[];
  /** Replaces the default control. Pass a component so it can use hooks. */
  Control?: (props: FilterControlProps) => ReactNode;
}

export interface TableSearch {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  label?: string;
  onSubmit?: (value: string) => void;
}

export interface TableToolbarProps {
  search?: TableSearch;
  filters?: readonly TableFilter[];
  /** Page actions such as New or Export. They stay beside search. */
  actions?: ReactNode;
  /** Extra drawer content that is not a draft filter. */
  extra?: ReactNode;
  /** Runs after Apply and Clear all so the page can return to page 1. */
  onFiltersCommit?: () => void;
  /**
   * When set, Clear all calls this instead of each filter's onChange.
   * Use it when one handler resets the whole filter set, including search.
   */
  onClearAll?: () => void;
}

function clearedOf(filter: TableFilter): string {
  return filter.clearedValue ?? "";
}

function resolve<T>(value: T | ((draft: Readonly<Record<string, string>>) => T), draft: Readonly<Record<string, string>>): T {
  return typeof value === "function" ? (value as (draft: Readonly<Record<string, string>>) => T)(draft) : value;
}

export function activeFilterCount(filters: readonly TableFilter[]): number {
  const applied = Object.fromEntries(filters.map((filter) => [filter.id, filter.value]));
  return filters.filter((filter) => {
    if (resolve(filter.hidden ?? false, applied)) return false;
    return filter.value !== clearedOf(filter);
  }).length;
}

/** Search stays in the toolbar. Every other filter opens in the drawer and applies together. */
export function TableToolbar({ search, filters = [], actions, extra, onFiltersCommit, onClearAll }: TableToolbarProps) {
  const { t } = useLocale();
  const searchId = useId();
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const count = activeFilterCount(filters);
  const showFilters = filters.length > 0 || extra != null;

  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2">
      {search ? (
        <label htmlFor={searchId} className="relative min-w-0 flex-1 basis-[12rem]">
          <span className="sr-only">{search.label ?? t("Search")}</span>
          <Search aria-hidden="true" className="pointer-events-none absolute start-4 top-1/2 h-4 w-4 -translate-y-1/2 text-charcoal/40" />
          <input
            id={searchId}
            type="search"
            value={search.value}
            placeholder={search.placeholder}
            aria-label={search.label ?? t("Search")}
            autoComplete="off"
            onChange={(event) => search.onChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                search.onSubmit?.(event.currentTarget.value);
              } else if (event.key === "Escape") {
                search.onChange("");
              }
            }}
            className="h-11 w-full min-w-0 rounded-full border border-line bg-white ps-10 pe-4 text-sm font-medium text-charcoal outline-none placeholder:font-normal placeholder:text-charcoal/40 hover:border-gray-400 focus:border-accent focus:ring-2 focus:ring-accent/30 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-100 [&::-webkit-search-cancel-button]:hidden"
          />
        </label>
      ) : null}
      {showFilters ? (
        <button
          ref={buttonRef}
          type="button"
          aria-haspopup="dialog"
          aria-expanded={open}
          onClick={() => setOpen(true)}
          className={`relative inline-flex h-11 shrink-0 items-center gap-2 rounded-full border px-3 text-sm font-semibold outline-none focus-visible:ring-2 focus-visible:ring-primary/40 ${
            count > 0
              ? "border-accent bg-accent/10 text-accent"
              : "border-line bg-white text-charcoal dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
          }`}
        >
          <Filter size={16} aria-hidden="true" />
          <span>{t("Filters")}</span>
          {count > 0 ? (
            <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-accent px-1.5 text-xs font-bold text-white">
              <span aria-hidden="true">{count}</span>
              <span className="sr-only">{t("{count} selected", { count })}</span>
            </span>
          ) : null}
        </button>
      ) : null}
      {actions ? <div className="flex min-w-0 flex-wrap items-center gap-2">{actions}</div> : null}
      {open ? (
        <FilterDrawer
          filters={filters}
          extra={extra}
          onClose={() => {
            setOpen(false);
            buttonRef.current?.focus();
          }}
          onApply={(draft) => {
            for (const filter of filters) {
              const next = draft[filter.id] ?? clearedOf(filter);
              if (next !== filter.value) filter.onChange(next);
            }
            onFiltersCommit?.();
            setOpen(false);
            buttonRef.current?.focus();
          }}
          onClear={() => {
            if (onClearAll) onClearAll();
            else {
              for (const filter of filters) {
                const next = clearedOf(filter);
                if (next !== filter.value) filter.onChange(next);
              }
            }
            onFiltersCommit?.();
          }}
        />
      ) : null}
    </div>
  );
}

export function FilterDrawer({
  filters,
  extra,
  onClose,
  onApply,
  onClear,
}: {
  filters: readonly TableFilter[];
  extra?: ReactNode;
  onClose: () => void;
  onApply: (draft: Readonly<Record<string, string>>) => void;
  onClear: () => void;
}) {
  const { t } = useLocale();
  const titleId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const [draft, setDraftState] = useState<Record<string, string>>(() =>
    Object.fromEntries(filters.map((filter) => [filter.id, filter.value])),
  );

  const setDraft = (patch: Record<string, string>) => {
    setDraftState((current) => ({ ...current, ...patch }));
  };

  const setValue = (filter: TableFilter, value: string) => {
    setDraftState((current) => {
      const next = { ...current, [filter.id]: value };
      for (const id of filter.clears ?? []) {
        const other = filters.find((item) => item.id === id);
        next[id] = other ? clearedOf(other) : "";
      }
      return next;
    });
  };

  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      closeRef.current();
    };
    document.addEventListener("keydown", onKey);
    const field = panelRef.current?.querySelector<HTMLElement>("[data-filter-field]");
    field?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const visible = filters.filter((filter) => !resolve(filter.hidden ?? false, draft));

  return createPortal(
    <div className="fixed inset-0 z-[80] flex justify-end">
      <button type="button" aria-label={t("Dismiss filters")} className="absolute inset-0 bg-charcoal/40" onClick={onClose} />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="relative flex h-dvh max-h-[100dvh] w-[min(22rem,100vw)] flex-col bg-white shadow-2xl dark:bg-zinc-900"
      >
        <header className="flex items-center justify-between gap-3 border-b border-line px-5 py-4">
          <h2 id={titleId} className="text-lg font-semibold">
            {t("Filters")}
          </h2>
          <button
            type="button"
            aria-label={t("Close")}
            onClick={onClose}
            className="inline-flex h-11 w-11 items-center justify-center rounded-full outline-none hover:bg-surface focus-visible:ring-2 focus-visible:ring-primary/40"
          >
            <X size={18} aria-hidden="true" />
          </button>
        </header>
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-4">
          {visible.map((filter) => (
            <FilterField key={filter.id} filter={filter} draft={draft} setDraft={setDraft} onValue={(value) => setValue(filter, value)} />
          ))}
          {extra}
        </div>
        <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-line px-5 py-4">
          <button
            type="button"
            onClick={() => {
              setDraftState(Object.fromEntries(filters.map((filter) => [filter.id, clearedOf(filter)])));
              onClear();
            }}
            className="inline-flex h-11 items-center rounded-full px-3 text-sm font-semibold text-charcoal outline-none hover:bg-surface focus-visible:ring-2 focus-visible:ring-primary/40 dark:text-zinc-100"
          >
            {t("Clear all")}
          </button>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onClose}
              className="inline-flex h-11 items-center rounded-full border border-line px-4 text-sm font-semibold outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
            >
              {t("Close")}
            </button>
            <button
              type="button"
              onClick={() => onApply(draft)}
              className="inline-flex h-11 items-center rounded-full bg-accent px-5 text-sm font-semibold text-white outline-none hover:bg-accent-hover focus-visible:ring-2 focus-visible:ring-primary/40"
            >
              {t("Apply")}
            </button>
          </div>
        </footer>
      </div>
    </div>,
    document.body,
  );
}

function FilterField({
  filter,
  draft,
  setDraft,
  onValue,
}: {
  filter: TableFilter;
  draft: Readonly<Record<string, string>>;
  setDraft: (patch: Record<string, string>) => void;
  onValue: (value: string) => void;
}) {
  const value = draft[filter.id] ?? clearedOf(filter);
  const disabled = resolve(filter.disabled ?? false, draft);
  const Control = filter.Control;
  const label = filter.label ? (
    <span className="mb-1.5 block text-sm font-medium text-charcoal dark:text-zinc-100">{filter.label}</span>
  ) : null;

  if (Control) {
    return (
      <div data-filter-field>
        {label}
        <Control value={value} setValue={onValue} draft={draft} setDraft={setDraft} />
      </div>
    );
  }

  if (filter.kind === "toggle") {
    const on = value === "true";
    return (
      <button
        data-filter-field
        type="button"
        role="switch"
        aria-checked={on}
        disabled={disabled}
        onClick={() => onValue(on ? "false" : "true")}
        className="flex min-h-11 w-full items-center justify-between gap-3 rounded-2xl border border-line px-3 text-sm font-medium outline-none focus-visible:ring-2 focus-visible:ring-primary/40 disabled:opacity-40"
      >
        <span>{filter.label}</span>
        <span className={`h-6 w-10 rounded-full p-0.5 ${on ? "bg-accent" : "bg-charcoal/15"}`}>
          <span className={`block h-5 w-5 rounded-full bg-white transition-transform ${on ? "translate-x-4" : ""}`} />
        </span>
      </button>
    );
  }

  if (filter.kind === "date") {
    return (
      <label data-filter-field className="block">
        {label}
        <DateInput
          aria-label={filter.label}
          value={value}
          disabled={disabled}
          min={resolve(filter.min, draft) || undefined}
          max={resolve(filter.max, draft) || undefined}
          onChange={(event) => onValue(event.target.value)}
        />
      </label>
    );
  }

  if (filter.kind === "text") {
    return (
      <label data-filter-field className="block">
        {label}
        <input
          aria-label={filter.label}
          value={value}
          disabled={disabled}
          placeholder={filter.placeholder}
          onChange={(event) => onValue(event.target.value)}
          className="h-11 w-full rounded-2xl border border-line bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-primary/30 disabled:opacity-40 dark:border-zinc-700 dark:bg-zinc-900"
        />
      </label>
    );
  }

  const options = resolve(filter.options ?? [], draft);
  return (
    <div data-filter-field>
      {label}
      <Select
        aria-label={filter.label}
        value={value}
        disabled={disabled}
        placeholder={filter.placeholder}
        options={options}
        onChange={onValue}
      />
    </div>
  );
}
