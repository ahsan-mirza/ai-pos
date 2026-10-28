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
  return (
    <nav aria-label="Product catalogue" className="-mx-1 mb-5 flex gap-2 overflow-x-auto px-1 pb-1">
      {LINKS.map(([to, label]) => {
        const active = pathname === to || pathname.startsWith(`${to}/`);
        return (
          <NavLink
            key={to}
            to={to}
            aria-current={active ? "page" : undefined}
            className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold ${
              active ? "bg-accent text-white" : "bg-white text-charcoal/70 ring-1 ring-line hover:text-charcoal"
            }`}
          >
            {label}
          </NavLink>
        );
      })}
    </nav>
  );
}
