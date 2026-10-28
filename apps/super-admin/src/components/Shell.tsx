import { BrandLogo } from "@ai-pos/ui";
import {
  Building2,
  CreditCard,
  Layers,
  LayoutDashboard,
  Inbox,
  Store,
  LogOut,
  MonitorSmartphone,
  Package,
  PanelLeftClose,
  PanelLeftOpen,
  Puzzle,
  Receipt,
  Landmark,
  Settings,
  X,
  type LucideIcon,
} from "lucide-react";
import { Fragment, useCallback, useEffect, useRef, useState, type FocusEvent, type MouseEvent, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { CatalogueNav, cataloguePath } from "./CatalogueNav";
import { useSession } from "../lib/session";

const COLLAPSED_KEY = "qios.console.sidebar-collapsed";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
}

const groups: { label: string; items: NavItem[] }[] = [
  {
    label: "Stores",
    items: [
      { to: "/overview", label: "Overview", icon: LayoutDashboard },
      { to: "/tenants", label: "Tenants", icon: Building2 },
      { to: "/requests", label: "Change requests", icon: Inbox },
    ],
  },
  {
    label: "Catalogue",
    items: [
      { to: "/catalogue", label: "Catalogue", icon: Layers },
      { to: "/packages", label: "Packages", icon: Package },
      { to: "/billing", label: "Billing", icon: Receipt },
      { to: "/hardware", label: "Hardware", icon: MonitorSmartphone },
      { to: "/addons", label: "Add-ons", icon: Puzzle },
      { to: "/modules", label: "Modules", icon: Layers },
      { to: "/business-types", label: "Business types", icon: Store },
      { to: "/subscriptions", label: "Subscriptions", icon: CreditCard },
      { to: "/payments", label: "Payments", icon: Landmark },
    ],
  },
  {
    label: "Settings",
    items: [{ to: "/settings", label: "Settings", icon: Settings }],
  },
];

const settingsSections: Record<string, string> = {
  "/settings/whatsapp": "WhatsApp Sales Contact",
  "/settings/email": "Email",
  "/settings/users": "Users",
};

const iconButton =
  "relative flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-charcoal/60 outline-none transition-colors hover:bg-charcoal/[0.05] hover:text-charcoal focus-visible:ring-2 focus-visible:ring-accent/40";

function isTyping(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))
  );
}

function isActive(pathname: string, to: string): boolean {
  return pathname === to || pathname.startsWith(`${to}/`);
}

function crumbsFor(pathname: string): { label: string; to?: string }[] {
  const section = Object.entries(settingsSections).find(([path]) => isActive(pathname, path));
  if (section) {
    return [
      { label: "Console", to: "/tenants" },
      { label: "Settings", to: "/settings" },
      { label: section[1] },
    ];
  }
  const current = groups.flatMap((group) => group.items).find((item) => isActive(pathname, item.to));
  return [
    { label: "Console", to: "/tenants" },
    { label: current?.label ?? "Console" },
  ];
}

interface Tip {
  label: ReactNode;
  top: number;
}

type TipHandler = (tip: Tip | null) => void;

function tipEvents(collapsed: boolean, onTip: TipHandler | undefined, label: ReactNode) {
  if (!collapsed || !onTip) return {};
  const show = (event: MouseEvent<HTMLElement> | FocusEvent<HTMLElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    onTip({ label, top: rect.top + rect.height / 2 });
  };
  const hide = () => onTip(null);
  return { onMouseEnter: show, onMouseLeave: hide, onFocus: show, onBlur: hide };
}

