import { motion } from "framer-motion";
import { Minus, Plus } from "lucide-react";
import { useState } from "react";
import {
  aed,
  cycleAmount,
  estimate,
  estimateNote,
  STORE_MAX,
  STORE_MIN,
  type PublicCatalog,
} from "../catalog";
import { moduleLabel } from "../modules";
import { Mark, type MarkName } from "./icons";
import { lift, rise, stagger, viewport } from "./motion";
import { SectionHeading } from "./SectionHeading";

const PLAN_ICONS: Record<string, MarkName> = {
  LITE: "zap",
  STANDARD: "spark",
  PRO: "layers",
};

export function Pricing({
  catalog,
  live,
  onDemo,
  onQuote,
}: {
  catalog: PublicCatalog;
  live: boolean;
  onDemo: (note: string) => void;
  onQuote: (note: string) => void;
}) {
  const [code, setCode] = useState("STANDARD");
  const [stores, setStores] = useState(3);
  const [cycleCode, setCycleCode] = useState("ANNUAL");
  const [protection, setProtection] = useState(false);
  const plan = catalog.plans.find((item) => item.code === code) ?? catalog.plans[0];
  if (!plan) return null;
  const quote = estimate(plan, stores, catalog, cycleCode, { protection });
  const note = estimateNote(plan, quote);
  const hardware = catalog.addons.find((addon) => addon.code === "hardware_lease");
  const protectionAddon = catalog.addons.find((addon) => addon.code === "equipment_protection");
  const extra = catalog.addons.find((addon) => addon.code === "extra_register");
  const onboarding = catalog.fees.find((fee) => fee.code === "onboarding");
  const monthsLabel = quote.cycle.months === 1 ? "month" : "months";

  return (
    <section id="pricing" className="border-t border-line bg-surface">
      <div className="mx-auto max-w-page px-4 py-16 sm:px-6 lg:px-8 lg:py-20">
        <SectionHeading kicker="Pricing" title="See what AxizPOS costs.">
          {live
            ? "Prices from the console catalog. Choose a package and a billing cycle, then set the number of stores."
            : "Starting catalog. The console list loads when the API is reachable."}
        </SectionHeading>

        <motion.div
          className="mt-8 grid items-stretch gap-3 lg:grid-cols-3"
          initial="hidden"
          whileInView="show"
          viewport={viewport}
          variants={stagger}
        >
          {catalog.plans.map((item) => {
            const selected = item.code === plan.code;
            return (
              <motion.button
                key={item.code}
                type="button"
                variants={rise}
                whileHover={lift}
                whileTap={{ scale: 0.985 }}
                aria-pressed={selected}
                onClick={() => setCode(item.code)}
                className={`flex h-full flex-col rounded-card border p-5 text-left ${selected ? "border-primary bg-primary/10" : "border-line bg-card"}`}
              >
                <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                  <Mark name={PLAN_ICONS[item.code] ?? "spark"} className="h-5 w-5" />
                </span>
                <span className="mt-4 block text-xs font-semibold uppercase tracking-[0.14em] text-primary">{item.code}</span>
                <h3 className="mt-2 text-2xl font-semibold text-charcoal">{item.name}</h3>
                <p className="mt-3 text-3xl font-semibold text-charcoal">{aed(item.monthly_fils)}</p>
                <p className="mt-1 text-sm text-charcoal/70">
                  {`/ month · ${item.included_registers} ${item.included_registers === 1 ? "register" : "registers"} · ${item.trial_days}-day trial`}
                </p>
                <ul className="mt-4 space-y-2 text-sm text-charcoal/75">
                  {item.included_modules.map((module) => (
                    <li key={module} className="flex items-start gap-2">
                      <Mark name="check" className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                      <span>{moduleLabel(module)}</span>
                    </li>
                  ))}
                </ul>
                <p
                  className={`mt-auto pt-4 text-sm font-medium ${item.code === "STANDARD" ? "text-primary" : "invisible"}`}
                  aria-hidden={item.code === "STANDARD" ? undefined : true}
                >
                  New stores start on this trial.
                </p>
              </motion.button>
            );
          })}
        </motion.div>

        <div className="mt-6 grid items-start gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(18rem,0.85fr)]">
          <div className="space-y-4">
            <div className="rounded-card border border-line bg-card p-5">
              <h3 className="text-lg font-semibold text-charcoal">Billing cycle</h3>
              <p className="mt-1 text-sm leading-6 text-charcoal/70">
                The discount applies to the {plan.name} package. Hardware, onboarding, and deposits stay at face value.
              </p>
              <div role="radiogroup" aria-label="Billing cycle" className="mt-4 grid gap-3 sm:grid-cols-2">
                {catalog.cycles.map((cycle) => {
                  const selected = cycle.code === quote.cycle.code;
                  const perStore = cycleAmount(plan.monthly_fils, cycle.months, cycle.discount_bps);
                  const best = cycle.code === quote.bestValueCode;
                  return (
                    <button
                      key={cycle.code}
                      type="button"
                      role="radio"
                      aria-checked={selected}
                      onClick={() => setCycleCode(cycle.code)}
                      className={`rounded-2xl border p-4 text-left ${selected ? "border-primary bg-primary/10" : "border-line bg-surface"}`}
                    >
                      <span className="flex items-center justify-between gap-2">
                        <span className="text-sm font-semibold text-charcoal">{cycle.name}</span>
                        {best ? (
                          <span className="rounded-full border border-primary/40 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-primary">
                            Best value
                          </span>
                        ) : null}
                      </span>
                      <span className="mt-2 block text-xl font-semibold text-charcoal">{aed(perStore)}</span>
                      <span className="mt-1 block text-sm text-charcoal/70">
                        per store · {cycle.discount_bps / 100}% off
                        {cycle.months > 1 ? ` · ${cycle.months} months` : ""}
                      </span>
                      <span className="mt-2 block text-xs font-medium text-charcoal/60">
                        {selected ? "Selected" : "Select"}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="rounded-card border border-line bg-card p-5">
              <div className="flex items-end justify-between gap-4">
                <label htmlFor="store-count" className="text-lg font-semibold text-charcoal">
                  How many stores do you operate?
                </label>
                <p className="text-3xl font-semibold tabular-nums text-charcoal">{quote.stores}</p>
              </div>
              <div className="mt-4 flex items-center gap-3">
                <button
                  type="button"
                  aria-label="Fewer stores"
                  disabled={quote.stores <= STORE_MIN}
                  onClick={() => setStores((current) => Math.max(STORE_MIN, current - 1))}
                  className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-line bg-surface text-charcoal disabled:opacity-40"
                >
                  <Minus className="h-4 w-4" />
                </button>
                <input
                  id="store-count"
                  type="range"
                  min={STORE_MIN}
                  max={STORE_MAX}
                  value={quote.stores}
                  onChange={(event) => setStores(Number(event.target.value))}
                  className="h-11 w-full accent-primary"
                />
                <button
                  type="button"
                  aria-label="More stores"
                  disabled={quote.stores >= STORE_MAX}
                  onClick={() => setStores((current) => Math.min(STORE_MAX, current + 1))}
                  className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-line bg-surface text-charcoal disabled:opacity-40"
                >
                  <Plus className="h-4 w-4" />
                </button>
              </div>
              <p className="mt-3 text-sm text-charcoal/70">
                {quote.registers} included {quote.registers === 1 ? "register" : "registers"} · {plan.included_registers}{" "}
                {plan.included_registers === 1 ? "register" : "registers"} in each {plan.name} store. From {STORE_MIN} to{" "}
                {STORE_MAX} stores.
              </p>
            </div>

            <div className="rounded-card border border-line bg-card p-5">
              <h3 className="text-lg font-semibold text-charcoal">Add-ons and fees</h3>
              <div className="mt-4 space-y-3">
                {hardware ? (
                  <article className="rounded-2xl border border-line bg-surface p-4">
                    <div className="flex items-start justify-between gap-4">
                      <h4 className="text-sm font-semibold text-charcoal">{hardware.name}</h4>
                      <p className="shrink-0 text-right text-sm font-semibold text-charcoal">
                        {aed(hardware.monthly_fils)} / mo
                        {hardware.one_time_fils > 0 ? (
                          <span className="mt-0.5 block font-medium text-charcoal/70">+ {aed(hardware.one_time_fils)} deposit</span>
                        ) : null}
                      </p>
                    </div>
                    <p className="mt-2 text-sm leading-6 text-charcoal/70">{hardware.description}</p>
                    <p className="mt-2 text-sm text-charcoal/70">
                      This estimate includes one lease for each of the {quote.registers} included{" "}
                      {quote.registers === 1 ? "register" : "registers"}.
                    </p>
                  </article>
                ) : null}

                {protectionAddon ? (
                  <label className="block cursor-pointer rounded-2xl border border-line bg-surface p-4">
                    <span className="flex items-start justify-between gap-4">
                      <span className="flex items-start gap-3">
                        <input
                          type="checkbox"
                          className="mt-1 h-4 w-4 accent-primary"
                          checked={protection}
                          onChange={(event) => setProtection(event.target.checked)}
                        />
                        <span>
                          <span className="block text-sm font-semibold text-charcoal">{protectionAddon.name}</span>
                          <span className="mt-1 block text-sm leading-6 text-charcoal/70">{protectionAddon.description}</span>
                        </span>
                      </span>
                      <span className="shrink-0 text-sm font-semibold text-charcoal">{aed(protectionAddon.monthly_fils)} / mo</span>
                    </span>
                    <span className="mt-2 block text-sm text-charcoal/70">
                      {protection
                        ? `Included for all ${quote.registers} leased ${quote.registers === 1 ? "register" : "registers"}.`
                        : "Optional. Leave it off and it stays out of the total."}
                    </span>
                  </label>
                ) : null}

                {extra ? (
                  <article className="rounded-2xl border border-line bg-surface p-4">
                    <div className="flex items-start justify-between gap-4">
                      <h4 className="text-sm font-semibold text-charcoal">{extra.name}</h4>
                      <p className="shrink-0 text-sm font-semibold text-charcoal">{aed(extra.monthly_fils)} / mo</p>
                    </div>
                    <p className="mt-2 text-sm leading-6 text-charcoal/70">{extra.description}</p>
                    <p className="mt-2 text-sm text-charcoal/70">
                      {plan.name} already includes {plan.included_registers}{" "}
                      {plan.included_registers === 1 ? "register" : "registers"} per store. Extra registers are not part of
                      this estimate.
                    </p>
                  </article>
                ) : null}

                {onboarding ? (
                  <article className="rounded-2xl border border-line bg-surface p-4">
                    <div className="flex items-start justify-between gap-4">
                      <h4 className="text-sm font-semibold text-charcoal">{onboarding.name}</h4>
                      <p className="shrink-0 text-sm font-semibold text-charcoal">{aed(onboarding.amount_fils)} once / store</p>
                    </div>
                    <p className="mt-2 text-sm leading-6 text-charcoal/70">
                      Charged once for each store. The billing-cycle discount does not apply.
                    </p>
                  </article>
                ) : null}
              </div>
            </div>
          </div>

          <aside className="rounded-card border border-primary/40 bg-card p-5 lg:sticky lg:top-24 lg:max-h-[calc(100dvh-7rem)] lg:overflow-y-auto">
            <div className="lg:sticky lg:top-0 lg:z-10 lg:-mx-5 lg:-mt-5 lg:mb-2 lg:border-b lg:border-line lg:bg-card lg:px-5 lg:pb-4 lg:pt-5">
            <h3 className="text-lg font-semibold text-charcoal">Your estimated cost</h3>
            <p className="mt-1 text-sm text-charcoal/70">
              {plan.name} · {quote.cycle.name} · {quote.stores} {quote.stores === 1 ? "store" : "stores"} · {quote.registers}{" "}
              included {quote.registers === 1 ? "register" : "registers"}
            </p>
            <p className="mt-4 text-sm font-medium text-charcoal/70">Due at the start</p>
            <p className="mt-1 text-4xl font-semibold tabular-nums text-charcoal" aria-live="polite">
              {aed(quote.dueNowFils)}
            </p>
            {quote.depositFils !== null ? (
              <p className="mt-2 text-sm text-charcoal/70">Includes a refundable deposit of {aed(quote.depositFils)}.</p>
            ) : null}
            <p className="mt-1 text-sm text-charcoal/70">
              Next cycle, if nothing changes: {aed(quote.nextCycleFils)}. Onboarding and the deposit are not charged again.
            </p>
            </div>

            <h4 className="mt-6 text-sm font-semibold text-charcoal">Recurring this cycle</h4>
            <Row
              label={`${plan.name} package`}
              detail={`${aed(quote.perStoreFils)} / store for ${quote.cycle.months} ${monthsLabel} · ${aed(plan.monthly_fils * quote.stores)} / month before the discount`}
              value={aed(quote.packageFils)}
            />
            {quote.leaseCycleFils !== null && quote.leaseMonthlyFils !== null ? (
              <Row
                label="Hardware lease"
                detail={`${aed(quote.leaseMonthlyFils)} / month for ${quote.registers} included ${quote.registers === 1 ? "register" : "registers"} · face value for ${quote.cycle.months} ${monthsLabel}`}
                value={aed(quote.leaseCycleFils)}
              />
            ) : null}
            {quote.protectionCycleFils !== null && quote.protectionMonthlyFils !== null ? (
              <Row
                label="Equipment protection"
                detail={`${aed(quote.protectionMonthlyFils)} / month · face value for ${quote.cycle.months} ${monthsLabel}`}
                value={aed(quote.protectionCycleFils)}
              />
            ) : null}

            {quote.onboardingFils !== null ? (
              <>
                <h4 className="mt-5 text-sm font-semibold text-charcoal">One-time</h4>
                <Row
                  label="Onboarding"
                  detail={
                    quote.onboardingUnitFils !== null
                      ? `${aed(quote.onboardingUnitFils)} once per store · ${quote.stores} ${quote.stores === 1 ? "store" : "stores"}`
                      : "Charged once"
                  }
                  value={aed(quote.onboardingFils)}
                />
              </>
            ) : null}

            {quote.depositFils !== null ? (
              <>
                <h4 className="mt-5 text-sm font-semibold text-charcoal">Refundable</h4>
                <Row
                  label="Hardware deposit"
                  detail="Collected up front and kept separate from the package discount."
                  value={aed(quote.depositFils)}
                />
              </>
            ) : null}

            <div className="mt-5 rounded-2xl bg-surface p-4">
              {quote.savingFils > 0 ? (
                <p className="text-sm font-medium text-charcoal">
                  Save {aed(quote.savingFils)} on the package compared with monthly billing over {quote.cycle.months}{" "}
                  {monthsLabel}.
                </p>
              ) : (
                <p className="text-sm font-medium text-charcoal">Monthly billing has no cycle discount on the package.</p>
              )}
              <p className="mt-2 text-sm text-charcoal/70">
                Effective package price {aed(quote.perStoreFils)} per store this cycle
                {quote.cycle.months > 1 ? `, about ${aed(Math.round(quote.perStoreFils / quote.cycle.months))} per store each month` : ""}.
              </p>
              {quote.paybackMonths !== null ? (
                <p className="mt-2 text-sm text-charcoal/70">
                  That package discount covers onboarding in about {quote.paybackMonths.toFixed(1)} months. Deposits are not
                  part of the saving.
                </p>
              ) : null}
            </div>

            <div className="mt-5">
              <h4 className="text-base font-semibold text-charcoal">Ready to get started with AxizPOS?</h4>
              <p className="mt-1 text-sm leading-6 text-charcoal/70">
                This estimate is not a final quote. Contact the team to confirm the package, hardware, and onboarding.
              </p>
              <div className="mt-4 flex flex-col gap-2 sm:flex-row lg:flex-col xl:flex-row">
                <button
                  type="button"
                  onClick={() => onQuote(note)}
                  className="inline-flex h-12 items-center justify-center rounded-2xl bg-primary px-5 text-sm font-semibold text-white hover:bg-primary-hover"
                >
                  Request a Quote
                </button>
                <button
                  type="button"
                  onClick={() => onDemo(note)}
                  className="inline-flex h-12 items-center justify-center rounded-2xl border border-line px-5 text-sm font-semibold text-charcoal"
                >
                  Book a Demo
                </button>
              </div>
            </div>
          </aside>
        </div>
      </div>
    </section>
  );
}

function Row({ label, detail, value }: { label: string; detail: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-line py-3 text-sm">
      <p>
        <span className="font-medium text-charcoal">{label}</span>
        <span className="mt-0.5 block text-charcoal/60">{detail}</span>
      </p>
      <p className="shrink-0 font-semibold tabular-nums text-charcoal">{value}</p>
    </div>
  );
}
