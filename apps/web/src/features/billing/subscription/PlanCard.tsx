import type { BillingPlan } from "@ai-pos/shared-types";

import { useLocale } from "@ai-pos/ui";
import { Building2, Layers, Package, ShoppingBag, Sparkles, Store, TrendingUp, Wallet, type LucideIcon } from "lucide-react";
import { useState } from "react";
import { planLimits } from "../subscriptionPlans";
import type { PriceView } from "./display";
import { DetailDrawer } from "./DetailDrawer";
import { OnboardingAssistanceNote } from "./OnboardingAssistance";
import { PriceDisplay } from "./PriceDisplay";

const ICONS: Record<string, LucideIcon> = {
  FREE: Store,
  LITE: ShoppingBag,
  STANDARD: Package,
  GROWTH: TrendingUp,
  PRO: Layers,
  PRO_AI: Sparkles,
  ENTERPRISE: Building2,
};

export function PlanCard({
  plan,
  price,
  current,
  highlighted,
  legacy,
  trialNote,
  pending = false,
  onboardingFils = 0,
  currency = "AED",
  onUpgrade,
}: {
  plan: BillingPlan;
  price: PriceView;
  current: boolean;
  highlighted: boolean;
  legacy: boolean;
  trialNote: boolean;
  pending?: boolean;
  onboardingFils?: number;
  currency?: string;
  onUpgrade: () => void;
}) {
  const { t } = useLocale();
  const [open, setOpen] = useState(false);
  const Icon = ICONS[plan.code] ?? Wallet;
  const limits = planLimits(plan);
  const custom = price.kind === "custom";
  const free = plan.code === "FREE";
  return (
    <article
      id={`plan-${plan.code}`}
      className={`flex h-full min-w-0 flex-col rounded-2xl border bg-white p-4 text-charcoal dark:bg-zinc-900 dark:text-white ${
        current ? "border-accent" : "border-line dark:border-zinc-800"
      } ${highlighted ? "ring-2 ring-accent" : ""}`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-zinc-50 text-charcoal/80 dark:bg-white/5 dark:text-white/80">
            <Icon size={18} aria-hidden="true" />
          </span>
          <h3 className="truncate text-lg font-semibold">{t(plan.name)}</h3>
        </div>
        <div className="flex shrink-0 flex-wrap justify-end gap-1">
          {current ? <span className="rounded-full bg-accent/10 px-2 py-0.5 text-xs font-semibold text-accent">{t("Current plan")}</span> : null}
          {pending && !current ? (
            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-900 dark:bg-amber-950 dark:text-amber-100">{t("Change requested")}</span>
          ) : null}
          {legacy ? <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-semibold dark:bg-white/10">{t("Legacy plan")}</span> : null}
          {custom ? <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-semibold dark:bg-white/10">{t("Custom")}</span> : null}
        </div>
      </div>
      <div className="mt-2">
        <PriceDisplay view={price} prominent />
        {!free && !custom && onboardingFils > 0 ? <OnboardingAssistanceNote amountFils={onboardingFils} currency={currency} /> : null}
      </div>
      <ul className="mt-3 flex-1 space-y-1 text-sm text-charcoal/75 dark:text-white/75">
        {limits.slice(0, 4).map((limit) => (
          <li key={limit.key}>
            {t(limit.label)}: <span className="tabular-nums">{limit.value}</span>
            {limit.unit === "days" ? ` ${t("days")}` : ""}
          </li>
        ))}
        {plan.included_modules.length === 1
          ? <li>{t("1 included module")}</li>
          : plan.included_modules.length > 1
            ? <li>{t("{count} included modules", { count: plan.included_modules.length })}</li>
            : null}
      </ul>
      {trialNote ? <p className="mt-2 text-xs text-charcoal/60 dark:text-white/60">{t("A free trial is offered only when this store is eligible.")}</p> : null}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        {current ? (
          <span className="inline-flex h-10 items-center text-sm font-semibold text-charcoal/60 dark:text-white/60">{t("Current plan")}</span>
        ) : custom ? (
          <p className="text-sm text-charcoal/70 dark:text-white/70">{t("Priced on a contract. Contact sales to continue on Enterprise.")}</p>
        ) : free ? null : (
          <button
            type="button"
            onClick={onUpgrade}
            className="inline-flex h-10 items-center rounded-full bg-accent px-4 text-sm font-semibold text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            {t("Upgrade to {plan}", { plan: plan.name })}
          </button>
        )}
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="inline-flex h-10 items-center rounded-full border border-line px-4 text-sm font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          {t("View details")}
        </button>
      </div>
      {open ? (
        <DetailDrawer title={t("Plan details")} onClose={() => setOpen(false)}>
          <div className="grid gap-4 text-sm text-charcoal dark:text-white">
            <PriceDisplay view={price} prominent />
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-charcoal/50">{t("Included features")}</h3>
              <ul className="mt-2 space-y-1">
                {limits.map((limit) => (
                  <li key={limit.key}>
                    {t(limit.label)}: <span className="tabular-nums">{limit.value}</span>
                    {limit.unit === "days" ? ` ${t("days")}` : ""}
                  </li>
                ))}
                <li>
                  {plan.included_modules.length === 1
                    ? t("1 included module")
                    : t("{count} included modules", { count: plan.included_modules.length })}
                </li>
              </ul>
            </div>
            {current ? (
              <p className="font-semibold">{t("Current plan")}</p>
            ) : custom ? (
              <p>{t("Priced on a contract. Contact sales to continue on Enterprise.")}</p>
            ) : free ? null : (
              <button
                type="button"
                onClick={() => {
                  setOpen(false);
                  onUpgrade();
                }}
                className="inline-flex h-10 items-center rounded-full bg-accent px-4 text-sm font-semibold text-white"
              >
                {t("Upgrade to {plan}", { plan: plan.name })}
              </button>
            )}
          </div>
        </DetailDrawer>
      ) : null}
    </article>
  );
}
