import {
  DEFAULT_BUSINESS_PROFILE,
  isBusinessProfile,
  isCapability,
  profileSpec,
  type BusinessProfile,
  type Capability,
} from "@ai-pos/shared-types";
import { useMemo } from "react";
import { useAuth } from "./auth";
import { useCurrency } from "./currency";

export interface Capabilities {
  profile: BusinessProfile;
  enabled: ReadonlySet<Capability>;
  planned: ReadonlySet<Capability>;
  /** False only when the API says this business has not finished onboarding. */
  onboarded: boolean;
  has: (capability: Capability) => boolean;
}

/**
 * What this business has switched on. Until settings have loaded, no module is treated as on.
 */
export function useCapabilities(): Capabilities {
  const { settings } = useCurrency();
  const { user } = useAuth();
  return useMemo(() => {
    const raw = settings?.business_profile;
    const profile = raw !== undefined && isBusinessProfile(raw) ? raw : DEFAULT_BUSINESS_PROFILE;
    const loaded = settings != null;
    const enabled = new Set(loaded ? (settings.capabilities ?? []).filter(isCapability) : []);
    const planned = new Set(loaded ? (settings.planned_capabilities ?? []).filter(isCapability) : []);
    const purchased = new Set(settings?.purchased_capabilities ?? []);
    const granted = new Set(user?.addon_modules ?? []);
    return {
      profile,
      enabled,
      planned,
      onboarded: settings?.onboarded !== false,
      has: (capability: Capability) => {
        if (!enabled.has(capability)) return false;
        if (!purchased.has(capability) || user?.addon_modules === undefined) return true;
        return granted.has(capability);
      },
    };
  }, [settings, user]);
}

export function useCapability(capability: Capability | undefined): boolean {
  const { has } = useCapabilities();
  return capability === undefined || has(capability);
}

/** "Store settings", "Restaurant settings", "Cafe settings": the business-wide settings named for this business type. */
export function useSettingsLabel(): string {
  return profileSpec(useCapabilities().profile).settingsLabel;
}
