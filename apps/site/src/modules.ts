import {
  CAPABILITIES,
  PROFILE_ELIGIBLE,
  PROFILE_PRESETS,
  capabilitySpec,
  isCapability,
  type BusinessProfile,
  type Capability,
} from "@ai-pos/shared-types";
import { aed, type Addon } from "./catalog";

const LABELS = new Map(CAPABILITIES.map((spec) => [spec.id, spec.label]));
const ORDER = new Map(CAPABILITIES.map((spec, index) => [spec.id, index]));

/** Configured business types, in catalogue order. Labels come from the profile registry. */
export const BUSINESS_TYPE_ORDER = [
  "electronics_wholesale",
  "wholesale_retail",
  "retail_fashion",
  "grocery",
  "restaurant",
  "cafe",
  "quick_service",
] as const satisfies readonly BusinessProfile[];

export function moduleLabel(id: string): string {
  if (!isCapability(id)) return id;
  return LABELS.get(id) ?? id;
}

function byCatalogue(left: Capability, right: Capability): number {
  return (ORDER.get(left) ?? 0) - (ORDER.get(right) ?? 0);
}

/** Starter modules versus the other modules this business type is allowed to use. */
export function profileModules(profile: BusinessProfile): { included: Capability[]; optional: Capability[] } {
  const preset = new Set(PROFILE_PRESETS[profile].capabilities);
  const eligible = [...PROFILE_ELIGIBLE[profile]].sort(byCatalogue);
  return {
    included: eligible.filter((id) => preset.has(id)),
    optional: eligible.filter((id) => !preset.has(id)),
  };
}

export function profilesFor(capability: Capability): BusinessProfile[] {
  return BUSINESS_TYPE_ORDER.filter((profile) => PROFILE_ELIGIBLE[profile].includes(capability));
}

export interface ModulePrice {
  addonName: string;
  label: string;
}

/** A public price exists only when a catalog add-on lists an amount and maps this module. */
export function priceLabel(addon: Addon): string | null {
  const parts: string[] = [];
  if (addon.monthly_fils > 0) parts.push(`${aed(addon.monthly_fils)} / month`);
  if (addon.one_time_fils > 0) {
    parts.push(addon.refundable ? `${aed(addon.one_time_fils)} refundable deposit` : `${aed(addon.one_time_fils)} once`);
  }
  return parts.length > 0 ? parts.join(" · ") : null;
}

export function publicModulePrices(addons: readonly Addon[]): Partial<Record<Capability, ModulePrice[]>> {
  const prices: Partial<Record<Capability, ModulePrice[]>> = {};
  for (const addon of addons) {
    if (!addon.active) continue;
    const label = priceLabel(addon);
    if (!label) continue;
    const keys = new Set(addon.module_keys);
    if (isCapability(addon.code)) keys.add(addon.code);
    for (const key of keys) {
      if (!isCapability(key)) continue;
      const list = prices[key] ?? [];
      list.push({ addonName: addon.name, label });
      prices[key] = list;
    }
  }
  return prices;
}

export function requirementLabel(capability: Capability): string | null {
  const needs = capabilitySpec(capability).requires;
  if (needs.length === 0) return null;
  return `Needs ${needs.map((id) => capabilitySpec(id).label).join(", ")}`;
}
