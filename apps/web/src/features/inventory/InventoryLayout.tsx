import { AxizTabs } from "@ai-pos/ui";
import { Capability, type BusinessProfile } from "@ai-pos/shared-types";
import { type CSSProperties } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { AiMark } from "../../components/ui/AiMark";
import { useTenant } from "../../context/TenantContext";
import { useCapabilities } from "../../lib/capabilities";
import { FASHION_PROFILES, MODEL_PROFILES, RETAIL_PROFILES } from "../../lib/industry";

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
  { to: "/inventory/meals", label: "Meals", capability: Capability.MenuModifiers },
  { to: "/inventory/replenishment", label: "Replenishment" },
  { to: "/inventory/counts", label: "Stock Counts" },
  { to: "/inventory/purchase-orders", label: "Purchase Orders" },
  { to: "/inventory/transfers", label: "Transfers" },
  { to: "/inventory/serials", label: "IMEI Tracker", capability: Capability.SerialTracking },
  { to: "/inventory/markdowns", label: "Markdowns", capability: Capability.VariantsMatrix, profiles: FASHION_PROFILES },
  { to: "/inventory/size-curve", label: "Size & color matrix", capability: Capability.VariantsMatrix, profiles: FASHION_PROFILES },
];

/** Header (4rem) plus this tab strip (3rem); split-view drawers subtract it from the viewport height. */
const chrome = { "--chrome": "7rem" } as CSSProperties;

export function InventoryLayout() {
  const { has } = useCapabilities();
  const { allows } = useTenant();
  const { pathname } = useLocation();
  const visible = tabs.filter((tab) => allows(tab.profiles) && (tab.capability === undefined || has(tab.capability)));
  const active = visible.find((tab) => pathname === tab.to || pathname.startsWith(`${tab.to}/`))?.to ?? "";

  return (
    <div className="flex min-h-full min-w-0 flex-col lg:h-full" style={chrome}>
      <div className="sticky top-0 z-20 min-w-0 bg-white lg:static">
        <AxizTabs
          ariaLabel="Inventory sections"
          inset="page"
          activeTab={active}
          tabs={visible.map((tab) => ({
            id: tab.to,
            label: tab.label,
            icon: tab.ai ? <AiMark size={13} className="text-accent" /> : undefined,
          }))}
          renderTab={({ tab, tabProps }) => <NavLink to={tab.id} {...tabProps} />}
        />
      </div>
      <div className="min-w-0 flex-1 lg:min-h-0 lg:overflow-y-auto">
        <Outlet />
      </div>
    </div>
  );
}
