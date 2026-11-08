import {
  SIGNUP_BUSINESS_CARDS,
  capabilitySpec,
  type Capability,
  type SignupBusinessCard,
  type SignupSubType,
} from "@ai-pos/shared-types";

const CHIP_PRIORITY: readonly Capability[] = [
  "tables",
  "kds",
  "split_bills",
  "delivery_channels",
  "menu_modifiers",
  "serial_tracking",
  "warranty",
  "repairs",
  "wholesale_pricing",
  "b2b_credit",
  "weighed_items",
  "fefo",
  "variants_matrix",
  "sales_orders",
  "customer_reorders",
  "alterations",
  "open_orders",
  "recipes",
  "loyalty",
];

const CHIP_LABEL: Partial<Record<Capability, string>> = {
  tables: "Table management",
  kds: "Kitchen orders",
  split_bills: "Split bills",
  delivery_channels: "Delivery orders",
  menu_modifiers: "Menu options",
  serial_tracking: "IMEI / serial tracking",
  warranty: "Warranty records",
  repairs: "Repairs",
  wholesale_pricing: "Customer pricing",
  b2b_credit: "Customer ledger",
  weighed_items: "Weighed items",
  fefo: "Expiry dates",
  variants_matrix: "Size and colour",
  sales_orders: "Deliveries",
  customer_reorders: "Repeat orders",
  alterations: "Alterations",
  open_orders: "Open orders",
  recipes: "Recipes",
  loyalty: "Customers",
};

const PAID_NOTE = "Paid add-ons stay off until they are on your plan.";

export function categoryColumns(width: number): 1 | 2 {
  return width < 480 ? 1 : 2;
}

export function businessMotion(reduced: boolean): { duration: number; ease: [number, number, number, number] } {
  if (reduced) return { duration: 0, ease: [0, 0, 1, 1] };
  return { duration: 0.32, ease: [0.4, 0, 0.2, 1] };
}

/** Selected category first. The same card objects stay in the list, so keys do not remount. */
export function orderedCategories(selectedProfile: string | null): SignupBusinessCard[] {
  const cards = [...SIGNUP_BUSINESS_CARDS];
  if (selectedProfile === null) return cards;
  const selected = cards.find((card) => card.profile === selectedProfile);
  if (!selected) return cards;
  return [selected, ...cards.filter((card) => card.profile !== selectedProfile)];
}

export function operatingModels(profile: string): readonly SignupSubType[] {
  return SIGNUP_BUSINESS_CARDS.find((card) => card.profile === profile)?.subTypes ?? [];
}

export function subTypeAfterCategoryChange(profile: string, current: string | null): string | null {
  if (current !== null && operatingModels(profile).some((model) => model.id === current)) return current;
  return null;
}

export function selectionReady(profile: string | null, subType: string | null): boolean {
  if (profile === null) return false;
  const models = operatingModels(profile);
  if (models.length === 0) return true;
  return models.some((model) => model.id === subType);
}

export function setupPreview(model: SignupSubType): { included: string[]; note: string } {
  const included = ["POS Register"];
  for (const id of CHIP_PRIORITY) {
    if (!model.modules.includes(id)) continue;
    included.push(CHIP_LABEL[id] ?? capabilitySpec(id).label);
    if (included.length === 5) break;
  }
  return { included, note: model.note ? `${model.note} ${PAID_NOTE}` : PAID_NOTE };
}
