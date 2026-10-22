import {
  DEFAULT_BUSINESS_PROFILE,
  isBusinessProfile,
  isCapability,
  profileSpec,
  resolveCapabilities,
  type BusinessProfile,
  type Capability,
} from "@ai-pos/shared-types";
import { useMemo } from "react";
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
 * What this business has switched on, from the business settings. Until settings load (or against an API that
 * predates profiles) everything built today stays on, so nothing an existing business uses ever flickers away.
 */
export function useCapabilities(): Capabilities {
  const { settings } = useCurrency();
  return useMemo(() => {
    const raw = settings?.business_profile;
    const profile = raw !== undefined && isBusinessProfile(raw) ? raw : DEFAULT_BUSINESS_PROFILE;
    const fallback = resolveCapabilities(profile);
    const enabled = new Set(settings?.capabilities ? settings.capabilities.filter(isCapability) : fallback.enabled);
    const planned = new Set(
      settings?.planned_capabilities ? settings.planned_capabilities.filter(isCapability) : fallback.planned,
    );
    return {
      profile,
      enabled,
      planned,
      onboarded: settings?.onboarded !== false,
      has: (capability: Capability) => enabled.has(capability),
    };
  }, [settings]);
}

export function useCapability(capability: Capability | undefined): boolean {
  const { has } = useCapabilities();
  return capability === undefined || has(capability);
}

/** "Store settings", "Restaurant settings", "Cafe settings": the business-wide settings named for this business type. */
export function useSettingsLabel(): string {
  return profileSpec(useCapabilities().profile).settingsLabel;
}
