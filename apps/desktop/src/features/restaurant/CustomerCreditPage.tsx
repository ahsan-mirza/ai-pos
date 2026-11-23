import { Capability, formatMoney } from "@ai-pos/shared-types";
import { useEffect, useState, type FormEvent } from "react";
import { useCapabilities } from "../../lib/capabilities";
import { RetailRequestError, retailCall } from "../../lib/retailClient";

interface CustomerRow {
  id: string;
  code: string;
  name: string;
  phone: string | null;
  email: string | null;
  customer_type: string;
  is_active: boolean;
  current_balance_cents: number;
  credit_limit_cents: number;
  available_credit_cents: number;
}

interface LedgerEntry {
  id: string;
  entry_type: string;
  amount_cents: number;
  balance_after_cents: number;
  invoice: string | null;
  method: string | null;
  note: string;
  created_at: string;
}

interface OpenInvoice {
  invoice: string;
  total_cents: number;
  amount_paid_cents: number;
  due_balance_cents: number;
  payment_status: string;
}

interface Statement {
  currency: string;
  total_invoiced_cents: number;
  total_paid_cents: number;
  entries: LedgerEntry[];
  open_invoices: OpenInvoice[];
  customer: CustomerRow;
}

function problem(caught: unknown, fallback: string): string {
  if (caught instanceof RetailRequestError && caught.offline) return "Customer credit needs a connection. No payment was recorded.";
  return caught instanceof Error ? caught.message : fallback;
}

