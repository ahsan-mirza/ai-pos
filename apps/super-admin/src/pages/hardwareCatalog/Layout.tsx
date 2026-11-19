import { AxizTabs } from "@ai-pos/ui";
import { NavLink, Outlet, useLocation } from "react-router-dom";

const LINKS = [
  ["/hardware-catalog", "Overview"],
  ["/hardware-catalog/categories", "Categories"],
  ["/hardware-catalog/products", "Products"],
  ["/hardware-catalog/packages", "Packages"],
  ["/hardware-catalog/enquiries", "Enquiries"],
] as const;

export function HardwareCatalogLayout() {
  const { pathname } = useLocation();
  const active =
    [...LINKS].reverse().find(([to]) => pathname === to || pathname.startsWith(`${to}/`))?.[0] ?? "/hardware-catalog";
  return (
    <div>
      <AxizTabs
        ariaLabel="Hardware catalog"
        inset="page"
        className="mb-5 w-full"
        activeTab={active}
        tabs={LINKS.map(([to, label]) => ({ id: to, label }))}
        renderTab={({ tab, tabProps }) => <NavLink to={tab.id} {...tabProps} />}
      />
      <Outlet />
    </div>
  );
}
