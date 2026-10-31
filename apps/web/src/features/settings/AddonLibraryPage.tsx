import {
  filterMarketplace,
  formatMoney,
  type MarketplaceCatalog,
  type MarketplaceItem,
  type MarketplaceSort,
} from "@ai-pos/shared-types";
import {
  CreditCard,
  Hash,
  Landmark,
  Layers,
  Monitor,
  Puzzle,
  Receipt,
  Shield,
  Truck,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ErrorNote, GhostButton, PrimaryButton, SearchField } from "../../components/ui/Field";
import { moduleDestination } from "../../components/layout/navigation";
import { apiGet, apiPost } from "../../lib/api";
import { errorMessage } from "../users/api";

const ICONS: Record<string, LucideIcon> = {
  monitor: Monitor,
  hash: Hash,
  layers: Layers,
  landmark: Landmark,
  truck: Truck,
  "credit-card": CreditCard,
  receipt: Receipt,
  shield: Shield,
  puzzle: Puzzle,
};

const STATE_LABEL: Record<MarketplaceItem["state"], string> = {
  included: "Included",
  available: "Available",
  activated: "Activated",
  pending_payment: "Pending payment",
  pending_activation: "Pending activation",
  expired: "Expired",
  unavailable: "Unavailable",
  unpriced: "Available",
};

function AddonMark({ item }: { item: MarketplaceItem }) {
  const listing = item.addon.listing;
  const [broken, setBroken] = useState(false);
  const Icon = ICONS[listing?.icon ?? ""] ?? Puzzle;
  if (listing?.image_url && !broken) {
    return (
      <img
        src={listing.image_url}
        alt=""
        className="h-11 w-11 rounded-xl border border-line object-cover"
        onError={() => setBroken(true)}
      />
    );
  }
  return (
    <span className="flex h-11 w-11 items-center justify-center rounded-xl border border-line bg-surface text-charcoal/70">
      <Icon className="h-5 w-5" aria-hidden="true" />
    </span>
  );
}

function priceLabel(item: MarketplaceItem): string {
  const addon = item.addon;
  if (item.state === "unpriced") return "Price configured by administrator.";
  const parts: string[] = [];
  if (addon.monthly_fils > 0) parts.push(`${formatMoney(addon.monthly_fils, "AED")} / month`);
  if (addon.one_time_fils > 0) {
    parts.push(
      addon.refundable
        ? `${formatMoney(addon.one_time_fils, "AED")} refundable deposit`
        : `${formatMoney(addon.one_time_fils, "AED")} one-time`,
    );
  }
  return parts.join(" · ") || "No extra charge";
}

function canPurchase(item: MarketplaceItem): boolean {
  return item.state === "available" && item.addon.module_keys.length > 0 && item.addon.monthly_fils > 0;
}