function initialsOf(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

function SidebarBrand({ collapsed }: { collapsed: boolean }) {
  return (
    <Link
      to="/overview"
      aria-label="QIOS Console home"
      className={`flex h-16 shrink-0 items-center overflow-hidden border-b border-line outline-none focus-visible:bg-charcoal/[0.03] ${collapsed ? "justify-center px-2" : "px-[22px]"}`}
    >
      <BrandLogo variant={collapsed ? "mark" : "wordmark"} tone="light" alt="" className={collapsed ? "h-8 w-8" : "h-8 max-w-full"} />
    </Link>
  );
}

function SidebarNav({
  collapsed,
  onNavigate,
  onTip,
}: {
  collapsed: boolean;
  onNavigate?: () => void;
  onTip?: TipHandler;
}) {
  const { pathname } = useLocation();
  const showTip = (item: NavItem) => (event: MouseEvent<HTMLElement> | FocusEvent<HTMLElement>) => {
    if (!collapsed || !onTip) return;
    const rect = event.currentTarget.getBoundingClientRect();
    onTip({ label: item.label, top: rect.top + rect.height / 2 });
  };
  const hideTip = () => onTip?.(null);

  return (
    <nav aria-label="Primary" className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-3 py-4" onScroll={hideTip}>
      {groups.map((group, index) => (
        <div key={group.label} className={index ? "mt-5" : ""}>
          <div className="relative mb-1 h-6" aria-hidden={collapsed}>
            <span
              className={`absolute inset-0 flex items-center px-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-charcoal/40 transition-opacity duration-200 ${
                collapsed ? "opacity-0" : "opacity-100"
              }`}
            >
              {group.label}
            </span>
            <span
              className={`absolute inset-x-3 top-1/2 h-px bg-line transition-opacity duration-200 ${
                collapsed && index ? "opacity-100" : "opacity-0"
              }`}
            />
          </div>
          <ul className="space-y-0.5">
            {group.items.map((item) => {
              const active = isActive(pathname, item.to);
              return (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    onClick={onNavigate}
                    aria-current={active ? "page" : undefined}
                    aria-label={collapsed ? item.label : undefined}
                    onMouseEnter={showTip(item)}
                    onMouseLeave={hideTip}
                    onFocus={showTip(item)}
                    onBlur={hideTip}
                    className={`group relative flex h-10 items-center gap-3 overflow-hidden rounded-lg px-[18px] text-[13px] font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-accent/40 ${
                      active
                        ? "bg-accent/[0.08] text-accent"
                        : "text-charcoal/70 hover:bg-charcoal/[0.04] hover:text-charcoal"
                    }`}
                  >
                    {active ? (
                      <span aria-hidden="true" className="absolute inset-y-2 left-0 w-[3px] rounded-r-full bg-accent" />
                    ) : null}
                    <item.icon
                      aria-hidden="true"
                      size={18}
                      strokeWidth={active ? 2 : 1.75}
                      className={`shrink-0 ${active ? "" : "text-charcoal/50 group-hover:text-charcoal/80"}`}
                    />
                    <span
                      className={`whitespace-nowrap transition-opacity duration-200 ${
                        collapsed ? "pointer-events-none opacity-0" : "opacity-100"
                      } ${active ? "font-semibold" : ""}`}
                    >
                      {item.label}
                    </span>
                  </NavLink>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function SidebarProfile({ collapsed, onTip }: { collapsed: boolean; onTip?: TipHandler }) {
  const { operator, signOut } = useSession();
  if (operator === null) return null;
  const details = (
    <>
      <span className="block font-semibold">{operator.full_name}</span>
      <span className="block text-[11px] font-normal text-white/70">{operator.role}</span>
    </>
  );

  return (
    <div className="shrink-0 space-y-1 border-t border-line p-3">
      <div
        tabIndex={collapsed ? 0 : undefined}
        role={collapsed ? "img" : undefined}
        aria-label={collapsed ? `Signed in as ${operator.full_name}, ${operator.role}` : undefined}
        title={collapsed ? undefined : `${operator.full_name} · ${operator.role}`}
        {...tipEvents(collapsed, onTip, details)}
        className={`flex items-center gap-3 overflow-hidden rounded-xl px-2.5 py-2 outline-none transition-colors focus-visible:ring-2 focus-visible:ring-accent/40 ${
          collapsed ? "" : "bg-[#f8fafc] ring-1 ring-line"
        }`}
      >
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent/10 text-[11px] font-bold text-accent ring-1 ring-accent/20">
          {initialsOf(operator.full_name)}
        </span>
        <span className={`min-w-0 transition-opacity duration-200 ${collapsed ? "pointer-events-none opacity-0" : "opacity-100"}`}>
          <span className="block truncate text-[13px] font-semibold">{operator.full_name}</span>
          <span className="block truncate text-[11px] text-charcoal/50">{operator.role}</span>
        </span>
      </div>
      <button
        type="button"
        onClick={signOut}
        aria-label={collapsed ? "Sign out" : undefined}
        {...tipEvents(collapsed, onTip, "Sign out")}
        className="group flex h-10 w-full items-center gap-3 overflow-hidden rounded-lg px-[18px] text-[13px] font-medium text-charcoal/70 outline-none transition-colors hover:bg-charcoal/[0.04] hover:text-charcoal focus-visible:ring-2 focus-visible:ring-accent/40"
      >
        <LogOut size={18} strokeWidth={1.75} aria-hidden="true" className="shrink-0 text-charcoal/50 group-hover:text-charcoal/80" />
        <span className={`whitespace-nowrap transition-opacity duration-200 ${collapsed ? "opacity-0" : "opacity-100"}`}>
          Sign out
        </span>
      </button>
    </div>
  );
}

function Sidebar({
  collapsed,
  mobileOpen,
  onCloseMobile,
}: {
  collapsed: boolean;
  mobileOpen: boolean;
  onCloseMobile: () => void;
}) {
  const [tip, setTip] = useState<Tip | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!collapsed) setTip(null);
  }, [collapsed]);

  useEffect(() => {
    if (!mobileOpen) return;
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCloseMobile();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mobileOpen, onCloseMobile]);

  return (
    <>
      <aside
        className={`relative z-20 hidden shrink-0 flex-col border-r border-line bg-white transition-[width] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] motion-reduce:transition-none lg:flex ${
          collapsed ? "w-20" : "w-64"
        }`}
      >
        <SidebarBrand collapsed={collapsed} />
        <SidebarNav collapsed={collapsed} onTip={setTip} />
        <SidebarProfile collapsed={collapsed} onTip={setTip} />
      </aside>

      {tip ? (
        <div
          role="tooltip"
          style={{ top: tip.top }}
          className="sidebar-tip pointer-events-none fixed left-[88px] z-50 -translate-y-1/2 whitespace-nowrap rounded-md bg-charcoal px-2.5 py-1.5 text-xs font-medium text-white shadow-lg"
        >
          <span aria-hidden="true" className="absolute -left-1 top-1/2 h-2 w-2 -translate-y-1/2 rotate-45 bg-charcoal" />
          {tip.label}
        </div>
      ) : null}

      {mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <div className="drawer-backdrop absolute inset-0 bg-charcoal/40 backdrop-blur-[2px]" onClick={onCloseMobile} />
          <div className="sidebar-sheet absolute inset-y-0 left-0 flex w-[min(288px,86vw)] flex-col border-r border-line bg-white shadow-2xl">
            <div className="relative">
              <SidebarBrand collapsed={false} />
              <button
                ref={closeRef}
                type="button"
                onClick={onCloseMobile}
                aria-label="Close navigation"
                className="absolute right-3 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-lg text-charcoal/60 hover:bg-charcoal/[0.05] hover:text-charcoal"
              >
                <X size={18} aria-hidden="true" />
              </button>
            </div>
            <SidebarNav collapsed={false} onNavigate={onCloseMobile} />
            <SidebarProfile collapsed={false} />
          </div>
        </div>
      ) : null}
    </>
  );
}

function Header({
  collapsed,
  onToggleCollapsed,
  onOpenMobile,
}: {
  collapsed: boolean;
  onToggleCollapsed: () => void;
  onOpenMobile: () => void;
}) {
  const { pathname } = useLocation();
  const crumbs = crumbsFor(pathname);

  return (
    <header className="relative z-30 flex h-16 shrink-0 items-center gap-2 border-b border-line bg-white/90 px-3 backdrop-blur supports-[backdrop-filter]:bg-white/75 md:px-4 lg:px-6">
      <button
        type="button"
        onClick={onToggleCollapsed}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        aria-keyshortcuts="["
        title={collapsed ? "Expand sidebar  [" : "Collapse sidebar  ["}
        className={`${iconButton} -ml-1.5 hidden lg:flex`}
      >
        {collapsed ? <PanelLeftOpen size={18} strokeWidth={1.75} /> : <PanelLeftClose size={18} strokeWidth={1.75} />}
      </button>
      <button type="button" onClick={onOpenMobile} aria-label="Open navigation" className={`${iconButton} -ml-1 lg:hidden`}>
        <PanelLeftOpen size={18} strokeWidth={1.75} />
      </button>

      <span aria-hidden="true" className="mx-1 hidden h-5 w-px bg-line lg:block" />

      <nav aria-label="Breadcrumb" className="min-w-0 flex-1">
        <ol className="flex min-w-0 items-center gap-1.5 text-[13px]">
          {crumbs.map((crumb, index) => {
            const last = index === crumbs.length - 1;
            return (
              <Fragment key={`${crumb.label}-${index}`}>
                {index ? (
                  <li aria-hidden="true" className="hidden text-charcoal/25 sm:block">
                    /
                  </li>
                ) : null}
                <li className={`min-w-0 ${last ? "" : "hidden sm:block"}`}>
                  {last ? (
                    <span aria-current="page" className="block truncate font-semibold text-charcoal">
                      {crumb.label}
                    </span>
                  ) : crumb.to ? (
                    <Link to={crumb.to} className="block truncate text-charcoal/50 transition-colors hover:text-charcoal">
                      {crumb.label}
                    </Link>
                  ) : (
                    <span className="block truncate text-charcoal/50">{crumb.label}</span>
                  )}
                </li>
              </Fragment>
            );
          })}
        </ol>
      </nav>
    </header>
  );
}

export function Shell() {
  const { pathname } = useLocation();
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(COLLAPSED_KEY) === "1");
  const [mobileOpen, setMobileOpen] = useState(false);

  const toggleCollapsed = useCallback(() => {
    setCollapsed((value) => {
      localStorage.setItem(COLLAPSED_KEY, value ? "0" : "1");
      return !value;
    });
  }, []);
  const closeMobile = useCallback(() => setMobileOpen(false), []);

  useEffect(() => setMobileOpen(false), [pathname]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "[" || event.metaKey || event.ctrlKey || event.altKey || isTyping(event.target)) return;
      if (document.querySelector(".modal-backdrop")) return;
      event.preventDefault();
      toggleCollapsed();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggleCollapsed]);

  return (
    <div className="flex h-dvh w-screen overflow-hidden bg-[#f8fafc] font-sans text-charcoal">
      <Sidebar collapsed={collapsed} mobileOpen={mobileOpen} onCloseMobile={closeMobile} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header collapsed={collapsed} onToggleCollapsed={toggleCollapsed} onOpenMobile={() => setMobileOpen(true)} />
        <main className="relative min-h-0 flex-1 overflow-y-auto overflow-x-hidden">
          <div className="p-4 md:p-6 lg:p-8">
            {cataloguePath(pathname) ? <CatalogueNav /> : null}
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
