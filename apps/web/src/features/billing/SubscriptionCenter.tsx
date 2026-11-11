import {
  formatMoney,
  CAPABILITIES,
  type BillingCatalog,
  type BillingCheckout,
  type BillingPlan,
  type BillingQuote,
  type MarketplaceCatalog,
  type MarketplaceItem,
} from "@ai-pos/shared-types";
import { useLocale } from "@ai-pos/ui";
import { useReducedMotion } from "framer-motion";
import { Check, Minus, Puzzle } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ErrorNote, PrimaryButton } from "../../components/ui/Field";
import { ApiRequestError, apiGet, apiPost } from "../../lib/api";
import { useCurrency } from "../../lib/currency";
import type { FeatureAccess } from "../../lib/featureAccess";
import { usePractice } from "../onboarding/practice";
import { ProAiTrialCard } from "./ProAiTrialCard";
import { comparableFeature, comparisonMark, isCustomPlan, isFreePlan, planLimits, visiblePlans } from "./subscriptionPlans";

export interface SubscriptionSummary {
  plan_name: string;
  plan_code: string;
  status: string;
  cycle_name: string;
  price_fils?: number;
  currency?: string;
  current_period_end?: string | null;
  trial_ends_at?: string | null;
}

interface PaymentAttention {
  kind: "awaiting_proof" | "pending_review" | "rejected" | "revoked";
  invoice_id: string;
  plan_code: string;
  cycle_code: string;
  currency: string;
  total_fils: number;
}

const STATUS_LABEL: Record<string, string> = {
  active: "Active",
  trialing: "Trial",
  past_due: "Past due",
  canceled: "Canceled",
};

const ATTENTION_LABEL: Record<PaymentAttention["kind"], string> = {
  awaiting_proof: "Awaiting payment",
  pending_review: "Under verification",
  rejected: "Payment rejected",
  revoked: "Subscription access was updated",
};

