import {
  DEFAULT_BUSINESS_PROFILE,
  DEFAULT_MODULE_SETTINGS,
  PROFILE_PRESETS,
  isBusinessProfile,
  isCapability,
  resolvePosPolicy,
  type BusinessProfile,
  type Capability,
  type ModuleSettings,
  type PosPolicy,
} from "@ai-pos/shared-types";
import { useSyncExternalStore } from "react";

export interface RegisterCapabilities {
  profile: BusinessProfile;
  enabled: ReadonlySet<Capability>;
  planned: ReadonlySet<Capability>;
  foodAndBeverage: boolean;
  /** Module configuration (scale labels, service charge, kitchen timers), with defaults filled in. */
  modules: ModuleSettings;
  /** The store has not gone live yet: sales rung up now are practice and Go live clears them. */
  practice: boolean;
  /** Till rules: discount reasons and limits, gift cards, the returns policy. */
  policy: PosPolicy;
}

export interface ProfileSnapshot {
  business_profile?: string | null;
  capabilities?: readonly string[] | null;
  planned_capabilities?: readonly string[] | null;
  module_settings?: Partial<ModuleSettings> | null;
  practice_mode?: boolean | null;
  pos_policy?: Partial<PosPolicy> | null;
  entitlement_revision?: number | null;
  purchased_capabilities?: readonly string[] | null;
  entitlement_until?: string | null;
}

const CACHE_KEY = "ai-pos.register-capabilities";

function modulesOf(raw: Partial<ModuleSettings> | null | undefined): ModuleSettings {
  return { ...DEFAULT_MODULE_SETTINGS, ...(raw ?? {}) };
}

function entitled(raw: ProfileSnapshot): readonly string[] | null | undefined {
  const capabilities = raw.capabilities;
  if (!capabilities) return capabilities;
  const until = raw.entitlement_until ? Date.parse(raw.entitlement_until) : Number.NaN;
  const purchased = new Set(raw.purchased_capabilities ?? []);
  if (purchased.size === 0 || Number.isNaN(until) || until > Date.now()) return capabilities;
  return capabilities.filter((id) => !purchased.has(id));
}

function build(raw: ProfileSnapshot | null): RegisterCapabilities {
  const name = raw?.business_profile ?? DEFAULT_BUSINESS_PROFILE;
  const profile = isBusinessProfile(name) ? name : DEFAULT_BUSINESS_PROFILE;
  const source = raw ? entitled(raw) : null;
  const enabled = source ? source.filter(isCapability) : [];
  const planned = raw?.planned_capabilities?.filter(isCapability) ?? [];
  return {
    profile,
    enabled: new Set(enabled),
    planned: new Set(planned),
    foodAndBeverage: PROFILE_PRESETS[profile].group === "food_beverage",
    modules: modulesOf(raw?.module_settings),
    practice: raw?.practice_mode === true,
    policy: resolvePosPolicy(raw?.pos_policy),
  };
}

function readCached(): ProfileSnapshot | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    return raw === null ? null : (JSON.parse(raw) as ProfileSnapshot);
  } catch {
    return null;
  }
}

/** A register with no entitlement snapshot shows no paid or profile modules. A cached snapshot keeps the
 * last list, and paid add-ons still follow the signed-in user. */
const OFFLINE_ADDON_SECONDS = 24 * 60 * 60;
let storeCurrent: RegisterCapabilities = build(readCached());
let purchased = new Set(readCached()?.purchased_capabilities ?? []);
let signedInAddons: ReadonlySet<string> | null = null;
let current: RegisterCapabilities = storeCurrent;
let revision = readCached()?.entitlement_revision ?? 0;
const listeners = new Set<() => void>();

function publish(): void {
  const granted = signedInAddons;
  const enabled =
    granted === null
      ? storeCurrent.enabled
      : new Set([...storeCurrent.enabled].filter((capability) => !purchased.has(capability) || granted.has(capability)));
  const next = { ...storeCurrent, enabled };
  const same =
    next.profile === current.profile &&
    next.practice === current.practice &&
    next.enabled.size === current.enabled.size &&
    [...next.enabled].every((capability) => current.enabled.has(capability)) &&
    JSON.stringify(next.modules) === JSON.stringify(current.modules) &&
    JSON.stringify(next.policy) === JSON.stringify(current.policy);
  if (same) return;
  current = next;
  for (const listener of listeners) listener();
}

/**
 * Limits paid add-ons to the modules the signed-in user may use.
 * Pass null on lock. An offline unlock older than a day drops add-on access until the till is online again.
 * A missing or unreadable list grants none of the paid modules. Core selling stays on the store profile.
 */
export function applySignedInAddons(
  modules: readonly string[] | null,
  options?: { offline?: boolean; syncedAt?: number; now?: number },
): void {
  if (modules === null) {
    signedInAddons = null;
  } else {
    const now = options?.now ?? Date.now() / 1000;
    const syncedAt = options?.syncedAt ?? now;
    const stale = options?.offline === true && now - syncedAt > OFFLINE_ADDON_SECONDS;
    signedInAddons = new Set(stale ? [] : modules);
  }
  publish();
}

export function applyProfile(raw: ProfileSnapshot | null | undefined): void {
  if (!raw?.capabilities) return;
  const nextRevision = raw.entitlement_revision ?? 0;
  if (nextRevision > 0 && revision > nextRevision) return;
  try {
    const {
      business_profile,
      capabilities,
      planned_capabilities,
      module_settings,
      practice_mode,
      pos_policy,
      entitlement_revision,
      purchased_capabilities,
      entitlement_until,
    } = raw;
    localStorage.setItem(
      CACHE_KEY,
      JSON.stringify({
        business_profile,
        capabilities,
        planned_capabilities,
        module_settings,
        practice_mode,
        pos_policy,
        entitlement_revision,
        purchased_capabilities,
        entitlement_until,
      }),
    );
  } catch {
    // Storage disabled: the in-memory copy still serves this session.
  }
  if (nextRevision > revision) revision = nextRevision;
  storeCurrent = build(raw);
  purchased = new Set(raw.purchased_capabilities ?? []);
  publish();
}

export function registerCapabilities(): RegisterCapabilities {
  return current;
}

export function hasCapability(capability: Capability): boolean {
  return current.enabled.has(capability);
}

export function moduleSettings(): ModuleSettings {
  return current.modules;
}

export function posPolicy(): PosPolicy {
  return current.policy;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useCapabilities(): RegisterCapabilities {
  return useSyncExternalStore(subscribe, registerCapabilities);
}

export function useCapability(capability: Capability): boolean {
  return useCapabilities().enabled.has(capability);
}
