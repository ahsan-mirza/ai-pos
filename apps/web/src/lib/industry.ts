import {
  Capability,
  isBusinessProfile,
  profileAllows,
  profileSpec,
  type BusinessProfile,
} from "@ai-pos/shared-types";

/** Retail trade profiles. Stored ids match BusinessProfile in shared-types. */
export const RETAIL_PROFILES = ["electronics_wholesale", "wholesale_retail", "retail_fashion", "grocery"] as const satisfies readonly BusinessProfile[];

/** Food and beverage profiles. */
export const FNB_PROFILES = ["restaurant", "cafe", "quick_service"] as const satisfies readonly BusinessProfile[];

export const FASHION_PROFILES = ["retail_fashion"] as const satisfies readonly BusinessProfile[];

/** Catalog models (Apple → iPhone 15 Pro) belong to electronics and fashion, not food service. */
export const MODEL_PROFILES = ["electronics_wholesale", "retail_fashion"] as const satisfies readonly BusinessProfile[];

/** A stored business-type id, or null when it is missing or not one this portal knows. */
export function knownBusinessType(value: string | null | undefined): BusinessProfile | null {
  return value !== undefined && value !== null && isBusinessProfile(value) ? value : null;
}

export function businessTypeOf(value: string | null | undefined): BusinessProfile {
  return knownBusinessType(value) ?? profileSpec(value).id;
}

export function isRetailProfile(profile: BusinessProfile): boolean {
  return (RETAIL_PROFILES as readonly string[]).includes(profile);
}

export function isFnBProfile(profile: BusinessProfile): boolean {
  return (FNB_PROFILES as readonly string[]).includes(profile);
}

/** Undefined means every business type. An allow-list hides the item from every other type. */
export function fitsProfiles(profile: BusinessProfile, allowed: readonly BusinessProfile[] | undefined): boolean {
  return allowed === undefined || allowed.includes(profile);
}

interface IndustryGate {
  prefix: string;
  profiles: readonly BusinessProfile[];
}

/** Pages whose screen exists only for some types, even when a related module is shared. */
const SURFACE_GATES: IndustryGate[] = [
  { prefix: "/inventory/models", profiles: MODEL_PROFILES },
  { prefix: "/inventory/batches", profiles: RETAIL_PROFILES },
  { prefix: "/inventory/markdowns", profiles: FASHION_PROFILES },
  { prefix: "/inventory/size-curve", profiles: FASHION_PROFILES },
  { prefix: "/returns", profiles: RETAIL_PROFILES },
];

/** Pages that follow the module catalogue: open when this business type is allowed to use the module. */
const CAPABILITY_GATES: { prefix: string; capability: Capability }[] = [
  { prefix: "/inventory/serials", capability: Capability.SerialTracking },
  { prefix: "/inventory/floor-plan", capability: Capability.Tables },
  { prefix: "/inventory/kitchen-agent", capability: Capability.Recipes },
  { prefix: "/inventory/kitchen", capability: Capability.Kds },
  { prefix: "/inventory/recipes", capability: Capability.Recipes },
  { prefix: "/inventory/recipe-usage", capability: Capability.Recipes },
  { prefix: "/inventory/modifiers", capability: Capability.MenuModifiers },
  { prefix: "/inventory/meals", capability: Capability.MenuModifiers },
  { prefix: "/repairs", capability: Capability.Repairs },
  { prefix: "/warranties", capability: Capability.Warranty },
  { prefix: "/trade-ins", capability: Capability.TradeIn },
  { prefix: "/consignment", capability: Capability.Consignment },
  { prefix: "/cheques", capability: Capability.Cheques },
  { prefix: "/gift-cards", capability: Capability.GiftCards },
  { prefix: "/reports/tips", capability: Capability.TipsServiceCharge },
  { prefix: "/settings/channels", capability: Capability.DeliveryChannels },
];

const GATES = [...SURFACE_GATES.map((gate) => gate.prefix), ...CAPABILITY_GATES.map((gate) => gate.prefix)].sort(
  (left, right) => right.length - left.length,
);

export function industryAllows(pathname: string, profile: BusinessProfile): boolean {
  const prefix = matchingGate(pathname);
  if (prefix === undefined) return true;
  const surface = SURFACE_GATES.find((gate) => gate.prefix === prefix);
  if (surface) return surface.profiles.includes(profile);
  const capability = CAPABILITY_GATES.find((gate) => gate.prefix === prefix);
  return capability !== undefined && profileAllows(profile, capability.capability);
}

function matchingGate(pathname: string): string | undefined {
  return GATES.find((item) => pathname === item || pathname.startsWith(`${item}/`));
}

/** True when the path is limited to some business types or modules. */
export function isIndustryGated(pathname: string): boolean {
  return matchingGate(pathname) !== undefined;
}

/**
 * A known business type uses the catalogue. A missing or unknown type may open shared pages only,
 * never a type-specific or module page.
 */
export function portalRouteAllowed(pathname: string, profile: string | null | undefined): boolean {
  const known = knownBusinessType(profile);
  if (known === null) return !isIndustryGated(pathname);
  return industryAllows(pathname, known);
}
