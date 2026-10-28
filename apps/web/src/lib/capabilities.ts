import {
  DEFAULT_BUSINESS_PROFILE,
  capabilitySpec,
  isBusinessProfile,
  isCapability,
  profileSpec,
  type BusinessProfile,
  type Capability,
} from "@ai-pos/shared-types";
import { useCallback, useMemo, useSyncExternalStore } from "react";
import { useAuth } from "./auth";
import { useCurrency } from "./currency";

let capabilityPreview: ReadonlySet<Capability> | null = null;
const previewListeners = new Set<() => void>();

function samePreview(left: ReadonlySet<Capability> | null, right: ReadonlySet<Capability> | null): boolean {
  if (left === right) return true;
  if (left === null || right === null || left.size !== right.size) return false;
  for (const capability of left) if (!right.has(capability)) return false;
  return true;
}

/** Unsaved module switches. The sidebar follows these until the settings page saves or closes. */
export function setCapabilityPreview(next: ReadonlySet<Capability> | null): void {
  if (samePreview(capabilityPreview, next)) return;
  capabilityPreview = next;
  previewListeners.forEach((listener) => listener());
}

function subscribeCapabilityPreview(listener: () => void): () => void {
  previewListeners.add(listener);
  return () => previewListeners.delete(listener);
}

function readCapabilityPreview(): ReadonlySet<Capability> | null {
  return capabilityPreview;
}

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
  const preview = useSyncExternalStore(subscribeCapabilityPreview, readCapabilityPreview);
  const base = useMemo(() => {
    const raw = settings?.business_profile;
    const profile = raw !== undefined && isBusinessProfile(raw) ? raw : DEFAULT_BUSINESS_PROFILE;
    const loaded = settings != null;
    return {
      profile,
      enabled: new Set(loaded ? (settings.capabilities ?? []).filter(isCapability) : []),
      planned: new Set(loaded ? (settings.planned_capabilities ?? []).filter(isCapability) : []),
      purchased: new Set(settings?.purchased_capabilities ?? []),
      onboarded: settings?.onboarded !== false,
    };
  }, [settings]);
  const has = useCallback(
    (capability: Capability) => {
      const switchedOn = preview
        ? preview.has(capability) && capabilitySpec(capability).available
        : base.enabled.has(capability);
      if (!switchedOn) return false;
      if (!base.purchased.has(capability) || user?.addon_modules === undefined) return true;
      return user.addon_modules.includes(capability);
    },
    [base, preview, user],
  );
  return { profile: base.profile, enabled: base.enabled, planned: base.planned, onboarded: base.onboarded, has };
}

export function useCapability(capability: Capability | undefined): boolean {
  const { has } = useCapabilities();
  return capability === undefined || has(capability);
}

/** "Store settings", "Restaurant settings", "Cafe settings": the business-wide settings named for this business type. */
export function useSettingsLabel(): string {
  return profileSpec(useCapabilities().profile).settingsLabel;
}
