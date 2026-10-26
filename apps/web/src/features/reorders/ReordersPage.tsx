import { ApiRequestError, apiGet, apiGetPage, apiPatch, apiPost } from "../../lib/api";
import { ErrorNote, PrimaryButton, SearchField } from "../../components/ui/Field";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

interface PlanItem {
  product_id: string;
  product_name: string;
  quantity: number;
  unit: string;
  available: number | null;
  discontinued: boolean;
  note: string | null;
}

interface Plan {
  id: string;
  customer_id: string;
  customer_name: string;
  customer_code: string;
  name: string;
  frequency: string;
  weekdays: number[];
  month_day: number | null;
  start_on: string;
  end_on: string | null;
  next_on: string | null;
  preferred_time: string | null;
  timezone: string;
  lead_days: number;
  fulfillment: string;
  delivery_address: string | null;
  notes: string;
  status: string;
  salesperson_name: string | null;
  notify_customer: boolean;
  items: PlanItem[];
}

interface Occurrence {
  id: string;
  plan_id: string;
  plan_name: string;
  customer_id: string;
  customer_name: string;
  customer_code: string;
  balance_cents: number;
  scheduled_on: string;
  preferred_time: string | null;
  status: string;
  fulfillment: string;
  delivery_address: string | null;
  salesperson_name: string | null;
  items: PlanItem[];
  stock_note: string;
  sales_order_id: string | null;
  sales_order_number: string | null;
  notification_status: string;
  notification_error: string | null;
  overdue: boolean;
  skip_reason: string | null;
}

interface DraftLine {
  product_id: string;
  name: string;
  quantity: string;
  unit: string;
}

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function problem(caught: unknown, fallback: string): string {
  return caught instanceof ApiRequestError ? caught.message : fallback;
}

