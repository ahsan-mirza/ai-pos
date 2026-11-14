import {
  filterMarketplace,
  formatMoney,
  type BillingCatalog,
  type BillingPlan,
  type BillingQuote,
  type MarketplaceCatalog,
  type MarketplaceItem,
  type MarketplaceSort,
} from "@ai-pos/shared-types";
import { AxizTabs, useLocale } from "@ai-pos/ui";
import { useReducedMotion } from "framer-motion";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { tabBarBleed } from "../../components/layout/AppShell";
import { SearchField } from "../../components/ui/Field";
import { ApiRequestError, apiGet, apiPost } from "../../lib/api";
import { useCurrency } from "../../lib/currency";
import type { FeatureAccess } from "../../lib/featureAccess";
import { usePractice } from "../onboarding/practice";
import { PluginCheckout } from "./PluginCheckout";
import { ProAiTrialCard } from "./ProAiTrialCard";
import { AddonCard } from "./subscription/AddonCard";
import { BillingPeriodSelector } from "./subscription/BillingPeriodSelector";
import { planPriceView, presentUsage, type UsagePayload } from "./subscription/display";
import { PlanCard } from "./subscription/PlanCard";
import { PlanChangeList } from "./subscription/PlanChangeList";
import { PlanComparisonTable } from "./subscription/PlanComparisonTable";
import { PlanQuoteDialog } from "./subscription/PlanQuoteDialog";
import { EmptyState, ErrorState, LoadingBlock, LoadingCards, SectionHeader } from "./subscription/States";
import { SubscriptionSummaryCard } from "./subscription/SubscriptionSummaryCard";
import { isCustomPlan, isFreePlan, planFamily, visiblePlans } from "./subscriptionPlans";


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

const ATTENTION_LABEL: Record<PaymentAttention["kind"], string> = {
  awaiting_proof: "Awaiting payment",
  pending_review: "Under verification",
  rejected: "Payment rejected",
  revoked: "Subscription access was updated",
};

const SUBSCRIPTION_SECTIONS = [
  ["#overview", "Current subscription"],
  ["#plans", "Plans"],
  ["#compare", "Feature comparison"],
  ["#plugins", "Plugins"],
  ["#billing", "Billing"],
] as const;

type SubscriptionSection = (typeof SUBSCRIPTION_SECTIONS)[number][0];

function sectionFromHash(hash: string): SubscriptionSection | null {
  const match = SUBSCRIPTION_SECTIONS.find(([href]) => href === hash);
  if (match) return match[0];
  if (hash.startsWith("#plan-")) return "#plans";
  if (hash.startsWith("#plugin-")) return "#plugins";
  return null;
}

function initialSubscriptionSection(focusPlan: string | null, focusPlugin: string | null): SubscriptionSection {
  if (typeof window !== "undefined") {
    const fromHash = sectionFromHash(window.location.hash);
    if (fromHash) return fromHash;
  }
  if (focusPlan) return "#plans";
  if (focusPlugin) return "#plugins";
  return "#overview";
}

function PayByCardStatus() {
  const { t } = useLocale();
  const [state, setState] = useState("");
  useEffect(() => {
    let cancelled = false;
    apiGet<{ state: string }>("/api/v1/payments/card-readiness")
      .then((row) => {
        if (!cancelled) setState(row.state);
      })
      .catch(() => {
        if (!cancelled) setState("");
      });
    return () => {
      cancelled = true;
    };
  }, []);
  if (!state) return null;
  const copy =
    state === "PACKAGE_REQUIRED"
      ? "Pay by Card is not included in this package."
      : state === "HARDWARE_NOT_PURCHASED"
        ? "Pay by Card is included. An EC machine is purchased separately."
        : "A card payment is not sent until an acquirer and a compatible machine are ready.";
  return (
    <section className="rounded-2xl border border-line bg-white px-4 py-3 dark:border-zinc-800 dark:bg-zinc-900">
      <h2 className="text-sm font-semibold text-charcoal dark:text-white">{t("Pay by Card")}</h2>
      <p className="mt-1 text-sm text-charcoal/70 dark:text-white/70">{t(copy)}</p>
    </section>
  );
}

