import type { ReactNode } from "react";
import { signupUrl } from "../env";

/** Primary conversion label. Every customer-facing CTA uses this exact text. */
export const GET_STARTED_LABEL = "Get Started Free";

/**
 * Signup creates a practice store on the Standard trial. The trial length and
 * package price come from the public catalog. Going live still follows that subscription.
 */
export const GET_STARTED_NOTE =
  "Opens registration. New stores start on the Standard trial shown in Pricing. Going live follows that subscription.";

export function GetStartedLink({ className, children }: { className: string; children?: ReactNode }) {
  return (
    <a href={signupUrl} className={className}>
      {children}
      {GET_STARTED_LABEL}
    </a>
  );
}
