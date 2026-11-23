import { formatMoney } from "@ai-pos/shared-types";
import { useEffect, useMemo, useState } from "react";
import { RetailRequestError, retailCall } from "../../lib/retailClient";
import { inTauri, openDocumentPdf } from "../../lib/tauri";
import { printReceipt } from "../printing/print";
import { shiftSaleReceipt } from "../printing/saleReceipt";
import { duplicateReceipt } from "./splitReceipts";

interface BillItem {
  description: string | null;
  quantity: number;
  unit_price_cents: number;
  tax_cents: number;
  line_total_cents: number;
}

interface BillTender {
  method: string;
  amount_cents: number;
}

interface Bill {
  id: string;
  invoice_number: string | null;
  client_sale_id: string;
  created_at: string;
  customer_name: string | null;
  status: string;
  payment_status: string;
  payment_method: string;
  subtotal_cents: number;
  tax_cents: number;
  total_cents: number;
  amount_paid_cents: number;
  due_balance_cents: number;
  currency: string;
  items: BillItem[];
  tenders: BillTender[];
}

const paymentLabel: Record<string, string> = {
  PAID: "Paid",
  PARTIAL: "Partially Paid",
  ON_ACCOUNT_UNPAID: "Unpaid",
};

function labelStatus(value: string): string {
  return paymentLabel[value] ?? value;
}

function startOf(day: Date): Date {
  return new Date(day.getFullYear(), day.getMonth(), day.getDate());
}

function inRange(iso: string, preset: string): boolean {
  if (preset === "all") return true;
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return false;
  const today = startOf(new Date());
  if (preset === "today") return when >= today;
  if (preset === "yesterday") {
    const yesterday = new Date(today);
    yesterday.setDate(today.getDate() - 1);
    return when >= yesterday && when < today;
  }
  if (preset === "week") {
    const week = new Date(today);
    week.setDate(today.getDate() - 6);
    return when >= week;
  }
  const month = new Date(today.getFullYear(), today.getMonth(), 1);
  return when >= month;
}

