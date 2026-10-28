import { Capability, type BusinessProfile } from "@ai-pos/shared-types";
import type { CSSProperties } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { AiMark } from "../../components/ui/AiMark";
import { useTenant } from "../../context/TenantContext";
import { useCapabilities } from "../../lib/capabilities";
import { MODEL_PROFILES, RETAIL_PROFILES } from "../../lib/industry";

const tabs: { to: string; label: string; capability?: Capability; profiles?: readonly BusinessProfile[]; ai?: boolean }[] = [
  { to: "/inventory/stock", label: "Stock" },
  { to: "/inventory/products", label: "Products" },
  { to: "/inventory/pricing", label: "Pricing", capability: Capability.WholesalePricing },
  { to: "/inventory/price-lists", label: "Price lists" },
  { to: "/inventory/price-changes", label: "Price changes" },
  { to: "/inventory/categories", label: "Categories" },
  { to: "/inventory/brands", label: "Brands" },
  { to: "/inventory/models", label: "Models", profiles: MODEL_PROFILES },
  { to: "/inventory/units", label: "Units" },
  { to: "/inventory/batches", label: "Batches", profiles: RETAIL_PROFILES },
  { to: "/inventory/expiring", label: "Expiring", capability: Capability.Fefo },
  { to: "/inventory/waste", label: "Waste", capability: Capability.Fefo },
  { to: "/inventory/modifiers", label: "Modifiers", capability: Capability.MenuModifiers },
  { to: "/inventory/meals", label: "Meals", capability: Capability.MenuModifiers },
  { to: "/inventory/floor-plan", label: "Floor plan", capability: Capability.Tables },
  { to: "/inventory/kitchen", label: "Kitchen stations", capability: Capability.Kds },
  { to: "/inventory/kitchen-agent", label: "Kitchen agent", capability: Capability.Recipes, ai: true },
  { to: "/inventory/recipes", label: "Recipes", capability: Capability.Recipes },
  { to: "/inventory/recipe-usage", label: "Ingredient usage", capability: Capability.Recipes },
  { to: "/inventory/replenishment", label: "Replenishment" },
  { to: "/inventory/counts", label: "Stock Counts" },
  { to: "/inventory/purchase-orders", label: "Purchase Orders" },
  { to: "/inventory/transfers", label: "Transfers" },
  { to: "/inventory/serials", label: "IMEI Tracker", capability: Capability.SerialTracking },
];

/** Header (4rem) plus this tab strip (3rem); split-view drawers subtract it from the viewport height. */
const chrome = { "--chrome": "7rem" } as CSSProperties;

export function InventoryLayout() {
  const { has } = useCapabilities();
  const { allows } = useTenant();
  return (
    <div className="flex min-h-full flex-col lg:h-full" style={chrome}>
      <nav
        aria-label="Inventory sections"
        className="no-scrollbar sticky top-0 z-20 flex h-12 shrink-0 gap-1 overflow-x-auto border-b border-line bg-white px-2 md:px-3 lg:static lg:px-4"
      >
        {tabs.filter((tab) => allows(tab.profiles) && (tab.capability === undefined || has(tab.capability))).map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            className={({ isActive }) =>
              `relative flex shrink-0 items-center whitespace-nowrap px-3 text-[13px] outline-none transition-colors after:absolute after:inset-x-2 after:bottom-0 after:h-0.5 after:rounded-full after:transition-colors focus-visible:bg-charcoal/[0.04] ${
                isActive
                  ? "font-semibold text-charcoal after:bg-accent"
                  : "font-medium text-charcoal/55 after:bg-transparent hover:text-charcoal hover:after:bg-line"
              }`
            }
          >
            {tab.ai ? <AiMark size={13} className="mr-1.5 text-accent" /> : null}
            {tab.label}
          </NavLink>
        ))}
      </nav>
      <div className="flex-1 lg:min-h-0 lg:overflow-y-auto">
        <Outlet />
      </div>
    </div>
  );
}
