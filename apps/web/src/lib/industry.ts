import { profileSpec, type BusinessProfile } from "@ai-pos/shared-types";

/** Retail trade profiles. Stored ids match BusinessProfile in shared-types. */
export const RETAIL_PROFILES = ["electronics_wholesale", "retail_fashion", "grocery"] as const satisfies readonly BusinessProfile[];

/** Food and beverage profiles. */
export const FNB_PROFILES = ["restaurant", "cafe", "quick_service"] as const satisfies readonly BusinessProfile[];

export const ELECTRONICS_PROFILES = ["electronics_wholesale"] as const satisfies readonly BusinessProfile[];

export const FASHION_PROFILES = ["retail_fashion"] as const satisfies readonly BusinessProfile[];

/** Catalog models (Apple → iPhone 15 Pro) belong to electronics and fashion, not food service. */
export const MODEL_PROFILES = ["electronics_wholesale", "retail_fashion"] as const satisfies readonly BusinessProfile[];

export function businessTypeOf(value: string | null | undefined): BusinessProfile {
  return profileSpec(value).id;
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

/** Longest prefix wins. A typed URL for another industry stops here instead of rendering the page. */
const GATES: IndustryGate[] = [
  { prefix: "/inventory/serials", profiles: ELECTRONICS_PROFILES },
  { prefix: "/inventory/models", profiles: MODEL_PROFILES },
  { prefix: "/inventory/batches", profiles: RETAIL_PROFILES },
  { prefix: "/inventory/markdowns", profiles: FASHION_PROFILES },
  { prefix: "/inventory/size-curve", profiles: FASHION_PROFILES },
  { prefix: "/inventory/floor-plan", profiles: FNB_PROFILES },
  { prefix: "/inventory/kitchen-agent", profiles: FNB_PROFILES },
  { prefix: "/inventory/kitchen", profiles: FNB_PROFILES },
  { prefix: "/inventory/recipes", profiles: FNB_PROFILES },
  { prefix: "/inventory/recipe-usage", profiles: FNB_PROFILES },
  { prefix: "/inventory/modifiers", profiles: FNB_PROFILES },
  { prefix: "/inventory/meals", profiles: FNB_PROFILES },
  { prefix: "/repairs", profiles: ELECTRONICS_PROFILES },
  { prefix: "/warranties", profiles: ELECTRONICS_PROFILES },
  { prefix: "/trade-ins", profiles: ELECTRONICS_PROFILES },
  { prefix: "/consignment", profiles: RETAIL_PROFILES },
  { prefix: "/cheques", profiles: ELECTRONICS_PROFILES },
  { prefix: "/gift-cards", profiles: FASHION_PROFILES },
  { prefix: "/returns", profiles: RETAIL_PROFILES },
  { prefix: "/reports/tips", profiles: FNB_PROFILES },
  { prefix: "/settings/channels", profiles: FNB_PROFILES },
].sort((left, right) => right.prefix.length - left.prefix.length);

export function industryAllows(pathname: string, profile: BusinessProfile): boolean {
  const gate = GATES.find((item) => pathname === item.prefix || pathname.startsWith(`${item.prefix}/`));
  return gate === undefined || gate.profiles.includes(profile);
}
