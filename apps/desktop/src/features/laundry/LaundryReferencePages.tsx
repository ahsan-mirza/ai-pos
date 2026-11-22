import { useEffect, useState, type ReactNode } from "react";
import { laundryCall, noticeFromError, type FloorNotice } from "./diagnostics";
import { retailCall } from "../../lib/retailClient";
import { LaundryEmptyState, LaundryErrorState, LaundryStatusBadge, money } from "./ui";

interface OrderRow {
  id: string;
  code: string;
  operational_status: string;
  payment_status: string;
  total_cents: number;
  amount_paid_cents: number;
  balance_due_cents: number;
  garment_count: number;
}

interface NamedRow {
  id: string;
  code?: string;
  name: string;
  pricing_unit?: string;
  base_rate_cents?: number;
  kind?: string;
  is_active?: boolean;
}

const CATALOGUE: Record<string, { title: string; path: string; detail: string }> = {
  services: {
    title: "Laundry Services",
    path: "/api/v1/laundry/services?active=true",
    detail: "Treatments such as wash and fold, dry cleaning, and ironing. These are not stock products.",
  },
  categories: {
    title: "Service Categories",
    path: "/api/v1/laundry/categories",
    detail: "Groups for the laundry service catalogue.",
  },
  "garment-types": {
    title: "Garment Types",
    path: "/api/v1/laundry/garments",
    detail: "Items received from the customer, such as a shirt or an abaya. A garment type is not a service.",
  },
  pricing: {
    title: "Service Pricing",
    path: "/api/v1/laundry/price-lists",
    detail: "Price lists used by the server when an order is priced. This screen does not calculate a total.",
  },
};

function useSignedList<T>(signedIn: boolean, path: string | null): { rows: T[] | null; notice: FloorNotice | null } {
  const [rows, setRows] = useState<T[] | null>(null);
  const [notice, setNotice] = useState<FloorNotice | null>(null);
  useEffect(() => {
    if (!signedIn || path === null) {
      setRows(null);
      return;
    }
    let cancelled = false;
    setNotice(null);
    void laundryCall<T[]>("GET", path)
      .then((data) => {
        if (!cancelled) setRows(data);
      })
      .catch((error: unknown) => {
        if (!cancelled) setNotice(noticeFromError(error));
      });
    return () => {
      cancelled = true;
    };
  }, [path, signedIn]);
  return { rows, notice };
}

