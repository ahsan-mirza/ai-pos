import { AxizTabs } from "@ai-pos/ui";
import { NavLink, useLocation } from "react-router-dom";

const LINKS = [
  ["/catalogue", "Overview"],
  ["/packages", "Packages"],
  ["/billing", "Billing"],
  ["/hardware", "Hardware"],
  ["/addons", "Add-ons"],
  ["/modules", "Modules"],
  ["/business-types", "Business types"],
  ["/subscriptions", "Subscriptions"],
  ["/payments", "Payments"],
] as const;

export function cataloguePath(pathname: string): boolean {
  return LINKS.some(([to]) => pathname === to || pathname.startsWith(`${to}/`));
}

/** One row of the product catalogue. Existing routes stay in place. */
export function CatalogueNav() {
  const { pathname } = useLocation();
  const active = LINKS.find(([to]) => pathname === to || pathname.startsWith(`${to}/`))?.[0] ?? "";
  return (
    <AxizTabs
      ariaLabel="Product catalogue"
      inset="page"
      className="-mx-4 -mt-4 mb-5 md:-mx-6 md:-mt-5"
      activeTab={active}
      tabs={LINKS.map(([to, label]) => ({ id: to, label }))}
      renderTab={({ tab, tabProps }) => <NavLink to={tab.id} {...tabProps} />}
    />
  );
}
