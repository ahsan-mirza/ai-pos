import { useLocale } from "@ai-pos/ui";
import { Check, Clock, Minus, Puzzle, Settings2 } from "lucide-react";
import type { ComparisonCell } from "./display";
import type { ComparisonMark } from "../subscriptionPlans";

const LABEL: Record<ComparisonCell, string> = {
  included: "Included",
  addon: "Add-on available",
  purchased: "Purchased",
  trial: "Trial",
  absent: "Not included",
  unconfigured: "Price not configured",
  custom: "Custom",
};

export function FeatureBadge({ mark }: { mark: ComparisonCell | ComparisonMark }) {
  const { t } = useLocale();
  const cell: ComparisonCell = mark === "plugin" ? "addon" : mark;
  const label = t(LABEL[cell]);
  if (cell === "included" || cell === "purchased") {
    return (
      <span className="inline-flex items-center gap-1 text-emerald-800 dark:text-emerald-300">
        <Check size={14} aria-hidden="true" />
        {label}
      </span>
    );
  }
  if (cell === "addon") {
    return (
      <span className="inline-flex items-center gap-1 text-accent">
        <Puzzle size={14} aria-hidden="true" />
        {label}
      </span>
    );
  }
  if (cell === "trial") {
    return (
      <span className="inline-flex items-center gap-1 text-amber-800 dark:text-amber-200">
        <Clock size={14} aria-hidden="true" />
        {label}
      </span>
    );
  }
  if (cell === "custom" || cell === "unconfigured") {
    return (
      <span className="inline-flex items-center gap-1 text-charcoal/70 dark:text-white/70">
        <Settings2 size={14} aria-hidden="true" />
        {label}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-charcoal/50 dark:text-white/45">
      <Minus size={14} aria-hidden="true" />
      {label}
    </span>
  );
}