export function SubscriptionCenter({
  subscription,
  attention,
  onInvoiced,
  trialEligible = false,
  billing,
}: {
  subscription: SubscriptionSummary | null;
  attention: PaymentAttention | null;
  onInvoiced: () => void;
  /** True only when the promotional-trial API says this store may start Pro AI. */
  trialEligible?: boolean;
  /** Current invoice actions. There is no invoice-history endpoint, so this is the open invoice only. */
  billing?: ReactNode;
}) {
  const { t } = useLocale();
  const reduced = useReducedMotion() === true;
  const { settings } = useCurrency();
  const { practice, openGoLive } = usePractice();
  const tRef = useRef(t);
  tRef.current = t;
  const [params] = useSearchParams();
  const focusPlan = params.get("plan");
  const focusPlugin = params.get("plugin");
  const [catalog, setCatalog] = useState<BillingCatalog | null | undefined>(undefined);
  const [features, setFeatures] = useState<FeatureAccess[] | null>(null);
  const [marketplace, setMarketplace] = useState<MarketplaceCatalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cycleCode, setCycleCode] = useState("");
  const [quotes, setQuotes] = useState<Record<string, BillingQuote>>({});
  const [quoteErrors, setQuoteErrors] = useState<Record<string, string>>({});
  const [upgrade, setUpgrade] = useState<BillingPlan | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiGet<BillingCatalog>("/api/v1/billing/catalog")
      .then((found) => {
        if (cancelled) return;
        setCatalog(found);
        const cycle = found.cycles.find((row) => row.active && row.code === "MONTHLY") ?? found.cycles.find((row) => row.active);
        setCycleCode((current) => current || cycle?.code || "");
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        setCatalog(null);
        setError(caught instanceof ApiRequestError ? caught.message : tRef.current("Could not load plans."));
      });
    apiGet<{ features: FeatureAccess[] }>("/api/v1/billing/features")
      .then((found) => {
        if (!cancelled) setFeatures(found.features);
      })
      .catch(() => {
        if (!cancelled) setFeatures([]);
      });
    apiGet<MarketplaceCatalog>("/api/v1/billing/marketplace")
      .then((found) => {
        if (!cancelled) setMarketplace(found);
      })
      .catch(() => {
        if (!cancelled) setMarketplace(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const plans = useMemo(
    () => visiblePlans(catalog?.plans ?? [], subscription?.plan_code ?? null),
    [catalog, subscription?.plan_code],
  );
  const current = plans.find((plan) => plan.code === subscription?.plan_code) ?? catalog?.plans.find((plan) => plan.code === subscription?.plan_code);
  const cycles = (catalog?.cycles ?? []).filter((cycle) => cycle.active).sort((left, right) => left.sort_order - right.sort_order);
  const payableCodes = plans
    .filter((plan) => !isFreePlan(plan) && !isCustomPlan(plan))
    .map((plan) => plan.code)
    .join(",");

  useEffect(() => {
    if (!cycleCode || payableCodes === "") return;
    let cancelled = false;
    setQuotes({});
    setQuoteErrors({});
    Promise.all(
      payableCodes.split(",").map((code) =>
        apiPost<BillingQuote>("/api/v1/billing/quote", { plan_code: code, cycle_code: cycleCode, addons: [], hardware: [] })
          .then((quote) => ({ code, quote, error: null as string | null }))
          .catch((caught: unknown) => ({
            code,
            quote: null as BillingQuote | null,
            error: caught instanceof ApiRequestError ? caught.message : tRef.current("Could not load plans."),
          })),
      ),
    ).then((rows) => {
      if (cancelled) return;
      const next: Record<string, BillingQuote> = {};
      const errors: Record<string, string> = {};
      for (const row of rows) {
        if (row.quote && row.quote.cycle_code === cycleCode) next[row.code] = row.quote;
        else if (row.error) errors[row.code] = row.error;
      }
      setQuotes(next);
      setQuoteErrors(errors);
    });
    return () => {
      cancelled = true;
    };
  }, [cycleCode, payableCodes]);

  useEffect(() => {
    const id = focusPlan ? `plan-${focusPlan}` : focusPlugin ? `plugin-${focusPlugin}` : "";
    if (!id || catalog === undefined) return;
    document.getElementById(id)?.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "center" });
  }, [focusPlan, focusPlugin, catalog, plans.length, marketplace, reduced]);

  const groups = useMemo(() => groupFeatures(features ?? [], plans), [features, plans]);
  const limits = planLimits(current);

  return (
    <div className="grid gap-8">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-charcoal dark:text-white">{t("Plans & add-ons")}</h1>
          <p className="mt-1 max-w-2xl text-sm text-charcoal/70 dark:text-white/70">
            {t("Review the published plans, compare what each one includes, and upgrade when you are ready.")}
          </p>
        </div>
        <a href="#plans" className="inline-flex h-10 items-center rounded-full bg-accent px-4 text-sm font-semibold text-white">
          {t("Explore plans")}
        </a>
      </header>

      <nav aria-label={t("Subscription sections")} className="flex flex-wrap gap-2 text-sm">
        {(
          [
            ["#overview", "Current subscription"],
            ["#plans", "Plans"],
            ["#compare", "Feature comparison"],
            ["#plugins", "Plugins"],
            ["#billing", "Billing"],
          ] as const
        ).map(([href, label]) => (
          <a key={href} href={href} className="rounded-full border border-line bg-white px-3 py-1.5 font-medium text-charcoal/80 dark:bg-zinc-900 dark:text-white/80">
            {t(label)}
          </a>
        ))}
      </nav>

      <ErrorNote message={error} />

      <section id="overview" className="rounded-3xl border border-line bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
        {subscription ? (
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-charcoal/50">{t("Current plan")}</p>
              <h2 className="mt-1 text-2xl font-semibold text-charcoal dark:text-white">{t(subscription.plan_name)}</h2>
              <p className="mt-1 text-sm tabular-nums text-charcoal/70 dark:text-white/70">
                {typeof subscription.price_fils === "number"
                  ? t("{price} · {cycle}", {
                      price: formatMoney(subscription.price_fils, subscription.currency || "AED"),
                      cycle: subscription.cycle_name,
                    })
                  : subscription.cycle_name}
              </p>
              <p className="mt-3 max-w-xl text-sm text-charcoal/80 dark:text-white/80">
                {subscription.plan_code === "FREE"
                  ? t("Your business is running on the Free plan. Upgrade whenever you need more capabilities.")
                  : t("Your business is on {plan}.", { plan: subscription.plan_name })}
              </p>
            </div>
            <span className="rounded-full bg-emerald-500/10 px-3 py-1 text-sm font-semibold text-emerald-800 dark:text-emerald-300">
              {t(STATUS_LABEL[subscription.status] ?? subscription.status)}
            </span>
          </div>
        ) : (
          <p className="text-sm text-charcoal/70">{t("No subscription is assigned yet.")}</p>
        )}
        <dl className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {subscription?.current_period_end ? (
            <Fact label={t("Next renewal")} value={subscription.current_period_end.slice(0, 10)} />
          ) : null}
          {subscription?.trial_ends_at ? <Fact label={t("Trial ends")} value={subscription.trial_ends_at.slice(0, 10)} /> : null}
          {limits.map((limit) => (
            <Fact key={limit.key} label={t(limit.label)} value={t(limit.unit === "days" ? "{count} days" : "{count} included", { count: limit.value })} />
          ))}
        </dl>
      </section>

      <ProAiTrialCard />

      <section id="plans" className="grid gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-semibold text-charcoal dark:text-white">{t("Plans")}</h2>
          {cycles.length > 0 ? (
            <div role="radiogroup" aria-label={t("Billing cycle")} className="flex flex-wrap gap-1 rounded-full bg-zinc-100 p-1 dark:bg-zinc-800">
              {cycles.map((cycle) => {
                const annual = cycle.code === "ANNUAL" ? catalog?.current_annual_discount_bps : undefined;
                const bps = annual != null && annual > 0 ? annual : cycle.discount_bps;
                const selected = cycle.code === cycleCode;
                return (
                  <button
                    key={cycle.code}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    onClick={() => setCycleCode(cycle.code)}
                    className={`h-9 rounded-full px-3 text-sm ${selected ? "bg-white font-semibold text-charcoal shadow-sm dark:bg-zinc-900 dark:text-white" : "text-charcoal/70 dark:text-white/70"}`}
                  >
                    {t(cycle.name)}
                    {bps > 0 ? <span className="ms-1 text-xs text-accent">{t("{percent}% off", { percent: bps / 100 })}</span> : null}
                  </button>
                );
              })}
            </div>
          ) : null}
        </div>
        {catalog === undefined ? (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {Array.from({ length: 4 }, (_, index) => (
              <div key={index} className="h-56 animate-pulse rounded-3xl bg-zinc-100 dark:bg-zinc-800" />
            ))}
          </div>
        ) : plans.length === 0 ? (
          <p className="text-sm text-charcoal/60">{t("No plans are published.")}</p>
        ) : (
          <div className="grid items-stretch gap-3 md:grid-cols-2 xl:grid-cols-4">
            {plans.map((plan) => (
              <PlanCard
                key={plan.code}
                plan={plan}
                quote={quotes[plan.code]?.cycle_code === cycleCode ? quotes[plan.code] : undefined}
                quoteError={quoteErrors[plan.code]}
                currency={subscription?.currency || quotes[plan.code]?.currency || "AED"}
                current={plan.code === subscription?.plan_code}
                highlighted={plan.code === focusPlan}
                trialEligible={trialEligible && plan.code === "PRO_AI"}
                onUpgrade={() => {
                  if (practice) openGoLive();
                  else setUpgrade(plan);
                }}
              />
            ))}
          </div>
        )}
        {catalog?.current_annual_discount_bps != null && cycleCode === "ANNUAL" ? (
          <p className="text-xs text-charcoal/60">
            {t("New Growth and Pro AI annual invoices use the published {percent}% discount. The amount due is the quote.", {
              percent: catalog.current_annual_discount_bps / 100,
            })}
          </p>
        ) : null}
      </section>

      {upgrade && catalog ? (
        <UpgradeQuote
          plan={upgrade}
          cycleCode={cycleCode}
          quote={quotes[upgrade.code] ?? null}
          transferAvailable={catalog.transfer_available === true}
          storeName={settings?.legal_name ?? ""}
          onClose={() => setUpgrade(null)}
          onInvoiced={() => {
            setUpgrade(null);
            onInvoiced();
          }}
        />
      ) : null}

      <section id="compare" className="grid gap-3">
        <h2 className="text-lg font-semibold text-charcoal dark:text-white">{t("Feature comparison")}</h2>
        {features === null ? (
          <div className="h-40 animate-pulse rounded-3xl bg-zinc-100 dark:bg-zinc-800" />
        ) : groups.length === 0 ? (
          <p className="text-sm text-charcoal/60">{t("No features are published for this business.")}</p>
        ) : (
          <div className="overflow-x-auto rounded-3xl border border-line bg-white dark:border-zinc-800 dark:bg-zinc-900">
            <table className="w-full min-w-[40rem] border-collapse text-sm">
              <thead>
                <tr className="border-b border-line text-start">
                  <th className="sticky start-0 bg-white px-4 py-3 text-start font-semibold dark:bg-zinc-900">{t("Feature")}</th>
                  {plans.map((plan) => (
                    <th key={plan.code} className="px-3 py-3 text-start font-semibold">
                      {t(plan.name)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {groups.map((group) => (
                  <GroupRows key={group.label} label={group.label} rows={group.rows} plans={plans} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section id="plugins" className="grid gap-3">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <h2 className="text-lg font-semibold text-charcoal dark:text-white">{t("Plugins")}</h2>
          <Link to="/settings/addons" className="text-sm font-semibold text-accent">
            {t("Explore add-ons")}
          </Link>
        </div>
        <p className="text-sm text-charcoal/70 dark:text-white/70">{t("Plugins are purchased separately. A plan change does not include them.")}</p>
        {marketplace === null ? (
          <div className="h-28 animate-pulse rounded-3xl bg-zinc-100 dark:bg-zinc-800" />
        ) : marketplace.items.length === 0 ? (
          <p className="text-sm text-charcoal/60">{t("No plugins are published.")}</p>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {marketplace.items.map((item) => (
              <PluginCard key={item.addon.code} item={item} currency={marketplace.currency} highlighted={item.addon.code === focusPlugin} onInvoiced={onInvoiced} />
            ))}
          </div>
        )}
      </section>

      <section id="billing" className="rounded-3xl border border-line bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
        <h2 className="text-lg font-semibold text-charcoal dark:text-white">{t("Billing")}</h2>
        {attention ? (
          <p className="mt-2 text-sm text-charcoal/80 dark:text-white/80">
            {t(ATTENTION_LABEL[attention.kind])} · {attention.plan_code} · {formatMoney(attention.total_fils, attention.currency)}
          </p>
        ) : (
          <p className="mt-2 text-sm text-charcoal/60">{t("There is no invoice waiting for a bank transfer.")}</p>
        )}
        <p className="mt-2 text-xs text-charcoal/50">{t("Paid features stay locked until a payment is verified. Verification stays in the console.")}</p>
        {billing ? <div className="mt-4">{billing}</div> : null}
      </section>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-zinc-50 px-3 py-2 dark:bg-white/5">
      <dt className="text-xs text-charcoal/50">{label}</dt>
      <dd className="mt-0.5 text-sm font-semibold tabular-nums text-charcoal dark:text-white">{value}</dd>
    </div>
  );
}

function PlanCard({
  plan,
  quote,
  quoteError,
  currency,
  current,
  highlighted,
  trialEligible,
  onUpgrade,
}: {
  plan: BillingPlan;
  quote?: BillingQuote;
  quoteError?: string;
  currency: string;
  current: boolean;
  highlighted: boolean;
  trialEligible: boolean;
  onUpgrade: () => void;
}) {
  const { t } = useLocale();
  const custom = isCustomPlan(plan);
  const free = isFreePlan(plan);
  const premium = plan.code === "PRO_AI";
  const price = custom
    ? t("Custom pricing")
    : quote
      ? t("{price} / {cycle}", { price: formatMoney(quote.total_fils, quote.currency), cycle: quote.cycle_name })
      : free
        ? formatMoney(plan.monthly_fils, currency)
        : "…";
  return (
    <article
      id={`plan-${plan.code}`}
      className={`flex h-full flex-col rounded-3xl border p-4 ${
        premium ? "border-accent/40 bg-accent/[0.04]" : "border-line bg-white dark:border-zinc-800 dark:bg-zinc-900"
      } ${highlighted ? "ring-2 ring-accent" : ""} ${current ? "shadow-sm" : ""}`}
    >
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-lg font-semibold text-charcoal dark:text-white">{t(plan.name)}</h3>
        {current ? <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-semibold dark:bg-white/10">{t("Current plan")}</span> : null}
        {custom ? <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-semibold dark:bg-white/10">{t("Custom")}</span> : null}
      </div>
      <p className="mt-2 text-sm font-semibold tabular-nums text-charcoal dark:text-white">{price ?? t("Included with signup")}</p>
      {quote && quote.discount_bps > 0 ? (
        <p className="text-xs text-charcoal/60">{t("{percent}% off this cycle", { percent: quote.discount_bps / 100 })}</p>
      ) : null}
      {!free && !custom && !quote && quoteError ? <p className="text-xs text-amber-800">{quoteError}</p> : null}
      <ul className="mt-3 flex-1 space-y-1 text-sm text-charcoal/75 dark:text-white/75">
        {planLimits(plan).slice(0, 4).map((limit) => (
          <li key={limit.key}>
            {t(limit.label)}: {limit.value}
            {limit.unit === "days" ? ` ${t("days")}` : ""}
          </li>
        ))}
        {plan.included_modules.length > 0 ? <li>{t("{count} included modules", { count: plan.included_modules.length })}</li> : null}
      </ul>
      {premium && trialEligible ? <p className="mt-2 text-xs text-charcoal/60">{t("A free trial is offered only when this store is eligible.")}</p> : null}
      <div className="mt-4">
        {current ? (
          <span className="inline-flex h-10 items-center text-sm font-semibold text-charcoal/60">{t("Current plan")}</span>
        ) : custom ? (
          <p className="text-sm text-charcoal/70">{t("Priced on a contract. Contact sales to continue on Enterprise.")}</p>
        ) : free ? null : (
          <button type="button" onClick={onUpgrade} className="inline-flex h-10 items-center rounded-full bg-accent px-4 text-sm font-semibold text-white">
            {t("Upgrade to {plan}", { plan: plan.name })}
          </button>
        )}
      </div>
    </article>
  );
}

function UpgradeQuote({
  plan,
  cycleCode,
  quote,
  transferAvailable,
  storeName,
  onClose,
  onInvoiced,
}: {
  plan: BillingPlan;
  cycleCode: string;
  quote: BillingQuote | null;
  transferAvailable: boolean;
  storeName: string;
  onClose: () => void;
  onInvoiced: () => void;
}) {
  const { t } = useLocale();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [issued, setIssued] = useState<BillingCheckout | null>(null);

  const issue = async () => {
    if (!storeName.trim()) {
      setError(t("Set the legal name in settings before creating an invoice."));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const checkout = await apiPost<BillingCheckout>("/api/v1/billing/checkout", {
        plan_code: plan.code,
        cycle_code: cycleCode,
        addons: [],
        hardware: [],
        mode: "keep",
        opening_stock: "keep",
        confirm: storeName.trim(),
        tax_acknowledged: true,
        payment: "transfer",
      });
      setIssued(checkout);
      onInvoiced();
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : t("Could not issue the invoice."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-3xl border border-accent/30 bg-white p-5 dark:border-accent/40 dark:bg-zinc-900">
      <div className="flex items-start justify-between gap-3">
        <h2 className="text-lg font-semibold">{t("Review quote")}</h2>
        <button type="button" onClick={onClose} className="text-sm font-medium text-charcoal/60">
          {t("Not now")}
        </button>
      </div>
      {quote ? (
        <>
          <p className="mt-1 text-sm text-charcoal/70">
            {quote.plan_name} · {quote.cycle_name} · {formatMoney(quote.total_fils, quote.currency)}
          </p>
          <ul className="mt-3 divide-y divide-line text-sm">
            {quote.lines.map((line) => (
              <li key={line.code} className="flex justify-between gap-3 py-2">
                <span>
                  {line.label}
                  {line.quantity > 1 ? ` × ${line.quantity}` : ""}
                </span>
                <span className="tabular-nums">{formatMoney(line.amount_fils, quote.currency)}</span>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p className="mt-2 text-sm text-charcoal/60">{t("The quote is not available for this cycle.")}</p>
      )}
      {!transferAvailable ? <p className="mt-3 text-sm text-amber-800">{t("Bank transfer details have not been published yet.")}</p> : null}
      {issued ? (
        <p className="mt-3 text-sm font-medium text-charcoal">
          {t("Awaiting payment")} · {formatMoney(issued.quote.total_fils, issued.quote.currency)}. {t("Paid features stay locked until a payment is verified.")}
        </p>
      ) : null}
      <ErrorNote message={error} />
      <div className="mt-4">
        <PrimaryButton type="button" disabled={busy || !quote || !transferAvailable || issued !== null} onClick={() => void issue()}>
          {busy ? t("Please wait…") : t("Generate invoice")}
        </PrimaryButton>
      </div>
    </section>
  );
}

function PluginCard({
  item,
  currency,
  highlighted,
  onInvoiced,
}: {
  item: MarketplaceItem;
  currency: string;
  highlighted: boolean;
  onInvoiced: () => void;
}) {
  const { t } = useLocale();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const purchasable = item.state === "available" && (item.addon.monthly_fils > 0 || item.addon.one_time_fils > 0);
  const price =
    item.state === "unpriced"
      ? t("Price configured by administrator.")
      : item.addon.monthly_fils > 0
        ? t("{price} per month", { price: formatMoney(item.addon.monthly_fils, currency) })
        : item.addon.one_time_fils > 0
          ? formatMoney(item.addon.one_time_fils, currency)
          : null;
  const buy = async () => {
    setBusy(true);
    setError(null);
    try {
      await apiPost(`/api/v1/billing/addons/${item.addon.code}/checkout`, {});
      onInvoiced();
      document.getElementById("billing")?.scrollIntoView({ block: "start" });
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : t("Could not issue the invoice."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <article id={`plugin-${item.addon.code}`} className={`rounded-3xl border border-line bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900 ${highlighted ? "ring-2 ring-accent" : ""}`}>
      <div className="flex items-start justify-between gap-2">
        <h3 className="font-semibold text-charcoal dark:text-white">{item.addon.name}</h3>
        <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-semibold dark:bg-white/10">{t(stateLabel(item.state))}</span>
      </div>
      <p className="mt-1 text-sm text-charcoal/70 dark:text-white/70">{item.addon.listing?.short_description || item.addon.description}</p>
      {item.compatible_labels.length > 0 ? <p className="mt-2 text-xs text-charcoal/50">{item.compatible_labels.join(" · ")}</p> : null}
      {price ? <p className="mt-2 text-sm font-semibold tabular-nums">{price}</p> : null}
      {item.reason && !purchasable ? <p className="mt-2 text-xs text-charcoal/60">{item.reason}</p> : null}
      {error ? <p className="mt-2 text-sm text-red-700">{error}</p> : null}
      {purchasable ? (
        <button type="button" disabled={busy} onClick={() => void buy()} className="mt-3 inline-flex h-10 items-center gap-2 rounded-full border border-line px-4 text-sm font-semibold">
          <Puzzle size={14} aria-hidden="true" />
          {busy ? t("Please wait…") : t("Subscribe")}
        </button>
      ) : null}
    </article>
  );
}

function stateLabel(state: MarketplaceItem["state"]): string {
  if (state === "included") return "Included";
  if (state === "activated") return "Activated";
  if (state === "pending_payment") return "Awaiting payment";
  if (state === "pending_activation") return "Pending activation";
  if (state === "expired") return "Expired";
  if (state === "unavailable") return "Unavailable";
  return "Available";
}

function GroupRows({ label, rows, plans }: { label: string; rows: FeatureAccess[]; plans: BillingPlan[] }) {
  const { t } = useLocale();
  return (
    <>
      <tr className="bg-zinc-50 dark:bg-white/5">
        <th colSpan={plans.length + 1} className="px-4 py-2 text-start text-xs font-semibold uppercase tracking-wide text-charcoal/50">
          {t(label)}
        </th>
      </tr>
      {rows.map((feature) => (
        <tr key={feature.feature_key} className="border-t border-line">
          <th className="sticky start-0 bg-white px-4 py-2 text-start font-medium dark:bg-zinc-900">{t(feature.label)}</th>
          {plans.map((plan) => {
            const mark = comparisonMark(plan, feature.feature_key, feature.plugin_code);
            return (
              <td key={plan.code} className="px-3 py-2">
                {mark === "included" ? (
                  <span className="inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-300">
                    <Check size={14} aria-hidden="true" />
                    {t("Included")}
                  </span>
                ) : mark === "plugin" ? (
                  <span className="text-charcoal/70 dark:text-white/70">{t("Plugin")}</span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-charcoal/40">
                    <Minus size={14} aria-hidden="true" />
                    {t("Not included")}
                  </span>
                )}
              </td>
            );
          })}
        </tr>
      ))}
    </>
  );
}

const GROUP_LABEL: Record<string, string> = {
  selling: "POS & Checkout",
  inventory: "Inventory & Products",
  customers: "Customers & CRM",
  service: "Service",
  food_beverage: "Restaurant & Kitchen",
};

/** Display groups for features that already exist. Empty categories are omitted. */
const FEATURE_GROUP: Record<string, string> = {
  ai_insights: "AI & Automation",
  deep_analytics: "Reports & Analytics",
  sales_insights: "Reports & Analytics",
  quotes_layaway: "Sales & Orders",
  sales_orders: "Sales & Orders",
  online_store: "Sales & Orders",
  promotions: "Sales & Orders",
  customer_reorders: "Sales & Orders",
  uae_einvoicing: "Finance & Accounting",
};

const GROUP_ORDER = [
  "POS & Checkout",
  "Sales & Orders",
  "Inventory & Products",
  "Customers & CRM",
  "Finance & Accounting",
  "Reports & Analytics",
  "AI & Automation",
  "Restaurant & Kitchen",
  "Service",
  "Other",
];

function groupFeatures(features: FeatureAccess[], plans: BillingPlan[]): { label: string; rows: FeatureAccess[] }[] {
  const visible = features.filter((feature) => comparableFeature(feature.state));
  const byGroup = new Map<string, FeatureAccess[]>();
  for (const feature of visible) {
    const spec = CAPABILITIES.find((row) => row.id === feature.feature_key);
    const label = FEATURE_GROUP[feature.feature_key] ?? GROUP_LABEL[spec?.group ?? ""] ?? "Other";
    const list = byGroup.get(label) ?? [];
    list.push(feature);
    byGroup.set(label, list);
  }
  void plans;
  return [...byGroup.entries()]
    .sort((left, right) => GROUP_ORDER.indexOf(left[0]) - GROUP_ORDER.indexOf(right[0]))
    .map(([label, rows]) => ({ label, rows }));
}
