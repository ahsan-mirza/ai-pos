import { useLocale } from "@ai-pos/ui";
import type { ReactNode } from "react";
import { signupUrl } from "../env";
import { track } from "../track";

/** Primary conversion label. Every customer-facing CTA uses this exact text. */
export const GET_STARTED_LABEL = "Get Started Free";

/**
 * Signup creates a store on the Free plan. Prices and the promotional trial
 * come from the public catalog. A paid plan still goes through the portal quote.
 */
export const GET_STARTED_NOTE =
  "Opens registration. New stores start on the Free plan. Paid plans and the promotional trial use the prices published in Pricing.";

export function GetStartedLink({ className, children }: { className: string; children?: ReactNode }) {
  const { t } = useLocale();
  const arabic = typeof document !== "undefined" && document.documentElement.lang === "ar";
  return (
    <a href={signupUrl} className={className} onClick={() => track("click_get_started", { page_path: window.location.pathname })}>
      {children}
      {arabic ? "ابدأ مجاناً" : t(GET_STARTED_LABEL)}
    </a>
  );
}
