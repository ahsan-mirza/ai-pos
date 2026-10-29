import { formatMoney, type ProductUpsert } from "@ai-pos/shared-types";
import { useState } from "react";
import { ui } from "../../components/shell/tokens";
import { retailCall, RetailRequestError } from "../../lib/retailClient";

const field = `mt-1 h-11 w-full rounded-xl px-3 ${ui.input}`;

interface CustomerPick {
  id: string;
  name: string;
  phone: string | null;
}

interface Quote {
  days: number;
  rental_net_cents: number;
  tax_cents: number;
  deposit_cents: number;
  total_due_cents: number;
  currency: string;
  available: number;
}

interface Created {
  reference: string;
}

export function RentModal({
  product,
  storeId,
  onClose,
  onBooked,
}: {
  product: ProductUpsert;
  storeId: string;
  onClose: () => void;
  onBooked: (reference: string) => void;
}) {
  const today = new Date().toISOString().slice(0, 10);
  const [start, setStart] = useState(today);
  const [end, setEnd] = useState(today);
  const [query, setQuery] = useState("");
  const [customers, setCustomers] = useState<CustomerPick[]>([]);
  const [customerId, setCustomerId] = useState("");
  const [quote, setQuote] = useState<Quote | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function findCustomers() {
    setMessage(null);
    try {
      setCustomers(await retailCall<CustomerPick[]>("GET", `/api/v1/rentals/customers?q=${encodeURIComponent(query.trim())}`));
    } catch (caught) {
      setMessage(caught instanceof RetailRequestError && caught.offline
        ? "Rental booking needs a connection to the server. Selling this item is still available."
        : caught instanceof Error ? caught.message : "Customer search failed.");
    }
  }

  async function price() {
    setMessage(null);
    const path =
      `/api/v1/rentals/quote?product_id=${product.id}&store_id=${storeId}` +
      `&start_date=${start}&return_date=${end}&quantity=1`;
    try {
      setQuote(await retailCall<Quote>("GET", path));
    } catch (caught) {
      setQuote(null);
      setMessage(caught instanceof RetailRequestError && caught.offline
        ? "Availability is confirmed on the server. Connect this register before booking."
        : caught instanceof Error ? caught.message : "This item is not available for those dates.");
    }
  }

  async function book() {
    if (!quote || !customerId) {
      setMessage("Choose a customer and check the dates first.");
      return;
    }
    setSaving(true);
    setMessage(null);
    try {
      const created = await retailCall<Created>("POST", "/api/v1/rentals", {
        client_request_id: crypto.randomUUID(),
        customer_id: customerId,
        store_id: storeId,
        product_id: product.id,
        start_date: start,
        return_date: end,
        quantity: 1,
        pay_charge_cents: quote.total_due_cents,
        pay_deposit_cents: quote.deposit_cents,
      });
      onBooked(created.reference);
    } catch (caught) {
      setMessage(caught instanceof RetailRequestError && caught.offline
        ? "The booking was not confirmed. Try again when the register is online. No charge was stored on this register."
        : caught instanceof Error ? caught.message : "Booking was not confirmed.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-black/40 p-4 sm:items-center">
      <form
        className="w-full max-w-lg rounded-3xl bg-white p-6 text-zinc-900 shadow-xl dark:bg-zinc-900 dark:text-white"
        onSubmit={(event) => {
          event.preventDefault();
          void book();
        }}
      >
        <h2 className="text-lg font-semibold">Rent {product.name}</h2>
        <p className="mt-1 text-sm text-zinc-500">The server confirms the dates. A deposit is held apart from the rental charge.</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <label className="text-sm">Start<input className={field} type="date" value={start} onChange={(event) => setStart(event.target.value)} /></label>
          <label className="text-sm">Return<input className={field} type="date" value={end} onChange={(event) => setEnd(event.target.value)} /></label>
        </div>
        <div className="mt-3 flex gap-2">
          <input className={field} value={query} placeholder="Customer name or phone" onChange={(event) => setQuery(event.target.value)} />
          <button type="button" className={`${ui.secondaryAction} h-11 px-4`} onClick={() => void findCustomers()}>Find</button>
        </div>
        <ul className="mt-2 max-h-28 space-y-1 overflow-auto text-sm">
          {customers.map((customer) => (
            <li key={customer.id}>
              <button type="button" className={customerId === customer.id ? "font-semibold text-primary" : ""} onClick={() => setCustomerId(customer.id)}>
                {customer.name}{customer.phone ? ` · ${customer.phone}` : ""}
              </button>
            </li>
          ))}
        </ul>
        <div className="mt-4 flex flex-wrap gap-2">
          <button type="button" className={`${ui.secondaryAction} h-11 px-4`} onClick={() => void price()}>Check availability</button>
          <button type="button" className={`${ui.secondaryAction} h-11 px-4`} onClick={onClose}>Close</button>
          <button type="submit" className={`${ui.primaryAction} h-11`} disabled={saving || !quote}>{saving ? "Booking…" : "Confirm rental"}</button>
        </div>
        {quote ? (
          <p className="mt-3 text-sm">
            {quote.days} days · charge {formatMoney(quote.total_due_cents, quote.currency)} · deposit {formatMoney(quote.deposit_cents, quote.currency)} · {quote.available} available
          </p>
        ) : null}
        {message ? <p className="mt-3 text-sm text-danger">{message}</p> : null}
      </form>
    </div>
  );
}
