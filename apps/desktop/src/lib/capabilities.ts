import {
  DEFAULT_BUSINESS_PROFILE,
  DEFAULT_MODULE_SETTINGS,
  PROFILE_PRESETS,
  isBusinessProfile,
  isCapability,
  resolveCapabilities,
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
}

const CACHE_KEY = "ai-pos.register-capabilities";

function modulesOf(raw: Partial<ModuleSettings> | null | undefined): ModuleSettings {
  return { ...DEFAULT_MODULE_SETTINGS, ...(raw ?? {}) };
}

function build(raw: ProfileSnapshot | null): RegisterCapabilities {
  const name = raw?.business_profile ?? DEFAULT_BUSINESS_PROFILE;
  const profile = isBusinessProfile(name) ? name : DEFAULT_BUSINESS_PROFILE;
  const fallback = resolveCapabilities(profile);
  const enabled = raw?.capabilities ? raw.capabilities.filter(isCapability) : fallback.enabled;
  const planned = raw?.planned_capabilities ? raw.planned_capabilities.filter(isCapability) : fallback.planned;
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

/** Until the API (or the register's cache) says otherwise every module built today is on, so a register never
 * loses a feature because it started offline. */
let current: RegisterCapabilities = build(readCached());
const listeners = new Set<() => void>();

export function applyProfile(raw: ProfileSnapshot | null | undefined): void {
  if (!raw?.capabilities) return;
  try {
    const { business_profile, capabilities, planned_capabilities, module_settings, practice_mode, pos_policy } = raw;
    localStorage.setItem(
      CACHE_KEY,
      JSON.stringify({ business_profile, capabilities, planned_capabilities, module_settings, practice_mode, pos_policy }),
    );
  } catch {
    // Storage disabled: the in-memory copy still serves this session.
  }
  const next = build(raw);
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
