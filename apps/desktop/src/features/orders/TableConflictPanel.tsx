import { useEffect, useState } from "react";
import { formatMoney } from "@ai-pos/shared-types";
import { OrderRequestError, call } from "./ordersClient";

type ConflictOrder = {
  id: string;
  number: number;
  status: string;
  service_type: string;
  table_id: string | null;
  opened_at: string;
  items: { id: string; quantity: number; unit_price_cents: number; note: string | null }[];
};

type TableConflict = {
  id: string;
  table_id: string | null;
  origin_device_id: string;
  origin_actor_id: string;
  reason: string;
  primary: ConflictOrder;
  conflicting: ConflictOrder;
};

/** Two offline tills opened one table. A manager keeps both orders, or voids the second if nothing was paid. */
export function TableConflictPanel({
  storeId,
  userId,
  currency,
}: {
  storeId: string;
  userId: string;
  currency: string;
}) {
  const [rows, setRows] = useState<TableConflict[]>([]);
  const [notice, setNotice] = useState<string | null>(null);

  async function load() {
    try {
      setRows(await call<TableConflict[]>("GET", `/api/v1/orders/table-conflicts?store_id=${storeId}`));
      setNotice(null);
    } catch (caught) {
      if (caught instanceof OrderRequestError && caught.offline) {
        setNotice("Table conflicts will load when the server is reachable.");
      }
    }
  }

  useEffect(() => {
    void load();
  }, [storeId]);

  async function decide(row: TableConflict, decision: "separate" | "void") {
    try {
      await call("POST", `/api/v1/orders/table-conflicts/${row.id}/resolve`, { user_id: userId, decision });
      setNotice(decision === "void" ? "The second order was voided. The first order is unchanged." : "The second order is now a separate takeaway. The bills were not merged.");
      await load();
    } catch (caught) {
      setNotice(caught instanceof Error ? caught.message : "The conflict could not be decided.");
    }
  }

  if (rows.length === 0 && notice === null) return null;
  return (
    <section aria-label="Table conflicts" className="mb-3 rounded-2xl border border-amber-400/60 bg-amber-500/10 px-4 py-3 text-sm">
      <h2 className="font-semibold">Tables used by two tills while offline</h2>
      {notice ? <p className="mt-1">{notice}</p> : null}
      {rows.map((row) => (
        <article key={row.id} className="mt-3 border-t border-amber-400/40 pt-3">
          <p>{row.reason} Till {row.origin_device_id}.</p>
          <OrderSummary title="On the table" order={row.primary} currency={currency} />
          <OrderSummary title="Waiting for review" order={row.conflicting} currency={currency} />
          <div className="mt-2 flex gap-2">
            <button type="button" className="rounded-full bg-zinc-900 px-3 py-1 text-white" onClick={() => void decide(row, "separate")}>
              Keep as a separate order
            </button>
            <button type="button" className="rounded-full border border-zinc-400 px-3 py-1" onClick={() => void decide(row, "void")}>
              Void the second order
            </button>
          </div>
        </article>
      ))}
    </section>
  );
}

function OrderSummary({ title, order, currency }: { title: string; order: ConflictOrder; currency: string }) {
  const total = order.items.reduce((sum, item) => sum + item.quantity * item.unit_price_cents, 0);
  return (
    <p className="mt-1">
      {title}: #{order.number} {order.service_type} {order.status}, {formatMoney(total, currency)}, opened {order.opened_at}.
    </p>
  );
}
