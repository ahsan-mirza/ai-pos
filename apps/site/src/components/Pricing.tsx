import { PROFILE_PRESETS, isCapability, type BusinessProfile } from "@ai-pos/shared-types";
import { useLocale } from "@ai-pos/ui";
import { motion } from "framer-motion";
import { Fragment, useState } from "react";
import {
  addonPriceText,
  comparisonMark,
  comparisonRows,
  defaultCountry,
  groupedComparison,
  isCustomPlan,
  isFreePlan,
  legacyPlanNames,
  money,
  planLimitLines,
  publicPlugins,
  publishedCountries,
  publishedPrice,
  showcasePlans,
  type Addon,
  type ComparisonRow,
  type Plan,
  type PublicCatalog,
} from "../catalog";
import { BUSINESS_TYPE_ORDER, moduleLabel, profilesFor } from "../modules";
import { GET_STARTED_NOTE, GetStartedLink } from "./GetStartedLink";
import { Mark, type MarkName } from "./icons";
import { lift, rise, stagger, viewport } from "./motion";
import { SectionHeading } from "./SectionHeading";

const PLAN_ICONS: Record<string, MarkName> = {
  FREE: "spark",
  GROWTH: "zap",
  PRO_AI: "layers",
  ENTERPRISE: "stores",
};