export function CustomerCreditPage() {
  const { enabled } = useCapabilities();
  const creditOn = enabled.has(Capability.B2bCredit);
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState<CustomerRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<CustomerRow | null>(null);
  const [statement, setStatement] = useState<Statement | null>(null);
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState<"cash" | "card" | "transfer">("cash");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    const handle = window.setTimeout(() => {
      void retailCall<CustomerRow[]>("GET", `/api/v1/customers?limit=100&q=${encodeURIComponent(query)}`)
        .then(setRows)
        .catch((caught: unknown) => setError(problem(caught, "Customers could not be loaded.")));
    }, 250);
    return () => window.clearTimeout(handle);
  }, [query]);

  async function open(customer: CustomerRow) {
    setSelected(customer);
    setStatement(null);
    setNotice(null);
    try {
      setStatement(await retailCall<Statement>("GET", `/api/v1/customers/${customer.id}/statement`));
    } catch (caught) {
      setError(problem(caught, "The statement could not be loaded."));
    }
  }

  async function receive(event: FormEvent) {
    event.preventDefault();
    if (!selected || !creditOn || busy) return;
    const cents = Math.round(Number(amount) * 100);
    if (!Number.isFinite(cents) || cents < 1) {
      setNotice("Enter the amount received.");
      return;
    }
    setBusy(true);
    setNotice(null);
    try {
      await retailCall("POST", `/api/v1/customers/${selected.id}/payments`, {
        amount_cents: cents,
        method,
        reference: "",
        note,
      });
      setAmount("");
      setNote("");
      const next = await retailCall<Statement>("GET", `/api/v1/customers/${selected.id}/statement`);
      setStatement(next);
      setNotice("Payment recorded on the customer ledger and applied to the oldest open invoice.");
    } catch (caught) {
      setNotice(problem(caught, "The payment was not recorded."));
    } finally {
      setBusy(false);
    }
  }

  const currency = statement?.currency ?? "AED";

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 p-4">
      <header>
        <h1 className="text-xl font-semibold">Customers</h1>
        <p className="text-sm text-zinc-500">Balances come from the customer ledger. A repayment adds a payment entry. It does not erase the original invoice.</p>
      </header>
      {!creditOn ? <p className="text-sm text-amber-800">Customer account credit is not enabled for this business. Repayment stays closed until that module is turned on.</p> : null}
      <input className="h-10 max-w-md rounded-xl border border-zinc-200 px-3 text-sm" placeholder="Name, mobile, or customer number" value={query} onChange={(event) => setQuery(event.target.value)} />
      {error ? <p className="text-sm text-red-700">{error}</p> : null}
      <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(20rem,1.1fr)]">
        <ul className="min-h-0 overflow-auto rounded-2xl border border-zinc-200">
          {rows.map((row) => (
            <li key={row.id}>
              <button type="button" className="flex w-full items-center justify-between gap-3 border-b border-zinc-100 px-3 py-2 text-left text-sm hover:bg-zinc-50" onClick={() => void open(row)}>
                <span>
                  <span className="font-medium">{row.name}</span>
                  <span className="mt-0.5 block text-xs text-zinc-500">{row.code} · {row.phone ?? "No mobile"} · {row.is_active ? "Active" : "Inactive"}</span>
                </span>
                <span className={`tabular-nums ${row.current_balance_cents > 0 ? "font-semibold text-amber-800" : "text-zinc-600"}`}>
                  {formatMoney(row.current_balance_cents, currency)}
                </span>
              </button>
            </li>
          ))}
        </ul>
        {statement && selected ? (
          <section className="min-h-0 overflow-auto rounded-2xl border border-zinc-200 p-4">
            <h2 className="text-lg font-semibold">{statement.customer.name}</h2>
            <p className="text-sm text-zinc-600">{statement.customer.email ?? "No email"} · {statement.customer.customer_type}</p>
            <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
              <div><dt className="text-zinc-500">Purchased</dt><dd className="font-semibold tabular-nums">{formatMoney(statement.total_invoiced_cents, currency)}</dd></div>
              <div><dt className="text-zinc-500">Paid</dt><dd className="font-semibold tabular-nums">{formatMoney(statement.total_paid_cents, currency)}</dd></div>
              <div><dt className="text-zinc-500">Outstanding</dt><dd className="font-semibold tabular-nums text-amber-800">{formatMoney(statement.customer.current_balance_cents, currency)}</dd></div>
              <div><dt className="text-zinc-500">Credit left</dt><dd className="tabular-nums">{formatMoney(statement.customer.available_credit_cents, currency)}</dd></div>
            </dl>
            <h3 className="mt-4 text-sm font-semibold">Open invoices</h3>
            <ul className="mt-1 space-y-1 text-sm">
              {statement.open_invoices.map((invoice) => (
                <li key={invoice.invoice} className="flex justify-between gap-2">
                  <span>{invoice.invoice} · {invoice.payment_status}</span>
                  <span className="tabular-nums">Due {formatMoney(invoice.due_balance_cents, currency)}</span>
                </li>
              ))}
              {statement.open_invoices.length === 0 ? <li className="text-zinc-500">No open invoice.</li> : null}
            </ul>
            <h3 className="mt-4 text-sm font-semibold">Ledger</h3>
            <ul className="mt-1 max-h-48 space-y-1 overflow-auto text-sm">
              {statement.entries.map((entry) => (
                <li key={entry.id} className="flex justify-between gap-2">
                  <span>{new Date(entry.created_at).toLocaleDateString()} · {entry.entry_type} {entry.invoice ?? ""}</span>
                  <span className="tabular-nums">{formatMoney(entry.amount_cents, currency)}</span>
                </li>
              ))}
            </ul>
            {creditOn ? (
              <form className="mt-4 space-y-2" onSubmit={(event) => void receive(event)}>
                <h3 className="text-sm font-semibold">Receive credit payment</h3>
                <p className="text-xs text-zinc-500">Applied to the oldest open invoice. The original credit entry stays on the ledger.</p>
                <div className="flex flex-wrap gap-2">
                  <input className="h-10 w-32 rounded-xl border border-zinc-200 px-3 text-sm" inputMode="decimal" placeholder="0.00" value={amount} onChange={(event) => setAmount(event.target.value)} />
                  <select className="h-10 rounded-xl border border-zinc-200 px-2 text-sm" value={method} onChange={(event) => setMethod(event.target.value as "cash" | "card" | "transfer")}>
                    <option value="cash">Cash</option>
                    <option value="card">Card</option>
                    <option value="transfer">Transfer</option>
                  </select>
                  <input className="h-10 min-w-40 flex-1 rounded-xl border border-zinc-200 px-3 text-sm" placeholder="Note" value={note} onChange={(event) => setNote(event.target.value)} />
                </div>
                <button type="submit" disabled={busy} className="h-10 rounded-full bg-zinc-900 px-4 text-sm font-semibold text-white disabled:opacity-50">Receive payment</button>
              </form>
            ) : null}
            {notice ? <p className="mt-2 text-sm">{notice}</p> : null}
          </section>
        ) : (
          <p className="text-sm text-zinc-500">Select a customer to see the ledger and open invoices.</p>
        )}
      </div>
    </div>
  );
}
