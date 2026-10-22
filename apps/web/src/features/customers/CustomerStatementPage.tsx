import {
  Capability,
  PAYMENT_TERMS_LABELS,
  PRICE_TIER_LABELS,
  formatMoney,
  type CustomerStatement,
  type LedgerEntryType,
} from "@ai-pos/shared-types";
import { ArrowLeft, Banknote, Gift, Printer, Send, SquarePen } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ErrorNote, GhostButton, PrimaryButton } from "../../components/ui/Field";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { Toast } from "../../components/ui/Toast";
import { apiGet } from "../../lib/api";
import { useCapability } from "../../lib/capabilities";
import { CreditRiskCard } from "./CreditRiskCard";
import { CustomerFormModal } from "./CustomerFormModal";
import { ReceivePaymentModal } from "./ReceivePaymentModal";
import { customersApi, message, shortDate } from "./api";

type EntryFilter = "all" | LedgerEntryType;

const entryOptions = [
  { value: "all", label: "All activity" },
  { value: "INVOICE", label: "Invoices" },
  { value: "PAYMENT", label: "Payments" },
  { value: "ADJUSTMENT", label: "Adjustments" },
] as const;

const entryLabels: Record<LedgerEntryType, string> = {
  INVOICE: "Invoice",
  PAYMENT: "Payment",
  ADJUSTMENT: "Adjustment",
};

