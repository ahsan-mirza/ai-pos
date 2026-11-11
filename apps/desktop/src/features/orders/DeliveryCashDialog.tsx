import { formatMoney, type Order } from "@ai-pos/shared-types";
import { useEffect, useState } from "react";
import { ManagerApprovalModal } from "../../components/ManagerApprovalModal";
import { ui } from "../../components/shell/tokens";
import type { CashierProfile } from "../../lib/tauri";
import { activeShiftId } from "../shifts/shift";
import { ordersApi } from "./ordersClient";

/** Cash the rider still owes the store, in cents. */
function outstanding(order: Order): number {
  return Math.max(0, (order.cod_expected_cents ?? 0) - (order.cod_handed_cents ?? 0));
}

export function DeliveryCashDialog({
  storeId,
  userId,
  currency,
  verify,
  onClose,
  onDone,
}: {
  storeId: string;
  userId: string;
  currency: string;
  verify: (username: string, pin: string) => Promise<CashierProfile>;
  onClose: () => void;
  onDone: (message: string) => void;
}) {
  const [rows, setRows] = useState<Order[]>([]);
  const [amounts, setAmounts] = useState<Record<string, string>>({});
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [shortfall, setShortfall] = useState<{ order: Order; cents: number; key: string; due: number } | null>(null);
  const shiftId = activeShiftId();

  useEffect(() => {
    void ordersApi.codPending(storeId).then(setRows).catch((caught: unknown) => {
      setError(caught instanceof Error ? caught.message : "Could not load rider cash.");
    });
  }, [storeId]);

  const submit = async (order: Order, cents: number, idempotencyKey: string, approvedById: string | null) => {
    if (!shiftId) return;
    setBusy(true);
    setError(null);
    try {
      const next = await ordersApi.acceptCod(order, userId, shiftId, cents, idempotencyKey, approvedById);
      setRows((current) => current.flatMap((item) => (item.id === next.id ? (outstanding(next) > 0 ? [next] : []) : [item])));
      setKeys((current) => {
        const copy = { ...current };
        delete copy[order.id];
        return copy;
      });
      onDone(
        next.payment_state === "PAID"
          ? `Order #${next.number} is paid. ${formatMoney(cents, currency)} is in the drawer.`
          : `Accepted ${formatMoney(cents, currency)}. ${formatMoney(outstanding(next), currency)} is still outstanding on #${next.number}.`,
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not accept the cash.");
    } finally {
      setBusy(false);
    }
  };

  const accept = (order: Order) => {
    if (!shiftId) {
      setError("Open a register shift before accepting rider cash.");
      return;
    }
    const cents = Math.round(Number(amounts[order.id] ?? "") * 100);
    const due = outstanding(order);
    if (!Number.isFinite(cents) || cents < 1 || cents > due) {
      setError("Enter the cash actually handed over, up to the amount still outstanding.");
      return;
    }
    const idempotencyKey = keys[order.id] ?? crypto.randomUUID();
    setKeys((current) => ({ ...current, [order.id]: idempotencyKey }));
    if (cents < due) {
      setShortfall({ order, cents, key: idempotencyKey, due });
      return;
    }
    void submit(order, cents, idempotencyKey, null);
  };

  const groups = new Map<string, Order[]>();
  for (const order of rows) {
    const name = order.rider_name ?? "Unassigned";
    groups.set(name, [...(groups.get(name) ?? []), order]);
  }

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-black/40 p-4 sm:items-center" role="presentation" onMouseDown={onClose}>
      <div
        role="dialog"
        aria-label="Rider cash handover"
        className="max-h-[80vh] w-full max-w-lg overflow-y-auto rounded-3xl bg-white p-5 dark:bg-zinc-900"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <h2 className="text-lg font-semibold">Rider cash</h2>
        <p className="mt-1 text-sm text-zinc-500">Only cash you count into the drawer is recorded. A short count stays outstanding.</p>
        {shiftId === null ? <p className="mt-3 text-sm text-amber-700">Open a register shift before accepting rider cash.</p> : null}
        {error ? <p className="mt-3 text-sm text-red-600">{error}</p> : null}
        {[...groups.entries()].map(([rider, orders]) => (
          <section key={rider} className="mt-4">
            <h3 className="text-sm font-semibold">{rider}</h3>
            <ul className="mt-2 space-y-2">
              {orders.map((order) => (
                <li key={order.id} className="rounded-2xl border border-zinc-200 p-3 text-sm dark:border-zinc-700">
                  <p className="font-semibold">#{order.number} · {order.name ?? "Guest"}</p>
                  <p className="text-zinc-500">
                    Expected {formatMoney(order.cod_expected_cents ?? 0, currency)}
                    {" · "}collected {formatMoney(order.cod_collected_cents ?? 0, currency)}
                    {" · "}outstanding {formatMoney(outstanding(order), currency)}
                  </p>
                  <div className="mt-2 flex gap-2">
                    <input
                      inputMode="decimal"
                      aria-label={`Cash received for order ${order.number}`}
                      value={amounts[order.id] ?? ""}
                      onChange={(event) => setAmounts((current) => ({ ...current, [order.id]: event.target.value }))}
                      placeholder="0.00"
                      className="h-10 flex-1 rounded-xl border border-zinc-300 px-3 dark:border-zinc-600 dark:bg-zinc-800"
                    />
                    <button type="button" disabled={busy || shiftId === null} onClick={() => void accept(order)} className={`${ui.primaryAction} h-10 px-4`}>
                      Accept
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        ))}
        {rows.length === 0 ? <p className="mt-4 text-sm text-zinc-500">No rider cash is waiting.</p> : null}
        <button type="button" onClick={onClose} className={`${ui.secondaryAction} mt-4 h-10 px-4`}>
          Close
        </button>
      </div>
      {shortfall ? (
        <ManagerApprovalModal
          reasons={[
            `Rider cash for #${shortfall.order.number} is short by ${formatMoney(shortfall.due - shortfall.cents, currency)}`,
          ]}
          subtitle="A manager with drawer override must approve a short count. The difference stays outstanding."
          verify={verify}
          onClose={() => setShortfall(null)}
          onApproved={(approver) => {
            const pending = shortfall;
            setShortfall(null);
            void submit(pending.order, pending.cents, pending.key, approver.id);
          }}
        />
      ) : null}
    </div>
  );
}
