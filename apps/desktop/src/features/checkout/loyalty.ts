import { env, previewHeaders } from "../../config/env";
import { inTauri } from "../../lib/tauri";

export interface LoyaltyRules {
  enabled: boolean;
  /** Points earned per whole business-currency unit paid. */
  earn_per_unit: number;
  /** Value of one point in minor units. */
  redeem_cents: number;
  min_redeem: number;
}

const OFF: LoyaltyRules = { enabled: false, earn_per_unit: 0, redeem_cents: 1, min_redeem: 1 };

export async function loadLoyaltyRules(): Promise<LoyaltyRules> {
  try {
    if (inTauri()) {
      const core = await import("@tauri-apps/api/core");
      return { ...OFF, ...(await core.invoke<Partial<LoyaltyRules>>("loyalty_settings")) };
    }
    const response = await fetch(`${env.apiBaseUrl}/api/v1/loyalty/settings`, {
      headers: previewHeaders(),
    });
    return response.ok ? { ...OFF, ...((await response.json()) as Partial<LoyaltyRules>) } : OFF;
  } catch {
    return OFF;
  }
}

/** The most points a customer can spend on this total, honouring the minimum redemption. */
export function maxRedeemable(rules: LoyaltyRules, balance: number, totalCents: number): number {
  if (!rules.enabled) return 0;
  const points = Math.min(balance, Math.floor(totalCents / rules.redeem_cents));
  return points >= rules.min_redeem ? points : 0;
}
