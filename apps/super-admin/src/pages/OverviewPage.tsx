import type { ConsoleOverview } from "@ai-pos/shared-types";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { PageHeader } from "../components/PageHeader";
import { ErrorNote } from "../components/ui";
import { api, errorText } from "../lib/api";
import { money } from "../lib/format";

function aed(fils: number): string {
  return money(fils, "AED");
}

const cards: { key: keyof ConsoleOverview; label: string; hint: string; money?: boolean }[] = [
  { key: "tenants", label: "Tenants", hint: "Every store account" },
  { key: "paying_subscriptions", label: "Paying", hint: "Status is active" },
  { key: "trialing", label: "Trials", hint: "Not included in MRR" },
  { key: "trials_ending_14d", label: "Trials ending", hint: "Within 14 days" },
  { key: "past_due", label: "Past due", hint: "Still in MRR" },
  { key: "suspended_tenants", label: "Suspended", hint: "Access paused, data kept" },
  { key: "mrr_fils", label: "MRR", hint: "Monthly equivalent", money: true },
  { key: "arr_fils", label: "ARR", hint: "MRR × 12", money: true },
  { key: "unpaid_checkouts_fils", label: "Unpaid checkouts", hint: "Pending go-live invoices", money: true },
  { key: "stores", label: "Stores", hint: "Last collected stats" },
  { key: "registers", label: "Registers", hint: "Last collected stats" },
  { key: "open_change_requests", label: "Open requests", hint: "Waiting on the console" },
];

export function OverviewPage() {
  const [data, setData] = useState<ConsoleOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api
      .get<ConsoleOverview>("/overview")
      .then(setData)
      .catch((caught: unknown) => setError(errorText(caught, "Could not load the overview.")));
  }, []);
  const peak = Math.max(1, ...(data?.by_plan.map((row) => row.mrr_fils) ?? [1]));
  return (
    <section>
      <PageHeader
        title="Overview"
        description="Subscription health from the control database. Trials, deposits, and one-time fees stay out of recurring revenue."
      />
      <ErrorNote message={error} />
      {data ? (
        <>
          <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {cards.map((card) => {
              const value = data[card.key];
              return (
                <article key={card.key} className="rounded-3xl border border-line bg-white px-5 py-4">
                  <p className="text-xs font-semibold uppercase tracking-wide text-charcoal/50">{card.label}</p>
                  <p className="mt-2 text-2xl font-semibold tabular-nums">
                    {card.money && typeof value === "number" ? aed(value) : String(value)}
                  </p>
                  <p className="mt-1 text-xs text-charcoal/50">{card.hint}</p>
                </article>
              );
            })}
          </div>
          <div className="mt-6 grid gap-4 lg:grid-cols-2">
            <article className="rounded-3xl border border-line bg-white p-5">
              <h2 className="text-sm font-semibold">Recurring revenue by package</h2>
              <ul className="mt-4 space-y-3">
                {data.by_plan.length === 0 ? <li className="text-sm text-charcoal/50">No paying subscriptions yet.</li> : null}
                {data.by_plan.map((row) => (
                  <li key={row.plan_code}>
                    <div className="flex items-baseline justify-between gap-3 text-sm">
                      <span className="font-medium">{row.plan_name}</span>
                      <span className="tabular-nums">
                        {aed(row.mrr_fils)} · {row.paying_tenants}
                      </span>
                    </div>
                    <div className="mt-1 h-2 overflow-hidden rounded-full bg-surface">
                      <div className="h-full rounded-full bg-accent" style={{ width: `${Math.round((row.mrr_fils / peak) * 100)}%` }} />
                    </div>
                  </li>
                ))}
              </ul>
            </article>
            <article className="rounded-3xl border border-line bg-white p-5">
              <h2 className="text-sm font-semibold">Subscription status</h2>
              <ul className="mt-4 divide-y divide-line text-sm">
                {data.by_status.map((row) => (
                  <li key={row.status} className="flex items-center justify-between py-2 capitalize">
                    <span>{row.status.replace("_", " ")}</span>
                    <span className="tabular-nums font-semibold">{row.tenants}</span>
                  </li>
                ))}
              </ul>
              <p className="mt-4 text-sm text-charcoal/60">
                {data.new_tenants_30d} new in 30 days · {data.practice_tenants} still in practice mode · {data.canceled} canceled
              </p>
              <Link to="/subscriptions" className="mt-3 inline-block text-sm font-semibold text-accent">
                Open subscriptions
              </Link>
            </article>
          </div>
          <ul className="mt-6 space-y-1 text-xs text-charcoal/50">
            {data.definitions.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </>
      ) : error ? null : (
        <p className="mt-6 text-sm text-charcoal/50">Loading the control database…</p>
      )}
    </section>
  );
}