export function AddonLibraryPage() {
  const navigate = useNavigate();
  const [catalog, setCatalog] = useState<MarketplaceCatalog | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [deferred, setDeferred] = useState("");
  const [state, setState] = useState("");
  const [category, setCategory] = useState("");
  const [pricing, setPricing] = useState("");
  const [sort, setSort] = useState<MarketplaceSort>("recommended");
  const [busyCode, setBusyCode] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => setDeferred(query), 250);
    return () => window.clearTimeout(timer);
  }, [query]);

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
        if (!cancelled) setLoadError(errorMessage(caught, "The add-on marketplace could not be loaded."));
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

  const purchase = async (item: MarketplaceItem) => {
    if (!canPurchase(item) || busyCode !== null) return;
    setBusyCode(item.addon.code);
    setError(null);
    try {
      await apiPost(`/api/v1/billing/addons/${item.addon.code}/checkout`, {});
      navigate("/subscription");
    } catch (caught) {
      setError(errorMessage(caught, `Could not start the invoice for ${item.addon.name}.`));
      setBusyCode(null);
    }
  };

  return (
    <div className="flex w-full flex-col gap-5">
      <header>
        <h1 className="text-xl font-semibold">Discover Add-ons</h1>
        <p className="mt-1 max-w-2xl text-sm text-charcoal/60">
          Extend your AxizPOS capabilities with powerful tools designed for your business.
        </p>
        {catalog ? (
          <p className="mt-3 text-sm text-charcoal/70">
            {catalog.available} available · {catalog.activated} activated · {catalog.pending} pending
            {catalog.recurring_fils > 0 ? ` · ${formatMoney(catalog.recurring_fils, catalog.currency)} / month` : ""}
          </p>
        ) : null}
      </header>
      <SearchField
        label="Search add-ons"
        placeholder="Search add-ons by name, feature or description..."
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      <div className="flex flex-wrap gap-2">
        <FilterSelect
          label="Status"
          value={state}
          onChange={setState}
          options={[
            ["", "All add-ons"],
            ["available", "Available"],
            ["included", "Included in package"],
            ["activated", "Activated"],
            ["pending_payment", "Pending payment"],
            ["pending_activation", "Pending activation"],
          ]}
        />
        <FilterSelect
          label="Category"
          value={category}
          onChange={setCategory}
          options={[["", "All categories"], ...categories.map((name) => [name, name] as [string, string])]}
        />
        <FilterSelect
          label="Pricing"
          value={pricing}
          onChange={setPricing}
          options={[
            ["", "Any price"],
            ["monthly", "Monthly"],
            ["once", "One-time"],
            ["deposit", "Refundable deposit"],
            ["unpriced", "Price not set"],
          ]}
        />
        <FilterSelect
          label="Sort"
          value={sort}
          onChange={(value) => setSort(value as MarketplaceSort)}
          options={[
            ["recommended", "Recommended"],
            ["name", "Name A–Z"],
            ["price_asc", "Lowest price"],
            ["price_desc", "Highest price"],
            ["recent", "Recently updated"],
          ]}
        />
      </div>
      <ErrorNote message={loadError ?? error} />
      {catalog === null && loadError === null ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {Array.from({ length: 6 }, (_, index) => (
            <div key={index} className="h-56 animate-pulse rounded-2xl border border-line bg-white" />
          ))}
        </div>
      ) : null}
      {catalog && items.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-line bg-white px-4 py-10 text-center text-sm text-charcoal/60">
          {deferred.trim() ? "No add-ons match that search." : "No add-ons are published for this view."}
        </p>
      ) : null}
      <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
        {items.map((item) => (
          <li key={item.addon.id} className="min-w-0">
            <article className="flex h-full flex-col rounded-2xl border border-line bg-white p-4 shadow-sm transition hover:border-charcoal/20">
              <div className="flex items-start gap-3">
                <AddonMark item={item} />
                <div className="min-w-0">
                  <h2 className="text-sm font-semibold">{item.addon.name}</h2>
                  <p className="mt-1 text-xs font-medium uppercase tracking-wide text-accent">{STATE_LABEL[item.state]}</p>
                </div>
              </div>
              <p className="mt-3 line-clamp-3 flex-1 text-sm text-charcoal/70">
                {item.addon.listing?.short_description || item.addon.description || "No description."}
              </p>
              {item.compatible_labels.length > 0 ? (
                <p className="mt-3 text-xs text-charcoal/50">Available for: {item.compatible_labels.join(" · ")}</p>
              ) : null}
              <p className="mt-2 text-sm font-medium">{priceLabel(item)}</p>
              <div className="mt-4 flex flex-wrap gap-2">
                <Link
                  to={`/settings/addons/${item.addon.code}`}
                  className="rounded-xl border border-line px-3 py-2 text-sm font-medium hover:bg-surface focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                >
                  View details
                </Link>
                <CardAction item={item} busy={busyCode === item.addon.code} onPurchase={() => void purchase(item)} />
              </div>
            </article>
          </li>
        ))}
      </ul>
    </div>
  );
}

