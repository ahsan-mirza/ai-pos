import {
  BusinessProfile,
  Capability,
  Permission,
  type BusinessProfile as Profile,
} from "@ai-pos/shared-types";

/** A tab is shown only when the profile lists it, any required capability is on, and the user holds a permission. */
export interface InventoryTab {
  id: string;
  label: string;
  permissions: readonly string[];
  capability?: Capability;
}

const view = [Permission.PortalAccess];
const catalogue = [Permission.PortalInventoryManage, Permission.PharmacyCatalogue];
const manage = [Permission.PortalInventoryManage];
const pricing = [Permission.PortalPricingManage];
const counts = [Permission.PortalAccess, Permission.InventoryAdjustStock];
const replenish = [Permission.ReplenishmentManage];

function tab(
  id: string,
  label: string,
  permissions: readonly string[],
  capability?: Capability,
): InventoryTab {
  return { id, label, permissions, capability };
}

/** Shared selling and stock sections. Profile lists add or drop from this set. */
const selling: InventoryTab[] = [
  tab("stock", "Stock", view),
  tab("products", "Products", catalogue),
  tab("pricing", "Pricing", [...view, ...pricing]),
  tab("price-lists", "Price lists", pricing),
  tab("price-changes", "Price changes", [...view, ...pricing]),
  tab("categories", "Categories", catalogue),
  tab("brands", "Brands", manage),
  tab("units", "Units", manage),
  tab("replenishment", "Replenishment", replenish),
  tab("counts", "Stock counts", counts),
  tab("purchase-orders", "Purchase orders", manage),
  tab("transfers", "Transfers", manage),
];

const batches = tab("batches", "Batches", manage);
const models = tab("models", "Models", manage);
const serials = tab("serials", "IMEI Tracker", view, Capability.SerialTracking);
const expiry = tab("expiry", "Expiry", view, Capability.Fefo);
const recipes = tab("recipes", "Recipes", manage, Capability.Recipes);

const grocery: InventoryTab[] = [
  ...selling.slice(0, 8),
  batches,
  expiry,
  ...selling.slice(8),
];

const units = selling.find((item) => item.id === "units");
if (units === undefined) {
  throw new Error("The units inventory tab is missing.");
}

const electronics: InventoryTab[] = [
  ...selling.slice(0, 7),
  models,
  units,
  batches,
  ...selling.slice(8),
  serials,
];

const fashion: InventoryTab[] = selling;

const food: InventoryTab[] = [...selling, recipes];

const pharmacy: InventoryTab[] = [
  tab("products", "Products", catalogue),
  tab("categories", "Medicine categories", catalogue),
  tab("stock", "Stock", view),
  tab("lots", "Manufacturer lots", manage),
  expiry,
  tab("purchase-orders", "Receiving", manage),
  tab("transfers", "Transfers", manage),
  tab("supplier-returns", "Supplier returns", manage),
  tab("recalls", "Recalls", manage),
  tab("quarantine", "Quarantine", manage),
  tab("release", "Authorized release", manage),
];

const BY_PROFILE: Record<Profile, readonly InventoryTab[]> = {
  [BusinessProfile.Grocery]: grocery,
  [BusinessProfile.ElectronicsWholesale]: electronics,
  [BusinessProfile.WholesaleRetail]: electronics,
  [BusinessProfile.RetailFashion]: fashion,
  [BusinessProfile.Restaurant]: food,
  [BusinessProfile.Cafe]: food,
  [BusinessProfile.QuickService]: food,
  [BusinessProfile.Pharmacy]: pharmacy,
};

export function inventoryTabs(
  profile: Profile,
  enabled: ReadonlySet<string>,
  permissions: readonly string[],
): InventoryTab[] {
  const listed = BY_PROFILE[profile] ?? [];
  return listed.filter(
    (item) =>
      (item.capability === undefined || enabled.has(item.capability)) &&
      item.permissions.some((permission) => permissions.includes(permission)),
  );
}

/** Cashiers keep sales search. The workspace opens only when an inventory permission is actually held. */
export function canOpenInventory(profile: Profile, enabled: ReadonlySet<string>, permissions: readonly string[]): boolean {
  return inventoryTabs(profile, enabled, permissions).length > 0;
}
