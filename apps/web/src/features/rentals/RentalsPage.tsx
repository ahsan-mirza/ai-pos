import { formatMoney, type ProductSearchHit } from "@ai-pos/shared-types";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ErrorNote, GhostButton, PrimaryButton, TextField } from "../../components/ui/Field";
import { apiGet, apiPost, apiPut } from "../../lib/api";
import { errorMessage } from "../users/api";

interface RentalLine {
  product_id: string;
  product_name: string;
  sku: string;
  quantity: number;
}

interface Rental {
  id: string;
  reference: string;
  customer_name: string;
  status: string;
  display_status: string;
  start_date: string;
  return_date: string;
  currency: string;
  agreed_net_cents: number;
  tax_cents: number;
  extension_net_cents: number;
  late_fee_cents: number;
  cleaning_fee_cents: number;
  damage_cents: number;
  amount_paid_cents: number;
  balance_cents: number;
  deposit_due_cents: number;
  deposit_collected_cents: number;
  deposit_held_cents: number;
  lines: RentalLine[];
}

interface Summary {
  currency: string;
  pickups_today: number;
  returns_today: number;
  active: number;
  overdue: number;
  in_preparation: number;
  rental_revenue_cents: number;
  fee_cents: number;
  deposits_held_cents: number;
  outstanding_cents: number;
  most_rented: { name: string; count: number }[];
}

interface Policy {
  product_id: string;
  product_name: string;
  sku: string;
  enabled: boolean;
  offer: "SALE" | "RENT" | "BOTH";
  price_per_day_cents: number;
  deposit_cents: number;
  buffer_days: number;
  late_fee_per_day_cents: number;
  min_days: number;
  default_days: number;
}

const iso = (value: Date) => value.toISOString().slice(0, 10);

function monthGrid(anchor: string): Date[] {
  const start = new Date(`${anchor.slice(0, 7)}-01T00:00:00`);
  const first = new Date(start);
  first.setDate(1 - ((start.getDay() + 6) % 7));
  return Array.from({ length: 42 }, (_, index) => {
    const day = new Date(first);
    day.setDate(first.getDate() + index);
    return day;
  });
}

