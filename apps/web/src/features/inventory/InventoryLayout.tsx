import { Capability, type BusinessProfile } from "@ai-pos/shared-types";
import { type CSSProperties, useEffect, useRef, useState } from "react";
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
  { to: "/inventory/modifiers", label: "Modifiers", capability: Capability.MenuModifiers },
  { to: "/inventory/meals", label: "Meals", capability: Capability.MenuModifiers },
  { to: "/inventory/floor-plan", label: "Floor plan", capability: Capability.Tables },
  { to: "/inventory/reservations", label: "Table reservations", capability: Capability.Tables, profiles: ["restaurant", "cafe"] },
  { to: "/inventory/kitchen", label: "Kitchen stations", capability: Capability.Kds },
  { to: "/inventory/kitchen-agent", label: "Kitchen agent", capability: Capability.Recipes, ai: true },
  { to: "/inventory/recipes", label: "Recipes", capability: Capability.Recipes },
  { to: "/inventory/recipe-usage", label: "Ingredient usage", capability: Capability.Recipes },
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
  const navRef = useRef<HTMLElement>(null);
  const [edges, setEdges] = useState({ left: false, right: false });
  const visible = tabs.filter((tab) => allows(tab.profiles) && (tab.capability === undefined || has(tab.capability)));

  useEffect(() => {
    const el = navRef.current;
    if (!el) return;
    const update = () => {
      setEdges({
        left: el.scrollLeft > 4,
        right: el.scrollLeft + el.clientWidth < el.scrollWidth - 4,
      });
    };
    el.querySelector<HTMLElement>('[aria-current="page"]')?.scrollIntoView({ inline: "nearest", block: "nearest" });
    update();
    el.addEventListener("scroll", update, { passive: true });
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => {
      el.removeEventListener("scroll", update);
      observer.disconnect();
    };
  }, [pathname, visible.length]);

  return (
    <div className="flex min-h-full flex-col lg:h-full" style={chrome}>
      <div className="sticky top-0 z-20 border-b border-line bg-white lg:static relative">
        <nav
          ref={navRef}
          aria-label="Inventory sections"
          className="no-scrollbar flex h-12 shrink-0 gap-1 overflow-x-auto px-4 md:px-6"
        >
          {visible.map((tab) => (
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
        {edges.left ? (
          <span aria-hidden="true" className="pointer-events-none absolute inset-y-0 left-0 w-8 bg-gradient-to-r from-white to-transparent" />
        ) : null}
        {edges.right ? (
          <span aria-hidden="true" className="pointer-events-none absolute inset-y-0 right-0 w-8 bg-gradient-to-l from-white to-transparent" />
        ) : null}
      </div>
      <div className="flex-1 lg:min-h-0 lg:overflow-y-auto">
        <Outlet />
      </div>
    </div>
  );
}
