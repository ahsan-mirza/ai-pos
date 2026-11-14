import { filterMarketplace, formatMoney, type MarketplaceCatalog, type MarketplaceItem, type MarketplaceSort } from "@ai-pos/shared-types";
import { useLocale } from "@ai-pos/ui";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ErrorNote, GhostButton, SearchField } from "../../components/ui/Field";
import { PluginCheckout } from "../billing/PluginCheckout";
import { AddonActions, AddonCard, AddonGlyph } from "../billing/subscription/AddonCard";
import { addonPriceView } from "../billing/subscription/display";
import { PriceDisplay } from "../billing/subscription/PriceDisplay";
import { MarketplaceStatus } from "../billing/subscription/SubscriptionStatus";
import { EmptyState, ErrorState, LoadingCards } from "../billing/subscription/States";
import { apiGet } from "../../lib/api";
import { errorMessage } from "../users/api";

export function AddonLibraryPage() {
  const { t } = useLocale();
  const [catalog, setCatalog] = useState<MarketplaceCatalog | null>(null);
  const [checkout, setCheckout] = useState<MarketplaceItem | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [deferred, setDeferred] = useState("");
  const [state, setState] = useState("");
  const [category, setCategory] = useState("");
  const [pricing, setPricing] = useState("");
  const [sort, setSort] = useState<MarketplaceSort>("recommended");

  useEffect(() => {
    const timer = window.setTimeout(() => setDeferred(query), 250);
    return () => window.clearTimeout(timer);
  }, [query]);

  const load = () => {
    setCatalog(null);
    setLoadError(null);
    apiGet<MarketplaceCatalog>("/api/v1/billing/marketplace")
      .then((next) => {
        setCatalog(next);
        setLoadError(null);
      })
      .catch((caught: unknown) => setLoadError(errorMessage(caught, "Could not load add-ons.")));
  };

  useEffect(() => {
    let cancelled = false;
    apiGet<MarketplaceCatalog>("/api/v1/billing/marketplace")
      .then((next) => {
        if (!cancelled) {
          setCatalog(next);
          setLoadError(null);
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) setLoadError(errorMessage(caught, "Could not load add-ons."));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const categories = useMemo(() => {
    const names = new Set<string>();
    for (const item of catalog?.items ?? []) {
      if (item.addon.listing?.category) names.add(item.addon.listing.category);
    }
    return [...names].sort();
  }, [catalog]);

  const items = useMemo(
    () => filterMarketplace(catalog?.items ?? [], deferred, state, category, pricing, sort),
    [catalog, deferred, state, category, pricing, sort],
  );

  return (
    <div className="flex w-full flex-col gap-5">
      <header>
        <h1 className="text-xl font-semibold text-charcoal dark:text-white">{t("Discover Add-ons")}</h1>
        <p className="mt-1 max-w-2xl text-sm text-charcoal/60 dark:text-white/60">
          {t("Extend your AxizPOS capabilities with powerful tools designed for your business.")}
        </p>
        {catalog ? (
          <p className="mt-3 text-sm text-charcoal/70 dark:text-white/70">
            {t("{count} available", { count: catalog.available })} · {t("{count} activated", { count: catalog.activated })} ·{" "}
            {t("{count} pending", { count: catalog.pending })}
            {catalog.recurring_fils > 0 ? (
              <>
                {" "}
                · <span dir="ltr">{formatMoney(catalog.recurring_fils, catalog.currency)}</span> {t("per month")}
              </>
            ) : null}
          </p>
        ) : null}
      </header>
      <SearchField
        label={t("Search add-ons")}
        placeholder={t("Search add-ons by name, feature or description...")}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      <div className="flex flex-wrap gap-2">
        <FilterSelect
          label={t("Status")}
          value={state}
          onChange={setState}
          options={[
            ["", t("All add-ons")],
            ["available", t("Available")],
            ["included", t("Included in package")],
            ["activated", t("Activated")],
            ["pending_payment", t("Pending payment")],
            ["pending_activation", t("Pending activation")],
          ]}
        />
        <FilterSelect
          label={t("Category")}
          value={category}
          onChange={setCategory}
          options={[["", t("All categories")], ...categories.map((name) => [name, name] as [string, string])]}
        />
        <FilterSelect
          label={t("Pricing")}
          value={pricing}
          onChange={setPricing}
          options={[
            ["", t("Any price")],
            ["monthly", t("Monthly")],
            ["once", t("One-time")],
            ["deposit", t("Refundable deposit")],
            ["unpriced", t("Price not set")],
          ]}
        />
        <FilterSelect
          label={t("Sort")}
          value={sort}
          onChange={(value) => setSort(value as MarketplaceSort)}
          options={[
            ["recommended", t("Recommended")],
            ["name", t("Name A–Z")],
            ["price_asc", t("Lowest price")],
            ["price_desc", t("Highest price")],
            ["recent", t("Recently updated")],
          ]}
        />
      </div>
      {loadError ? <ErrorState message={t(loadError)} onRetry={load} /> : null}
      {catalog === null && loadError === null ? <LoadingCards count={6} tall /> : null}
      {catalog && items.length === 0 ? (
        <EmptyState title={deferred.trim() ? t("No add-ons match that search.") : t("No add-ons are published for this view.")} />
      ) : null}
      <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
        {items.map((item) => (
          <li key={item.addon.id} className="min-w-0">
            <AddonCard item={item} currency={catalog?.currency || "AED"} onPurchase={() => setCheckout(item)} />
          </li>
        ))}
      </ul>
      {checkout ? (
        <PluginCheckout
          item={checkout}
          onClose={() => setCheckout(null)}
          onDone={() => {
            setCheckout(null);
            setCatalog(null);
            apiGet<MarketplaceCatalog>("/api/v1/billing/marketplace")
              .then(setCatalog)
              .catch(() => setCheckout(null));
          }}
        />
      ) : null}
    </div>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: readonly (readonly [string, string])[];
}) {
  return (
    <label className="text-xs font-medium text-charcoal/60 dark:text-white/60">
      {label}
      <select
        className="mt-1 block rounded-xl border border-line bg-white px-3 py-2 text-sm text-charcoal focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-100"
        value={value}
        aria-label={label}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map(([option, text]) => (
          <option key={option || "all"} value={option}>
            {text}
          </option>
        ))}
      </select>
    </label>
  );
}

export function AddonDetailPage() {
  const { t } = useLocale();
  const { code } = useParams();
  const navigate = useNavigate();
  const [catalog, setCatalog] = useState<MarketplaceCatalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checkoutOpen, setCheckoutOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiGet<MarketplaceCatalog>("/api/v1/billing/marketplace")
      .then((next) => {
        if (!cancelled) setCatalog(next);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(errorMessage(caught, "Could not load add-ons."));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const item = catalog?.items.find((row) => row.addon.code === code) ?? null;
  const listing = item?.addon.listing;

  if (error && catalog === null) return <ErrorState message={error} />;
  if (catalog === null) return <LoadingCards count={1} tall />;
  if (item === null) {
    return (
      <div className="grid gap-3">
        <EmptyState title={t("This add-on is not available.")} />
        <Link to="/settings/addons" className="text-sm font-medium text-accent">
          {t("Back to add-ons")}
        </Link>
      </div>
    );
  }

  return (
    <div className="flex w-full flex-col gap-6 text-charcoal dark:text-zinc-100">
      <Link to="/settings/addons" className="text-sm font-medium text-accent">
        {t("All add-ons")}
      </Link>
      <header className="flex flex-wrap items-start gap-4">
        <AddonGlyph item={item} />
        <div className="min-w-0 flex-1">
          <h1 className="text-xl font-semibold">{item.addon.name}</h1>
          <p className="mt-1 text-sm text-charcoal/70 dark:text-zinc-300" dir="auto">{listing?.short_description || item.addon.description}</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {listing?.category ? <p className="text-xs font-medium uppercase tracking-wide text-charcoal/50">{listing.category}</p> : null}
            <MarketplaceStatus state={item.state} />
          </div>
          <div className="mt-2">
            <PriceDisplay view={addonPriceView(item, catalog.currency)} />
          </div>
        </div>
      </header>
      <ErrorNote message={error} />
      <Section title={t("Overview")}>
        <p className="text-sm text-charcoal/80 dark:text-zinc-300">{listing?.overview || item.addon.description || t("No overview yet.")}</p>
      </Section>
      <PointList title={t("Benefits")} rows={listing?.benefits ?? []} />
      <PointList title={t("Features")} rows={listing?.features ?? []} />
      <PointList title={t("How it works")} rows={listing?.steps ?? []} />
      <Section title={t("Compatibility")}>
        <p className="text-sm text-charcoal/80 dark:text-zinc-300">
          {item.compatible_labels.length > 0 ? item.compatible_labels.join(" · ") : t("Available with the current packages.")}
        </p>
      </Section>
      <Section title={t("Pricing")}>
        <PriceDisplay view={addonPriceView(item, catalog.currency)} />
        <p className="mt-2 text-sm text-charcoal/60">{t("Amounts are the catalogue prices.")}</p>
        {item.invoice_id ? (
          <p className="mt-2 text-sm text-charcoal/60">
            {t("Invoice")} <span dir="ltr">{item.invoice_id}</span>
          </p>
        ) : null}
      </Section>
      {(listing?.requirements.length ?? 0) > 0 ? (
        <Section title={t("Requirements")}>
          <ul className="list-disc space-y-1 ps-5 text-sm text-charcoal/80 dark:text-zinc-300">
            {listing?.requirements.map((row) => (
              <li key={row}>{row}</li>
            ))}
          </ul>
        </Section>
      ) : null}
      <Section title={t("Support")}>
        <div className="space-y-2 text-sm text-charcoal/80 dark:text-zinc-300">
          {listing?.support ? <p>{listing.support}</p> : <p>{t("Use the existing AxizPOS support contact.")}</p>}
          {listing?.documentation_url ? (
            <a className="block text-accent" href={listing.documentation_url} rel="noreferrer">
              {t("Documentation")}
            </a>
          ) : null}
          {listing?.video_url ? (
            <a className="block text-accent" href={listing.video_url} rel="noreferrer">
              {t("Video")}
            </a>
          ) : null}
        </div>
        {(listing?.faqs.length ?? 0) > 0 ? (
          <dl className="mt-4 space-y-3">
            {listing?.faqs.map((faq) => (
              <div key={faq.question}>
                <dt className="text-sm font-medium">{faq.question}</dt>
                <dd className="text-sm text-charcoal/70 dark:text-zinc-300">{faq.answer}</dd>
              </div>
            ))}
          </dl>
        ) : null}
      </Section>
      <div className="sticky bottom-0 flex flex-wrap items-center gap-3 rounded-2xl border border-line bg-white p-4 dark:border-zinc-600 dark:bg-zinc-900">
        <AddonActions item={item} onPurchase={() => setCheckoutOpen(true)} />
        <GhostButton onClick={() => navigate("/settings/addons")}>{t("Close")}</GhostButton>
      </div>
      {checkoutOpen ? (
        <PluginCheckout
          item={item}
          onClose={() => setCheckoutOpen(false)}
          onDone={() => {
            setCheckoutOpen(false);
            navigate("/subscription");
          }}
        />
      ) : null}
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h2 className="text-sm font-semibold">{title}</h2>
      <div className="mt-2">{children}</div>
    </section>
  );
}

function PointList({ title, rows }: { title: string; rows: readonly { title: string; description: string }[] }) {
  if (rows.length === 0) return null;
  return (
    <Section title={title}>
      <ul className="grid gap-3 sm:grid-cols-2">
        {rows.map((row) => (
          <li key={`${row.title}-${row.description}`} className="rounded-2xl border border-line bg-white p-3 dark:border-zinc-800 dark:bg-zinc-900">
            <p className="text-sm font-medium">{row.title}</p>
            {row.description ? <p className="mt-1 text-sm text-charcoal/70 dark:text-zinc-300">{row.description}</p> : null}
          </li>
        ))}
      </ul>
    </Section>
  );
}
