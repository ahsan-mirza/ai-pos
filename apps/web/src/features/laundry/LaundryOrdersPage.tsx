import { useCallback, useEffect, useState } from "react";
import { env } from "../../config/env";
import { ApiRequestError, apiGet, apiPost, getAccessToken } from "../../lib/api";

interface Named { id: string; name: string }
interface ServiceRow extends Named { pricing_unit: string }
interface GarmentRow {
  id: string;
  service_id: string;
  description: string;
  quantity: number;
  condition: string;
  instructions: string;
  stage: string;
  line_snapshot: { unit_price_cents: number };
}
interface OrderRow {
  id: string;
  code: string;
  customer_id: string;
  intake_store_id: string;
  order_type: string;
  operational_status: string;
  payment_status: string;
  instructions: string;
  total_cents: number;
  tax_cents: number;
  amount_paid_cents: number;
  balance_due_cents: number;
  version: number;
  promised_at: string | null;
  pricing_snapshot: { lines: { unit_price_cents: number; rate_bps: number }[] };
  garments: GarmentRow[];
  bags: { id: string; net_weight: number; gross_weight: number; tare_weight: number }[];
  tags: { id: string; code: string; status: string }[];
  events: { id: string; kind: string; reason: string }[];
  photos: { id: string; mime: string; byte_size: number; created_at: string }[];
}
interface DraftLine {
  key: string;
  service_id: string;
  quantity: string;
  description: string;
  condition: string;
  instructions: string;
}

function money(cents: number): string {
  return (cents / 100).toFixed(2);
}

function blankLine(serviceId: string): DraftLine {
  return { key: crypto.randomUUID(), service_id: serviceId, quantity: "1", description: "", condition: "", instructions: "" };
}

