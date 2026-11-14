import type { MarketplaceItem } from "@ai-pos/shared-types";
import { useLocale } from "@ai-pos/ui";
import { CreditCard, Hash, Landmark, Layers, Monitor, Puzzle, Receipt, Shield, Truck, type LucideIcon } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { moduleDestination } from "../../../components/layout/navigation";
import { addonNextStep, addonPriceView } from "./display";
import { DetailDrawer } from "./DetailDrawer";
import { PriceDisplay } from "./PriceDisplay";
import { MarketplaceStatus } from "./SubscriptionStatus";

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

export function AddonGlyph({ item }: { item: MarketplaceItem }) {
  const listing = item.addon.listing;
  const [broken, setBroken] = useState(false);
  const Icon = ICONS[listing?.icon ?? ""] ?? Puzzle;
  if (listing?.image_url && !broken) {
    return <img src={listing.image_url} alt="" className="size-11 rounded-xl border border-line object-cover" onError={() => setBroken(true)} />;
  }
  return (
    <span className="flex size-11 items-center justify-center rounded-xl border border-line bg-zinc-50 text-charcoal/70 dark:border-zinc-500 dark:bg-zinc-800 dark:text-zinc-100">
      <Icon className="size-5" aria-hidden="true" />
    </span>
  );
}

export function AddonActions({ item, onPurchase }: { item: MarketplaceItem; onPurchase: () => void }) {
  const { t } = useLocale();
  const step = addonNextStep(item, moduleDestination(item.addon.code));
  if (step.type === "purchase") {
    return (
      <button
        type="button"
        onClick={onPurchase}
        className="inline-flex h-10 items-center gap-2 rounded-full bg-accent px-4 text-sm font-semibold text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        <Puzzle size={14} aria-hidden="true" />
        {t("Buy Now")}
      </button>
    );
  }
  if (step.type === "link") {
    return (
      <Link to={step.href} className="inline-flex h-10 items-center text-sm font-semibold text-accent">
        {t(step.label)}
      </Link>
    );
  }
  return <span className="inline-flex min-h-10 items-center text-sm text-charcoal/60 dark:text-white/60">{step.translate ? t(step.label) : step.label}</span>;
}

export function AddonCard({
  item,
  currency,
  highlighted = false,
  onPurchase,
}: {
  item: MarketplaceItem;
  currency: string;
  highlighted?: boolean;
  onPurchase: () => void;
}) {
  const { t } = useLocale();
  const [open, setOpen] = useState(false);
  const price = addonPriceView(item, currency);
  const description = item.addon.listing?.short_description || item.addon.description;
  return (
    <article
      id={`plugin-${item.addon.code}`}
      className={`flex h-full min-w-0 flex-col rounded-2xl border border-line bg-white p-4 text-charcoal dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-100 ${
        highlighted ? "ring-2 ring-accent" : ""
      }`}
    >
      <div className="flex items-start gap-3">
        <AddonGlyph item={item} />
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <h3 className="text-sm font-semibold" dir="auto">{item.addon.name}</h3>
            <button
              type="button"
              aria-label={t("View details")}
              onClick={() => setOpen(true)}
              className="shrink-0 text-xs font-semibold text-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              {t("View details")}
            </button>
          </div>
          <div className="mt-1">
            <MarketplaceStatus state={item.state} />
          </div>
        </div>
      </div>
      <p className="mt-3 line-clamp-3 flex-1 text-sm text-charcoal/70 dark:text-white/70" dir="auto">{description || t("No description.")}</p>
      {item.addon.listing?.category ? <p className="mt-2 text-xs text-charcoal/60">{item.addon.listing.category}</p> : null}
      {item.addon.listing?.featured ? <p className="mt-1 text-xs font-semibold text-accent">{t("Featured")}</p> : null}
      <div className="mt-2">
        <PriceDisplay view={price} />
      </div>
      {item.compatible_labels.length > 0 ? (
        <p className="mt-2 text-xs text-charcoal/60">{item.compatible_labels.join(" · ")}</p>
      ) : null}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <AddonActions item={item} onPurchase={onPurchase} />
      </div>
      {open ? (
        <DetailDrawer title={t("Add-on details")} onClose={() => setOpen(false)}>
          <div className="grid gap-4 text-sm text-charcoal dark:text-white">
            <div className="flex items-center gap-3">
              <AddonGlyph item={item} />
              <MarketplaceStatus state={item.state} />
            </div>
            <p className="text-charcoal/80 dark:text-white/80" dir="auto">{item.addon.listing?.overview || description || t("No description.")}</p>
            <PriceDisplay view={price} prominent />
            {item.compatible_labels.length > 0 ? (
              <p>
                <span className="font-semibold">{t("Eligibility")}: </span>
                {item.compatible_labels.join(" · ")}
              </p>
            ) : null}
            {item.reason ? <p className="text-charcoal/70 dark:text-white/70">{t(item.reason)}</p> : null}
            <AddonActions item={item} onPurchase={onPurchase} />
          </div>
        </DetailDrawer>
      ) : null}
    </article>
  );
}
