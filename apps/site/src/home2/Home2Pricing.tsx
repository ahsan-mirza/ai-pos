import { Check, Minus, Sparkles } from "lucide-react";
import { Fragment, useEffect, useState } from "react";
import { capabilitySpec, isCapability } from "@ai-pos/shared-types";
import {
  comparisonMark,
  comparisonRows,
  defaultCountry,
  groupedComparison,
  isCustomPlan,
  loadCatalog,
  money,
  planLimitLines,
  publishedPrice,
  showcasePlans,
  EMPTY_CATALOG,
  type PublicCatalog,
} from "../catalog";
import { apiBaseUrl } from "../env";
import { GetStartedLink } from "../components/GetStartedLink";
import { CapabilityIcon, PLAN_ICONS } from "../capabilityIcon";
import { moduleLabel } from "../modules";
import { track } from "../track";

const MARK = {
  included: "Included",
  addon: "Add-on",
  custom: "Custom",
  absent: "Not included",
} as const;

export function Home2Pricing({ onContact }: { onContact: (note: string) => void }) {
  const [catalog, setCatalog] = useState<PublicCatalog>(EMPTY_CATALOG);
  const [status, setStatus] = useState<"loading" | "ready" | "unavailable">("loading");
  const [cycleCode, setCycleCode] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    loadCatalog(`${apiBaseUrl}/api/v1/billing/public-catalog`).then((result) => {
      if (cancelled) return;
      setCatalog(result.catalog);
      setStatus(result.live ? "ready" : "unavailable");
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const plans = showcasePlans(catalog);
  const cycle = catalog.cycles.find((item) => item.code === cycleCode) ?? catalog.cycles.find((item) => item.code === "MONTHLY") ?? catalog.cycles[0];
  const country = defaultCountry(catalog);
  const groups = groupedComparison(comparisonRows(plans, catalog.addons, null));

  return (
    <section className="h2-pricing" id="pricing" aria-labelledby="h2-pricing-title">
      <p className="h2-pricing-kicker">Simple and transparent pricing</p>
      <h2 id="h2-pricing-title">Choose the Right POS Plan for Your Business</h2>
      <p className="h2-pricing-lead">Start with the features your business needs and choose a plan that grows with your operations.</p>

      {status === "loading" ? <p className="h2-pricing-note">Loading the published catalog.</p> : null}
      {status === "unavailable" ? <p className="h2-pricing-note">Published subscription prices are unavailable right now. Amounts stay hidden until the catalog can be loaded.</p> : null}
      {status === "ready" && plans.length === 0 ? <p className="h2-pricing-note">No current plans are published.</p> : null}

      {status === "ready" && cycle && plans.length > 0 ? (
        <>
          {catalog.cycles.length > 1 ? (
            <div className="h2-cycles" role="radiogroup" aria-label="Billing period">
              {catalog.cycles.map((item) => {
                const selected = item.code === cycle.code;
                const sample = plans.find((plan) => !isCustomPlan(plan) && plan.code !== "FREE");
                const bps = sample ? publishedPrice(sample, item, catalog, country).discountBps : item.discount_bps;
                return (
                  <button
                    key={item.code}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    className={selected ? "is-on" : undefined}
                    onClick={() => {
                      setCycleCode(item.code);
                      track("click_billing_period", { billing_period: item.code });
                    }}
                  >
                    {item.name}
                    {bps > 0 ? <span>{bps / 100}% off</span> : null}
                  </button>
                );
              })}
            </div>
          ) : null}

          <div className="h2-plan-grid">
            {plans.map((plan) => {
              const price = publishedPrice(plan, cycle, catalog, country);
              const limits = planLimitLines(plan);
              return (
                <article key={plan.code} className="h2-plan">
                  <div className="h2-plan-name">
                    <PlanIcon code={plan.code} />
                    <h3>{plan.name}</h3>
                  </div>
                  {price.kind === "priced" && price.amountFils !== null ? (
                    <p key={cycle.code} className="h2-plan-price">
                      {money(price.amountFils, price.currency || "AED")}
                    </p>
                  ) : null}
                  <p className="h2-plan-cycle">
                    {price.kind === "free" ? "No subscription charge" : price.kind === "custom" ? "Contact sales. A zero amount is not a purchase price." : price.kind === "priced" ? cycle.name : "Price is not published for this period."}
                    {price.kind === "priced" && price.discountBps > 0 ? ` · ${price.discountBps / 100}% off` : ""}
                  </p>
                  {limits.length > 0 ? (
                    <ul>
                      {limits.map((limit) => (
                        <li key={limit.key}>
                          {limit.label}: {limit.text}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  {plan.included_modules.length > 0 ? (
                    <ul>
                      {plan.included_modules.map((module) => (
                        <li key={module}>
                          <CapabilityIcon id={module} size={16} />
                          {moduleLabel(module)}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  {isCustomPlan(plan) ? (
                    <button
                      type="button"
                      className="h2-btn"
                      onClick={() => {
                        track("click_contact_sales", { plan: plan.code });
                        onContact(`${plan.name}: custom pricing. Contact sales. This page does not create an invoice.`);
                      }}
                    >
                      Contact Sales
                    </button>
                  ) : (
                    <GetStartedLink className="h2-btn" />
                  )}
                </article>
              );
            })}
          </div>

          {groups.length > 0 ? (
            <div className="h2-compare">
              <h3>Included in each plan</h3>
              <p>A check is published on that plan. Add-on means it is sold separately. Custom is negotiated and is not a listed add-on.</p>
              <div className="h2-compare-scroll">
                <table>
                  <caption>Published plan comparison for {plans.map((plan) => plan.name).join(", ")}</caption>
                  <thead>
                    <tr>
                      <th scope="col">Feature</th>
                      {plans.map((plan) => (
                        <th key={plan.code} scope="col">
                          {plan.name}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {groups.map((group) => (
                      <Fragment key={group.label}>
                        <tr>
                          <th colSpan={plans.length + 1} scope="colgroup">
                            {group.label}
                          </th>
                        </tr>
                        {group.rows.map((row) => {
                          const detail = isCapability(row.key) ? capabilitySpec(row.key).description : moduleLabel(row.key);
                          return (
                            <tr key={row.key}>
                              <th scope="row" title={detail}>
                                <span className="h2-feature">
                                  <CapabilityIcon id={row.key} size={16} />
                                  {moduleLabel(row.key)}
                                </span>
                              </th>
                              {plans.map((plan) => {
                                const mark = comparisonMark(plan, row);
                                return (
                                  <td key={plan.code}>
                                    <span className={`h2-mark is-${mark}`} title={detail}>
                                      {mark === "included" ? <Check size={16} strokeWidth={2} aria-hidden="true" /> : null}
                                      {mark === "absent" ? <Minus size={16} strokeWidth={2} aria-hidden="true" /> : null}
                                      <span className="h2-sr">{MARK[mark]}</span>
                                      {mark === "addon" || mark === "custom" ? MARK[mark] : null}
                                    </span>
                                  </td>
                                );
                              })}
                            </tr>
                          );
                        })}
                      </Fragment>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}

function PlanIcon({ code }: { code: string }) {
  const Icon = PLAN_ICONS[code] ?? Sparkles;
  return <Icon size={20} strokeWidth={1.75} aria-hidden="true" />;
}
