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
    <section id="pricing" className="bg-white/[0.02] py-24">
      <div className="mx-auto max-w-page px-5 lg:px-8">
        <SectionHeading kicker="Console catalog" title="Packages, cycles, and add-ons." />
        <p className="mt-3 text-sm text-mist">
          {live ? "Prices from the console catalog." : "Starting catalog. The console list loads when the API is reachable."}
        </p>
        <div className="mt-8 grid gap-3 lg:grid-cols-3">
          {catalog.plans.map((item) => {
            const selected = item.code === plan.code;
            return (
              <button
                key={item.code}
                type="button"
                onClick={() => setCode(item.code)}
                className={`rounded-2xl border p-5 text-left ${selected ? "border-emerald-400 bg-emerald-400/10" : "border-white/10 bg-ink/40"}`}
              >
                <span className="text-xs uppercase tracking-[0.16em] text-glow">{item.code}</span>
                <h3 className="mt-2 text-2xl font-semibold">{item.name}</h3>
                <p className="mt-3 text-3xl font-semibold">{aed(item.monthly_fils)}</p>
                <p className="mt-1 text-sm text-mist">
                  / month · {item.included_registers} {item.included_registers === 1 ? "register" : "registers"} ·{" "}
                  {item.trial_days}-day trial
                </p>
                <ul className="mt-4 space-y-1 text-sm text-mist">
                  {item.included_modules.map((module) => (
                    <li key={module}>{moduleLabel(module)}</li>
                  ))}
                </ul>
                {item.code === "STANDARD" && <p className="mt-4 text-sm text-emerald-300">New stores start on this trial.</p>}
              </button>
            );
          })}
        </div>

        <div className="mt-4 grid gap-3 lg:grid-cols-[1.05fr_0.95fr]">
          <div className="rounded-2xl border border-white/10 p-5">
            <h3 className="text-lg font-semibold">Billing cycles for {plan.name}</h3>
            <p className="mt-2 text-sm text-mist">
              The discount applies to the recurring package. Deposits and onboarding stay at face value.
            </p>
            <div className="mt-4">
              {catalog.cycles.map((cycle) => (
                <div key={cycle.code} className="flex items-baseline justify-between gap-4 border-b border-white/10 py-3 text-sm">
                  <p>
                    {cycle.name}
                    <span className="mt-0.5 block text-mist">{cycle.discount_bps / 100}% off</span>
                  </p>
                  <p>{aed(cycleAmount(plan.monthly_fils, cycle.months, cycle.discount_bps))} / store</p>
                </div>
              ))}
            </div>
            <h3 className="mt-6 text-lg font-semibold">Add-ons and fees</h3>
            <div className="mt-2">
              {catalog.addons.map((addon) => (
                <div key={addon.code} className="flex items-baseline justify-between gap-4 border-b border-white/10 py-3 text-sm">
                  <p>
                    {addon.name}
                    <span className="mt-0.5 block text-mist">{addon.description}</span>
                  </p>
                  <p className="shrink-0 text-right">
                    {aed(addon.monthly_fils)} / mo
                    {addon.one_time_fils > 0 ? ` + ${aed(addon.one_time_fils)}` : ""}
                  </p>
                </div>
              ))}
              {catalog.fees.map((fee) => (
                <div key={fee.code} className="flex items-baseline justify-between gap-4 border-b border-white/10 py-3 text-sm">
                  <p>{fee.name}</p>
                  <p>{aed(fee.amount_fils)} once</p>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-cyan-400/30 p-5">
            <h3 className="text-lg font-semibold">Estimate for {plan.name}</h3>
            <label htmlFor="store-count" className="mt-4 block text-sm text-mist">
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
            <p className="mt-4 text-xs leading-5 text-mist">
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
    <div className="flex items-baseline justify-between gap-4 border-b border-white/10 py-3 text-sm">
      <p className="text-mist">{label}</p>
      <p className="font-semibold">{value}</p>
    </div>
  );
}