export function RentalsPage() {
  const [from, setFrom] = useState(() => iso(new Date()));
  const [to, setTo] = useState(() => iso(new Date(Date.now() + 30 * 24 * 60 * 60 * 1000)));
  const [view, setView] = useState<"today" | "list" | "calendar" | "catalogue">("today");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [rows, setRows] = useState<Rental[]>([]);
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [selected, setSelected] = useState<Rental | null>(null);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<ProductSearchHit[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [daily, setDaily] = useState("");
  const [deposit, setDeposit] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [board, bookings, terms] = await Promise.all([
        apiGet<Summary>(`/api/v1/rentals/summary?from=${from}&to=${to}`),
        apiGet<Rental[]>(`/api/v1/rentals?start=${from}&end=${to}`),
        apiGet<Policy[]>("/api/v1/rentals/products"),
      ]);
      setSummary(board);
      setRows(bookings);
      setPolicies(terms);
      setSelected((current) => bookings.find((row) => row.id === current?.id) ?? current);
    } catch (caught) {
      setError(errorMessage(caught, "Rentals could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, [from, to]);

  useEffect(() => {
    void load();
  }, [load]);

  const days = useMemo(() => monthGrid(from), [from]);
  const money = (cents: number) => formatMoney(cents, summary?.currency ?? "AED");

  async function searchProducts() {
    if (query.trim().length < 1) return;
    setHits(await apiGet<ProductSearchHit[]>(`/api/v1/products/search?q=${encodeURIComponent(query.trim())}&limit=8`));
  }

  async function enable(productId: string) {
    const cents = Math.round(Number(daily) * 100);
    const depositCents = Math.round(Number(deposit || "0") * 100);
    if (!Number.isFinite(cents) || cents < 0) {
      setError("Enter a daily rental price.");
      return;
    }
    await apiPut(`/api/v1/rentals/products/${productId}`, {
      enabled: true,
      offer: "BOTH",
      price_per_day_cents: cents,
      deposit_cents: Number.isFinite(depositCents) ? depositCents : 0,
      min_days: 1,
      default_days: 1,
      buffer_days: 1,
      late_fee_per_day_cents: 0,
      cleaning_fee_cents: 0,
      requires_inspection: true,
    });
    await load();
  }

  async function act(path: string, body?: unknown) {
    if (!selected) return;
    setError(null);
    try {
      const next = await apiPost<Rental>(`/api/v1/rentals/${selected.id}/${path}`, body ?? {});
      setSelected(next);
      await load();
    } catch (caught) {
      setError(errorMessage(caught, "That rental action was refused."));
    }
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Rentals</h1>
          <p className="mt-1 text-sm text-charcoal/60">Book catalogue items, hold a refundable deposit, and return them after inspection.</p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <TextField label="From" type="date" value={from} onChange={(event) => setFrom(event.target.value)} />
          <TextField label="To" type="date" value={to} onChange={(event) => setTo(event.target.value)} />
          <GhostButton type="button" onClick={() => void load()}>Refresh</GhostButton>
        </div>
      </header>
      <div className="flex flex-wrap gap-2">
        {(["today", "list", "calendar", "catalogue"] as const).map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => setView(item)}
            className={`rounded-full px-4 py-2 text-sm capitalize ${view === item ? "bg-accent text-white" : "bg-white border border-line"}`}
          >
            {item}
          </button>
        ))}
      </div>
      <ErrorNote message={error} />
      {loading && !summary ? <div className="h-36 animate-pulse rounded-card bg-surface" /> : null}

      {view === "today" && summary ? (
        <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {[
            ["Pickups today", String(summary.pickups_today)],
            ["Returns today", String(summary.returns_today)],
            ["Out now", String(summary.active)],
            ["Overdue", String(summary.overdue)],
            ["In preparation", String(summary.in_preparation)],
            ["Rental revenue", money(summary.rental_revenue_cents)],
            ["Fees", money(summary.fee_cents)],
            ["Deposits held", money(summary.deposits_held_cents)],
          ].map(([label, value]) => (
            <article key={label} className="rounded-card border border-line bg-white p-5">
              <p className="text-sm text-charcoal/60">{label}</p>
              <p className="mt-3 text-2xl font-semibold tabular-nums">{value}</p>
            </article>
          ))}
        </section>
      ) : null}

      {view === "calendar" ? (
        <div className="grid grid-cols-7 gap-1">
          {days.map((day) => {
            const key = iso(day);
            const count = rows.filter((row) => row.start_date <= key && row.return_date >= key && row.status !== "cancelled").length;
            return (
              <button key={key} type="button" onClick={() => setFrom(key)} className="min-h-16 rounded-xl border border-line bg-white p-2 text-left text-xs">
                <span className="font-medium">{day.getDate()}</span>
                {count > 0 ? <span className="mt-2 block rounded-full bg-accent/15 px-2 py-0.5 text-accent">{count} booked</span> : null}
              </button>
            );
          })}
        </div>
      ) : null}

      {view !== "catalogue" ? (
        <section className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
          <ul className="space-y-2">
            {rows.length === 0 ? <li className="text-sm text-charcoal/60">No rentals in this period.</li> : null}
            {rows.map((row) => (
              <li key={row.id}>
                <button type="button" onClick={() => setSelected(row)} className="w-full rounded-card border border-line bg-white p-4 text-left">
                  <span className="font-medium">{row.reference}</span>
                  <span className="ml-2 text-sm text-charcoal/60">{row.customer_name}</span>
                  <span className="mt-1 block text-sm">{row.lines[0]?.product_name} · {row.start_date} to {row.return_date}</span>
                  <span className="mt-1 block text-xs uppercase tracking-wide text-accent">{row.display_status}</span>
                </button>
              </li>
            ))}
          </ul>
          {selected ? (
            <article className="rounded-card border border-line bg-white p-5">
              <h2 className="text-lg font-semibold">{selected.reference}</h2>
              <p className="mt-1 text-sm text-charcoal/70">{selected.customer_name} · {selected.display_status}</p>
              <p className="mt-3 text-sm">Charge {money(selected.agreed_net_cents + selected.tax_cents + selected.extension_net_cents)} · balance {money(selected.balance_cents)}</p>
              <p className="text-sm">Deposit held {money(selected.deposit_held_cents)} of {money(selected.deposit_due_cents)}</p>
              <div className="mt-4 flex flex-wrap gap-2">
                <GhostButton type="button" onClick={() => void act("ready")}>Ready</GhostButton>
                <GhostButton type="button" onClick={() => void act("handover", { condition: "As described" })}>Hand over</GhostButton>
                <GhostButton type="button" onClick={() => void act("return", { condition: "Returned", cleaning: false, repair: false })}>Return</GhostButton>
                <GhostButton type="button" onClick={() => void act("release")}>Release</GhostButton>
                <GhostButton type="button" onClick={() => void act("cancel")}>Cancel</GhostButton>
              </div>
            </article>
          ) : null}
        </section>
      ) : (
        <section className="space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <TextField label="Find a product" value={query} onChange={(event) => setQuery(event.target.value)} />
            <TextField label="Price per day" value={daily} onChange={(event) => setDaily(event.target.value)} />
            <TextField label="Deposit" value={deposit} onChange={(event) => setDeposit(event.target.value)} />
            <PrimaryButton type="button" onClick={() => void searchProducts()}>Search</PrimaryButton>
          </div>
          <ul className="space-y-2">
            {hits.map((hit) => (
              <li key={hit.product.id} className="flex items-center justify-between rounded-card border border-line bg-white p-4">
                <span>{hit.product.name} · {hit.product.sku}</span>
                <GhostButton type="button" onClick={() => void enable(hit.product.id)}>Enable rental</GhostButton>
              </li>
            ))}
          </ul>
          <ul className="space-y-2">
            {policies.map((policy) => (
              <li key={policy.product_id} className="rounded-card border border-line bg-white p-4 text-sm">
                {policy.product_name} · {policy.offer} · {money(policy.price_per_day_cents)} / day · deposit {money(policy.deposit_cents)}
              </li>
            ))}
          </ul>
        </section>
      )}
      {summary && summary.most_rented.length > 0 ? (
        <p className="text-sm text-charcoal/70">
          Most rented: {summary.most_rented.map((row) => `${row.name} (${row.count})`).join(", ")}
        </p>
      ) : null}
    </div>
  );
}