export function LaundryOrdersPage() {
  const [orders, setOrders] = useState<OrderRow[]>([]);
  const [stores, setStores] = useState<Named[]>([]);
  const [customers, setCustomers] = useState<Named[]>([]);
  const [services, setServices] = useState<ServiceRow[]>([]);
  const [lines, setLines] = useState<DraftLine[]>([]);
  const [selected, setSelected] = useState<OrderRow | null>(null);
  const [photos, setPhotos] = useState<{ id: string; url: string }[]>([]);
  const [query, setQuery] = useState("");
  const [deposit, setDeposit] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    const [nextOrders, nextStores, nextCustomers, nextServices] = await Promise.all([
      apiGet<OrderRow[]>(`/api/v1/laundry/orders?q=${encodeURIComponent(query)}`),
      apiGet<Named[]>("/api/v1/stores"),
      apiGet<Named[]>("/api/v1/customers?limit=100"),
      apiGet<ServiceRow[]>("/api/v1/laundry/services?active=true"),
    ]);
    setOrders(nextOrders);
    setStores(nextStores);
    setCustomers(nextCustomers);
    setServices(nextServices);
    setLines((current) => (current.length > 0 ? current : [blankLine(nextServices[0]?.id ?? "")]));
    return nextOrders;
  }, [query]);

  useEffect(() => {
    load().catch((caught) => setError(caught instanceof ApiRequestError ? caught.message : "Orders could not be loaded."));
  }, [load]);

  useEffect(() => {
    if (selected === null) return;
    const token = getAccessToken();
    let cancelled = false;
    void Promise.all(selected.photos.map(async (photo) => {
      const response = await fetch(`${env.apiBaseUrl}/api/v1/laundry/orders/${selected.id}/photos/${photo.id}`, {
        headers: { Authorization: `Bearer ${token ?? ""}`, ...(env.tenantDomain ? { "X-Tenant-Domain": env.tenantDomain } : {}) },
      });
      if (!response.ok) return null;
      return { id: photo.id, url: URL.createObjectURL(await response.blob()) };
    })).then((rows) => {
      if (!cancelled) setPhotos(rows.filter((row): row is { id: string; url: string } => row !== null));
    });
    return () => {
      cancelled = true;
    };
  }, [selected]);

  async function open(id: string) {
    setError("");
    setSelected(await apiGet<OrderRow>(`/api/v1/laundry/orders/${id}`));
  }

  const nameOf = (rows: Named[], id: string) => rows.find((row) => row.id === id)?.name ?? id;

  return (
    <section className="space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-semibold">Laundry orders</h1>
        <p className="text-sm text-charcoal/70">Intake totals come from the server. Clothes in process are not stock for sale.</p>
      </header>
      {error ? <p role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</p> : null}
      {notice ? <p role="status" className="rounded-xl border border-line px-4 py-3 text-sm">{notice}</p> : null}
      <form
        className="grid gap-2 rounded-2xl border border-line p-4 sm:grid-cols-2"
        onSubmit={(event) => {
          event.preventDefault();
          const body = new FormData(event.currentTarget);
          const depositCents = Number(body.get("deposit") || 0);
          const payload: Record<string, unknown> = {
            idempotency_key: crypto.randomUUID(),
            intake_store_id: String(body.get("store_id")),
            customer_id: String(body.get("customer_id")),
            order_type: String(body.get("order_type")),
            promised_at: body.get("promised") ? new Date(String(body.get("promised"))).toISOString() : null,
            express: body.get("express") === "on",
            instructions: String(body.get("instructions") || ""),
            garments: lines.filter((line) => services.find((row) => row.id === line.service_id)?.pricing_unit !== "KG").map((line) => ({
              service_id: line.service_id,
              quantity: Number(line.quantity || 1),
              description: line.description,
              condition: line.condition,
              instructions: line.instructions,
            })),
            bags: [],
          };
          if (depositCents > 0) payload.deposit = { amount_cents: depositCents, method: "cash" };
          setError("");
          setNotice("");
          void apiPost<OrderRow>("/api/v1/laundry/orders", payload)
            .then(async (created) => {
              setSelected(created);
              setNotice(`Server accepted ${created.code}. Total ${money(created.total_cents)}.`);
              await load();
            })
            .catch((caught) => setError(caught instanceof ApiRequestError ? caught.message : "The order was not accepted."));
        }}
      >
        <h2 className="font-medium sm:col-span-2">New intake</h2>
        <select name="customer_id" aria-label="Customer" className="rounded-xl border border-line px-3 py-2" required>
          {customers.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
        </select>
        <select name="store_id" aria-label="Intake branch" className="rounded-xl border border-line px-3 py-2" required>
          {stores.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
        </select>
        <select name="order_type" aria-label="Order type" className="rounded-xl border border-line px-3 py-2">
          <option value="WALK_IN">Walk-in</option>
          <option value="DROP_OFF">Drop-off</option>
          <option value="PICKUP">Pickup</option>
        </select>
        <input name="promised" type="datetime-local" aria-label="Promised at" className="rounded-xl border border-line px-3 py-2" />
        <input name="instructions" placeholder="Special instructions" aria-label="Special instructions" className="rounded-xl border border-line px-3 py-2 sm:col-span-2" />
        {lines.map((line) => (
          <div key={line.key} className="grid gap-2 sm:col-span-2 sm:grid-cols-2">
            <select aria-label="Service" value={line.service_id} className="rounded-xl border border-line px-3 py-2" onChange={(event) => setLines((rows) => rows.map((row) => row.key === line.key ? { ...row, service_id: event.target.value } : row))}>
              {services.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
            </select>
            <input aria-label="Garment quantity" value={line.quantity} className="rounded-xl border border-line px-3 py-2" onChange={(event) => setLines((rows) => rows.map((row) => row.key === line.key ? { ...row, quantity: event.target.value } : row))} />
            <input aria-label="Garment description" placeholder="Description" value={line.description} className="rounded-xl border border-line px-3 py-2" onChange={(event) => setLines((rows) => rows.map((row) => row.key === line.key ? { ...row, description: event.target.value } : row))} />
            <input aria-label="Condition" placeholder="Condition" value={line.condition} className="rounded-xl border border-line px-3 py-2" onChange={(event) => setLines((rows) => rows.map((row) => row.key === line.key ? { ...row, condition: event.target.value } : row))} />
          </div>
        ))}
        <button type="button" className="rounded-full border border-line px-4 py-2 text-sm" onClick={() => setLines((rows) => [...rows, blankLine(services[0]?.id ?? "")])}>Add garment</button>
        <input name="deposit" placeholder="Deposit cents" aria-label="Deposit in cents" className="rounded-xl border border-line px-3 py-2" />
        <label className="flex items-center gap-2 text-sm"><input name="express" type="checkbox" /> Express</label>
        <button type="submit" className="rounded-full bg-accent px-4 py-2 text-sm text-white">Create order</button>
      </form>
      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          void load().then((rows) => {
            const found = rows.find((row) => row.code === query.trim());
            if (found) return open(found.id);
            return undefined;
          }).catch((caught) => setError(caught instanceof ApiRequestError ? caught.message : "Orders could not be loaded."));
        }}
      >
        <input value={query} onChange={(event) => setQuery(event.target.value)} aria-label="Search orders" placeholder="Search order code" className="rounded-xl border border-line px-3 py-2" />
        <button type="submit" className="rounded-full border border-line px-4 py-2 text-sm">Search</button>
      </form>
      {orders.length === 0 ? <p>No laundry orders yet.</p> : (
        <ul className="divide-y divide-line rounded-2xl border border-line">
          {orders.map((order) => (
            <li key={order.id}>
              <button type="button" className="w-full px-4 py-3 text-left text-sm" onClick={() => void open(order.id)}>
                {order.code} · {order.order_type} · {order.operational_status} · {order.payment_status} · {money(order.total_cents)}
              </button>
            </li>
          ))}
        </ul>
      )}
      {selected ? (
        <article className="space-y-2 rounded-2xl border border-line p-4 text-sm" aria-label="Order detail">
          <h2 className="font-medium">{selected.code}</h2>
          <p>Customer {nameOf(customers, selected.customer_id)}</p>
          <p>Branch {nameOf(stores, selected.intake_store_id)}</p>
          <p>Status {selected.operational_status}</p>
          {selected.instructions ? <p>Instructions {selected.instructions}</p> : null}
          <p aria-label="Order total">Total {money(selected.total_cents)} · tax {money(selected.tax_cents)} · paid {money(selected.amount_paid_cents)} · due {money(selected.balance_due_cents)}</p>
          <p>Accepted rate {selected.pricing_snapshot.lines[0]?.unit_price_cents ?? 0} cents · tax {selected.pricing_snapshot.lines[0]?.rate_bps ?? 0} bps</p>
          <ul aria-label="Garments">
            {selected.garments.map((garment) => <li key={garment.id}>{garment.description || "Garment"} · {nameOf(services, garment.service_id)} · qty {garment.quantity} · {garment.condition || "no condition noted"} · {garment.stage}</li>)}
          </ul>
          <ul aria-label="Bags">
            {selected.bags.map((bag) => <li key={bag.id}>Bag net {bag.net_weight} · gross {bag.gross_weight} · tare {bag.tare_weight}</li>)}
          </ul>
          <ul aria-label="Tags">
            {selected.tags.map((tag) => <li key={tag.id}>{tag.code} · {tag.status}</li>)}
          </ul>
          <ul aria-label="Order timeline">
            {selected.events.map((event) => <li key={event.id}>{event.kind}{event.reason ? ` · ${event.reason}` : ""}</li>)}
          </ul>
          <ul aria-label="Photos">
            {photos.map((photo) => <li key={photo.id}><img src={photo.url} alt="Intake evidence" width={140} /></li>)}
          </ul>
          <form
            className="flex gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              const amount = Number(deposit);
              if (!Number.isInteger(amount) || amount < 1) {
                setError("Enter the deposit in cents.");
                return;
              }
              void apiPost<OrderRow>(`/api/v1/laundry/orders/${selected.id}/deposits`, {
                id: crypto.randomUUID(),
                amount_cents: amount,
                method: "cash",
                version: selected.version,
              }).then((updated) => {
                setSelected(updated);
                setDeposit("");
                setNotice(`Payment recorded. Due ${money(updated.balance_due_cents)}.`);
              }).catch((caught) => setError(caught instanceof ApiRequestError ? caught.message : "The payment was not recorded."));
            }}
          >
            <input value={deposit} onChange={(event) => setDeposit(event.target.value)} aria-label="Additional deposit cents" placeholder="Additional deposit cents" className="rounded-xl border border-line px-3 py-2" />
            <button type="submit" className="rounded-full border border-line px-4 py-2 text-sm">Take payment</button>
          </form>
        </article>
      ) : null}
    </section>
  );
}