function CardAction({ item, busy, onPurchase }: { item: MarketplaceItem; busy: boolean; onPurchase: () => void }) {
  if (item.state === "included") return <span className="px-1 py-2 text-sm text-charcoal/60">Included in your plan</span>;
  if (item.state === "activated") {
    const destination = moduleDestination(item.addon.code);
    return destination ? (
      <Link to={destination} className="px-1 py-2 text-sm font-medium text-accent">
        Open
      </Link>
    ) : (
      <span className="px-1 py-2 text-sm text-charcoal/60">Activated</span>
    );
  }
  if (item.state === "pending_payment") {
    return (
      <Link to="/subscription" className="px-1 py-2 text-sm font-medium text-accent">
        View invoice
      </Link>
    );
  }
  if (item.state === "pending_activation") return <span className="px-1 py-2 text-sm text-charcoal/60">Payment verification in progress</span>;
  if (item.state === "expired") {
    return (
      <Link to="/subscription" className="px-1 py-2 text-sm font-medium text-accent">
        Review subscription
      </Link>
    );
  }
  if (canPurchase(item)) {
    return (
      <PrimaryButton disabled={busy} onClick={onPurchase}>
        {busy ? "Starting…" : "Purchase"}
      </PrimaryButton>
    );
  }
  if (item.state === "unpriced") return <span className="px-1 py-2 text-sm text-charcoal/60">Contact administrator</span>;
  if (item.state === "unavailable") return <span className="px-1 py-2 text-sm text-charcoal/60">{item.reason}</span>;
  return <span className="px-1 py-2 text-sm text-charcoal/60">Added on the package invoice</span>;
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
    <label className="text-xs font-medium text-charcoal/60">
      {label}
      <select
        className="mt-1 block rounded-xl border border-line bg-white px-3 py-2 text-sm text-charcoal focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
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
  const { code } = useParams();
  const navigate = useNavigate();
  const [catalog, setCatalog] = useState<MarketplaceCatalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiGet<MarketplaceCatalog>("/api/v1/billing/marketplace")
      .then((next) => {
        if (!cancelled) setCatalog(next);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(errorMessage(caught, "The add-on could not be loaded."));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const item = catalog?.items.find((row) => row.addon.code === code) ?? null;
  const listing = item?.addon.listing;

  const purchase = async () => {
    if (item === null || !canPurchase(item)) return;
    setBusy(true);
    setError(null);
    try {
      await apiPost(`/api/v1/billing/addons/${item.addon.code}/checkout`, {});
      navigate("/subscription");
    } catch (caught) {
      setError(errorMessage(caught, "Could not start the invoice."));
      setBusy(false);
    }
  };

  if (error && catalog === null) return <ErrorNote message={error} />;
  if (catalog === null) return <div className="h-64 animate-pulse rounded-2xl border border-line bg-white" />;
  if (item === null) {
    return (
      <div className="rounded-2xl border border-dashed border-line bg-white px-4 py-10 text-center text-sm text-charcoal/60">
        This add-on is not available.
        <div className="mt-4">
          <Link to="/settings/addons" className="text-sm font-medium text-accent">
            Back to add-ons
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="flex w-full flex-col gap-6">
      <Link to="/settings/addons" className="text-sm font-medium text-accent">
        All add-ons
      </Link>
      <header className="flex flex-wrap items-start gap-4">
        <AddonMark item={item} />
        <div className="min-w-0 flex-1">
          <h1 className="text-xl font-semibold">{item.addon.name}</h1>
          <p className="mt-1 text-sm text-charcoal/70">{listing?.short_description || item.addon.description}</p>
          <p className="mt-2 text-xs font-medium uppercase tracking-wide text-accent">
            {listing?.category ?? "operations"} · {STATE_LABEL[item.state]}
          </p>
          <p className="mt-2 text-sm font-medium">{priceLabel(item)}</p>
        </div>
      </header>
      <ErrorNote message={error} />
      <Section title="Overview">
        <p className="text-sm text-charcoal/80">{listing?.overview || item.addon.description || "No overview yet."}</p>
      </Section>
      <PointList title="Benefits" rows={listing?.benefits ?? []} />
      <PointList title="Features" rows={listing?.features ?? []} />
      <PointList title="How it works" rows={listing?.steps ?? []} />
      <Section title="Compatibility">
        <p className="text-sm text-charcoal/80">
          {item.compatible_labels.length > 0 ? item.compatible_labels.join(" · ") : "Available with the current packages."}
        </p>
      </Section>
      <Section title="Pricing">
        <p className="text-sm text-charcoal/80">{priceLabel(item)}. Amounts are the catalogue prices in AED.</p>
        {item.invoice_id ? <p className="mt-2 text-sm text-charcoal/60">Invoice {item.invoice_id}</p> : null}
      </Section>
      {(listing?.requirements.length ?? 0) > 0 ? (
        <Section title="Requirements">
          <ul className="list-disc space-y-1 pl-5 text-sm text-charcoal/80">
            {listing?.requirements.map((row) => (
              <li key={row}>{row}</li>
            ))}
          </ul>
        </Section>
      ) : null}
      <Section title="Support">
        <div className="space-y-2 text-sm text-charcoal/80">
          {listing?.support ? <p>{listing.support}</p> : <p>Use the existing AxizPOS support contact.</p>}
          {listing?.documentation_url ? (
            <a className="block text-accent" href={listing.documentation_url} rel="noreferrer">
              Documentation
            </a>
          ) : null}
          {listing?.video_url ? (
            <a className="block text-accent" href={listing.video_url} rel="noreferrer">
              Video
            </a>
          ) : null}
        </div>
        {(listing?.faqs.length ?? 0) > 0 ? (
          <dl className="mt-4 space-y-3">
            {listing?.faqs.map((faq) => (
              <div key={faq.question}>
                <dt className="text-sm font-medium">{faq.question}</dt>
                <dd className="text-sm text-charcoal/70">{faq.answer}</dd>
              </div>
            ))}
          </dl>
        ) : null}
      </Section>
      <div className="sticky bottom-0 flex flex-wrap items-center gap-3 rounded-2xl border border-line bg-white p-4">
        <CardAction item={item} busy={busy} onPurchase={() => void purchase()} />
        <GhostButton onClick={() => navigate("/settings/addons")}>Close</GhostButton>
      </div>
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
          <li key={`${row.title}-${row.description}`} className="rounded-2xl border border-line bg-white p-3">
            <p className="text-sm font-medium">{row.title}</p>
            {row.description ? <p className="mt-1 text-sm text-charcoal/70">{row.description}</p> : null}
          </li>
        ))}
      </ul>
    </Section>
  );
}
