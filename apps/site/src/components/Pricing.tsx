import { useState } from "react";
import { aed, cycleAmount, estimate, type PublicCatalog } from "../catalog";
import { moduleLabel } from "../modules";
import { SectionHeading } from "./SectionHeading";

export function Pricing({ catalog, live }: { catalog: PublicCatalog; live: boolean }) {
  const [code, setCode] = useState("STANDARD");
  const [stores, setStores] = useState(3);
  const plan = catalog.plans.find((item) => item.code === code) ?? catalog.plans[0];
  if (!plan) return null;
  const quote = estimate(plan, stores, catalog);

  return (
    <section id="pricing" className="border-t border-line bg-surface">
      <div className="mx-auto max-w-page px-4 py-16 sm:px-6 lg:px-8 lg:py-20">
        <SectionHeading kicker="Pricing" title="Packages from the live catalog.">
          {live ? "Prices from the console catalog." : "Starting catalog. The console list loads when the API is reachable."}
        </SectionHeading>
        <div className="mt-8 grid gap-3 lg:grid-cols-3">
          {catalog.plans.map((item) => {
            const selected = item.code === plan.code;
            return (
              <button
                key={item.code}
                type="button"
                onClick={() => setCode(item.code)}
                className={`rounded-card border p-5 text-left ${selected ? "border-primary bg-primary/10" : "border-line bg-card"}`}
              >
                <span className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">{item.code}</span>
                <h3 className="mt-2 text-2xl font-semibold text-charcoal">{item.name}</h3>
                <p className="mt-3 text-3xl font-semibold text-charcoal">{aed(item.monthly_fils)}</p>
                <p className="mt-1 text-sm text-charcoal/70">
                  {`/ month · ${item.included_registers} ${item.included_registers === 1 ? "register" : "registers"} · ${item.trial_days}-day trial`}
                </p>
                <ul className="mt-4 space-y-1 text-sm text-charcoal/75">
                  {item.included_modules.map((module) => (
                    <li key={module}>{moduleLabel(module)}</li>
                  ))}
                </ul>
                {item.code === "STANDARD" && <p className="mt-4 text-sm font-medium text-primary">New stores start on this trial.</p>}
              </button>
            );
          })}
        </div>

        <div className="mt-4 grid gap-3 lg:grid-cols-[1.05fr_0.95fr]">
          <div className="rounded-card border border-line bg-card p-5">
            <h3 className="text-lg font-semibold text-charcoal">Billing cycles for {plan.name}</h3>
            <p className="mt-2 text-sm text-charcoal/70">
              The discount applies to the recurring package. Deposits and onboarding stay at face value.
            </p>
            <div className="mt-4">
              {catalog.cycles.map((cycle) => (
                <div key={cycle.code} className="flex items-baseline justify-between gap-4 border-b border-line py-3 text-sm">
                  <p>
                    {cycle.name}
                    <span className="mt-0.5 block text-charcoal/60">{cycle.discount_bps / 100}% off</span>
                  </p>
                  <p>{aed(cycleAmount(plan.monthly_fils, cycle.months, cycle.discount_bps))} / store</p>
                </div>
              ))}
            </div>
            <h3 className="mt-6 text-lg font-semibold text-charcoal">Add-ons and fees</h3>
            <div className="mt-2">
              {catalog.addons.map((addon) => (
                <div key={addon.code} className="flex items-baseline justify-between gap-4 border-b border-line py-3 text-sm">
                  <p>
                    {addon.name}
                    <span className="mt-0.5 block text-charcoal/60">{addon.description}</span>
                  </p>
                  <p className="shrink-0 text-right">
                    {aed(addon.monthly_fils)} / mo
                    {addon.one_time_fils > 0 ? ` + ${aed(addon.one_time_fils)}` : ""}
                  </p>
                </div>
              ))}
              {catalog.fees.map((fee) => (
                <div key={fee.code} className="flex items-baseline justify-between gap-4 border-b border-line py-3 text-sm">
                  <p>{fee.name}</p>
                  <p>{aed(fee.amount_fils)} once</p>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-card border border-primary/40 bg-card p-5">
            <h3 className="text-lg font-semibold text-charcoal">Estimate for {plan.name}</h3>
            <label htmlFor="store-count" className="mt-4 block text-sm text-charcoal/70">
              Stores: {stores}
            </label>
            <input
              id="store-count"
              type="range"
              min={1}
              max={24}
              value={stores}
              onChange={(event) => setStores(Number(event.target.value))}
              className="mt-2 w-full"
            />
            <div className="mt-4">
              <Row label="Package / month" value={aed(quote.software)} />
              {quote.lease !== null && <Row label="Hardware lease / month" value={aed(quote.lease)} />}
              {quote.deposit !== null && <Row label="Refundable deposits" value={aed(quote.deposit)} />}
              {quote.saving !== null && <Row label={`Saved on ${quote.cycleName ?? "annual"}`} value={`${aed(quote.saving)} / cycle`} />}
              {quote.paybackMonths !== null && (
                <Row label="Onboarding covered by that saving" value={`${quote.paybackMonths.toFixed(1)} months`} />
              )}
            </div>
            <p className="mt-4 text-xs leading-5 text-charcoal/60">
              One hardware lease per included register ({quote.registers}{" "}
              {quote.registers === 1 ? "register" : "registers"}).
              {quote.discountPercent !== null
                ? ` ${quote.cycleName ?? "Annual"} takes ${quote.discountPercent}% off the package for that cycle.`
                : ""}{" "}
              Payback divides the onboarding fee by the monthly value of that discount. Deposits are not part of the saving.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-line py-3 text-sm">
      <p className="text-charcoal/70">{label}</p>
      <p className="font-semibold">{value}</p>
    </div>
  );
}
