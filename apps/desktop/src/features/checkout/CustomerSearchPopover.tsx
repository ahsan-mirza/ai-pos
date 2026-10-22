import { PRICE_TIER_LABELS } from "@ai-pos/shared-types";
import { Plus, Search } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { useCapabilities } from "../../lib/capabilities";
import type { RegisterCustomer } from "../../lib/tauri";
import { searchCustomers } from "./wholesaleClient";

interface CustomerSearchPopoverProps {
  disabled?: boolean;
  onSelect: (customer: RegisterCustomer) => void;
  /** Called with the typed text when nobody matches and the cashier chooses to add them. */
  onQuickAdd: (query: string) => void;
}

/** Finds a customer by name, phone, code, company or TRN in the register's cache; offers to add one when none match. */
export function CustomerSearchPopover({ disabled = false, onSelect, onQuickAdd }: CustomerSearchPopoverProps) {
  const { foodAndBeverage } = useCapabilities();
  const listId = useId();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState<RegisterCustomer[]>([]);
  const [active, setActive] = useState(0);
  const boxRef = useRef<HTMLDivElement>(null);
  const trimmed = query.trim();
  const canAdd = trimmed.length >= 2 && results.length === 0;

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      searchCustomers(query)
        .then((rows) => {
          if (!cancelled) {
            setResults(rows);
            setActive(0);
          }
        })
        .catch(() => {
          if (!cancelled) setResults([]);
        });
    }, 120);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [open, query]);

  useEffect(() => {
    const onPointer = (event: PointerEvent) => {
      if (boxRef.current && !boxRef.current.contains(event.target as Node)) setOpen(false);
    };
    window.addEventListener("pointerdown", onPointer);
    return () => window.removeEventListener("pointerdown", onPointer);
  }, []);

  const choose = (row: RegisterCustomer) => {
    onSelect(row);
    setQuery("");
    setOpen(false);
  };

  const add = () => {
    onQuickAdd(trimmed);
    setQuery("");
    setOpen(false);
  };

  return (
    <div ref={boxRef} className="relative">
      <label htmlFor="customer-search" className="sr-only">
        {foodAndBeverage ? "Find a guest" : "Attach B2B customer or walk-in"}
      </label>
      <Search
        size={16}
        aria-hidden="true"
        className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-500 dark:text-white/50"
      />
      <input
        id="customer-search"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        autoComplete="off"
        disabled={disabled}
        value={query}
        placeholder={foodAndBeverage ? "Find a guest" : "Attach B2B Customer / Walk-in"}
        onFocus={() => setOpen(true)}
        onChange={(event) => {
          setQuery(event.target.value);
          setOpen(true);
        }}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setActive((index) => Math.min(index + 1, Math.max(results.length - 1, 0)));
          } else if (event.key === "ArrowUp") {
            event.preventDefault();
            setActive((index) => Math.max(index - 1, 0));
          } else if (event.key === "Enter") {
            event.preventDefault();
            const row = results[active];
            if (row) choose(row);
            else if (canAdd) add();
          } else if (event.key === "Escape") {
            setOpen(false);
          }
        }}
        className="h-12 w-full rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900/60 pl-10 pr-4 text-sm tabular-nums text-zinc-900 dark:text-white placeholder:text-zinc-500 dark:placeholder:text-white/40 transition-colors focus:border-primary focus:outline-none focus:ring-4 focus:ring-primary/20 disabled:opacity-40"
      />
      {open ? (
        <ul
          id={listId}
          role="listbox"
          className="absolute left-0 right-0 top-full z-20 mt-1.5 max-h-72 overflow-y-auto rounded-2xl bg-white p-1.5 text-charcoal shadow-2xl"
        >
          {results.length === 0 ? (
            <li className="px-3 py-2.5 text-sm text-charcoal/60">
              {trimmed === "" ? "No customers cached on this register yet." : `No customer matches "${trimmed}".`}
            </li>
          ) : null}
          {canAdd ? (
            <li role="option" aria-selected="true">
              <button
                type="button"
                onClick={add}
                className="flex w-full items-center gap-2 rounded-xl bg-primary/10 px-3 py-2.5 text-left text-sm font-semibold text-primary transition-colors hover:bg-primary hover:text-white"
              >
                <Plus size={16} aria-hidden="true" className="shrink-0" />
                <span className="min-w-0 truncate">Add "{trimmed}" as new customer</span>
              </button>
            </li>
          ) : null}
          {results.map((row, index) => (
            <li key={row.id} role="option" aria-selected={index === active}>
              <button
                type="button"
                onMouseEnter={() => setActive(index)}
                onClick={() => choose(row)}
                className={`flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2 text-left ${index === active ? "bg-surface" : ""}`}
              >
                <span className="min-w-0">
                  <span className="block truncate text-sm font-semibold">{row.company_name ?? row.name}</span>
                  <span className="block truncate text-xs tabular-nums text-charcoal/50">
                    {[row.code === "NEW" ? "Not synced yet" : row.code, row.phone].filter(Boolean).join(" · ")}
                  </span>
                </span>
                <span
                  className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                    row.customer_type === "WHOLESALE" ? "bg-primary text-white" : "bg-surface text-charcoal/60"
                  }`}
                >
                  {row.customer_type === "WHOLESALE" ? PRICE_TIER_LABELS[row.price_tier] : "Walk-in"}
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