const SUBSCRIPTION_TAB_PREFIX = "subscription-sections";
const SUBSCRIPTION_PANEL_ID = "subscription-sections-panel";

function subscriptionTabId(section: string): string {
  return `${SUBSCRIPTION_TAB_PREFIX}-tab-${section.replace(/[^A-Za-z0-9_-]/g, "-")}`;
}

function SubscriptionSections({ section, onChange }: { section: string; onChange: (id: string) => void }) {
  const { t } = useLocale();
  const active = SUBSCRIPTION_SECTIONS.some(([href]) => href === section) ? section : "#overview";
  return (
    <div className={`${tabBarBleed} w-[calc(100%+2rem)] md:w-[calc(100%+3rem)]`}>
      <AxizTabs
        ariaLabel={t("Subscription sections")}
        activeTab={active}
        onChange={onChange}
        idPrefix={SUBSCRIPTION_TAB_PREFIX}
        controls={SUBSCRIPTION_PANEL_ID}
        tabs={SUBSCRIPTION_SECTIONS.map(([href, label]) => ({ id: href, label: t(label), href }))}
      />
    </div>
  );
}

export function SubscriptionCenter({
  subscription,
  attention,
  onInvoiced,
  trialEligible = false,
  billing,
  accessState = null,
  trial = null,
}: {
  subscription: SubscriptionSummary | null;
  attention: PaymentAttention | null;
  onInvoiced: () => void;
  /** True only when the promotional-trial API says this store may start Pro AI. */
  trialEligible?: boolean;
  accessState?: string | null;
  trial?: { status: string; capabilities: string[]; days_remaining: number | null; expires_at: string | null } | null;
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
  const [section, setSection] = useState(() => initialSubscriptionSection(focusPlan, focusPlugin));
  const [reloadKey, setReloadKey] = useState(0);
  const [catalog, setCatalog] = useState<BillingCatalog | null | undefined>(undefined);
  const [features, setFeatures] = useState<FeatureAccess[] | undefined>(undefined);
  const [featureError, setFeatureError] = useState<string | null>(null);
  const [marketplace, setMarketplace] = useState<MarketplaceCatalog | null | undefined>(undefined);
  const [marketplaceError, setMarketplaceError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cycleCode, setCycleCode] = useState("");
  const [quotes, setQuotes] = useState<Record<string, BillingQuote>>({});
  const [quoteErrors, setQuoteErrors] = useState<Record<string, string>>({});
  const [usageKey, setUsageKey] = useState(0);
  const [usage, setUsage] = useState<UsagePayload | null | undefined>(undefined);
  const [usageError, setUsageError] = useState<string | null>(null);
  const [upgrade, setUpgrade] = useState<BillingPlan | null>(null);
  const [changeKey, setChangeKey] = useState(0);
  const [pendingPlan, setPendingPlan] = useState<string | null>(null);
  const rememberPending = useCallback((code: string | null) => setPendingPlan(code), []);
  const [checkout, setCheckout] = useState<MarketplaceItem | null>(null);

  useEffect(() => {
    let cancelled = false;
    setCatalog(undefined);
    setFeatures(undefined);
    setFeatureError(null);
    setMarketplace(undefined);
    setMarketplaceError(null);
    setError(null);
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
      .catch((caught: unknown) => {
        if (cancelled) return;
        setFeatures([]);
        setFeatureError(caught instanceof ApiRequestError ? caught.message : "Could not load features.");
      });
    apiGet<MarketplaceCatalog>("/api/v1/billing/marketplace")
      .then((found) => {
        if (!cancelled) setMarketplace(found);
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        setMarketplace(null);
        setMarketplaceError(caught instanceof ApiRequestError ? caught.message : "Could not load add-ons.");
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  useEffect(() => {
    let cancelled = false;
    setUsage(undefined);
    setUsageError(null);
    apiGet<UsagePayload>("/api/v1/billing/usage")
      .then((found) => {
        if (!cancelled) setUsage(found);
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        setUsage(null);
        setUsageError(caught instanceof ApiRequestError ? caught.message : "Could not load usage.");
      });
    return () => {
      cancelled = true;
    };
  }, [usageKey]);

  const plans = useMemo(
    () => visiblePlans(catalog?.plans ?? [], subscription?.plan_code ?? null),
    [catalog, subscription?.plan_code],
  );
  const current = plans.find((plan) => plan.code === subscription?.plan_code) ?? catalog?.plans.find((plan) => plan.code === subscription?.plan_code);
  const cycles = (catalog?.cycles ?? []).filter((cycle) => cycle.active).sort((left, right) => left.sort_order - right.sort_order);
  const onboardingFee = (catalog?.fees ?? []).find((fee) => fee.code === "onboarding" && fee.active && fee.amount_fils > 0) ?? null;
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
    const sync = () => {
      const fromHash = sectionFromHash(window.location.hash);
      if (fromHash) {
        setSection(fromHash);
        return;
      }
      const search = new URLSearchParams(window.location.search);
      if (search.get("plan")) setSection("#plans");
      else if (search.get("plugin")) setSection("#plugins");
      else setSection("#overview");
    };
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);

  useEffect(() => {
    if (focusPlan) setSection("#plans");
    else if (focusPlugin) setSection("#plugins");
  }, [focusPlan, focusPlugin]);

  useEffect(() => {
    const hash = window.location.hash;
    const id = focusPlan
      ? `plan-${focusPlan}`
      : focusPlugin
        ? `plugin-${focusPlugin}`
        : hash.startsWith("#plan-") || hash.startsWith("#plugin-")
          ? hash.slice(1)
          : "";
    if (!id || catalog === undefined) return;
    document.getElementById(id)?.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "center" });
  }, [focusPlan, focusPlugin, catalog, plans.length, marketplace, reduced, section]);

  const retry = () => setReloadKey((value) => value + 1);

  return (
    <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-6">
      <header className="flex min-w-0 flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-charcoal dark:text-white">{t("Plans & add-ons")}</h1>
          <p className="mt-1 max-w-2xl text-sm text-charcoal/70 dark:text-white/70">
            {t("Review the published plans, compare what each one includes, and upgrade when you are ready.")}
          </p>
        </div>
        <a
          href="#plans"
          className="inline-flex h-10 items-center rounded-full bg-accent px-4 text-sm font-semibold text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          {t("Explore plans")}
        </a>
      </header>

      <SubscriptionSections
        section={section}
        onChange={(id) => {
          const next = sectionFromHash(id);
          if (next) setSection(next);
        }}
      />
      <div
        id={SUBSCRIPTION_PANEL_ID}
        role="tabpanel"
        aria-labelledby={subscriptionTabId(section)}
        className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-6"
      >
      {section === "#overview" ? (
        <>
          <PayByCardStatus />
          <section id="overview" className="min-w-0 rounded-2xl border border-line bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
            <SubscriptionSummaryCard
              subscription={subscription}
              plan={current}
              usage={usage}
              usageError={usageError}
              onRetryUsage={() => setUsageKey((value) => value + 1)}
              features={featureError ? null : features}
              purchased={(marketplace?.items ?? [])
                .filter((item) => item.state === "activated")
                .map((item) => ({ name: item.addon.name, keys: item.addon.module_keys }))}
              plans={plans}
              onUpgrade={(next) => {
                if (practice) openGoLive();
                else setUpgrade(next);
              }}
              accessState={accessState}
              attentionLabel={attention ? ATTENTION_LABEL[attention.kind] : null}
              trial={trial}
            />
          </section>
          <ProAiTrialCard />
        </>
      ) : null}

      {section === "#plans" ? (
      <section id="plans" className="min-w-0 grid grid-cols-[minmax(0,1fr)] gap-4">
        <SectionHeader title={t("Plans")} action={<BillingPeriodSelector cycles={cycles} value={cycleCode} annualDiscountBps={catalog?.current_annual_discount_bps} onChange={setCycleCode} />} />
        <PlanChangeList refreshKey={changeKey} onPendingPlan={rememberPending} />
        {catalog === undefined ? (
          <LoadingCards count={4} tall />
        ) : catalog === null ? (
          <ErrorState message={error ?? t("Could not load plans.")} onRetry={retry} />
        ) : plans.length === 0 ? (
          <EmptyState title={t("No plans are published.")} />
        ) : (
          <div className="grid items-stretch gap-3 md:grid-cols-2 xl:grid-cols-4">
            {plans.map((plan) => {
              const quote = quotes[plan.code]?.cycle_code === cycleCode ? quotes[plan.code] : undefined;
              const payable = !isFreePlan(plan) && !isCustomPlan(plan);
              return (
                <PlanCard
                  key={plan.code}
                  plan={plan}
                  price={planPriceView({
                    plan,
                    quote,
                    quoteError: quoteErrors[plan.code],
                    currency: subscription?.currency || quote?.currency || "AED",
                    pending: payable && !quote && !quoteErrors[plan.code],
                  })}
                  current={plan.code === subscription?.plan_code}
                  pending={pendingPlan === plan.code}
                  highlighted={plan.code === focusPlan}
                  legacy={planFamily(plan) === "legacy"}
                  trialNote={trialEligible && plan.code === "PRO_AI"}
                  onboardingFils={plan.code === "GROWTH" || plan.code === "PRO_AI" ? (onboardingFee?.amount_fils ?? 0) : 0}
                  currency={subscription?.currency || "AED"}
                  onUpgrade={() => {
                    if (practice) openGoLive();
                    else setUpgrade(plan);
                  }}
                />
              );
            })}
          </div>
        )}
        {catalog?.current_annual_discount_bps != null && cycleCode === "ANNUAL" ? (
          <p className="text-xs text-charcoal/60 dark:text-white/60">
            {t("New Growth and Pro AI annual invoices use the published {percent}% discount. The amount due is the quote.", {
              percent: catalog.current_annual_discount_bps / 100,
            })}
          </p>
        ) : null}
      </section>
      ) : null}

      {section === "#compare" ? (
      <section id="compare" className="min-w-0 grid grid-cols-[minmax(0,1fr)] gap-3">
        <SectionHeader title={t("Feature comparison")} />
        {features === undefined ? (
          <LoadingBlock />
        ) : featureError ? (
          <ErrorState message={t(featureError)} onRetry={retry} />
        ) : (
          <PlanComparisonTable
            plans={plans}
            features={features}
            currentCode={subscription?.plan_code ?? null}
            items={marketplace?.items ?? []}
            usage={usage ? presentUsage(usage) : []}
            onSelectPlan={(plan) => {
              if (practice) openGoLive();
              else setUpgrade(plan);
            }}
          />
        )}
      </section>
      ) : null}

      {section === "#plugins" ? (
      <section id="plugins" className="min-w-0 grid grid-cols-[minmax(0,1fr)] gap-3">
        <SectionHeader
          title={t("Plugins")}
          subtitle={t("Plugins are purchased separately. A plan change does not include them.")}
          action={
            <Link to="/settings/addons" className="text-sm font-semibold text-accent">
              {t("Explore add-ons")}
            </Link>
          }
        />
        {marketplace === undefined ? (
          <LoadingCards count={4} />
        ) : marketplaceError || marketplace === null ? (
          <ErrorState message={t(marketplaceError ?? "Could not load add-ons.")} onRetry={retry} />
        ) : (
          <AddonBrowser
            items={marketplace.items}
            currency={marketplace.currency}
            focusPlugin={focusPlugin}
            onPurchase={setCheckout}
          />
        )}
      </section>
      ) : null}

      {section === "#billing" ? (
      <section id="billing" className="min-w-0 rounded-2xl border border-line bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
        <SectionHeader title={t("Billing")} />
        {attention ? (
          <p className="mt-3 text-sm text-charcoal/80 dark:text-white/80">
            {t(ATTENTION_LABEL[attention.kind])} · <span dir="ltr">{attention.plan_code}</span> ·{" "}
            <span dir="ltr">{formatMoney(attention.total_fils, attention.currency)}</span>
          </p>
        ) : (
          <div className="mt-3">
            <EmptyState title={t("There is no invoice waiting for a bank transfer.")} />
          </div>
        )}
        <p className="mt-3 text-xs text-charcoal/50">{t("Paid features stay locked until a payment is verified. Verification stays in the console.")}</p>
        {billing ? <div className="mt-4">{billing}</div> : null}
      </section>
      ) : null}
      </div>

      {upgrade && catalog ? (
        <PlanQuoteDialog
          key={`${upgrade.code}-${cycleCode}`}
          plan={upgrade}
          cycleCode={cycleCode}
          quote={quotes[upgrade.code] ?? null}
          onboardingFils={upgrade.code === "GROWTH" || upgrade.code === "PRO_AI" ? (onboardingFee?.amount_fils ?? 0) : 0}
          currency={subscription?.currency || quotes[upgrade.code]?.currency || "AED"}
          transferAvailable={catalog.transfer_available === true}
          storeName={settings?.legal_name ?? ""}
          onClose={() => setUpgrade(null)}
          onInvoiced={() => {
            setUpgrade(null);
            setChangeKey((value) => value + 1);
            onInvoiced();
          }}
          onRequested={() => setChangeKey((value) => value + 1)}
        />
      ) : null}

      {checkout ? (
        <PluginCheckout
          item={checkout}
          onClose={() => setCheckout(null)}
          onDone={() => {
            setCheckout(null);
            onInvoiced();
          }}
        />
      ) : null}
    </div>
  );
}

function AddonBrowser({
  items,
  currency,
  focusPlugin,
  onPurchase,
}: {
  items: MarketplaceItem[];
  currency: string;
  focusPlugin: string | null;
  onPurchase: (item: MarketplaceItem) => void;
}) {
  const { t } = useLocale();
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const categories = useMemo(() => {
    const names = new Set<string>();
    for (const item of items) {
      if (item.addon.listing?.category) names.add(item.addon.listing.category);
    }
    return [...names].sort();
  }, [items]);
  const visible = useMemo(
    () => filterMarketplace(items, query, "", category, "", "recommended" satisfies MarketplaceSort),
    [items, query, category],
  );
  return (
    <div className="grid gap-3">
      <SearchField label={t("Search add-ons")} placeholder={t("Search add-ons")} value={query} onChange={(event) => setQuery(event.target.value)} />
      {categories.length > 0 ? (
        <div className="flex flex-wrap gap-2" role="group" aria-label={t("Category")}>
          <FilterChip selected={category === ""} onClick={() => setCategory("")} label={t("All categories")} />
          {categories.map((name) => (
            <FilterChip key={name} selected={category === name} onClick={() => setCategory(name)} label={name} />
          ))}
        </div>
      ) : null}
      {items.length === 0 ? (
        <EmptyState title={t("No plugins are published.")} />
      ) : visible.length === 0 ? (
        <EmptyState title={t("No add-ons match that search.")} />
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {visible.map((item) => (
            <AddonCard
              key={item.addon.code}
              item={item}
              currency={currency}
              highlighted={item.addon.code === focusPlugin}
              onPurchase={() => onPurchase(item)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function FilterChip({ selected, onClick, label }: { selected: boolean; onClick: () => void; label: string }) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onClick}
      className={`inline-flex h-9 items-center rounded-full border px-3 text-xs font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
        selected ? "border-accent bg-accent/10 text-charcoal dark:text-white" : "border-line text-charcoal/70 dark:text-white/70"
      }`}
    >
      {label}
    </button>
  );
}
