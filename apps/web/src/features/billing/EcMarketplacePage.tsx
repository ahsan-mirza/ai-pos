import { formatMoney, type Store } from "@ai-pos/shared-types";
import { useLocale } from "@ai-pos/ui";
import { Cable, ShieldCheck, TabletSmartphone, Wrench } from "lucide-react";
import { useEffect, useState } from "react";
import { ErrorNote, PrimaryButton } from "../../components/ui/Field";
import { apiGet, apiPost, apiUpload } from "../../lib/api";
import { EcDevicesPanel } from "./EcDevicesPanel";
import { storesApi } from "../users/api";

interface EcMachine {
  id: string;
  name: string;
  model: string;
  manufacturer: string;
  device_type: string;
  purchase_fils: number | null;
  installation_fils: number;
  warranty_months: number;
  currency: string;
  stock_qty: number | null;
  specifications: Record<string, string>;
  description: string;
}

interface QuoteLine {
  label: string;
  amount_fils: number;
}

interface Quote {
  currency: string;
  one_time_fils: number;
  recurring_fils: number;
  total_fils: number;
  lines: QuoteLine[];
}

interface Checkout {
  checkout_id: string;
  quote: Quote;
  bank: Record<string, string> | null;
}

interface Readiness {
  state: string;
  production_ready: boolean;
  blockers: string[];
  reason: string;
}

interface HardwareOrder {
  id: string;
  reference: string;
  payment_status: string;
  fulfillment_status: string;
  one_time_fils: number;
  currency: string;
}

function money(fils: number | null | undefined, currency: string): string {
  return formatMoney(fils ?? 0, currency || "AED");
}

