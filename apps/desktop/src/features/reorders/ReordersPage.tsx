import { useCallback, useEffect, useState } from "react";
import { PageFrame } from "../../components/shell/RegisterShell";
import { useShellPage } from "../../components/shell/ShellContext";
import { RetailRequestError, retailCall } from "../../lib/retailClient";
import type { CashierSession } from "../auth/session";

interface Item {
  product_name: string;
  quantity: number;
  unit: string;
  available: number | null;
  discontinued: boolean;
}

interface Alert {
  id: string;
  customer_name: string;
  customer_code: string;
  plan_name: string;
  scheduled_on: string;
  preferred_time: string | null;
  status: string;
  fulfillment: string;
  delivery_address: string | null;
  salesperson_name: string | null;
  balance_cents: number;
  items: Item[];
  stock_note: string;
  sales_order_number: string | null;
  notification_status: string;
  overdue: boolean;
}

function problem(caught: unknown): string {
  return caught instanceof RetailRequestError ? caught.message : "Could not update the reminder.";
}

export function ReordersPage({ session }: { session: CashierSession }) {
  const [rows, setRows] = useState<Alert[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const notify = useCallback((message: string) => setError(message), []);
  useShellPage(busy, notify);

  const load = useCallback(async () => {
    const found = await retailCall<Alert[]>("GET", "/api/v1/reorders/occurrences?view=due&limit=50");
    setRows(found);
    setSelected((current) => current ?? found[0]?.id ?? null);
  }, []);

  useEffect(() => {
    void load().catch((caught: unknown) => setError(problem(caught)));
  }, [load]);

  const act = async (id: string, action: string, body?: unknown) => {
    setBusy(true);
    setError(null);
    try {
      await retailCall("POST", `/api/v1/reorders/occurrences/${id}/${action}`, body ?? { user_id: session.user.id });
      await load();
    } catch (caught) {
      setError(problem(caught));
    } finally {
      setBusy(false);
    }
  };

  const current = rows?.find((row) => row.id === selected) ?? null;
  const list = (
    <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
      {rows?.length === 0 ? <li className="p-4 text-sm text-zinc-500">No reorder alerts.</li> : null}
      {rows?.map((row) => (
        <li key={row.id}>
          <button type="button" onClick={() => setSelected(row.id)} className={`block w-full px-4 py-3 text-left ${row.id === selected ? "bg-primary-500/10" : ""}`}>
            <span className="block font-semibold">{row.customer_name}</span>
            <span className="text-xs text-zinc-500">{row.customer_code} · {row.scheduled_on}{row.overdue ? " · overdue" : ""}</span>
          </button>
        </li>
      ))}
    </ul>
  );

  return (
    <PageFrame title="Reorder alerts" sync={{ tone: "live", label: "Live", title: "Reminders are stored on the server." }} drawer={list}>
      <div className="mx-auto max-w-3xl space-y-4 p-4">
        {error ? <p className="rounded-xl bg-red-500/10 px-4 py-3 text-sm text-red-700">{error}</p> : null}
        {current === null ? <p className="text-sm text-zinc-500">{rows === null ? "Loading alerts…" : "Select a reminder."}</p> : null}
        {current ? (
          <article className="space-y-3 rounded-2xl border border-zinc-200 p-4 dark:border-zinc-800">
            <header>
              <h2 className="text-lg font-semibold">{current.customer_name}</h2>
              <p className="text-sm text-zinc-500">{current.customer_code} · {current.plan_name}</p>
            </header>
            <p className="text-sm">Due {current.scheduled_on}{current.preferred_time ? ` at ${current.preferred_time}` : ""} · {current.status.toLowerCase()}</p>
            <ul className="text-sm">
              {current.items.map((item) => (
                <li key={`${item.product_name}-${item.unit}`}>
                  {item.product_name} × {item.quantity} {item.unit}
                  {item.discontinued ? " · discontinued" : item.available !== null ? ` · ${item.available} on hand` : ""}
                </li>
              ))}
            </ul>
            <p className="text-sm text-zinc-500">
              {current.fulfillment === "DELIVERY" ? "Delivery" : "Collection"}
              {current.delivery_address ? ` · ${current.delivery_address}` : ""}
              {current.salesperson_name ? ` · ${current.salesperson_name}` : ""}
              {` · Balance ${(current.balance_cents / 100).toFixed(2)}`}
            </p>
            {current.stock_note ? <p className="text-sm text-amber-700">{current.stock_note}</p> : null}
            {current.sales_order_number ? <p className="text-sm">Draft order {current.sales_order_number}</p> : null}
            <div className="flex flex-wrap gap-2">
              <button type="button" disabled={busy} className="rounded-full bg-primary-500 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40" onClick={() => void act(current.id, "order", { user_id: session.user.id })}>Create order</button>
              <button type="button" disabled={busy} className="rounded-full border px-4 py-2 text-sm" onClick={() => void act(current.id, "snooze", { hours: 4 })}>Snooze</button>
              <button type="button" disabled={busy} className="rounded-full border px-4 py-2 text-sm" onClick={() => void act(current.id, "skip", { reason: "Skipped at the register" })}>Skip this one</button>
              <button type="button" disabled={busy} className="rounded-full border px-4 py-2 text-sm" onClick={() => void act(current.id, "complete")}>Delivered</button>
            </div>
          </article>
        ) : null}
      </div>
    </PageFrame>
  );
}