export function CustomerStatementPage() {
  const { customerId = "" } = useParams();
  const [statement, setStatement] = useState<CustomerStatement | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<EntryFilter>("all");
  const [dialog, setDialog] = useState<"payment" | "edit" | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);
  const creditModule = useCapability(Capability.B2bCredit);

  const load = useCallback(async () => {
    try {
      setStatement(await customersApi.statement(customerId));
      setError(null);
    } catch (caught) {
      setError(message(caught, "Could not load the statement."));
    }
  }, [customerId]);

  useEffect(() => {
    void load();
  }, [load]);

  const entries = useMemo(() => {
    const rows = statement?.entries ?? [];
    return [...(filter === "all" ? rows : rows.filter((row) => row.entry_type === filter))].reverse();
  }, [statement, filter]);

  if (statement === null) {
    return (
      <section className="rounded-card border border-line bg-white p-8">
        <Link to="/customers" className="inline-flex items-center gap-2 text-sm font-semibold hover:text-accent">
          <ArrowLeft size={16} aria-hidden="true" /> Customers
        </Link>
        {error ? <ErrorNote message={error} /> : <p className="mt-4 text-sm text-charcoal/60">Loading statement…</p>}
      </section>
    );
  }

  const { customer, currency, aging } = statement;
  const wholesale = customer.customer_type === "WHOLESALE";
  const used = customer.credit_limit_cents > 0 ? Math.min(100, Math.round((customer.current_balance_cents / customer.credit_limit_cents) * 100)) : 0;
  const buckets = [
    { label: "Current", value: aging.current, alert: false },
    { label: "1–30 days", value: aging.days_1_30, alert: aging.days_1_30 > 0 },
    { label: "31–60 days", value: aging.days_31_60, alert: aging.days_31_60 > 0 },
    { label: "61–90 days", value: aging.days_61_90, alert: aging.days_61_90 > 0 },
    { label: "90+ days", value: aging.days_90_plus, alert: aging.days_90_plus > 0 },
  ];

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link to="/customers" className="inline-flex items-center gap-2 text-sm font-semibold hover:text-accent">
          <ArrowLeft size={16} aria-hidden="true" /> All customers
        </Link>
        <div className="flex flex-wrap gap-2">
          <GhostButton
            onClick={() =>
              void customersApi
                .statementPdf(customer.id)
                .then((blob) => window.open(URL.createObjectURL(blob), "_blank"))
                .catch((caught: unknown) => setError(message(caught, "Could not build the statement PDF.")))
            }
          >
            <Printer size={16} aria-hidden="true" className="-ml-1 mr-2" /> Statement PDF
          </GhostButton>
          <GhostButton
            onClick={() =>
              void customersApi
                .sendStatements([customer.id])
                .then((result) =>
                  setToast(
                    result.queued
                      ? "Statement queued for sending."
                      : "Not sent: the customer has not opted in to messages on a channel with a contact.",
                  ),
                )
                .catch((caught: unknown) => setError(message(caught, "Could not send the statement.")))
            }
          >
            <Send size={16} aria-hidden="true" className="-ml-1 mr-2" /> Send statement
          </GhostButton>
          <GhostButton onClick={() => setDialog("edit")}>
            <SquarePen size={16} aria-hidden="true" className="-ml-1 mr-2" /> Edit profile
          </GhostButton>
          {wholesale ? (
            <GhostButton
              onClick={() => {
                const hold = !customer.credit_hold;
                const reason = hold ? window.prompt("Why is this account going on hold?", "") : "";
                if (hold && reason === null) return;
                void customersApi
                  .creditHold(customer.id, { hold, reason: reason ?? "" })
                  .then(() => {
                    setToast(hold ? "Account placed on credit hold." : "Credit hold lifted.");
                    return load();
                  })
                  .catch((caught: unknown) => setError(message(caught, "Could not change the credit hold.")));
              }}
            >
              {customer.credit_hold ? "Lift credit hold" : "Place on hold"}
            </GhostButton>
          ) : null}
          <PrimaryButton onClick={() => setDialog("payment")}>
            <Banknote size={16} aria-hidden="true" className="-ml-2 mr-2" /> Receive payment
          </PrimaryButton>
        </div>
      </div>

      {customer.credit_hold ? (
        <p role="status" className="rounded-2xl bg-accent px-5 py-3 text-sm font-semibold text-white">
          On credit hold: {customer.credit_hold_reason ?? "placed by a manager"}. On-account sales need a manager's approval.
        </p>
      ) : null}
      {(customer.cheque_exposure_cents ?? 0) > 0 ? (
        <p className="rounded-2xl bg-surface px-5 py-3 text-sm text-charcoal/70">
          {formatMoney(customer.cheque_exposure_cents ?? 0, currency)} in uncleared cheques is already credited to this account.
        </p>
      ) : null}
      <LoyaltyStrip customerId={customer.id} currency={currency} />
      {wholesale && creditModule ? (
        <CreditRiskCard customerId={customer.id} currency={currency} refreshKey={statement.generated_at} />
      ) : null}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <article className="rounded-card bg-charcoal p-6 text-white">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="text-xs font-medium uppercase tracking-[0.16em] text-white/50">{customer.code}</p>
              <h2 className="mt-1 truncate text-2xl font-semibold">{customer.company_name ?? customer.name}</h2>
              <p className="mt-1 text-sm text-white/60">
                {[customer.company_name ? customer.name : null, customer.phone, customer.email].filter(Boolean).join(" · ")}
              </p>
              {customer.trn_vat_number ? (
                <p className="mt-1 font-mono text-xs text-white/60">TRN {customer.trn_vat_number}</p>
              ) : null}
            </div>
            <div className="flex flex-wrap gap-1.5">
              <span className="rounded-full bg-accent px-3 py-1 text-xs font-semibold">
                {wholesale ? PRICE_TIER_LABELS[customer.price_tier] : "Retail"}
              </span>
              {wholesale ? (
                <span className="rounded-full bg-white/10 px-3 py-1 text-xs font-semibold">
                  {PAYMENT_TERMS_LABELS[customer.payment_terms]}
                </span>
              ) : null}
            </div>
          </div>
          <div className="mt-6 grid grid-cols-3 gap-4">
            <div>
              <p className="text-xs text-white/50">Balance due</p>
              <p className="mt-1 text-3xl font-semibold tabular-nums">{formatMoney(customer.current_balance_cents, currency)}</p>
            </div>
            <div>
              <p className="text-xs text-white/50">Credit limit</p>
              <p className="mt-1 text-xl font-semibold tabular-nums">{formatMoney(customer.credit_limit_cents, currency)}</p>
            </div>
            <div>
              <p className="text-xs text-white/50">{customer.available_credit_cents < 0 ? "Over limit" : "Available"}</p>
              <p className={`mt-1 text-xl font-semibold tabular-nums ${customer.available_credit_cents < 0 ? "text-accent" : ""}`}>
                {formatMoney(Math.abs(customer.available_credit_cents), currency)}
              </p>
            </div>
          </div>
          {wholesale ? (
            <div className="mt-4 h-2 overflow-hidden rounded-full bg-white/10" aria-hidden="true">
              <div
                className={`h-full rounded-full ${customer.available_credit_cents < 0 ? "bg-accent" : "bg-white/70"}`}
                style={{ width: `${used}%` }}
              />
            </div>
          ) : null}
        </article>

        <article className="rounded-card border border-line bg-white p-6">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold">Aging</h3>
            <p className="text-sm text-charcoal/60 tabular-nums">
              {formatMoney(customer.overdue_cents, currency)} overdue
            </p>
          </div>
          <div className="mt-4 grid grid-cols-5 gap-2">
            {buckets.map((bucket) => (
              <div
                key={bucket.label}
                className={`rounded-2xl p-3 ${bucket.alert ? "bg-accent text-white" : "bg-surface"}`}
              >
                <p className={`text-[11px] font-semibold uppercase tracking-wide ${bucket.alert ? "text-white/80" : "text-charcoal/50"}`}>
                  {bucket.label}
                </p>
                <p className="mt-2 text-sm font-semibold tabular-nums">{formatMoney(bucket.value, currency)}</p>
              </div>
            ))}
          </div>
          <dl className="mt-5 grid grid-cols-2 gap-3 text-sm">
            <div className="rounded-2xl bg-surface p-3">
              <dt className="text-xs text-charcoal/50">Invoiced to date</dt>
              <dd className="mt-1 font-semibold tabular-nums">{formatMoney(statement.total_invoiced_cents, currency)}</dd>
            </div>
            <div className="rounded-2xl bg-surface p-3">
              <dt className="text-xs text-charcoal/50">Paid to date</dt>
              <dd className="mt-1 font-semibold tabular-nums">{formatMoney(statement.total_paid_cents, currency)}</dd>
            </div>
          </dl>
        </article>
      </div>

      <div className="rounded-card border border-line bg-white p-6">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold">Unpaid invoices</h3>
          <p className="text-sm text-charcoal/60">{statement.open_invoices.length} open</p>
        </div>
        {statement.open_invoices.length === 0 ? (
          <p className="text-sm text-charcoal/60">Nothing outstanding. The account is clear.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-charcoal/50">
                <tr>
                  <th className="pb-3 font-medium">Invoice</th>
                  <th className="pb-3 font-medium">Issued</th>
                  <th className="pb-3 font-medium">Due</th>
                  <th className="pb-3 text-right font-medium">Total</th>
                  <th className="pb-3 text-right font-medium">Paid</th>
                  <th className="pb-3 text-right font-medium">Balance</th>
                  <th className="pb-3 pl-6 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {statement.open_invoices.map((invoice) => (
                  <tr key={invoice.sale_id} className="border-t border-line">
                    <td className="py-3 font-mono text-xs">{invoice.invoice}</td>
                    <td className="py-3">{shortDate(invoice.created_at)}</td>
                    <td className="py-3">{shortDate(invoice.due_date)}</td>
                    <td className="py-3 text-right tabular-nums">{formatMoney(invoice.total_cents, currency)}</td>
                    <td className="py-3 text-right tabular-nums">{formatMoney(invoice.amount_paid_cents, currency)}</td>
                    <td className="py-3 text-right font-semibold tabular-nums">{formatMoney(invoice.due_balance_cents, currency)}</td>
                    <td className="py-3 pl-6">
                      {invoice.days_overdue > 0 ? (
                        <span className="inline-flex rounded-full bg-accent px-2.5 py-0.5 text-[11px] font-semibold text-white">
                          {invoice.days_overdue} days overdue
                        </span>
                      ) : (
                        <span className="inline-flex rounded-full bg-charcoal px-2.5 py-0.5 text-[11px] font-semibold text-white">
                          {invoice.payment_status === "PARTIAL" ? "Part paid" : "Not yet due"}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="rounded-card border border-line bg-white p-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-lg font-semibold">Statement of account</h3>
          <SegmentedControl label="Ledger filter" value={filter} options={entryOptions} onChange={setFilter} />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[880px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-charcoal/50">
              <tr>
                <th className="pb-3 font-medium">Date</th>
                <th className="pb-3 font-medium">Type</th>
                <th className="pb-3 font-medium">Reference</th>
                <th className="pb-3 font-medium">Details</th>
                <th className="pb-3 text-right font-medium">Charges</th>
                <th className="pb-3 text-right font-medium">Payments</th>
                <th className="pb-3 text-right font-medium">Balance</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => (
                <tr key={entry.id} className="border-t border-line">
                  <td className="py-3 whitespace-nowrap">{shortDate(entry.created_at)}</td>
                  <td className="py-3">
                    <span
                      className={`inline-flex rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
                        entry.entry_type === "PAYMENT"
                          ? "bg-charcoal text-white"
                          : entry.entry_type === "INVOICE"
                            ? "bg-surface text-charcoal ring-1 ring-line"
                            : "bg-accent/10 text-accent ring-1 ring-accent/40"
                      }`}
                    >
                      {entryLabels[entry.entry_type]}
                    </span>
                  </td>
                  <td className="py-3 font-mono text-xs">{entry.invoice ?? (entry.reference || "—")}</td>
                  <td className="py-3 text-charcoal/70">
                    {[entry.method ? entry.method.replace("_", " ") : null, entry.note, entry.due_date ? `Due ${shortDate(entry.due_date)}` : null]
                      .filter(Boolean)
                      .join(" · ") || "—"}
                  </td>
                  <td className="py-3 text-right tabular-nums">
                    {entry.amount_cents > 0 ? formatMoney(entry.amount_cents, currency) : ""}
                  </td>
                  <td className="py-3 text-right tabular-nums">
                    {entry.amount_cents < 0 ? formatMoney(-entry.amount_cents, currency) : ""}
                  </td>
                  <td className="py-3 text-right font-semibold tabular-nums">
                    {formatMoney(entry.balance_after_cents, currency)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {entries.length === 0 ? <p className="py-8 text-sm text-charcoal/60">No ledger activity yet.</p> : null}
        </div>
      </div>

      {dialog === "payment" ? (
        <ReceivePaymentModal
          customer={customer}
          invoices={statement.open_invoices}
          currency={currency}
          onClose={() => setDialog(null)}
          onReceived={(result) => {
            setDialog(null);
            const applied = result.allocations.map((item) => item.invoice).join(", ");
            setToast(
              `Payment of ${formatMoney(-result.entry.amount_cents, currency)} recorded${applied ? ` against ${applied}` : ""}.`,
            );
            void load();
          }}
        />
      ) : null}
      {dialog === "edit" ? (
        <CustomerFormModal
          customer={customer}
          currency={currency}
          onClose={() => setDialog(null)}
          onSaved={() => {
            setDialog(null);
            setToast("Profile saved.");
            void load();
          }}
        />
      ) : null}
      {toast ? <Toast message={toast} onDismiss={dismissToast} /> : null}
    </section>
  );
}

interface LoyaltyStanding {
  points: number;
  tier: string | null;
  multiplier_pct: number;
  spend_12m_cents: number;
  next_tier: string | null;
  next_tier_gap_cents: number | null;
  expiring_soon: number;
}

function LoyaltyStrip({ customerId, currency }: { customerId: string; currency: string }) {
  const [standing, setStanding] = useState<LoyaltyStanding | null>(null);
  useEffect(() => {
    apiGet<LoyaltyStanding>(`/api/v1/loyalty/customers/${customerId}/standing`)
      .then(setStanding)
      .catch(() => setStanding(null));
  }, [customerId]);
  if (standing === null || (standing.points === 0 && standing.tier === null && standing.spend_12m_cents === 0)) return null;
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-2xl border border-line bg-white px-5 py-3 text-sm">
      <span className="flex items-center gap-2 font-semibold">
        <Gift size={16} aria-hidden="true" className="text-accent" />
        <span className="tabular-nums">{standing.points.toLocaleString()} points</span>
      </span>
      {standing.tier ? (
        <span className="rounded-full bg-charcoal px-3 py-1 text-xs font-semibold text-white">
          {standing.tier} · earns {standing.multiplier_pct}%
        </span>
      ) : null}
      <span className="text-charcoal/60 tabular-nums">12-month spend {formatMoney(standing.spend_12m_cents, currency)}</span>
      {standing.next_tier && standing.next_tier_gap_cents !== null ? (
        <span className="text-charcoal/60 tabular-nums">
          {formatMoney(standing.next_tier_gap_cents, currency)} more for {standing.next_tier}
        </span>
      ) : null}
      {standing.expiring_soon > 0 ? (
        <span className="font-medium text-accent tabular-nums">{standing.expiring_soon.toLocaleString()} points expire within 30 days</span>
      ) : null}
    </div>
  );
}
