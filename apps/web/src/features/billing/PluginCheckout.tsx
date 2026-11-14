import { formatMoney, type MarketplaceItem } from "@ai-pos/shared-types";
import { AxizDatePicker, useLocale } from "@ai-pos/ui";
import { useEffect, useState } from "react";
import { ErrorNote, GhostButton, PrimaryButton } from "../../components/ui/Field";
import { ApiRequestError, apiGet, apiPost, apiUpload } from "../../lib/api";

interface PaymentMethod {
  code: string;
  display_name: string;
  category: string;
  available: boolean;
  reason: string;
  instructions: string;
  test_mode?: boolean;
}

interface Quote {
  currency: string;
  cycle_name: string;
  months: number;
  total_fils: number;
  lines: { label: string; amount_fils: number }[];
}

interface Started {
  id: string;
  invoice_id: string | null;
  status: string;
  reference: string;
  test_mode?: boolean;
  amount_fils: number;
  currency: string;
  bank: Record<string, string> | null;
  method_code: string;
}

export function PluginCheckout({
  item,
  onClose,
  onDone,
}: {
  item: MarketplaceItem;
  onClose: () => void;
  onDone: () => void;
}) {
  const { t } = useLocale();
  const [methods, setMethods] = useState<PaymentMethod[] | null>(null);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [method, setMethod] = useState("");
  const [started, setStarted] = useState<Started | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [date, setDate] = useState("");
  const [reference, setReference] = useState("");
  const [key] = useState(() => crypto.randomUUID());
  const [sandbox, setSandbox] = useState(false);
  const [scenario, setScenario] = useState("approved");

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      apiGet<PaymentMethod[]>("/api/v1/billing/payment-methods?purpose=PLUGIN_PURCHASE"),
      apiGet<Quote>(`/api/v1/billing/addons/${item.addon.code}/quote`),
      apiGet<{ sandbox: boolean }>("/api/v1/billing/payment-environment"),
    ])
      .then(([foundMethods, foundQuote, environment]) => {
        if (cancelled) return;
        setMethods(foundMethods);
        setQuote(foundQuote);
        setSandbox(environment.sandbox);
        const first = foundMethods.find((row) => row.available);
        setMethod(first?.code ?? "");
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(caught instanceof ApiRequestError ? caught.message : t("Could not open checkout."));
      });
    return () => {
      cancelled = true;
    };
  }, [item.addon.code, t]);

  const pay = async () => {
    setBusy(true);
    setError(null);
    try {
      const next = await apiPost<Started>("/api/v1/billing/payments", {
        purpose_type: "PLUGIN_PURCHASE",
        purpose_ref: item.addon.code,
        method_code: method,
        idempotency_key: key,
        scenario: chosen?.test_mode ? scenario : "",
      });
      setStarted(next);
      if (next.method_code !== "bank_transfer" && !next.test_mode) onDone();
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : t("Could not start the payment."));
    } finally {
      setBusy(false);
    }
  };

  const upload = async () => {
    if (started?.invoice_id == null || file === null || date === "") return;
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.set("invoice_id", started.invoice_id);
      form.set("amount_fils", String(started.amount_fils));
      form.set("transferred_on", date);
      form.set("idempotency_key", key);
      form.set("bank_reference", reference || started.reference);
      form.set("receipt", file);
      await apiUpload("/api/v1/billing/transfers", form);
      onDone();
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : t("Could not submit the payment proof."));
    } finally {
      setBusy(false);
    }
  };

  const chosen = methods?.find((row) => row.code === method) ?? null;

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-charcoal/40 p-4 sm:items-center" role="presentation">
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="plugin-checkout-title"
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-3xl border border-line bg-white p-5 text-charcoal dark:border-zinc-800 dark:bg-zinc-900 dark:text-white"
      >
        <h2 id="plugin-checkout-title" className="text-lg font-semibold">
          {t("Buy Now")}
        </h2>
        {sandbox ? (
          <p className="mt-2 rounded-2xl bg-amber-100 px-3 py-2 text-sm font-medium text-amber-950">
            TEST · {t("Test payments only. No real money will be charged.")}
          </p>
        ) : null}
        <p className="mt-1 text-sm text-charcoal/70 dark:text-white/70">{item.addon.name}</p>
        <p className="mt-2 text-sm text-charcoal/70 dark:text-white/70">{item.addon.listing?.short_description || item.addon.description}</p>
        {quote ? (
          <dl className="mt-4 grid gap-1 text-sm">
            <div className="flex justify-between gap-3">
              <dt>{t("Billing")}</dt>
              <dd>
                {quote.cycle_name} · {quote.months}
              </dd>
            </div>
            <div className="flex justify-between gap-3 font-semibold">
              <dt>{t("Total")}</dt>
              <dd className="tabular-nums">{formatMoney(quote.total_fils, quote.currency)}</dd>
            </div>
          </dl>
        ) : null}
        <ErrorNote message={error} />
        {started === null ? (
          <fieldset className="mt-4 grid gap-2">
            <legend className="text-sm font-medium">{t("Payment method")}</legend>
            {(methods ?? []).map((row) => (
              <label key={row.code} className="flex items-start gap-2 text-sm">
                <input
                  type="radio"
                  name="payment-method"
                  value={row.code}
                  checked={method === row.code}
                  disabled={!row.available}
                  onChange={() => setMethod(row.code)}
                />
                <span>
                  <span className="font-medium">{row.display_name}</span>
                  {row.available ? null : <span className="block text-charcoal/60 dark:text-white/60">{row.reason}</span>}
                </span>
              </label>
            ))}
            {chosen?.test_mode ? (
              <label className="grid gap-1 text-sm">
                {t("Sandbox scenario")}
                <select className="rounded-xl border border-line px-3 py-2 dark:bg-zinc-950" value={scenario} onChange={(event) => setScenario(event.target.value)}>
                  <option value="approved">Approved</option>
                  <option value="declined">Declined</option>
                  <option value="timeout">Timeout</option>
                  <option value="pending">Pending</option>
                </select>
              </label>
            ) : null}
          </fieldset>
        ) : started.method_code === "bank_transfer" && started.bank ? (
          <div className="mt-4 grid gap-2 text-sm">
            <p>
              {t("Reference")} <span className="font-semibold">{started.reference}</span>
            </p>
            <p>
              {started.bank.bank_name} · {started.bank.holder_name} · {started.bank.iban || started.bank.account_number}
            </p>
            <label className="grid gap-1">
              {t("Transfer date")}
              <AxizDatePicker
                required
                aria-label={t("Transfer date")}
                value={date}
                onChange={(event) => setDate(event.target.value)}
                className="h-10 w-full rounded-xl border border-line bg-white text-sm dark:bg-zinc-950"
              />
            </label>
            <label className="grid gap-1">
              {t("Bank reference")}
              <input className="rounded-xl border border-line px-3 py-2 dark:bg-zinc-950" value={reference} onChange={(event) => setReference(event.target.value)} />
            </label>
            <label className="grid gap-1">
              {t("Receipt")}
              <input
                type="file"
                accept="application/pdf,image/png,image/jpeg"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
            </label>
          </div>
        ) : (
          <p className="mt-4 text-sm">
            {started.status === "SANDBOX_APPROVED"
              ? t("TEST approved. This test result does not activate the plugin.")
              : started.status === "DECLINED"
                ? t("The test payment was declined. The plugin stays inactive.")
                : started.status === "SANDBOX_UNKNOWN"
                  ? t("The test payment timed out. It is not approved or declined.")
                  : t("This payment stays unpaid until it is verified.")}
          </p>
        )}
        <div className="mt-5 flex flex-wrap gap-2">
          {started === null ? (
            <PrimaryButton disabled={busy || chosen?.available !== true} onClick={() => void pay()}>
              {busy ? t("Please wait…") : t("Buy Now")}
            </PrimaryButton>
          ) : started.method_code === "bank_transfer" ? (
            <PrimaryButton disabled={busy || file === null || date === ""} onClick={() => void upload()}>
              {busy ? t("Please wait…") : t("Submit proof")}
            </PrimaryButton>
          ) : null}
          <GhostButton onClick={onClose}>{t("Close")}</GhostButton>
        </div>
      </section>
    </div>
  );
}
