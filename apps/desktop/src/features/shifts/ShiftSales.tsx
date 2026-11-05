import { Permission, formatMoney } from "@ai-pos/shared-types";
import { useEffect, useMemo, useState } from "react";
import { useShell } from "../../components/shell/ShellContext";
import { inTauri, recentShifts, shiftHistory, type LocalShift, type ShiftHistory, type ShiftSaleRow } from "../../lib/tauri";
import type { CashierSession } from "../auth/session";
import { printReceipt } from "../printing/print";
import { shiftSaleReceipt } from "../printing/saleReceipt";
import { paymentLabels } from "../returns/returnMath";
import { queueReturnLookup } from "../returns/pendingLookup";

const statusLabel: Record<string, string> = {
  completed: "Completed",
  partially_returned: "Partially returned",
  returned: "Returned",
};

function when(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function ShiftSales({
  session,
  currency,
  onClose,
}: {
  session: CashierSession;
  currency: string;
  onClose: () => void;
}) {
  const { navigate } = useShell();
  const canHistory = session.user.permissions.includes(Permission.PosShiftManage);
  const [shifts, setShifts] = useState<LocalShift[]>([]);
  const [shiftId, setShiftId] = useState<string | undefined>(undefined);
  const [history, setHistory] = useState<ShiftHistory | null>(null);
  const [query, setQuery] = useState("");
  const [payment, setPayment] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<ShiftSaleRow | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const money = (cents: number) => formatMoney(cents, currency);

  useEffect(() => {
    if (!inTauri()) {
      setLoading(false);
      setError("Sales for this shift are stored on the register.");
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        if (canHistory) setShifts(await recentShifts(12));
        const found = await shiftHistory(shiftId);
        if (!cancelled) {
          setHistory(found);
          setError(null);
        }
      } catch (caught) {
        if (!cancelled) setError(caught instanceof Error ? caught.message : String(caught));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [canHistory, shiftId]);

  const sales = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (history?.sales ?? []).filter((sale) => {
      if (payment && !sale.payment.toLowerCase().includes(payment)) return false;
      if (status && sale.status !== status) return false;
      if (needle === "") return true;
      const haystack = [sale.invoice_number, sale.customer_name, ...sale.lines.map((line) => `${line.name} ${line.sku}`)]
        .join(" ")
        .toLowerCase();
      return haystack.includes(needle);
    });
  }, [history, query, payment, status]);

  const startReturn = (sale: ShiftSaleRow) => {
    if (sale.status === "returned") {
      setNotice("This invoice has already been fully returned.");
      return;
    }
    queueReturnLookup(sale.invoice_number);
    onClose();
    navigate("returns");
  };

  const reprint = (sale: ShiftSaleRow) => {
    const doc = shiftSaleReceipt({
      number: sale.invoice_number,
      issuedAt: sale.sold_at,
      cashier: session.user.full_name,
      customer: sale.customer_name === "Walk-in" ? null : sale.customer_name,
      lines: sale.lines.map((line) => ({
        name: line.name,
        quantity: line.quantity,
        unitCents: line.unit_price_cents,
        lineCents: line.line_total_cents,
      })),
      subtotalCents: sale.gross_cents,
      taxCents: sale.tax_cents,
      totalCents: sale.total_cents,
      tenders: sale.tenders.map((tender) => ({
        label: paymentLabels[tender.method as keyof typeof paymentLabels] ?? tender.method,
        amountCents: tender.amount_cents,
      })),
      currency,
    });
    void printReceipt(doc, { kickDrawer: false, manual: true }).then((printed) => {
      setNotice(printed.printed ? `Receipt ${sale.invoice_number} sent to the printer.` : printed.message ?? "The receipt could not be printed.");
    });
  };

  return (
    <div className="mt-5 space-y-3">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <label className="block text-xs font-medium text-charcoal/70 dark:text-zinc-400">
          Invoice, customer, or item
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="DT-01-S-000125"
            className="modal-input mt-1 font-normal"
          />
        </label>
        {canHistory && shifts.length > 0 ? (
          <label className="block text-xs font-medium text-charcoal/70 dark:text-zinc-400">
            Shift
            <select
              className="modal-input mt-1 font-normal"
              value={shiftId ?? ""}
              onChange={(event) => {
                setShiftId(event.target.value || undefined);
                setSelected(null);
                setLoading(true);
              }}
            >
              <option value="">Current shift</option>
              {shifts.map((shift) => (
                <option key={shift.id} value={shift.id}>
                  {when(shift.opened_at)} · {shift.status === "OPEN" ? "Open" : shift.z_number || "Closed"}
                </option>
              ))}
            </select>
          </label>
        ) : null}
      </div>
      <div className="flex flex-wrap gap-2">
        <select className="modal-input w-auto font-normal" value={payment} onChange={(event) => setPayment(event.target.value)} aria-label="Payment">
          <option value="">All payments</option>
          <option value="cash">Cash</option>
          <option value="card">Card</option>
          <option value="transfer">Transfer</option>
        </select>
        <select className="modal-input w-auto font-normal" value={status} onChange={(event) => setStatus(event.target.value)} aria-label="Status">
          <option value="">All statuses</option>
          <option value="completed">Completed</option>
          <option value="partially_returned">Partially returned</option>
          <option value="returned">Returned</option>
        </select>
      </div>
      {error ? <p className="text-sm text-red-700">{error}</p> : null}
      {notice ? <p className="text-sm text-charcoal/70 dark:text-zinc-300">{notice}</p> : null}
      {loading ? <div className="h-24 animate-pulse rounded-2xl bg-charcoal/5" /> : null}
      {!loading && sales.length === 0 ? (
        <p className="text-sm text-charcoal/60 dark:text-zinc-400">No sales on this register match this shift.</p>
      ) : null}
      {sales.length > 0 ? (
        <div className="max-h-64 overflow-auto rounded-2xl border border-line dark:border-zinc-800">
          <table className="min-w-full text-left text-sm">
            <thead className="text-xs text-charcoal/60 dark:text-zinc-400">
              <tr>
                <th className="px-3 py-2 font-medium">Invoice</th>
                <th className="px-3 py-2 font-medium">When</th>
                <th className="px-3 py-2 font-medium">Customer</th>
                <th className="px-3 py-2 font-medium">Total</th>
                <th className="px-3 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {sales.map((sale) => (
                <tr
                  key={sale.id}
                  className="cursor-pointer border-t border-line hover:bg-charcoal/5 dark:border-zinc-800"
                  onClick={() => setSelected(sale)}
                >
                  <td className="whitespace-nowrap px-3 py-2 font-medium">{sale.invoice_number}</td>
                  <td className="whitespace-nowrap px-3 py-2">{when(sale.sold_at)}</td>
                  <td className="px-3 py-2">{sale.customer_name}</td>
                  <td className="whitespace-nowrap px-3 py-2 tabular-nums">{money(sale.total_cents)}</td>
                  <td className="whitespace-nowrap px-3 py-2">
                    {statusLabel[sale.status] ?? sale.status}
                    {sale.sync_status === "pending" ? " · not synced" : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {selected ? (
        <article className="rounded-2xl border border-line bg-surface p-3 dark:border-zinc-800 dark:bg-zinc-800/60">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="font-semibold">{selected.invoice_number}</h3>
              <p className="text-xs text-charcoal/60 dark:text-zinc-400">
                {when(selected.sold_at)} · {selected.customer_name} · {selected.payment || "Payment"}
              </p>
            </div>
            <button type="button" className="text-sm" onClick={() => setSelected(null)}>
              Close
            </button>
          </div>
          <ul className="mt-3 space-y-2 text-sm">
            {selected.lines.map((line) => (
              <li key={line.id} className="flex justify-between gap-3">
                <span>
                  {line.name}
                  {line.sku ? ` · ${line.sku}` : ""}
                  <span className="block text-xs text-charcoal/50">
                    Sold {line.quantity} · returned {line.returned_quantity} · left {Math.max(0, line.quantity - line.returned_quantity)}
                  </span>
                </span>
                <span className="tabular-nums">{money(line.line_total_cents)}</span>
              </li>
            ))}
          </ul>
          <dl className="mt-3 space-y-1 text-sm">
            <div className="flex justify-between"><dt>Gross</dt><dd className="tabular-nums">{money(selected.gross_cents)}</dd></div>
            <div className="flex justify-between"><dt>Discount</dt><dd className="tabular-nums">{money(selected.discount_cents)}</dd></div>
            <div className="flex justify-between"><dt>Tax</dt><dd className="tabular-nums">{money(selected.tax_cents)}</dd></div>
            <div className="flex justify-between font-semibold"><dt>Total</dt><dd className="tabular-nums">{money(selected.total_cents)}</dd></div>
            <div className="flex justify-between"><dt>Refunded</dt><dd className="tabular-nums">{money(selected.refunded_cents)}</dd></div>
          </dl>
          {(history?.returns ?? []).filter((row) => row.original_sale_id === selected.id).length > 0 ? (
            <div className="mt-3 text-sm">
              <p className="font-medium">Returns</p>
              <ul className="mt-1 space-y-1">
                {history?.returns
                  .filter((row) => row.original_sale_id === selected.id)
                  .map((row) => (
                    <li key={row.id}>
                      {row.credit_note_number} · {money(row.total_refund_cents)}
                      {row.sync_status === "pending" ? " · waiting to sync" : ""}
                    </li>
                  ))}
              </ul>
            </div>
          ) : null}
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" className="modal-save" disabled={selected.status === "returned"} onClick={() => startReturn(selected)}>
              Return items
            </button>
            <button type="button" className="rounded-full border border-line px-4 py-2 text-sm" onClick={() => reprint(selected)}>
              Reprint receipt
            </button>
          </div>
        </article>
      ) : null}
    </div>
  );
}
