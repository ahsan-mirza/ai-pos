import { profileSpec } from "@ai-pos/shared-types";
import { useCallback, useEffect, useState } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { useTenant } from "../../context/TenantContext";
import { FirstWinChecklist } from "../../features/onboarding/FirstWinChecklist";
import { PracticeBanner, PracticeProvider, TaxPortalBanner } from "../../features/onboarding/practice";
import { industryAllows } from "../../lib/industry";
import { StoreScopeProvider } from "../../lib/storeScope";
import { Header } from "./Header";
import { Sidebar } from "./Sidebar";

const COLLAPSED_KEY = "ai-pos.sidebar-collapsed";

function isTyping(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))
  );
}

export function AppShell() {
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
    <StoreScopeProvider>
      <PracticeProvider>
        <div className="flex h-dvh w-screen overflow-hidden bg-[#f8fafc] font-sans text-charcoal">
          <Sidebar collapsed={collapsed} mobileOpen={mobileOpen} onCloseMobile={closeMobile} />
          <div className="flex min-w-0 flex-1 flex-col">
            <PracticeBanner />
            <TaxPortalBanner />
            <Header collapsed={collapsed} onToggleCollapsed={toggleCollapsed} onOpenMobile={() => setMobileOpen(true)} />
            <main className="relative min-h-0 flex-1 overflow-y-auto overflow-x-hidden">
              <IndustryGate />
            </main>
          </div>
        </div>
        <FirstWinChecklist />
      </PracticeProvider>
    </StoreScopeProvider>
  );
}

/** Blocks a deep link when this business type does not use the page. */
function IndustryGate() {
  const { pathname } = useLocation();
  const { businessType, ready } = useTenant();
  if (ready && !industryAllows(pathname, businessType)) {
    const name = profileSpec(businessType).label;
    return (
      <section className="m-6 max-w-lg rounded-card border border-line bg-white p-8">
        <h1 className="text-xl font-semibold">Not part of this portal</h1>
        <p className="mt-2 text-sm text-charcoal/70">{name} does not use this page.</p>
        <Link to="/" className="mt-4 inline-block text-sm font-semibold text-accent">
          Back to the dashboard
        </Link>
      </section>
    );
  }
  return <Outlet />;
}

/** Padding for card-based pages; full-bleed workspaces such as Purchase Batches render outside it. */
export function PageFrame() {
  return (
    <div className="p-4 md:p-6 lg:p-8">
      <Outlet />
    </div>
  );
}
