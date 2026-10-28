import type { BillingCatalog, ConsoleOverview, HardwareItem, ModuleSummary } from "@ai-pos/shared-types";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { PageHeader } from "../components/PageHeader";
import { ErrorNote } from "../components/ui";
import { api, errorText } from "../lib/api";
import { money } from "../lib/format";

interface Snapshot {
  catalog: BillingCatalog;
  hardware: HardwareItem[];
  summary: ModuleSummary;
  overview: ConsoleOverview;
}

export function CataloguePage() {
  const [data, setData] = useState<Snapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      api.get<BillingCatalog>("/billing/catalog"),
      api.get<HardwareItem[]>("/hardware/items"),
      api.get<ModuleSummary>("/modules/summary"),
      api.get<ConsoleOverview>("/overview"),
    ])
      .then(([catalog, hardware, summary, overview]) => {
        if (cancelled) return;
        setData({ catalog, hardware, summary, overview });
        setError(null);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(errorText(caught, "Could not load the catalogue."));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const publishedPlans = data?.catalog.plans.filter((plan) => plan.active).length ?? 0;
  const activeAddons = data?.catalog.addons.filter((addon) => addon.active).length ?? 0;
  const availableHardware = data?.hardware.filter((item) => item.available).length ?? 0;

  return (
    <section>
      <PageHeader
        title="Catalogue"
        description="Packages, hardware, and add-ons published from here are what the public site and checkout use."
      />
      <ErrorNote message={error} />
      {loading && data === null ? <p className="text-sm text-charcoal/60">Loading catalogue…</p> : null}
      {data ? (
        <>
          <dl className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            <Metric label="Published packages" value={String(publishedPlans)} hint={`${data.catalog.plans.length} in the catalogue`} href="/packages" />
            <Metric label="Active add-ons" value={String(activeAddons)} hint={`${data.summary.mapped_addons} mapped to a module`} href="/addons" />
            <Metric label="Available hardware" value={String(availableHardware)} hint={`${data.hardware.length} products`} href="/hardware" />
            <Metric
              label="Active subscriptions"
              value={String(data.summary.active_subscriptions)}
              hint={`${data.summary.trialing_subscriptions} on trial`}
              href="/subscriptions"
            />
            <Metric label="Pending verifications" value={String(data.summary.pending_payments)} hint="Receipts awaiting review" href="/payments" />
            <Metric
              label="Monthly recurring revenue"
              value={money(data.overview.mrr_fils, data.overview.currency)}
              hint="Active subscriptions. Trials, deposits, and one-time fees are excluded."
              href="/subscriptions"
            />
          </dl>
          <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Shortcut to="/packages" title="Packages" text="Prices, registers, trials, and what is published." />
            <Shortcut to="/billing" title="Billing cycles" text="Discounts on recurring charges, and the onboarding fee." />
            <Shortcut to="/hardware" title="Hardware" text="Lease, purchase, and refundable deposits." />
            <Shortcut to="/addons" title="Add-ons" text="Recurring rent, one-time charges, and module mapping." />
          </div>
        </>
      ) : null}
    </section>
  );
}

function Metric({ label, value, hint, href }: { label: string; value: string; hint: string; href: string }) {
  return (
    <div className="rounded-2xl border border-line bg-white px-5 py-4 shadow-sm">
      <dt className="text-xs font-semibold uppercase tracking-wide text-charcoal/50">{label}</dt>
      <dd className="mt-2 text-2xl font-semibold tabular-nums">{value}</dd>
      <p className="mt-1 text-xs text-charcoal/50">{hint}</p>
      <Link to={href} className="mt-3 inline-block text-xs font-semibold text-accent">
        Manage
      </Link>
    </div>
  );
}

function Shortcut({ to, title, text }: { to: string; title: string; text: string }) {
  return (
    <Link to={to} className="rounded-2xl border border-line bg-white p-4 shadow-sm hover:border-accent/40">
      <span className="block text-sm font-semibold">{title}</span>
      <span className="mt-1 block text-xs leading-5 text-charcoal/60">{text}</span>
    </Link>
  );
}
