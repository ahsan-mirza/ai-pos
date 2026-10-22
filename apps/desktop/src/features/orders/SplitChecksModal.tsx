import { comboSummary, formatMoney, modifierSummary, unpaidItems, type Order } from "@ai-pos/shared-types";
import { CreditCard, Minus, Plus, Users, X } from "lucide-react";
import { useEffect, useId, useMemo, useState } from "react";
import { MAX_GUESTS } from "../checkout/tenders";

interface SplitChecksModalProps {
  order: Order;
  currency: string;
  onClose: () => void;
  /** Pays one check: its lines settle as their own sale. */
  onPayCheck: (itemIds: string[], label: string) => void;
  /** Pays the whole order as one sale shared equally between guests. */
  onPayEqually: (guests: number) => void;
}

/** Split a tab into checks by tapping lines (or by seat), or share the whole bill equally between guests. */
export function SplitChecksModal({ order, currency, onClose, onPayCheck, onPayEqually }: SplitChecksModalProps) {
  const titleId = useId();
  const items = useMemo(() => unpaidItems(order), [order]);
  const seats = useMemo(
    () => [...new Set(items.map((item) => item.seat).filter((seat): seat is number => seat !== null))].sort((a, b) => a - b),
    [items],
  );
  const [checks, setChecks] = useState(() => Math.max(2, seats.length));
  const [assigned, setAssigned] = useState<Record<string, number>>(() =>
    Object.fromEntries(items.map((item) => [item.id, item.seat ? Math.max(0, seats.indexOf(item.seat)) : 0])),
  );
  const [guests, setGuests] = useState(() => Math.max(2, order.covers || seats.length));

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const checkOf = (itemId: string) => Math.min(assigned[itemId] ?? 0, checks - 1);
  const totals = Array.from({ length: checks }, (_, check) =>
    items.filter((item) => checkOf(item.id) === check).reduce((sum, item) => sum + item.unit_price_cents * item.quantity, 0),
  );

  function bySeat() {
    setChecks(Math.max(2, seats.length));
    setAssigned(Object.fromEntries(items.map((item) => [item.id, item.seat ? seats.indexOf(item.seat) : 0])));
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <div role="dialog" aria-modal="true" aria-labelledby={titleId} className="modal-card max-w-2xl">
        <div className="flex items-center justify-between gap-3">
          <h2 id={titleId} className="text-lg font-semibold">
            Split #{order.number}
          </h2>
          <button type="button" aria-label="Close" onClick={onClose} className="flex h-9 w-9 items-center justify-center rounded-full hover:bg-zinc-100 dark:hover:bg-white/10">
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        <section className="mt-4 rounded-2xl border border-zinc-200 p-3 dark:border-white/10">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-semibold">By item</span>
            <span className="text-xs text-zinc-500 dark:text-white/50">Tap a check number on each line.</span>
            <div className="ml-auto flex items-center gap-1.5">
              {seats.length > 1 ? (
                <button type="button" onClick={bySeat} className="h-8 rounded-full bg-zinc-100 px-3 text-xs font-semibold dark:bg-white/10">
                  One check per seat
                </button>
              ) : null}
              <button type="button" aria-label="Fewer checks" disabled={checks <= 2} onClick={() => setChecks(checks - 1)} className="flex h-8 w-8 items-center justify-center rounded-full bg-zinc-100 disabled:opacity-40 dark:bg-white/10">
                <Minus size={14} aria-hidden="true" />
              </button>
              <span className="w-14 text-center text-xs font-semibold">{checks} checks</span>
              <button type="button" aria-label="More checks" disabled={checks >= items.length} onClick={() => setChecks(checks + 1)} className="flex h-8 w-8 items-center justify-center rounded-full bg-zinc-100 disabled:opacity-40 dark:bg-white/10">
                <Plus size={14} aria-hidden="true" />
              </button>
            </div>
          </div>
          <ul className="custom-scrollbar mt-2 max-h-64 space-y-1 overflow-y-auto">
            {items.map((item) => (
              <li key={item.id} className="flex items-center gap-2 rounded-xl bg-zinc-50 px-2.5 py-1.5 text-sm dark:bg-white/[0.04]">
                <span className="min-w-0 flex-1 truncate">
                  {item.quantity} × {item.product_name}
                  {item.components?.length ? <span className="text-xs text-zinc-500"> · {comboSummary(item.components)}</span> : null}
                  {item.modifiers.length ? <span className="text-xs text-zinc-500"> · {modifierSummary(item.modifiers)}</span> : null}
                  {item.seat ? <span className="text-xs text-zinc-500"> · seat {item.seat}</span> : null}
                </span>
                <span className="shrink-0 tabular-nums">{formatMoney(item.unit_price_cents * item.quantity, currency)}</span>
                <div className="flex shrink-0 gap-1" role="group" aria-label={`Check for ${item.product_name}`}>
                  {Array.from({ length: checks }, (_, check) => (
                    <button key={check} type="button" aria-pressed={checkOf(item.id) === check} onClick={() => setAssigned({ ...assigned, [item.id]: check })}
                      className={`h-7 w-7 rounded-full text-xs font-bold ${checkOf(item.id) === check ? "bg-primary text-white" : "bg-zinc-200/70 dark:bg-white/10"}`}>
                      {check + 1}
                    </button>
                  ))}
                </div>
              </li>
            ))}
          </ul>
          <div className="mt-3 grid gap-2 sm:grid-cols-3">
            {totals.map((cents, check) => (
              <button
                key={check}
                type="button"
                disabled={cents === 0}
                onClick={() => onPayCheck(items.filter((item) => checkOf(item.id) === check).map((item) => item.id), `check ${check + 1} of #${order.number}`)}
                className="flex h-12 items-center justify-between rounded-2xl border border-zinc-200 px-3 text-sm font-semibold hover:border-primary disabled:opacity-40 dark:border-white/10"
              >
                <span className="inline-flex items-center gap-1.5"><CreditCard size={15} aria-hidden="true" /> Check {check + 1}</span>
                <span className="tabular-nums">{formatMoney(cents, currency)}</span>
              </button>
            ))}
          </div>
          <p className="mt-2 text-xs text-zinc-500 dark:text-white/50">Each check is its own sale; the tab stays open until every line is paid.</p>
        </section>

        <section className="mt-3 flex flex-wrap items-center gap-2 rounded-2xl border border-zinc-200 p-3 text-sm dark:border-white/10">
          <Users size={16} aria-hidden="true" />
          <span className="font-semibold">Split equally into</span>
          <button type="button" aria-label="Fewer guests" disabled={guests <= 2} onClick={() => setGuests(guests - 1)} className="flex h-8 w-8 items-center justify-center rounded-full bg-zinc-100 disabled:opacity-40 dark:bg-white/10">
            <Minus size={14} aria-hidden="true" />
          </button>
          <span className="w-6 text-center font-bold tabular-nums">{guests}</span>
          <button type="button" aria-label="More guests" disabled={guests >= MAX_GUESTS} onClick={() => setGuests(guests + 1)} className="flex h-8 w-8 items-center justify-center rounded-full bg-zinc-100 disabled:opacity-40 dark:bg-white/10">
            <Plus size={14} aria-hidden="true" />
          </button>
          <span className="text-xs text-zinc-500 dark:text-white/50">≈ {formatMoney(Math.ceil(order.open_cents / guests), currency)} each before tax</span>
          <button type="button" onClick={() => onPayEqually(guests)} className="ml-auto h-10 rounded-full bg-primary px-4 text-sm font-semibold text-white">
            Pay {guests} ways
          </button>
        </section>
      </div>
    </div>
  );
}