export function BillHistoryPage() {
  const [rows, setRows] = useState<Bill[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [preset, setPreset] = useState("all");
  const [pay, setPay] = useState("");
  const [selected, setSelected] = useState<Bill | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void retailCall<Bill[]>("GET", "/api/v1/sales?limit=200")
      .then((value) => {
        if (!cancelled) setRows(value);
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        const offline = caught instanceof RetailRequestError && caught.offline;
        setError(offline ? "Bill history needs a connection. This register does not keep a complete tenant bill archive offline." : caught instanceof Error ? caught.message : "Bills could not be loaded.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return rows.filter((row) => {
      if (!inRange(row.created_at, preset)) return false;
      if (pay !== "" && row.payment_status !== pay && row.payment_method !== pay) return false;
      if (needle === "") return true;
      const invoice = (row.invoice_number ?? row.client_sale_id).toLowerCase();
      return invoice.includes(needle) || (row.customer_name ?? "").toLowerCase().includes(needle);
    });
  }, [pay, preset, query, rows]);

  async function reprint(bill: Bill) {
    const doc = duplicateReceipt(
      shiftSaleReceipt({
        number: bill.invoice_number ?? bill.client_sale_id.slice(0, 8).toUpperCase(),
        issuedAt: bill.created_at,
        cashier: "Recorded cashier",
        customer: bill.customer_name,
        lines: bill.items.map((item) => ({
          name: item.description?.trim() || "Item",
          quantity: item.quantity,
          unitCents: item.unit_price_cents,
          lineCents: item.line_total_cents,
        })),
        subtotalCents: bill.subtotal_cents,
        taxCents: bill.tax_cents,
        totalCents: bill.total_cents,
        tenders: bill.tenders.map((tender) => ({ label: tender.method, amountCents: tender.amount_cents })),
        currency: bill.currency,
      }),
    );
    const printed = await printReceipt(doc, { kickDrawer: false, manual: true });
    setNotice(printed.message ? `The bill is unchanged. Printer: ${printed.message}` : "Duplicate receipt sent. No new sale or payment was created.");
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 p-4">
      <header>
        <h1 className="text-xl font-semibold">Bill History</h1>
        <p className="text-sm text-zinc-500">Latest completed bills for this sign-in. A branch user sees that branch only. Prices are the saved sale, not the current menu.</p>
      </header>
      <div className="flex flex-wrap gap-2">
        <input className="h-10 min-w-48 flex-1 rounded-xl border border-zinc-200 px-3 text-sm" placeholder="Invoice or customer" value={query} onChange={(event) => setQuery(event.target.value)} />
        <select className="h-10 rounded-xl border border-zinc-200 px-2 text-sm" value={preset} onChange={(event) => setPreset(event.target.value)}>
          <option value="all">All loaded</option>
          <option value="today">Today</option>
          <option value="yesterday">Yesterday</option>
          <option value="week">This week</option>
          <option value="month">This month</option>
        </select>
        <select className="h-10 rounded-xl border border-zinc-200 px-2 text-sm" value={pay} onChange={(event) => setPay(event.target.value)}>
          <option value="">Any payment</option>
          <option value="PAID">Paid</option>
          <option value="PARTIAL">Partially Paid</option>
          <option value="ON_ACCOUNT_UNPAID">Unpaid</option>
        </select>
      </div>
      {notice ? <p className="text-sm text-zinc-700">{notice}</p> : null}
      {error ? <p className="text-sm text-red-700">{error}</p> : null}
      {loading ? <p className="text-sm">Loading bills…</p> : null}
      <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[minmax(0,1.4fr)_minmax(18rem,1fr)]">
        <div className="min-h-0 overflow-auto rounded-2xl border border-zinc-200">
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 bg-zinc-50 text-xs uppercase text-zinc-500">
              <tr>
                <th className="px-3 py-2">Invoice</th>
                <th className="px-3 py-2">When</th>
                <th className="px-3 py-2">Customer</th>
                <th className="px-3 py-2">Total</th>
                <th className="px-3 py-2">Due</th>
                <th className="px-3 py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((row) => (
                <tr key={row.id} className="cursor-pointer border-t border-zinc-100 hover:bg-zinc-50" onClick={() => setSelected(row)}>
                  <td className="px-3 py-2 font-medium">{row.invoice_number ?? row.client_sale_id.slice(0, 8).toUpperCase()}</td>
                  <td className="px-3 py-2">{new Date(row.created_at).toLocaleString()}</td>
                  <td className="px-3 py-2">{row.customer_name ?? "—"}</td>
                  <td className="px-3 py-2 tabular-nums">{formatMoney(row.total_cents, row.currency)}</td>
                  <td className="px-3 py-2 tabular-nums">{formatMoney(row.due_balance_cents, row.currency)}</td>
                  <td className="px-3 py-2">{labelStatus(row.payment_status)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {selected ? (
          <aside className="overflow-auto rounded-2xl border border-zinc-200 p-4">
            <h2 className="text-lg font-semibold">{selected.invoice_number ?? "Bill"}</h2>
            <p className={`mt-1 text-sm font-semibold ${selected.due_balance_cents > 0 ? "text-amber-700" : "text-emerald-700"}`}>
              {labelStatus(selected.payment_status)}
              {selected.due_balance_cents > 0 ? ` · Due ${formatMoney(selected.due_balance_cents, selected.currency)}` : ""}
            </p>
            <p className="mt-2 text-sm text-zinc-600">{selected.customer_name ?? "No customer"} · {selected.status} · {selected.payment_method}</p>
            <ul className="mt-3 space-y-1 text-sm">
              {selected.items.map((item, index) => (
                <li key={index} className="flex justify-between gap-2">
                  <span>{item.quantity} × {item.description?.trim() || "Item"}</span>
                  <span className="tabular-nums">{formatMoney(item.line_total_cents, selected.currency)}</span>
                </li>
              ))}
            </ul>
            <dl className="mt-3 space-y-1 text-sm">
              <div className="flex justify-between"><dt>Subtotal</dt><dd className="tabular-nums">{formatMoney(selected.subtotal_cents, selected.currency)}</dd></div>
              <div className="flex justify-between"><dt>Tax</dt><dd className="tabular-nums">{formatMoney(selected.tax_cents, selected.currency)}</dd></div>
              <div className="flex justify-between font-semibold"><dt>Total</dt><dd className="tabular-nums">{formatMoney(selected.total_cents, selected.currency)}</dd></div>
              <div className="flex justify-between"><dt>Paid</dt><dd className="tabular-nums">{formatMoney(selected.amount_paid_cents, selected.currency)}</dd></div>
            </dl>
            <div className="mt-4 flex flex-wrap gap-2">
              <button type="button" className="h-10 rounded-full bg-zinc-900 px-4 text-sm font-semibold text-white" onClick={() => void reprint(selected)}>Print receipt</button>
              <button
                type="button"
                className="h-10 rounded-full border border-zinc-300 px-4 text-sm font-semibold"
                onClick={() => {
                  if (!inTauri()) {
                    setNotice("PDF export runs on the register and uses the saved invoice.");
                    return;
                  }
                  void openDocumentPdf("invoice", selected.id, selected.invoice_number ?? "invoice").then(
                    () => setNotice("Invoice PDF opened from the saved sale."),
                    (caught: unknown) => setNotice(caught instanceof Error ? caught.message : "The PDF could not be opened. The bill is unchanged."),
                  );
                }}
              >
                Download PDF
              </button>
            </div>
          </aside>
        ) : (
          <p className="text-sm text-zinc-500">Select a bill to see its saved lines, tax, and balance.</p>
        )}
      </div>
    </div>
  );
}
