import { Capability } from "@ai-pos/shared-types";

/** Module to open when a live capability is on. Order is the dashboard priority. */
const FOCUS: readonly { capability: Capability; moduleId: string }[] = [
  { capability: Capability.SerialTracking, moduleId: "serials" },
  { capability: Capability.Warranty, moduleId: "warranties" },
  { capability: Capability.Repairs, moduleId: "repairs" },
  { capability: Capability.TradeIn, moduleId: "trade-ins" },
  { capability: Capability.VariantsMatrix, moduleId: "size-curve" },
  { capability: Capability.WholesalePricing, moduleId: "pricing" },
  { capability: Capability.SalesOrders, moduleId: "sales-orders" },
  { capability: Capability.CustomerReorders, moduleId: "reorders" },
  { capability: Capability.B2bCredit, moduleId: "customers" },
  { capability: Capability.WeighedItems, moduleId: "products" },
  { capability: Capability.Fefo, moduleId: "expiring" },
  { capability: Capability.Tables, moduleId: "floor-plan" },
  { capability: Capability.Kds, moduleId: "kitchen" },
  { capability: Capability.MenuModifiers, moduleId: "modifiers" },
  { capability: Capability.MenuModifiers, moduleId: "meals" },
  { capability: Capability.DeliveryChannels, moduleId: "channels" },
];

const BASE = ["sales", "products", "customers", "stock"] as const;

/** Live capabilities choose the modules. An unknown profile adds nothing by itself. */
export function focusModuleIds(capabilities: readonly string[]): string[] {
  const enabled = new Set(capabilities);
  const ids: string[] = [];
  for (const row of FOCUS) {
    if (enabled.has(row.capability) && !ids.includes(row.moduleId)) ids.push(row.moduleId);
  }
  for (const id of BASE) {
    if (!ids.includes(id)) ids.push(id);
  }
  return ids;
}