export function Pricing({
  catalog,
  status,
  onQuote,
}: {
  catalog: PublicCatalog;
  status: "loading" | "ready" | "unavailable";
  onQuote: (note: string) => void;
}) {
  const plans = showcasePlans(catalog);
  const [code, setCode] = useState<string | null>(null);
  const [cycleCode, setCycleCode] = useState<string | null>(null);
  const [countryCode, setCountryCode] = useState<string | null>(null);
  const [profile, setProfile] = useState<BusinessProfile | "all">("all");
  const countries = publishedCountries(catalog);
  const country = countries.includes(countryCode ?? "") ? countryCode : defaultCountry(catalog);
  const plan = plans.find((item) => item.code === code) ?? plans.find((item) => item.code === "GROWTH") ?? plans[0];
  const cycle =
    catalog.cycles.find((item) => item.code === cycleCode) ??
    catalog.cycles.find((item) => item.code === "MONTHLY") ??
    catalog.cycles[0];
  const legacy = legacyPlanNames(catalog);
  const trial = catalog.promotional_trial;
  const trialPlan = plans.find((item) => item.code === trial.plan_code);
  const showTrial = status === "ready" && trial.enabled && trial.days > 0 && trialPlan !== undefined;
  const business = profile === "all" ? null : profile;
  const groups = groupedComparison(comparisonRows(plans, catalog.addons, business));
  const addons = publicPlugins(catalog.addons, business);
  const monthlyCycle = catalog.cycles.find((item) => item.code === "MONTHLY") ?? null;
  const annualCycle = catalog.cycles.find((item) => item.code === "ANNUAL") ?? null;
  const priceCurrency = catalogCurrency(plans, cycle, catalog, country);
  const fees = catalog.fees.filter((fee) => fee.amount_fils > 0);
  const { t, locale } = useLocale();

  return (
    <section id="pricing" className="border-t border-line bg-surface">
      <div className="mx-auto max-w-page px-4 py-16 sm:px-6 lg:px-8 lg:py-20">
        <SectionHeading kicker={t("Pricing")} title={t("Everything your business needs, with a plan that grows with you.")}>
          {status === "ready"
            ? t("Start with essential POS capabilities for free. Upgrade for advanced tools, AI-powered insights, and optional business extensions whenever you need them.")
            : status === "loading"
              ? t("Loading the published catalog.")
              : t("The published catalog could not be loaded. Prices stay hidden until it is reachable.")}
        </SectionHeading>
        {status === "ready" ? (
          <div className="mt-6 flex flex-wrap gap-2">
            <GetStartedLink className="inline-flex h-11 items-center justify-center rounded-full bg-primary px-4 text-sm font-semibold text-white hover:bg-primary-hover" />
            <a href="#plan-comparison" className="inline-flex h-11 items-center justify-center rounded-full border border-line bg-card px-4 text-sm font-semibold text-charcoal">
              {t("Compare Plans")}
            </a>
            <a href="#plugins" className="inline-flex h-11 items-center justify-center rounded-full border border-line bg-card px-4 text-sm font-semibold text-charcoal">
              {t("Explore Plugins")}
            </a>
            <button
              type="button"
              onClick={() => onQuote(t("Contact sales about a published plan or plugin. This page does not create an invoice."))}
              className="inline-flex h-11 items-center justify-center rounded-full border border-line bg-card px-4 text-sm font-semibold text-charcoal"
            >
              {t("Contact Sales")}
            </button>
          </div>
        ) : null}

        {status === "loading" ? <PlanSkeleton /> : null}

        {status === "unavailable" ? (
          <p className="mt-8 rounded-card border border-line bg-card p-5 text-sm text-charcoal/70">
            {t("Published subscription prices are unavailable right now.")}
          </p>
        ) : null}

        {status === "ready" && plans.length === 0 ? (
          <p className="mt-8 rounded-card border border-line bg-card p-5 text-sm text-charcoal/70">
            {t("No current plans are published.")}
          </p>
        ) : null}

        {status === "ready" && plan && cycle ? (
          <>
            {showTrial && trialPlan ? (
              <div className="mt-8 rounded-card border border-primary/30 bg-card p-5">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">{t("Promotional trial")}</p>
                <h3 className="mt-2 text-xl font-semibold text-charcoal">
                  {t("Try {plan} free for {days} days", { plan: trialPlan.name, days: trial.days })}
                </h3>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-charcoal/70">
                  {t("Offered once, from the published trial settings. Your Free or other eligible plan stays in place. No payment and no automatic charge.")}
                  {trial.eligible_plans.length > 0
                    ? t(" Eligible plans: {plans}.", { plans: namesFor(plans, trial.eligible_plans).join(", ") })
                    : ""}
                </p>
              </div>
            ) : null}

            {countries.length > 1 ? (
              <div role="radiogroup" aria-label={t("Country")} className="mt-8 flex flex-wrap gap-2">
                {countries.map((item) => {
                  const selected = item === country;
                  return (
                    <button
                      key={item}
                      type="button"
                      role="radio"
                      aria-checked={selected}
                      onClick={() => setCountryCode(item)}
                      className={`inline-flex h-10 items-center rounded-full border px-4 text-sm font-semibold ${selected ? "border-primary bg-primary text-white" : "border-line bg-card text-charcoal"}`}
                    >
                      {regionName(item, locale)}
                    </button>
                  );
                })}
              </div>
            ) : null}
            {country ? (
              <p className="mt-3 text-sm text-charcoal/70">{t("Prices for {region} use the published country list.", { region: regionName(country, locale) })}</p>
            ) : null}

            {catalog.cycles.length > 0 ? (
              <div role="radiogroup" aria-label={t("Billing cycle")} className="mt-8 flex flex-wrap gap-2">
                {catalog.cycles.map((item) => {
                  const selected = item.code === cycle.code;
                  const bps =
                    item.code === "ANNUAL" && catalog.current_annual_discount_bps !== null
                      ? catalog.current_annual_discount_bps
                      : item.discount_bps;
                  return (
                    <button
                      key={item.code}
                      type="button"
                      role="radio"
                      aria-checked={selected}
                      onClick={() => setCycleCode(item.code)}
                      className={`inline-flex h-10 items-center rounded-full border px-4 text-sm font-semibold ${selected ? "border-primary bg-primary text-white" : "border-line bg-card text-charcoal"}`}
                    >
                      {t(item.name)}
                      {bps > 0 ? <span className={selected ? "ms-2 font-medium" : "ms-2 font-medium text-charcoal/60"}>{t("{percent}% off", { percent: bps / 100 })}</span> : null}
                    </button>
                  );
                })}
              </div>
            ) : null}
            {catalog.current_annual_discount_bps !== null && cycle.code === "ANNUAL" ? (
              <p className="mt-3 text-sm text-charcoal/70">
                {t("New plans use the published {percent}% annual discount. The amount shown is that published price.", {
                  percent: catalog.current_annual_discount_bps / 100,
                })}
              </p>
            ) : null}

            <motion.div
              className="mt-6 grid items-stretch gap-3 sm:grid-cols-2 xl:grid-cols-4"
              initial="hidden"
              whileInView="show"
              viewport={viewport}
              variants={stagger}
            >
              {plans.map((item) => (
                <PlanCard
                  key={item.code}
                  plan={item}
                  cycleName={cycle.name}
                  price={publishedPrice(item, cycle, catalog, country)}
                  monthly={monthlyCycle ? publishedPrice(item, monthlyCycle, catalog, country) : null}
                  annual={annualCycle ? publishedPrice(item, annualCycle, catalog, country) : null}
                  annualDiscountBps={annualCycle ? (catalog.current_annual_discount_bps ?? annualCycle.discount_bps) : 0}
                  selected={item.code === plan.code}
                  trialNote={showTrial && item.code === trial.plan_code ? `${trial.days}-day trial when eligible` : null}
                  onSelect={() => setCode(item.code)}
                  onQuote={onQuote}
                />
              ))}
            </motion.div>

            <Summary
              plan={plan}
              cycleName={cycle.name}
              price={publishedPrice(plan, cycle, catalog, country)}
              fees={fees}
              onQuote={onQuote}
            />

            {groups.length > 0 ? (
              <div id="plan-comparison" className="mt-10">
                <h3 className="text-lg font-semibold text-charcoal">{t("Included in each plan")}</h3>
                <p className="mt-1 max-w-3xl text-sm leading-6 text-charcoal/70">
                  {t("A check is a capability published on that plan. An optional add-on is purchased separately. A dash is not part of the plan.")}
                </p>
                <div role="radiogroup" aria-label={t("Business type")} className="mt-4 flex gap-2 overflow-x-auto pb-1">
                  <ProfileChoice label={t("All types")} selected={profile === "all"} onSelect={() => setProfile("all")} />
                  {BUSINESS_TYPE_ORDER.map((id) => (
                    <ProfileChoice
                      key={id}
                      label={t(PROFILE_PRESETS[id].shortLabel)}
                      selected={profile === id}
                      onSelect={() => setProfile(id)}
                    />
                  ))}
                </div>
                <div className="mt-4 space-y-6 md:hidden">
                  <p className="text-sm text-charcoal/70">{t("Showing {plan}. Choose another plan above to compare.", { plan: plan.name })}</p>
                  {groups.map((group) => (
                    <section key={group.label}>
                      <h4 className="text-xs font-semibold uppercase tracking-[0.14em] text-charcoal/60">{t(group.label)}</h4>
                      <ul className="mt-2 divide-y divide-line rounded-card border border-line bg-card">
                        {group.rows.map((row) => (
                          <li key={row.key} className="flex items-center justify-between gap-3 px-4 py-3">
                            <span className="text-sm font-medium text-charcoal">{t(moduleLabel(row.key))}</span>
                            <Availability plan={plan} row={row} addons={addons} onQuote={onQuote} />
                          </li>
                        ))}
                      </ul>
                    </section>
                  ))}
                </div>
                <div className="mt-4 hidden overflow-x-auto rounded-card border border-line bg-card md:block">
                  <table className="w-full min-w-[48rem] border-separate border-spacing-0 text-sm">
                    <caption className="sr-only">{t("Published plan comparison for {plans}", { plans: plans.map((item) => item.name).join(", ") })}</caption>
                    <thead>
                      <tr>
                        <th className="sticky start-0 z-20 border-b border-line bg-card px-4 py-3 text-start font-semibold text-charcoal">{t("Feature")}</th>
                        {plans.map((item) => (
                          <th key={item.code} className="border-b border-line bg-card px-3 py-3 text-start font-semibold text-charcoal">
                            {item.name}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {groups.map((group) => (
                        <Fragment key={group.label}>
                          <tr>
                            <th colSpan={plans.length + 1} scope="colgroup" className="border-b border-line bg-surface px-4 py-2 text-start text-xs font-semibold uppercase tracking-[0.14em] text-charcoal/60">
                              {t(group.label)}
                            </th>
                          </tr>
                          {group.rows.map((row) => (
                            <tr key={row.key}>
                              <th scope="row" className="sticky start-0 z-10 border-b border-line bg-card px-4 py-2.5 text-start font-medium text-charcoal">
                                {t(moduleLabel(row.key))}
                              </th>
                              {plans.map((item) => (
                                <td key={item.code} className="border-b border-line px-3 py-2.5 align-middle">
                                  <Availability plan={item} row={row} addons={addons} onQuote={onQuote} />
                                </td>
                              ))}
                            </tr>
                          ))}
                        </Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : null}

            {addons.length > 0 ? (
              <div id="plugins" className="mt-12">
                <h3 className="text-lg font-semibold text-charcoal">{t("Extend AxizPOS with optional plugins")}</h3>
                <p className="mt-1 max-w-3xl text-sm leading-6 text-charcoal/70">
                  {t("Optional plugins are purchased separately and are not automatically included in your base subscription.")}
                </p>
                <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {addons.map((addon) => (
                    <PluginCard key={addon.code} addon={addon} currency={priceCurrency} onQuote={onQuote} />
                  ))}
                </div>
              </div>
            ) : null}

            {legacy.length > 0 ? (
              <p className="mt-8 text-sm text-charcoal/60">
                {t("Existing {plans} subscriptions keep their current terms. They are not offered as new plans here.", { plans: legacy.join(", ") })}
              </p>
            ) : null}
          </>
        ) : null}
      </div>
    </section>
  );
}

function namesFor(plans: Plan[], codes: string[]): string[] {
  return codes.map((code) => plans.find((plan) => plan.code === code)?.name ?? code);
}

function PlanCard({
  plan,
  cycleName,
  price,
  monthly,
  annual,
  annualDiscountBps,
  selected,
  trialNote,
  onSelect,
  onQuote,
}: {
  plan: Plan;
  cycleName: string;
  price: ReturnType<typeof publishedPrice>;
  monthly: ReturnType<typeof publishedPrice> | null;
  annual: ReturnType<typeof publishedPrice> | null;
  annualDiscountBps: number;
  selected: boolean;
  trialNote: string | null;
  onSelect: () => void;
  onQuote: (note: string) => void;
}) {
  const limits = planLimitLines(plan);
  const accent = plan.code === "PRO_AI";
  const { t } = useLocale();
  const headline = priceLine(price, t);
  const cycleLabel = t(cycleName);
  return (
    <motion.article
      variants={rise}
      whileHover={lift}
      className={`flex h-full flex-col rounded-card border p-5 text-start ${selected ? "border-primary bg-primary/10" : accent ? "border-primary/30 bg-card" : "border-line bg-card"}`}
    >
      <button type="button" aria-pressed={selected} onClick={onSelect} className="flex flex-1 flex-col text-start">
        <span className="flex items-center justify-between gap-2">
          <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary/10 text-primary">
            <Mark name={PLAN_ICONS[plan.code] ?? "spark"} className="h-5 w-5" />
          </span>
          {isFreePlan(plan) ? <span className="text-xs font-semibold uppercase tracking-wide text-charcoal/60">{t("Start here")}</span> : null}
          {isCustomPlan(plan) ? <span className="text-xs font-semibold uppercase tracking-wide text-primary">{t("Custom")}</span> : null}
        </span>
        <h3 className="mt-4 text-2xl font-semibold text-charcoal">{plan.name}</h3>
        <p className="mt-3 text-3xl font-semibold text-charcoal">{headline}</p>
        <p className="mt-1 text-sm text-charcoal/70">
          {price.kind === "free"
            ? t("Forever")
            : price.kind === "custom"
              ? t("Priced on a contract")
              : price.kind === "priced"
                ? t("/ {cycle}", { cycle: cycleLabel }) + (price.discountBps > 0 ? ` · ${t("{percent}% off", { percent: price.discountBps / 100 })}` : "")
                : t("Published price unavailable")}
        </p>
        {monthly?.kind === "priced" && annual?.kind === "priced" && monthly.amountFils !== null && annual.amountFils !== null ? (
          <p className="mt-2 text-sm text-charcoal/70">
            {t("{amount} / month", { amount: money(monthly.amountFils, monthly.currency || "AED") })}
            {" · "}
            {t("{amount} / year", { amount: money(annual.amountFils, annual.currency || "AED") })}
            {annualDiscountBps > 0 ? ` · ${t("save {percent}%", { percent: annualDiscountBps / 100 })}` : ""}
          </p>
        ) : null}
        {limits.length > 0 ? (
          <ul className="mt-4 space-y-1 text-sm text-charcoal/75">
            {limits.map((limit) => (
              <li key={limit.key}>
                {t(limit.label)}: {limit.key === "sales_history_days" ? t("{count} days", { count: limit.text.replace(/ days$/, "") }) : limit.text}
              </li>
            ))}
          </ul>
        ) : null}
        {plan.included_modules.length > 0 ? (
          <ul className="mt-4 space-y-2 text-sm text-charcoal/75">
            {plan.included_modules.slice(0, 6).map((module) => (
              <li key={module} className="flex items-start gap-2">
                <Mark name="check" className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                <span>{t(moduleLabel(module))}</span>
              </li>
            ))}
          </ul>
        ) : null}
        {plan.included_modules.length > 6 ? (
          <p className="mt-2 text-sm text-charcoal/60">{t("{count} more included capabilities", { count: plan.included_modules.length - 6 })}</p>
        ) : null}
        {trialNote ? <p className="mt-4 text-sm font-medium text-primary">{trialNote}</p> : null}
        {isCustomPlan(plan) ? <p className="mt-4 text-sm text-charcoal/70">{t("Contact sales. A zero amount is not a purchase price.")}</p> : null}
      </button>
      <div className="mt-4">
        {isCustomPlan(plan) ? (
          <button
            type="button"
            onClick={() => onQuote(t("{plan}: custom pricing. Contact sales. This page does not create an invoice.", { plan: plan.name }))}
            className="inline-flex h-11 w-full items-center justify-center rounded-2xl bg-primary px-4 text-sm font-semibold text-white hover:bg-primary-hover"
          >
            {t("Contact Sales")}
          </button>
        ) : (
          <GetStartedLink className="inline-flex h-11 w-full items-center justify-center rounded-2xl bg-primary px-4 text-sm font-semibold text-white hover:bg-primary-hover" />
        )}
      </div>
    </motion.article>
  );
}

function priceLine(price: ReturnType<typeof publishedPrice>, t: (text: string, vars?: Record<string, string | number>) => string): string {
  if (price.kind === "custom") return t("Custom");
  if (price.kind === "free") return t("Free");
  if (price.kind === "unavailable" || price.amountFils === null) return "—";
  return money(price.amountFils, price.currency || "AED");
}

function ProfileChoice({ label, selected, onSelect }: { label: string; selected: boolean; onSelect: () => void }) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      onClick={onSelect}
      className={`inline-flex h-9 shrink-0 items-center rounded-full border px-3 text-sm font-semibold ${selected ? "border-primary bg-primary text-white" : "border-line bg-card text-charcoal"}`}
    >
      {label}
    </button>
  );
}

function Availability({
  plan,
  row,
  addons,
  onQuote,
}: {
  plan: Plan;
  row: ComparisonRow;
  addons: readonly Addon[];
  onQuote: (note: string) => void;
}) {
  const { t } = useLocale();
  const mark = comparisonMark(plan, row);
  if (mark === "included") {
    return (
      <span title={t("Included in this plan")} className="inline-flex items-center gap-1.5 text-sm font-medium text-primary">
        <Mark name="check" className="h-4 w-4" />
        <span className="sr-only lg:hidden">{t("Included")}</span>
        <span className="hidden lg:inline">{t("Included")}</span>
      </span>
    );
  }
  if (mark === "addon") {
    const plugin = addons.find((addon) => row.pluginCodes.includes(addon.code));
    const href = plugin ? `#plugin-${plugin.code}` : "#plugins";
    return (
      <a href={href} title={t("Purchased separately. Not included in this plan.")} className="text-sm font-medium text-charcoal/80 underline decoration-primary/40 underline-offset-2">
        {t("Optional add-on")}
      </a>
    );
  }
  if (mark === "custom") {
    return (
      <button
        type="button"
        title={t("Priced with an Enterprise contract")}
        onClick={() => onQuote(t("{plan}: {feature} is custom. This page does not create an invoice.", { plan: plan.name, feature: t(moduleLabel(row.key)) }))}
        className="text-sm font-medium text-primary underline decoration-primary/40 underline-offset-2"
      >
        {t("Custom")}
      </button>
    );
  }
  return (
    <span title={t("Not included in this plan")} className="text-sm text-charcoal/40">
      <span aria-hidden="true">—</span>
      <span className="sr-only">{t("Not included")}</span>
    </span>
  );
}

function PluginCard({ addon, currency, onQuote }: { addon: Addon; currency: string | null; onQuote: (note: string) => void }) {
  const { t } = useLocale();
  const price = addonPriceText(addon, currency);
  const types = businessTypeLabels(addon).map((label) => t(label));
  const quotedElsewhere = price === null && currency !== null && currency !== "AED" && (addon.monthly_fils > 0 || addon.one_time_fils > 0);
  return (
    <article id={`plugin-${addon.code}`} className="flex flex-col rounded-card border border-line bg-card p-5">
      <div className="flex items-start justify-between gap-3">
        <h4 className="text-base font-semibold text-charcoal">{addon.name}</h4>
        {addon.featured ? <span className="text-xs font-semibold uppercase tracking-wide text-primary">{t("Featured")}</span> : null}
      </div>
      {addon.category ? <p className="mt-1 text-xs font-semibold uppercase tracking-[0.14em] text-charcoal/50">{t(addon.category)}</p> : null}
      <p className="mt-2 text-sm leading-6 text-charcoal/70">{addon.short_description || addon.description}</p>
      {addon.benefits.length > 0 ? (
        <ul className="mt-3 space-y-1 text-sm text-charcoal/75">
          {addon.benefits.slice(0, 3).map((benefit) => (
            <li key={benefit.title || benefit.description}>{benefit.title || benefit.description}</li>
          ))}
        </ul>
      ) : null}
      {types.length > 0 ? <p className="mt-3 text-xs leading-5 text-charcoal/60">{t("Business types: {types}", { types: types.join(", ") })}</p> : null}
      <p className="mt-3 text-sm font-semibold text-charcoal">
        {addon.monthly_fils <= 0 && addon.one_time_fils <= 0
          ? t("No charge is published for this plugin.")
          : (price ?? (quotedElsewhere ? t("Price is quoted in the portal for this country.") : t("Price is not published.")))}
      </p>
      {price ? <p className="mt-1 text-xs text-charcoal/60">{addon.monthly_fils > 0 ? t("Billed monthly.") : t("One-time charge.")}</p> : null}
      <div className="mt-4">
        {addon.documentation_url ? (
          <a href={addon.documentation_url} className="text-sm font-semibold text-primary">
            {t("Learn more")}
          </a>
        ) : (
          <button
            type="button"
            onClick={() => onQuote(t("{name} plugin. Optional and priced separately. This page does not start a plugin subscription.", { name: addon.name }))}
            className="text-sm font-semibold text-primary"
          >
            {t("Learn more")}
          </button>
        )}
      </div>
    </article>
  );
}

function businessTypeLabels(addon: Addon): string[] {
  const names = new Set<string>();
  for (const key of addon.module_keys) {
    if (!isCapability(key)) continue;
    for (const profile of profilesFor(key)) names.add(PROFILE_PRESETS[profile].shortLabel);
  }
  return [...names];
}

function catalogCurrency(
  plans: readonly Plan[],
  cycle: PublicCatalog["cycles"][number] | undefined,
  catalog: PublicCatalog,
  country: string | null,
): string | null {
  if (!cycle) return country ? null : "AED";
  for (const plan of plans) {
    const price = publishedPrice(plan, cycle, catalog, country);
    if (price.currency) return price.currency;
  }
  return country ? null : "AED";
}

function Summary({
  plan,
  cycleName,
  price,
  fees,
  onQuote,
}: {
  plan: Plan;
  cycleName: string;
  price: ReturnType<typeof publishedPrice>;
  fees: { name: string; amount_fils: number }[];
  onQuote: (note: string) => void;
}) {
  const { t } = useLocale();
  const chargeFees = !isFreePlan(plan) && !isCustomPlan(plan) && price.kind === "priced" ? fees : [];
  const currency = price.currency || "AED";
  const feeTotal = chargeFees.reduce((sum, fee) => sum + fee.amount_fils, 0);
  const due = price.kind === "priced" && price.amountFils !== null ? price.amountFils + feeTotal : null;
  const note = summaryNote(plan, cycleName, price, chargeFees, t);
  return (
    <aside className="mt-6 rounded-card border border-line bg-card p-5">
      <h3 className="text-lg font-semibold text-charcoal">{plan.name}</h3>
      {price.kind === "free" ? (
        <p className="mt-2 text-sm leading-6 text-charcoal/70">
          {t("New stores start on {plan}. There is no payment and no invoice for this plan.", { plan: plan.name })}
        </p>
      ) : null}
      {price.kind === "custom" ? (
        <p className="mt-2 text-sm leading-6 text-charcoal/70">
          {t("{plan} is priced on a contract. This page does not create an invoice for it.", { plan: plan.name })}
        </p>
      ) : null}
      {price.kind === "priced" && price.amountFils !== null ? (
        <div className="mt-4 space-y-2 text-sm">
          <Row label={t("{name} · {cycle}", { name: plan.name, cycle: t(cycleName) })} value={money(price.amountFils, currency)} />
          {chargeFees.map((fee) => (
            <Row key={fee.name} label={t("{name} · once", { name: fee.name })} value={money(fee.amount_fils, currency)} />
          ))}
          {due !== null ? <Row label={t("Published total")} value={money(due, currency)} /> : null}
        </div>
      ) : null}
      <p className="mt-3 text-sm leading-6 text-charcoal/70">
        {t("Plugins and hardware are not part of this total. The portal quote is the amount due when you upgrade.")}
      </p>
      <div className="mt-4 flex flex-col gap-2 sm:flex-row">
        {isCustomPlan(plan) ? (
          <button
            type="button"
            onClick={() => onQuote(note)}
            className="inline-flex h-12 items-center justify-center rounded-2xl bg-primary px-5 text-sm font-semibold text-white hover:bg-primary-hover"
          >
            {t("Request a Quote")}
          </button>
        ) : (
          <GetStartedLink className="inline-flex h-12 items-center justify-center rounded-2xl bg-primary px-5 text-sm font-semibold text-white hover:bg-primary-hover" />
        )}
        {!isCustomPlan(plan) ? (
          <button
            type="button"
            onClick={() => onQuote(note)}
            className="inline-flex h-12 items-center justify-center rounded-2xl border border-line px-5 text-sm font-semibold text-charcoal"
          >
            {t("Request a Quote")}
          </button>
        ) : null}
      </div>
      <p className="mt-3 text-xs leading-5 text-charcoal/60">{t(GET_STARTED_NOTE)}</p>
    </aside>
  );
}

function summaryNote(
  plan: Plan,
  cycleName: string,
  price: ReturnType<typeof publishedPrice>,
  fees: { name: string; amount_fils: number }[],
  t: (text: string, vars?: Record<string, string | number>) => string,
): string {
  if (price.kind === "custom") return t("{plan}: custom pricing. Contact sales. This page does not create an invoice.", { plan: plan.name });
  if (price.kind === "free") return t("{plan}: no payment and no invoice.", { plan: plan.name });
  if (price.kind !== "priced" || price.amountFils === null) return t("{plan}: published price is unavailable.", { plan: plan.name });
  const currency = price.currency || "AED";
  const discount = price.discountBps > 0 ? t(" {percent}% off the package.", { percent: price.discountBps / 100 }) : "";
  const extras = fees.map((fee) => t(" {name} {amount} once.", { name: fee.name, amount: money(fee.amount_fils, currency) })).join("");
  return t("{plan}, {cycle}.{discount} Package {amount}.{extras} Plugins are separate. Not an invoice.", {
    plan: plan.name,
    cycle: t(cycleName),
    discount,
    amount: money(price.amountFils, currency),
    extras,
  }).slice(0, 500);
}

function regionName(code: string, locale: string): string {
  try {
    return new Intl.DisplayNames([locale], { type: "region" }).of(code) ?? code;
  } catch {
    return code;
  }
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-line py-2">
      <span className="text-charcoal/70">{label}</span>
      <span className="font-semibold tabular-nums text-charcoal">{value}</span>
    </div>
  );
}

function PlanSkeleton() {
  return (
    <div className="mt-8 grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-hidden="true">
      {["a", "b", "c", "d"].map((key) => (
        <div key={key} className="h-64 animate-pulse rounded-card border border-line bg-card" />
      ))}
    </div>
  );
}