/** Terminals from the existing hardware catalogue. A purchase does not change the package. */
export function EcMarketplacePage() {
  const { t } = useLocale();
  const [machines, setMachines] = useState<EcMachine[] | null>(null);
  const [orders, setOrders] = useState<HardwareOrder[]>([]);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [stores, setStores] = useState<Store[]>([]);
  const [storeId, setStoreId] = useState("");
  const [kind, setKind] = useState<"all" | "WIRED" | "ANDROID">("all");
  const [compare, setCompare] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [quote, setQuote] = useState<Quote | null>(null);
  const [checkout, setCheckout] = useState<Checkout | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => {
    setError(null);
    void Promise.all([
      apiGet<EcMachine[]>("/api/v1/billing/ec-machines"),
      apiGet<HardwareOrder[]>("/api/v1/billing/ec-orders"),
      apiGet<Readiness>("/api/v1/payments/card-readiness"),
      storesApi.list(),
    ])
      .then(([catalog, placed, ready, branches]) => {
        setMachines(catalog);
        setOrders(placed);
        setReadiness(ready);
        setStores(branches);
        setStoreId((current) => current || branches[0]?.id || "");
      })
      .catch((caught: unknown) => setError(caught instanceof Error ? caught.message : t("Could not load this list")));
  };

  useEffect(load, [t]);

  const visible = (machines ?? []).filter((row) => kind === "all" || row.device_type === kind);
  const chosen = visible.filter((row) => compare.includes(row.id)).slice(0, 3);

  const buy = async (item: EcMachine) => {
    if (!storeId) {
      setError(t("Choose a branch"));
      return;
    }
    setBusy(true);
    setError(null);
    setCheckout(null);
    try {
      const priced = await apiPost<Quote>("/api/v1/billing/ec-quote", {
        hardware: [{ item_id: item.id, quantity: 1, mode: "purchase", store_id: storeId }],
      });
      setSelectedId(item.id);
      setQuote(priced);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : t("Could not save this."));
    } finally {
      setBusy(false);
    }
  };

  const place = async (itemId: string) => {
    setBusy(true);
    setError(null);
    try {
      const placed = await apiPost<Checkout>("/api/v1/billing/ec-checkout", {
        hardware: [{ item_id: itemId, quantity: 1, mode: "purchase", store_id: storeId }],
      });
      setCheckout(placed);
      setQuote(placed.quote);
      load();
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : t("Could not save this."));
    } finally {
      setBusy(false);
    }
  };

  const submitProof = async (file: File) => {
    if (!checkout) return;
    const form = new FormData();
    form.set("invoice_id", checkout.checkout_id);
    form.set("amount_fils", String(checkout.quote.total_fils));
    form.set("transferred_on", new Date().toISOString().slice(0, 10));
    form.set("idempotency_key", checkout.checkout_id);
    form.set("receipt", file);
    setBusy(true);
    try {
      await apiUpload("/api/v1/billing/transfers", form);
      setError(null);
      load();
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : t("Could not save this."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid min-w-0 gap-6">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight text-charcoal dark:text-white">{t("EC Terminal Marketplace")}</h1>
        <p className="mt-1 max-w-2xl text-sm text-charcoal/70 dark:text-white/70">
          {t("Choose the payment terminal that fits your checkout setup.")}
        </p>
      </header>
      <ErrorNote message={error} />
      <section className="rounded-3xl border border-line bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
        <h2 className="text-lg font-semibold text-charcoal dark:text-white">{t("Pay by Card Readiness")}</h2>
        <p className="mt-1 text-sm text-charcoal/70 dark:text-white/70">
          {readiness ? t(readiness.reason) : t("Loading")}
        </p>
        <p className="mt-2 text-sm text-charcoal/70 dark:text-white/70">
          {t("Pay by Card software access requires an eligible subscription. The terminal is purchased separately.")}
        </p>
        {readiness?.production_ready ? null : (
          <p className="mt-2 text-sm font-medium text-charcoal dark:text-white">{t("Production payments are not available.")}</p>
        )}
      </section>
      <div className="flex flex-wrap items-end gap-3">
        {(["all", "WIRED", "ANDROID"] as const).map((value) => (
          <button
            key={value}
            type="button"
            onClick={() => setKind(value)}
            className={`rounded-full px-4 py-2 text-sm font-semibold ${kind === value ? "bg-accent text-white" : "bg-white text-charcoal dark:bg-zinc-900 dark:text-white"}`}
          >
            {value === "all" ? t("All") : value === "WIRED" ? t("Wired") : t("Android")}
          </button>
        ))}
        <label className="text-sm text-charcoal dark:text-white">
          {t("Branch")}
          <select className="ms-2 rounded-lg border border-line bg-white px-2 py-1 dark:border-zinc-700 dark:bg-zinc-900" value={storeId} onChange={(event) => setStoreId(event.target.value)}>
            {stores.map((store) => (
              <option key={store.id} value={store.id}>{store.name}</option>
            ))}
          </select>
        </label>
      </div>
      {machines === null ? <p className="text-sm text-charcoal/60">{t("Loading")}</p> : null}
      {machines && visible.length === 0 ? (
        <p className="text-sm text-charcoal/70 dark:text-white/70">{t("No EC machines are published yet.")}</p>
      ) : null}
      <div className="grid gap-4 md:grid-cols-2">
        {visible.map((item) => (
          <article key={item.id} className="rounded-3xl border border-line bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
            <div className="flex items-center gap-2 text-sm font-semibold text-charcoal dark:text-white">
              {item.device_type === "ANDROID" ? <TabletSmartphone size={16} aria-hidden="true" /> : <Cable size={16} aria-hidden="true" />}
              {item.device_type === "ANDROID" ? t("Android") : t("Wired")}
            </div>
            <h2 className="mt-2 text-xl font-semibold text-charcoal dark:text-white">{item.name}</h2>
            <p className="text-sm text-charcoal/60 dark:text-white/60">{[item.manufacturer, item.model].filter(Boolean).join(" · ")}</p>
            <p className="mt-3 text-lg font-semibold tabular-nums text-charcoal dark:text-white" dir="ltr">{money(item.purchase_fils, item.currency)}</p>
            <ul className="mt-3 space-y-1 text-sm text-charcoal/70 dark:text-white/70">
              <li className="flex items-center gap-2"><ShieldCheck size={14} aria-hidden="true" />{t("Warranty")}: {item.warranty_months}</li>
              <li className="flex items-center gap-2"><Wrench size={14} aria-hidden="true" />{t("Installation")}: <span dir="ltr">{money(item.installation_fils, item.currency)}</span></li>
              <li>{item.stock_qty == null ? t("Stock is not tracked") : t("Available") + `: ${item.stock_qty}`}</li>
            </ul>
            <div className="mt-4 flex flex-wrap gap-2">
              <PrimaryButton disabled={busy} onClick={() => void buy(item)}>{t("Buy machine")}</PrimaryButton>
              <button
                type="button"
                className="rounded-full border border-line px-4 py-2 text-sm font-semibold dark:border-zinc-700"
                onClick={() => setCompare((current) => current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id].slice(-3))}
              >
                {t("Compare")}
              </button>
            </div>
          </article>
        ))}
      </div>
      {chosen.length > 1 ? (
        <section className="overflow-x-auto rounded-3xl border border-line bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
          <h2 className="mb-3 text-lg font-semibold text-charcoal dark:text-white">{t("Compare")}</h2>
          <table className="w-full min-w-[32rem] text-sm">
            <thead>
              <tr>{chosen.map((item) => <th key={item.id} className="px-2 py-2 text-start">{item.name}</th>)}</tr>
            </thead>
            <tbody>
              <tr>{chosen.map((item) => <td key={item.id} className="px-2 py-2">{item.device_type === "ANDROID" ? t("Android") : t("Wired")}</td>)}</tr>
              <tr>{chosen.map((item) => <td key={item.id} className="px-2 py-2" dir="ltr">{money(item.purchase_fils, item.currency)}</td>)}</tr>
              <tr>{chosen.map((item) => <td key={item.id} className="px-2 py-2">{item.warranty_months}</td>)}</tr>
              <tr>{chosen.map((item) => <td key={item.id} className="px-2 py-2">{item.specifications.connectivity || "—"}</td>)}</tr>
            </tbody>
          </table>
        </section>
      ) : null}
      {quote ? (
        <section className="rounded-3xl border border-line bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
          <h2 className="text-lg font-semibold text-charcoal dark:text-white">{t("Checkout summary")}</h2>
          <ul className="mt-2 space-y-1 text-sm">
            {quote.lines.map((line) => (
              <li key={line.label} className="flex justify-between gap-4">
                <span>{line.label}</span>
                <span dir="ltr">{money(line.amount_fils, quote.currency)}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 font-semibold" dir="ltr">{t("Total")} {money(quote.total_fils, quote.currency)}</p>
          <p className="mt-1 text-sm text-charcoal/60">{t("Creating the order does not mark it paid.")}</p>
          {checkout ? (
            <div className="mt-3 text-sm">
              <p>{t("Payment is pending until the transfer is verified.")}</p>
              {checkout.bank ? <p className="mt-1" dir="ltr">{checkout.bank.iban || checkout.bank.account_number}</p> : null}
              <label className="mt-3 block">
                {t("Upload the transfer receipt")}
                <input className="mt-1 block" type="file" onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void submitProof(file);
                }} />
              </label>
            </div>
          ) : (
            <PrimaryButton className="mt-3" disabled={busy || !selectedId} onClick={() => void place(selectedId)}>{t("Place order")}</PrimaryButton>
          )}
        </section>
      ) : null}
      <EcDevicesPanel />
      <section>
        <h2 className="text-lg font-semibold text-charcoal dark:text-white">{t("Your terminal orders")}</h2>
        {orders.length === 0 ? <p className="mt-2 text-sm text-charcoal/60">{t("No terminal orders yet.")}</p> : (
          <ul className="mt-2 space-y-2 text-sm">
            {orders.map((order) => (
              <li key={order.id} className="rounded-2xl border border-line bg-white px-4 py-3 dark:border-zinc-800 dark:bg-zinc-900">
                <span dir="ltr">{order.reference}</span>
                {" · "}
                {order.payment_status}
                {" · "}
                {order.fulfillment_status}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