function money(cents: number): string {
  return (cents / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function CustomerReorderCard({ customerId }: { customerId: string }) {
  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    apiGetPage<Plan>(`/api/v1/reorders/plans?customer_id=${customerId}`, { offset: 0, limit: 20 })
      .then((page) => {
        if (live) setPlans(page.rows);
      })
      .catch((caught: unknown) => {
        if (live) setError(problem(caught, "Could not load reorder plans."));
      });
    return () => {
      live = false;
    };
  }, [customerId]);

  return (
    <section className="rounded-card border border-line bg-white p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Recurring orders</h2>
        <Link to={`/reorders?customer=${customerId}`} className="text-sm font-semibold text-accent hover:underline">
          Manage plans
        </Link>
      </div>
      {error ? <ErrorNote message={error} /> : null}
      {plans === null ? <p className="mt-3 text-sm text-charcoal/60">Loading plans…</p> : null}
      {plans?.length === 0 ? <p className="mt-3 text-sm text-charcoal/60">No reorder plan for this customer yet.</p> : null}
      <ul className="mt-3 divide-y divide-line">
        {plans?.map((plan) => (
          <li key={plan.id} className="flex flex-wrap items-baseline justify-between gap-2 py-2 text-sm">
            <span className="font-medium">{plan.name}</span>
            <span className="text-charcoal/60">
              {plan.frequency.toLowerCase().replace("_", " ")} · {plan.status.toLowerCase()}
              {plan.next_on ? ` · next ${plan.next_on}` : ""}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function ReordersPage() {
  const [params] = useSearchParams();
  const customerId = params.get("customer") ?? "";
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [plans, setPlans] = useState<Plan[]>([]);
  const [alerts, setAlerts] = useState<Occurrence[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [editing, setEditing] = useState<Plan | null>(null);
  const [open, setOpen] = useState(Boolean(customerId));

  const load = useCallback(async () => {
    const planQuery = new URLSearchParams();
    const alertQuery = new URLSearchParams({ view: "due" });
    if (query.trim()) {
      planQuery.set("q", query.trim());
      alertQuery.set("q", query.trim());
    }
    if (status) planQuery.set("status", status);
    if (customerId) {
      planQuery.set("customer_id", customerId);
      alertQuery.set("customer_id", customerId);
    }
    const [planPage, alertPage] = await Promise.all([
      apiGetPage<Plan>(`/api/v1/reorders/plans?${planQuery}`, { offset: 0, limit: 50 }),
      apiGetPage<Occurrence>(`/api/v1/reorders/occurrences?${alertQuery}`, { offset: 0, limit: 50 }),
    ]);
    setPlans(planPage.rows);
    setAlerts(alertPage.rows);
  }, [query, status, customerId]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load().catch((caught: unknown) => setError(problem(caught, "Could not load reorder plans.")));
    }, 200);
    return () => window.clearTimeout(timer);
  }, [load]);

  const act = async (path: string, body?: unknown) => {
    setError(null);
    try {
      await apiPost(path, body ?? {});
      setNotice("Saved.");
      await load();
    } catch (caught) {
      setError(problem(caught, "Could not update the reminder."));
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Reorder management</h1>
          <p className="mt-1 text-sm text-charcoal/60">Reminders stay pending until someone confirms the order.</p>
        </div>
        <PrimaryButton onClick={() => { setEditing(null); setOpen(true); }}>New plan</PrimaryButton>
      </div>
      {error ? <ErrorNote message={error} /> : null}
      {notice ? <p className="text-sm font-medium text-emerald-700">{notice}</p> : null}

      <div className="flex flex-wrap gap-3">
        <SearchField className="min-w-[240px] flex-1" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Customer, product, plan, salesperson, order" />
        <select value={status} onChange={(event) => setStatus(event.target.value)} className="h-10 rounded-full border border-line bg-white px-4 text-sm" aria-label="Plan status">
          <option value="">All plans</option>
          <option value="ACTIVE">Active</option>
          <option value="PAUSED">Paused</option>
          <option value="COMPLETED">Completed</option>
          <option value="ARCHIVED">Archived</option>
        </select>
      </div>

      <section className="overflow-hidden rounded-card border border-line bg-white">
        <h2 className="border-b border-line px-5 py-3 text-sm font-semibold">Due and overdue</h2>
        {alerts.length === 0 ? <p className="px-5 py-4 text-sm text-charcoal/60">Nothing is due.</p> : null}
        <ul className="divide-y divide-line">
          {alerts.map((row) => (
            <li key={row.id} className="space-y-2 px-5 py-4 text-sm">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="font-semibold">{row.customer_name} <span className="font-normal text-charcoal/50">{row.customer_code}</span></p>
                <p className="text-charcoal/60">{row.scheduled_on}{row.preferred_time ? ` · ${row.preferred_time}` : ""} · {row.overdue ? "overdue" : row.status.toLowerCase()}</p>
              </div>
              <p>{row.items.map((item) => `${item.product_name} × ${item.quantity} ${item.unit}`).join(", ")}</p>
              <p className="text-charcoal/60">
                {row.fulfillment === "DELIVERY" ? "Delivery" : "Collection"}
                {row.delivery_address ? ` · ${row.delivery_address}` : ""}
                {row.salesperson_name ? ` · ${row.salesperson_name}` : ""}
                {` · Balance ${money(row.balance_cents)}`}
                {` · Notice ${row.notification_status.toLowerCase()}`}
              </p>
              {row.stock_note ? <p className="text-amber-800">{row.stock_note}</p> : null}
              {row.sales_order_number ? <p>Order {row.sales_order_number}</p> : null}
              <div className="flex flex-wrap gap-2">
                <button type="button" className="rounded-full border border-line px-3 py-1.5 font-semibold" onClick={() => void act(`/api/v1/reorders/occurrences/${row.id}/order`)}>Create order</button>
                <button type="button" className="rounded-full border border-line px-3 py-1.5" onClick={() => void act(`/api/v1/reorders/occurrences/${row.id}/snooze`, { hours: 4 })}>Snooze 4h</button>
                <button type="button" className="rounded-full border border-line px-3 py-1.5" onClick={() => void act(`/api/v1/reorders/occurrences/${row.id}/skip`, { reason: "Customer skipped this delivery" })}>Skip this one</button>
                <button type="button" className="rounded-full border border-line px-3 py-1.5" onClick={() => void act(`/api/v1/reorders/occurrences/${row.id}/complete`)}>Delivered</button>
                {row.notification_status === "FAILED" ? (
                  <button type="button" className="rounded-full border border-line px-3 py-1.5" onClick={() => void act(`/api/v1/reorders/occurrences/${row.id}/retry-notification`)}>Retry notice</button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section className="overflow-x-auto rounded-card border border-line bg-white">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="border-b border-line text-xs uppercase tracking-wide text-charcoal/50">
            <tr>
              <th className="px-4 py-3 font-semibold">Customer</th>
              <th className="px-4 py-3 font-semibold">Plan</th>
              <th className="px-4 py-3 font-semibold">Next</th>
              <th className="px-4 py-3 font-semibold">Status</th>
              <th className="px-4 py-3 font-semibold" />
            </tr>
          </thead>
          <tbody>
            {plans.map((plan) => (
              <tr key={plan.id} className="border-b border-line last:border-0">
                <td className="px-4 py-3">{plan.customer_name}<div className="text-xs text-charcoal/50">{plan.customer_code}</div></td>
                <td className="px-4 py-3">{plan.name}<div className="text-xs text-charcoal/50">{plan.items.map((item) => `${item.quantity} ${item.product_name}`).join(", ")}</div></td>
                <td className="px-4 py-3">{plan.next_on ?? "—"}<div className="text-xs text-charcoal/50">{plan.frequency.toLowerCase()}</div></td>
                <td className="px-4 py-3">{plan.status.toLowerCase()}</td>
                <td className="px-4 py-3 text-right">
                  <button type="button" className="mr-2 font-semibold text-accent" onClick={() => { setEditing(plan); setOpen(true); }}>Edit</button>
                  {plan.status === "ACTIVE" ? <button type="button" className="mr-2" onClick={() => void act(`/api/v1/reorders/plans/${plan.id}/pause`)}>Pause</button> : null}
                  {plan.status === "PAUSED" ? <button type="button" className="mr-2" onClick={() => void act(`/api/v1/reorders/plans/${plan.id}/resume`)}>Resume</button> : null}
                  {plan.status !== "ARCHIVED" ? <button type="button" onClick={() => void act(`/api/v1/reorders/plans/${plan.id}/archive`)}>Archive</button> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {plans.length === 0 ? <p className="px-4 py-4 text-sm text-charcoal/60">No plans match.</p> : null}
      </section>

      {open ? (
        <PlanForm
          customerId={customerId}
          plan={editing}
          onClose={() => setOpen(false)}
          onSaved={() => {
            setOpen(false);
            setNotice(editing ? "Plan updated. Earlier reminders stay as they were." : "Plan saved.");
            void load();
          }}
        />
      ) : null}
    </div>
  );
}

function PlanForm({
  customerId,
  plan,
  onClose,
  onSaved,
}: {
  customerId: string;
  plan: Plan | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [customerQuery, setCustomerQuery] = useState("");
  const [customers, setCustomers] = useState<{ id: string; name: string; code: string }[]>([]);
  const [chosenCustomer, setChosenCustomer] = useState(plan?.customer_id || customerId);
  const [name, setName] = useState(plan?.name ?? "Standing order");
  const [frequency, setFrequency] = useState(plan?.frequency ?? "DAILY");
  const [weekdays, setWeekdays] = useState<number[]>(plan?.weekdays ?? [0]);
  const [monthDay, setMonthDay] = useState(String(plan?.month_day ?? 1));
  const [start, setStart] = useState(plan?.start_on ?? new Date().toISOString().slice(0, 10));
  const [end, setEnd] = useState(plan?.end_on ?? "");
  const [time, setTime] = useState(plan?.preferred_time ?? "09:00");
  const [lead, setLead] = useState(String(plan?.lead_days ?? 0));
  const [fulfillment, setFulfillment] = useState(plan?.fulfillment ?? "DELIVERY");
  const [address, setAddress] = useState(plan?.delivery_address ?? "");
  const [notes, setNotes] = useState(plan?.notes ?? "");
  const [notify, setNotify] = useState(plan?.notify_customer ?? false);
  const [productQuery, setProductQuery] = useState("");
  const [hits, setHits] = useState<{ id: string; name: string; units: string[] }[]>([]);
  const [lines, setLines] = useState<DraftLine[]>(
    plan?.items.map((item) => ({ product_id: item.product_id, name: item.product_name, quantity: String(item.quantity), unit: item.unit })) ?? [],
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (customerQuery.trim().length < 2) return;
    const timer = window.setTimeout(() => {
      void apiGet<{ id: string; name: string; code: string }[]>(`/api/v1/customers?q=${encodeURIComponent(customerQuery.trim())}&limit=8`)
        .then(setCustomers)
        .catch(() => setCustomers([]));
    }, 200);
    return () => window.clearTimeout(timer);
  }, [customerQuery]);

  useEffect(() => {
    if (productQuery.trim().length < 2) return;
    const timer = window.setTimeout(() => {
      void apiGet<{ product: { id: string; name: string; sellable_units?: string[] } }[]>(
        `/api/v1/products/search?q=${encodeURIComponent(productQuery.trim())}&limit=8`,
      )
        .then((rows) => setHits(rows.map((row) => ({ id: row.product.id, name: row.product.name, units: row.product.sellable_units ?? ["PIECE"] }))))
        .catch(() => setHits([]));
    }, 200);
    return () => window.clearTimeout(timer);
  }, [productQuery]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!chosenCustomer) {
      setError("Choose a customer.");
      return;
    }
    const items = lines.filter((line) => Number(line.quantity) > 0);
    if (items.length === 0) {
      setError("Add at least one product.");
      return;
    }
    setBusy(true);
    setError(null);
    const itemsBody = items.map((line) => ({ product_id: line.product_id, quantity: Number(line.quantity), unit: line.unit }));
    const shared = {
      name,
      frequency,
      weekdays: frequency === "CUSTOM_DAYS" ? weekdays : [],
      month_day: frequency === "MONTHLY" ? Number(monthDay) : null,
      start_on: start,
      end_on: end || null,
      clear_end: !end,
      preferred_time: time || null,
      lead_days: Number(lead) || 0,
      fulfillment,
      delivery_address: address || null,
      notes,
      notify_customer: notify,
      items: itemsBody,
    };
    try {
      if (plan) await apiPatch(`/api/v1/reorders/plans/${plan.id}`, shared);
      else {
        const { clear_end: _ignored, ...created } = shared;
        await apiPost("/api/v1/reorders/plans", { customer_id: chosenCustomer, ...created });
      }
      onSaved();
    } catch (caught) {
      setError(problem(caught, "Could not save the plan."));
      setBusy(false);
    }
  };

  return (
    <form onSubmit={(event) => void submit(event)} className="space-y-4 rounded-card border border-line bg-white p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">{plan ? "Edit plan" : "New reorder plan"}</h2>
        <button type="button" onClick={onClose} className="text-sm font-semibold">Close</button>
      </div>
      {error ? <ErrorNote message={error} /> : null}
      {plan ? null : (
        <label className="block text-sm font-medium">
          Customer
          <input value={customerQuery} onChange={(event) => setCustomerQuery(event.target.value)} placeholder="Search by name or code" className="mt-1 h-10 w-full rounded-xl border border-line px-3" />
          <ul className="mt-1">
            {customers.map((customer) => (
              <li key={customer.id}>
                <button type="button" className="text-sm text-accent" onClick={() => { setChosenCustomer(customer.id); setCustomerQuery(`${customer.name} (${customer.code})`); setCustomers([]); }}>
                  {customer.name} · {customer.code}
                </button>
              </li>
            ))}
          </ul>
        </label>
      )}
      <div className="grid gap-3 md:grid-cols-2">
        <label className="text-sm font-medium">Plan name<input value={name} onChange={(event) => setName(event.target.value)} className="mt-1 h-10 w-full rounded-xl border border-line px-3" required /></label>
        <label className="text-sm font-medium">Frequency
          <select value={frequency} onChange={(event) => setFrequency(event.target.value)} className="mt-1 h-10 w-full rounded-xl border border-line px-3">
            <option value="DAILY">Daily</option>
            <option value="WEEKLY">Weekly</option>
            <option value="MONTHLY">Monthly</option>
            <option value="CUSTOM_DAYS">Selected days</option>
          </select>
        </label>
        <label className="text-sm font-medium">Starts<input type="date" value={start} onChange={(event) => setStart(event.target.value)} className="mt-1 h-10 w-full rounded-xl border border-line px-3" required /></label>
        <label className="text-sm font-medium">Ends<input type="date" value={end} onChange={(event) => setEnd(event.target.value)} className="mt-1 h-10 w-full rounded-xl border border-line px-3" /></label>
        <label className="text-sm font-medium">Preferred time<input type="time" value={time} onChange={(event) => setTime(event.target.value)} className="mt-1 h-10 w-full rounded-xl border border-line px-3" /></label>
        <label className="text-sm font-medium">Remind this many days ahead<input type="number" min={0} max={14} value={lead} onChange={(event) => setLead(event.target.value)} className="mt-1 h-10 w-full rounded-xl border border-line px-3" /></label>
        <label className="text-sm font-medium">Handover
          <select value={fulfillment} onChange={(event) => setFulfillment(event.target.value)} className="mt-1 h-10 w-full rounded-xl border border-line px-3">
            <option value="DELIVERY">Delivery</option>
            <option value="COLLECTION">Collection</option>
          </select>
        </label>
        <label className="text-sm font-medium">Address<input value={address} onChange={(event) => setAddress(event.target.value)} className="mt-1 h-10 w-full rounded-xl border border-line px-3" /></label>
      </div>
      {frequency === "CUSTOM_DAYS" ? (
        <div className="flex flex-wrap gap-2">
          {DAYS.map((label, index) => (
            <button key={label} type="button" aria-pressed={weekdays.includes(index)} onClick={() => setWeekdays((current) => current.includes(index) ? current.filter((day) => day !== index) : [...current, index])} className={`rounded-full border px-3 py-1 text-sm ${weekdays.includes(index) ? "border-charcoal bg-charcoal text-white" : "border-line"}`}>{label}</button>
          ))}
        </div>
      ) : null}
      {frequency === "MONTHLY" ? (
        <label className="block text-sm font-medium">Day of month<input type="number" min={1} max={28} value={monthDay} onChange={(event) => setMonthDay(event.target.value)} className="mt-1 h-10 w-32 rounded-xl border border-line px-3" /></label>
      ) : null}
      <label className="block text-sm font-medium">Notes<textarea value={notes} onChange={(event) => setNotes(event.target.value)} className="mt-1 w-full rounded-xl border border-line px-3 py-2" rows={2} /></label>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={notify} onChange={(event) => setNotify(event.target.checked)} />Tell the customer when a reminder is due, if they have opted in</label>
      <div>
        <label className="text-sm font-medium">Add a product<input value={productQuery} onChange={(event) => setProductQuery(event.target.value)} className="mt-1 h-10 w-full rounded-xl border border-line px-3" placeholder="Name, SKU, or barcode" /></label>
        <ul>
          {hits.map((hit) => (
            <li key={hit.id}><button type="button" className="text-sm text-accent" onClick={() => { setLines((current) => [...current, { product_id: hit.id, name: hit.name, quantity: "1", unit: hit.units[0] ?? "PIECE" }]); setProductQuery(""); setHits([]); }}>{hit.name}</button></li>
          ))}
        </ul>
        <ul className="mt-2 space-y-2">
          {lines.map((line, index) => (
            <li key={`${line.product_id}-${index}`} className="flex flex-wrap items-center gap-2 text-sm">
              <span className="min-w-40 flex-1">{line.name}</span>
              <input aria-label={`Quantity for ${line.name}`} value={line.quantity} onChange={(event) => setLines((current) => current.map((item, at) => at === index ? { ...item, quantity: event.target.value } : item))} className="h-9 w-20 rounded-lg border border-line px-2" />
              <input aria-label={`Unit for ${line.name}`} value={line.unit} onChange={(event) => setLines((current) => current.map((item, at) => at === index ? { ...item, unit: event.target.value.toUpperCase() } : item))} className="h-9 w-28 rounded-lg border border-line px-2" />
              <button type="button" onClick={() => setLines((current) => current.filter((_, at) => at !== index))}>Remove</button>
            </li>
          ))}
        </ul>
      </div>
      <PrimaryButton type="submit" disabled={busy}>{busy ? "Saving…" : "Save plan"}</PrimaryButton>
    </form>
  );
}
