import { Permission } from "@ai-pos/shared-types";
import { useMemo, useState } from "react";
import { PageFrame } from "../../components/shell/RegisterShell";
import type { CashierSession } from "../auth/session";
import { useCapabilities } from "../../lib/capabilities";
import type { WorkspaceAccess } from "./panels";
import { inventoryTabs } from "./tabs";
import {
  BatchesPanel,
  BrandsPanel,
  CategoriesPanel,
  CountsPanel,
  ExpiryPanel,
  LotsPanel,
  ModelsPanel,
  PriceChangesPanel,
  PriceListsPanel,
  PricingPanel,
  ProductsPanel,
  PurchaseOrdersPanel,
  RecipesPanel,
  ReplenishmentPanel,
  SerialsPanel,
  StockPanel,
  TransfersPanel,
  UnitsPanel,
} from "./panels";

export function InventoryPage({ session }: { session: CashierSession }) {
  const { profile, enabled } = useCapabilities();
  const permissions = session.user.permissions;
  const tabs = useMemo(() => inventoryTabs(profile, enabled, permissions), [profile, enabled, permissions]);
  const [tab, setTab] = useState(tabs[0]?.id ?? "");
  const current = tabs.some((item) => item.id === tab) ? tab : (tabs[0]?.id ?? "");
  const online = session.mode === "online";
  const allow = (permission: string) => permissions.includes(permission);
  const manage = allow(Permission.PortalInventoryManage);
  const pharmacyCatalogue = manage || allow(Permission.PharmacyCatalogue);
  const props = {
    online,
    storeId: session.user.store_id,
    manage,
    pharmacy: profile === "pharmacy",
    pharmacyCatalogue,
    canAdjust: allow(Permission.InventoryAdjustStock),
    canPrice: allow(Permission.PortalPricingManage),
    weighed: enabled.has("weighed_items"),
    serialized: enabled.has("serial_tracking"),
    fashion: profile === "retail_fashion",
    fnb: profile === "restaurant" || profile === "cafe" || profile === "quick_service",
    recipes: enabled.has("recipes"),
    profile,
  };

  return (
    <PageFrame
      title="Inventory & Stock"
      sync={
        online
          ? { tone: "live", label: "Live", title: "Inventory changes use the server ledger." }
          : { tone: "offline", label: "Offline", title: "Inventory changes stay closed until the connection returns." }
      }
      drawer={null}
    >
      <div className="flex min-h-full flex-col gap-4 p-4">
        {tabs.length === 0 ? (
          <p className="text-sm text-zinc-600 dark:text-zinc-300">This sign-in cannot open inventory management.</p>
        ) : (
          <>
            <div className="flex gap-2 overflow-x-auto" role="tablist" aria-label="Inventory sections">
              {tabs.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  role="tab"
                  aria-selected={item.id === current}
                  onClick={() => setTab(item.id)}
                  className={`h-12 shrink-0 rounded-xl px-4 text-sm font-semibold ${
                    item.id === current ? "bg-primary-500 text-white" : "bg-white text-zinc-700 ring-1 ring-zinc-200 dark:bg-zinc-900 dark:text-zinc-200 dark:ring-zinc-700"
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>
            {!online ? (
              <p className="rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-950">
                Showing this register only when a list was already loaded. Stock adjustments, receiving, counts, transfers and pharmacy lot actions need a live connection.
              </p>
            ) : null}
            <Panel id={current} access={props} />
          </>
        )}
      </div>
    </PageFrame>
  );
}

function Panel({ id, access }: { id: string; access: WorkspaceAccess }) {
  switch (id) {
    case "stock":
      return <StockPanel {...access} />;
    case "products":
      return <ProductsPanel {...access} />;
    case "categories":
      return <CategoriesPanel {...access} />;
    case "brands":
      return <BrandsPanel {...access} />;
    case "models":
      return <ModelsPanel {...access} />;
    case "units":
      return <UnitsPanel {...access} />;
    case "pricing":
      return <PricingPanel {...access} />;
    case "price-lists":
      return <PriceListsPanel {...access} />;
    case "price-changes":
      return <PriceChangesPanel {...access} />;
    case "batches":
    case "lots":
      return <BatchesPanel {...access} pharmacyLots={id === "lots"} />;
    case "expiry":
      return <ExpiryPanel {...access} />;
    case "recipes":
      return <RecipesPanel {...access} />;
    case "replenishment":
      return <ReplenishmentPanel {...access} />;
    case "counts":
      return <CountsPanel {...access} />;
    case "purchase-orders":
      return <PurchaseOrdersPanel {...access} />;
    case "transfers":
      return <TransfersPanel {...access} />;
    case "serials":
      return <SerialsPanel {...access} />;
    case "supplier-returns":
    case "recalls":
    case "quarantine":
    case "release":
      return <LotsPanel {...access} mode={id} />;
    default:
      return null;
  }
}
