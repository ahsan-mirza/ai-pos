import { useLocale } from "@ai-pos/ui";
import { marketplaceStatusLabel, subscriptionStatusLabel } from "./display";
import type { MarketplaceItem } from "@ai-pos/shared-types";

function tone(status: string): string {
  if (status === "active" || status === "trialing" || status === "activated" || status === "included") {
    return "bg-emerald-500/10 text-emerald-800 dark:text-emerald-300";
  }
  if (status === "past_due" || status === "pending_payment" || status === "pending_activation" || status === "unpriced") {
    return "bg-amber-500/10 text-amber-900 dark:text-amber-200";
  }
  if (status === "canceled" || status === "expired" || status === "unavailable") {
    return "bg-red-500/10 text-red-800 dark:text-red-300";
  }
  return "bg-zinc-100 text-charcoal/80 dark:bg-white/10 dark:text-white/80";
}

export function SubscriptionStatus({ status }: { status: string }) {
  const { t } = useLocale();
  const label = t(subscriptionStatusLabel(status));
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${tone(status)}`}>
      <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />
      {label}
    </span>
  );
}

export function MarketplaceStatus({ state }: { state: MarketplaceItem["state"] }) {
  const { t } = useLocale();
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${tone(state)}`}>
      <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />
      {t(marketplaceStatusLabel(state))}
    </span>
  );
}