/** Existing orders. Read only: this list does not change payment or production state. */
export function LaundryActiveOrders({ signedIn, action }: { signedIn: boolean; action?: ReactNode }) {
  const { rows, notice } = useSignedList<OrderRow>(signedIn, signedIn ? "/api/v1/laundry/orders" : null);
  const heading = (
    <div className="flex items-center justify-between gap-3">
      <h1 className="text-xl font-semibold text-zinc-900">Active Orders</h1>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
  if (!signedIn) return <div className="space-y-3">{heading}<p className="text-sm">Unlock the register to load orders.</p></div>;
  if (notice) return <div className="space-y-3">{heading}<LaundryErrorState notice={notice} /></div>;
  if (rows === null) return <div className="space-y-3">{heading}<p className="text-sm">Loading orders.</p></div>;
  if (rows.length === 0) return <div className="space-y-3">{heading}<LaundryEmptyState title="No laundry orders" detail="New orders appear here after the server accepts them." /></div>;
  return (
    <div className="space-y-3">
      {heading}
      <p className="text-sm text-zinc-500">Production status and payment status are separate. A ready order can still have a balance.</p>
      <ul className="space-y-2" aria-label="Laundry orders">
        {rows.map((order) => (
          <li key={order.id} className="rounded-2xl bg-white p-4 ring-1 ring-zinc-200">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="font-semibold">{order.code}</p>
              <p className="text-sm">{order.garment_count} garments</p>
            </div>
            <p className="mt-2 flex flex-wrap items-center gap-2 text-sm">
              Production <LaundryStatusBadge value={order.operational_status} />
              Payment <LaundryStatusBadge value={order.payment_status} />
            </p>
            <p className="mt-2 text-sm text-charcoal/70">
              Total {money(order.total_cents)} · deposit {money(order.amount_paid_cents)} · balance {money(order.balance_due_cents)}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Read-only catalogue. Editing stays in Business Pro; this register does not create stock movements. */
export function LaundryCataloguePage({ station, signedIn }: { station: string; signedIn: boolean }) {
  const spec = CATALOGUE[station];
  const { rows, notice } = useSignedList<NamedRow>(signedIn, signedIn && spec ? spec.path : null);
  if (!spec) return null;
  return (
    <div className="space-y-3">
      <h1 className="text-xl font-semibold text-zinc-900">{spec.title}</h1>
      <p className="text-sm text-zinc-500">{spec.detail}</p>
      <p className="text-sm text-zinc-500">
        Service templates are applied in Business Pro. This register does not edit them. Detergent, packaging, and other physical products stay in Inventory.
      </p>
      {!signedIn ? <p className="text-sm">Unlock the register to load the catalogue.</p> : null}
      {notice ? <LaundryErrorState notice={notice} /> : null}
      {signedIn && !notice && rows === null ? <p className="text-sm">Loading the catalogue.</p> : null}
      {rows && rows.length === 0 ? <LaundryEmptyState title="Nothing in this list" detail="The catalogue did not return any rows." /> : null}
      {rows && rows.length > 0 ? (
        <ul className="space-y-2" aria-label={spec.title}>
          {rows.map((row) => (
            <li key={row.id} className="rounded-2xl bg-white p-4 ring-1 ring-zinc-200">
              <p className="font-semibold">{row.name}</p>
              <p className="text-sm text-charcoal/70">
                {[row.code, row.pricing_unit, row.kind, row.base_rate_cents !== undefined ? money(row.base_rate_cents) : "", row.is_active === false ? "Inactive" : ""]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/** Existing customers only. This screen does not register a customer. */
export function LaundryCustomersPage({ signedIn }: { signedIn: boolean }) {
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState<NamedRow[] | null>(null);
  const [notice, setNotice] = useState<FloorNotice | null>(null);
  useEffect(() => {
    if (!signedIn) {
      setRows(null);
      return;
    }
    let cancelled = false;
    void retailCall<NamedRow[]>("GET", "/api/v1/customers/sync")
      .then((data) => {
        if (!cancelled) setRows(data);
      })
      .catch((error: unknown) => {
        if (!cancelled) setNotice(noticeFromError(error));
      });
    return () => {
      cancelled = true;
    };
  }, [signedIn]);
  const shown = (rows ?? []).filter((row) => row.name.toLowerCase().includes(query.trim().toLowerCase()));
  return (
    <div className="space-y-3">
      <h1 className="text-xl font-semibold text-zinc-900">Customers</h1>
      <p className="text-sm text-zinc-500">Look up a customer already on this register. A new customer is added only through a workflow this register already supports. This screen does not create one.</p>
      {!signedIn ? <p className="text-sm">Unlock the register to load customers.</p> : null}
      {notice ? <LaundryErrorState notice={notice} /> : null}
      {signedIn && !notice ? (
        <label className="block text-xs font-semibold uppercase tracking-wide text-charcoal/55">
          Find a customer
          <input className="mt-1 min-h-12 w-full rounded-xl border border-zinc-200 px-3" value={query} onChange={(event) => setQuery(event.target.value)} />
        </label>
      ) : null}
      {rows && shown.length === 0 ? <LaundryEmptyState title="No matching customer" detail="Try another name, or take the order as the walk-in customer already on the register." /> : null}
      {shown.length > 0 ? (
        <ul className="space-y-2" aria-label="Customers">
          {shown.map((row) => (
            <li key={row.id} className="rounded-2xl bg-white p-4 ring-1 ring-zinc-200">{row.name}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
